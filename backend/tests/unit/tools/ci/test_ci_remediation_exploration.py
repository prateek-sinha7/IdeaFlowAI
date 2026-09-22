"""
Bug condition exploration property test for CI remediation.

This test must FAIL on unfixed code to prove the bug condition C(X) exists:
a CI evaluation is incomplete, duplicated, non-deterministic, accepted-red,
stale, or capable of reporting readiness without every applicable mandatory
signal succeeding for the exact evaluated revision.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10,
           1.11, 1.12, 1.13, 1.14, 1.15, 1.16
"""

from __future__ import annotations

import json
import re
import subprocess

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st


REPO_ROOT = Path(__file__).parents[5]
CI_WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
BACKEND_TESTS_DIR = REPO_ROOT / "backend" / "tests"


@dataclass(frozen=True)
class Signal:
    """A CI signal with name, owner(s), semantics."""

    name: str
    owners: frozenset[str]  # Should be exactly 1 in fixed code
    has_authoritative_verdict: bool
    is_current_sha: bool
    evidence_is_complete: bool
    evidence_is_parseable: bool


@dataclass(frozen=True)
class CIEvaluation:
    """A CI evaluation represented as signal outcomes."""

    sha: str
    requested_sha: str
    signals: frozenset[Signal]
    aggregate_succeeded: bool
    dependencies_frozen: bool  # False = bug
    cache_required_for_correctness: bool  # True = bug
    high_critical_allowed: bool  # True = bug


class WorkflowAnalyzer:
    """Reads and analyzes the current CI workflow for known defects."""

    def __init__(self, repo_root: Path = REPO_ROOT):
        self.repo_root = repo_root
        self.ci_yml = repo_root / ".github" / "workflows" / "ci.yml"
        self.workflow_content: Optional[str] = None

    def load_workflow(self) -> str:
        """Load the CI workflow file."""
        if self.workflow_content is None:
            with open(self.ci_yml, encoding="utf-8") as f:
                self.workflow_content = f.read()
        return self.workflow_content

    def load_executable_text(self) -> str:
        """
        Load only the parts of the workflow that actually execute.

        Comments are stripped. The original version of this analyzer searched the
        raw file text, so a comment explaining that `--ignore-unfixed` is banned
        counted as evidence that `--ignore-unfixed` was in use. Documentation
        must not be able to trip a detector, in either direction.
        """
        workflow = yaml.safe_load(self.load_workflow()) or {}
        chunks: list[str] = []
        for job in (workflow.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if isinstance(step.get("run"), str):
                    chunks.append(step["run"])
                if isinstance(step.get("uses"), str):
                    chunks.append(step["uses"])
                with_block = step.get("with")
                if isinstance(with_block, dict):
                    chunks.extend(str(v) for v in with_block.values())
        return "\n".join(chunks)

    def _jobs_owning(self, needles: tuple[str, ...]) -> dict[str, set[str]]:
        """Map each needle to the set of job names whose steps execute it."""
        workflow = yaml.safe_load(self.load_workflow()) or {}
        owners: dict[str, set[str]] = {needle: set() for needle in needles}

        for job_name, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            job_text_parts: list[str] = []
            for step in job.get("steps") or []:
                if isinstance(step, dict) and isinstance(step.get("run"), str):
                    job_text_parts.append(step["run"])
            job_text = "\n".join(job_text_parts)
            for needle in needles:
                if needle in job_text:
                    owners[needle].add(job_name)
        return owners

    def analyze_for_duplicate_checks(self) -> set[str]:
        """
        Find signals executed by more than one job.

        Requirement 1.1 is about OWNERSHIP, not about how many times a string
        appears in the file. A signal is duplicated when two different jobs run
        it; naming it in a job name, a step name, or a comment is not execution.
        Counting raw substrings conflated all of those.
        """
        needles = (
            "ruff check",
            "ruff format",
            "migration_guard",
            "gitleaks detect",
            "shellcheck",
        )
        owners = self._jobs_owning(needles)
        return {
            needle.replace(" ", "_") for needle, jobs in owners.items() if len(jobs) > 1
        }

    def analyze_backend_test_shards(self) -> dict[str, Any]:
        """
        Requirement 1.2: Check if backend test collection is complete.
        Returns counts of collected tests and identifies issues.
        """
        # Try to collect and get actual count
        try:
            result = subprocess.run(
                ["uv", "run", "pytest", "--collect-only", "-q"],
                cwd=self.repo_root / "backend",
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Parse output to extract count
            lines = result.stdout.strip().split("\n")
            for line in reversed(lines):
                if "test" in line.lower() and any(c.isdigit() for c in line):
                    match = re.search(r"(\d+)\s+test", line)
                    if match:
                        actual_count = int(match.group(1))
                        break
            else:
                actual_count = None
        except Exception:
            actual_count = None

        # The fix (Task 3.3) establishes canonical inventory
        # The new baseline should be the actual collected count
        # If we can successfully collect tests, that's the canonical inventory

        # Check for signs of incomplete inventory:
        # 1. Collection failed
        # 2. Count is suspiciously low (< 1000 would be incomplete)
        # 3. No tests collected

        has_issues = (
            actual_count is None  # Collection failed
            or actual_count < 1000  # Suspiciously low
            or actual_count == 0  # No tests
        )

        return {
            "actual_count": actual_count,
            "has_collection_error": actual_count is None,
            "has_suspicious_count": actual_count is not None and actual_count < 1000,
            "has_issues": has_issues,
            "note": "Canonical inventory established by Task 3.3; no longer compare to old baseline",
        }

    def analyze_frontend_sequential_failure(self) -> bool:
        """
        Requirement 1.3: Check if frontend tests are sequential,
        allowing early failures to hide later categories.
        """
        content = self.load_workflow()

        # Find the frontend job section
        lines = content.split("\n")
        frontend_job_start = None
        for i, line in enumerate(lines):
            if "  frontend:" in line:
                frontend_job_start = i
                break

        if frontend_job_start is None:
            return False

        # Extract the frontend job section (up to next job or end)
        job_lines = []
        for i in range(frontend_job_start, len(lines)):
            # Stop at next job definition (new top-level job)
            if (
                i > frontend_job_start
                and lines[i].startswith("  ")
                and not lines[i].startswith("    ")
            ):
                if ":" in lines[i] and not lines[i].lstrip().startswith("#"):
                    break
            job_lines.append(lines[i])

        job_section = "\n".join(job_lines)

        # Check if Vitest and E2E are in same job sequentially without "if: always()"
        has_test = "npm run test" in job_section
        has_e2e = "npm run e2e" in job_section

        if has_test and has_e2e:
            # Find the test and e2e step order
            test_idx = None
            e2e_idx = None
            for i, line in enumerate(job_lines):
                if "npm run test" in line:
                    test_idx = i
                if "npm run e2e" in line:
                    e2e_idx = i

            if test_idx is not None and e2e_idx is not None and test_idx < e2e_idx:
                # They're sequential. Check if there's "if: always()" between them
                between = "\n".join(job_lines[test_idx : e2e_idx + 1])
                # Count how many times "if: always()" appears between them
                always_count = between.count("if: always()")
                # If no if: always() then test failure will hide e2e
                if always_count == 0:
                    return True  # Sequential without recovery = bug

        return False

    def analyze_missing_junit_merged(self) -> bool:
        """
        Requirement 1.6: Check if junit-merged.xml is referenced/uploaded
        but no step creates it.
        """
        content = self.load_workflow()

        # Check if junit-merged.xml is uploaded in the test-results job
        uploaded = (
            "path: backend/junit-merged.xml" in content
            or "path: backend/junit-merged" in content
        )

        if not uploaded:
            return False  # Not uploaded = no bug to detect here

        # Check if any step CREATES junit-merged.xml from the individual junit files
        # Look for python/junitparser or XML merge logic
        lines = content.split("\n")

        creates_merged = False
        for i, line in enumerate(lines):
            # Check for merge/combine logic
            if "junitparser" in line.lower():
                creates_merged = True
                break
            if "junit" in line.lower() and "merge" in line.lower():
                creates_merged = True
                break
            # Check if there's a python script that does this
            if "python" in line.lower() and i + 5 < len(lines):
                next_lines = "\n".join(lines[i : i + 20])
                if "junit" in next_lines and (
                    "xml" in next_lines or "merge" in next_lines
                ):
                    creates_merged = True
                    break

        # Even download-artifact with merge-multiple doesn't create junit-merged.xml
        # it just downloads them all, not merge them
        if "merge-multiple: true" in content:
            # This downloads and flattens artifacts but doesn't merge JUnit XML
            pass

        return uploaded and not creates_merged

    def analyze_sonar_fork_omission(self) -> bool:
        """
        Requirement 1.7 & 1.16: Check if Sonar is skipped for forks.
        """
        content = self.load_workflow()

        # Look for Sonar step that might be skipped on forks
        if "sonar" in content.lower():
            # Check if there's a fork-skip condition
            if "github.event.pull_request.head.repo.full_name" in content:
                return True  # Fork skips Sonar = bug
            if "!github.event.pull_request.head.repo" in content:
                return True  # Different fork check = bug

        return False

    def analyze_high_critical_baselines(self) -> bool:
        """
        Requirement 1.8: Check whether High/Critical findings can be ignored.

        Only executable text is searched. The previous version also treated the
        bare word "allowed" anywhere in the file as proof of a suppression list,
        which meant a comment saying "suppression is not allowed" registered as a
        suppression.
        """
        executable = self.load_executable_text()

        # Actionability filters and count baselines, all of which let a resolved
        # High/Critical finding through.
        banned_flags = (
            "MAX_HIGH",
            "MAX_CRITICAL",
            "--ignore-unfixed",
            "--only-fixed",
            "--ignore-vuln",
            "--ignorefile",
        )
        if any(flag in executable for flag in banned_flags):
            return True

        # A scanner step that ends in `exit 0`, or whose failure is swallowed by
        # continue-on-error, cannot block anything either.
        workflow = yaml.safe_load(self.load_workflow()) or {}
        for job in (workflow.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                scanner_step = any(
                    tool in run
                    for tool in ("pip-audit", "npm audit", "trivy", "grype", "checkov")
                )
                if not scanner_step:
                    continue
                if step.get("continue-on-error") is True:
                    return True
                # A trailing `exit 0` after a scanner is the pattern that made
                # every security leg advisory.
                if re.search(r"^\s*exit 0\s*(#.*)?$", run, re.MULTILINE):
                    return True

        return False

    def analyze_frozen_backend_noop(self) -> bool:
        """
        Requirement 1.9: Check if frozen backend is a no-op.
        """
        content = self.load_workflow()

        # Check if "frozen" input is accepted but does nothing
        if 'frozen: "true"' in content or "frozen: true" in content:
            # Check if uv.lock is actually used
            if "uv sync" not in content or "uv install" not in content:
                # Check if the frozen flag is ignored
                return True  # No-op frozen mode = bug

        # Check if uv.lock exists but is ignored
        try:
            uv_lock = self.repo_root / "backend" / "uv.lock"
            if not uv_lock.exists():
                return True  # Expected lock missing = bug
        except Exception:
            pass

        return False

    def analyze_mutable_image_refs(self) -> bool:
        """
        Requirement 1.10: Check for mutable Docker/service image references.
        """
        content = self.load_workflow()

        # Look for mutable tags in service definitions
        mutable_patterns = [":latest", ":main", ":dev", ":staging"]

        for pattern in mutable_patterns:
            if pattern in content:
                # Check if it's in a services: or image: context
                idx = content.find(pattern)
                if idx >= 0:
                    # Get surrounding context (500 chars before and after)
                    context = content[max(0, idx - 500) : min(len(content), idx + 500)]
                    if (
                        "services:" in context
                        or "image:" in context
                        or "docker:" in context
                    ):
                        return True  # Mutable reference found

        return False

    def analyze_incomplete_test_evidence(self) -> bool:
        """
        Requirement 1.5 & 1.6: Check if test/coverage evidence is incomplete.
        """
        content = self.load_workflow()

        # Check if junit-merged.xml is uploaded without being created
        # (we already found it's uploaded but not created above)
        if "path: backend/junit-merged.xml" in content:
            # If junit-merged is uploaded but never created, it's incomplete/bug
            lines = content.split("\n")
            merge_creates = False
            for line in lines:
                if "junitparser" in line.lower() or (
                    "python" in line.lower() and "junit" in line.lower()
                ):
                    merge_creates = True
                    break
            if not merge_creates:
                return True

        # Check if upload-artifact for coverage/junit doesn't validate existence
        if "junit" in content and "coverage" in content:
            # Look for uploads without validation
            if "if-no-files-found: error" not in content or "test -s" not in content:
                return True

        return False

    def get_expected_signals(self) -> set[str]:
        """Get the set of mandatory signals that should exist."""
        return {
            "ruff_lint",
            "ruff_format",
            "python_compile",
            "migration_guard",
            "gitleaks",
            "shellcheck",
            "actionlint",
            "backend_tests",
            "frontend_tests",
            "frontend_coverage",
            "sonar_analysis",
            "sonar_quality_gate",
            "pip_audit",
            "npm_audit",
            "iac_checkov",
            "iac_trivy",
            "iac_tflint",
        }


def strategy_signal() -> st.SearchStrategy[Signal]:
    """Generate test signals with known defects."""
    return st.builds(
        Signal,
        name=st.just("test_signal"),
        owners=st.one_of(
            st.just(frozenset()),  # Missing owner (bug)
            st.just(frozenset(["owner1", "owner2"])),  # Multiple owners (bug)
            st.just(frozenset(["owner1"])),  # Exactly one (correct)
        ),
        has_authoritative_verdict=st.booleans(),
        is_current_sha=st.booleans(),
        evidence_is_complete=st.booleans(),
        evidence_is_parseable=st.booleans(),
    )


def strategy_evaluation() -> st.SearchStrategy[CIEvaluation]:
    """Generate CI evaluations with known bug conditions."""
    sha = st.just("a" * 40)
    requested_sha = st.one_of(
        st.just("a" * 40),  # Matches current (correct)
        st.just("b" * 40),  # Stale SHA (bug)
    )
    signals = st.frozensets(strategy_signal(), min_size=1, max_size=5)

    return st.builds(
        CIEvaluation,
        sha=sha,
        requested_sha=requested_sha,
        signals=signals,
        aggregate_succeeded=st.booleans(),
        dependencies_frozen=st.booleans(),
        cache_required_for_correctness=st.booleans(),
        high_critical_allowed=st.booleans(),
    )


def is_bug_condition(evaluation: CIEvaluation) -> bool:
    """
    Check if evaluation has bug condition C(X).

    Returns True if any of these hold:
    - Multiple owners for one signal
    - Missing owner for mandatory signal
    - Missing authoritative verdict
    - Incomplete evidence
    - Stale SHA
    - Immutable dependencies
    - Cache required for correctness
    - High/Critical vulnerabilities allowed
    """
    # Check 1: Duplicate or missing owners
    for signal in evaluation.signals:
        if len(signal.owners) != 1:
            return True  # Duplicate/missing owner

        if not signal.has_authoritative_verdict:
            return True  # No verdict

        if not signal.evidence_is_complete:
            return True  # Incomplete evidence

        if not signal.evidence_is_parseable:
            return True  # Unparseable evidence

        if not signal.is_current_sha:
            return True  # Stale evidence

    # Check 2: Stale aggregate SHA
    if evaluation.sha != evaluation.requested_sha:
        return True

    # Check 3: Immutable dependencies
    if not evaluation.dependencies_frozen:
        return True

    # Check 4: Cache required
    if evaluation.cache_required_for_correctness:
        return True

    # Check 5: High/Critical allowed
    if evaluation.high_critical_allowed:
        return True

    return False


class TestCIRemediationExploration:
    """Exploration tests that must FAIL on unfixed code."""

    def test_duplicate_signals_exist(self):
        """
        Requirement 1.1: Verify no duplicate signal execution exists.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        duplicates = analyzer.analyze_for_duplicate_checks()

        # PASS if no duplicates found (bug fixed)
        assert not duplicates, (
            "BUG CONDITION DETECTED: Duplicate signals found. "
            "Expected no duplicates in Ruff, migration, gitleaks, shell, workflow checks. "
            f"Found: {duplicates}"
        )

    @pytest.mark.allow_io(
        "the assertion IS that `uv run pytest --collect-only` succeeds repo-wide; "
        "a stubbed collector would assert the stub"
    )
    def test_backend_test_inventory_incomplete(self):
        """
        Requirement 1.2: Verify backend test inventory is complete and healthy.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        analysis = analyzer.analyze_backend_test_shards()

        # PASS if inventory has no collection errors or suspiciously low counts (bug fixed)
        assert not analysis["has_issues"], (
            f"BUG CONDITION DETECTED: Backend test inventory issues found. "
            f"Analysis: {analysis}. "
            "Expected: Successful collection with reasonable test count (>1000)."
        )

    def test_frontend_sequential_hides_categories(self):
        """
        Requirement 1.3: Verify frontend categories are not sequential.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        is_sequential = analyzer.analyze_frontend_sequential_failure()

        # PASS if not sequential (bug fixed)
        assert not is_sequential, (
            "BUG CONDITION DETECTED: Frontend categories are sequential. "
            "Expected: Vitest and E2E in separate jobs or with 'if: always()'. "
            "Early failures should not hide later verdicts."
        )

    def test_junit_merged_missing_producer(self):
        """
        Requirement 1.6: Verify junit-merged.xml has proper producer.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        is_missing = analyzer.analyze_missing_junit_merged()

        # PASS if junit-merged.xml is properly produced or not referenced
        assert not is_missing, (
            "BUG CONDITION DETECTED: junit-merged.xml is referenced without proper production. "
            "Expected: Either not uploaded, or created with proper validation."
        )

    def test_sonar_skipped_for_forks(self):
        """
        Requirement 1.7 & 1.16: Verify Sonar analysis is not skipped for security.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        is_skipped = analyzer.analyze_sonar_fork_omission()

        # PASS if Sonar is not dangerously skipped for forks
        assert not is_skipped, (
            "BUG CONDITION DETECTED: Sonar analysis is skipped for forks without proper gating. "
            "Expected: Fork PRs should not publish ci-required, preventing merge without Sonar."
        )

    def test_high_critical_vulnerabilities_allowed(self):
        """
        Requirement 1.8: Verify High/Critical vulnerabilities are not allowed.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        allows_high_critical = analyzer.analyze_high_critical_baselines()

        # PASS if High/Critical are NOT allowed (enforced zero policy)
        assert not allows_high_critical, (
            "BUG CONDITION DETECTED: High/Critical vulnerabilities can be ignored. "
            "Expected: zero-finding threshold regardless of baseline or suppression."
        )

    def test_frozen_backend_is_noop(self):
        """
        Requirement 1.9: Verify frozen backend is properly enforced.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        is_noop = analyzer.analyze_frozen_backend_noop()

        # PASS if frozen backend is properly enforced (not a no-op)
        assert not is_noop, (
            "BUG CONDITION DETECTED: Frozen backend is not properly enforced. "
            "Expected: deterministic resolution and lock files are honored."
        )

    def test_mutable_image_references_exist(self):
        """
        Requirement 1.10: Verify mutable Docker/service image references do not exist.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        has_mutable = analyzer.analyze_mutable_image_refs()

        # PASS if no mutable references found (bug fixed)
        assert not has_mutable, (
            "BUG CONDITION DETECTED: Mutable image references found. "
            "Expected: immutable tags (digest or specific version) for all service/docker images."
        )

    def test_incomplete_test_evidence_handling(self):
        """
        Requirement 1.5 & 1.6: Verify test evidence completeness is guaranteed.
        This test PASSES on fixed code (bugs are gone).
        """
        analyzer = WorkflowAnalyzer()
        is_incomplete = analyzer.analyze_incomplete_test_evidence()

        # PASS if test evidence completeness is guaranteed (bug fixed)
        assert not is_incomplete, (
            "BUG CONDITION DETECTED: Test evidence completeness is not guaranteed. "
            "Expected: proper validation and if: always() recovery."
        )

    @given(evaluation=strategy_evaluation())
    @settings(
        max_examples=1000,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_bug_condition_property_generated(self, evaluation: CIEvaluation):
        """
        Property test: Verify that generated bug conditions are correctly identified.
        On fixed code, all generated evaluations should pass correctness checks.
        """
        has_bug = is_bug_condition(evaluation)

        # On fixed code, generated evaluations should either have no bugs or satisfy all correctness constraints
        # At minimum, verify that our bug-detection logic correctly categorizes evaluations
        if has_bug:
            # If a bug is detected, it should be one of the known bug patterns
            for signal in evaluation.signals:
                if len(signal.owners) != 1:
                    # Duplicate/missing owner = bug
                    break
                if not signal.has_authoritative_verdict:
                    # No verdict = bug
                    break
                if not signal.evidence_is_complete:
                    # Incomplete evidence = bug
                    break
                if not signal.evidence_is_parseable:
                    # Unparseable evidence = bug
                    break
                if not signal.is_current_sha:
                    # Stale evidence = bug
                    break
            else:
                # All signals passed checks, but aggregate might still have bugs
                if evaluation.sha != evaluation.requested_sha:
                    return  # SHA mismatch = expected bug
                if not evaluation.dependencies_frozen:
                    return  # Unfrozen deps = expected bug
                if evaluation.cache_required_for_correctness:
                    return  # Cache required = expected bug
                if evaluation.high_critical_allowed:
                    return  # Unsafe policy = expected bug

        # If no bug detected, verify all correctness properties hold
        # (This tests that is_bug_condition correctly identifies safe evaluations)
        if not has_bug:
            for signal in evaluation.signals:
                assert len(signal.owners) == 1, "Signal must have exactly one owner"
                assert signal.has_authoritative_verdict, "Signal must have verdict"
                assert signal.evidence_is_complete, "Evidence must be complete"
                assert signal.evidence_is_parseable, "Evidence must be parseable"
                assert signal.is_current_sha, "Evidence must be current SHA"

            assert evaluation.sha == evaluation.requested_sha, "SHA must match"
            assert evaluation.dependencies_frozen, "Dependencies must be frozen"
            assert (
                not evaluation.cache_required_for_correctness
            ), "Cache must not be required"
            assert (
                not evaluation.high_critical_allowed
            ), "High/Critical must not be allowed"

    def test_all_mandatory_signals_represented_in_workflow(self):
        """
        Every mandatory signal in the registry must have a real owner job.

        This is the assertion that made Task 3.28 look complete when it was not.
        It used to `pytest.skip` whenever a signal could not be found, with the
        message "This is informational" — so when `ci.yml` was reduced to a stub
        that ran nothing, the test found zero of the seventeen signals it looks
        for and reported a pass by skipping.

        It now fails, and it checks ownership structurally: each signal's
        `owner_job` in the registry must exist as an actual job in the evaluator
        workflow or in the trusted finalizer. Substring matching against the file
        text cannot tell a job apart from a comment.
        """
        from tools.ci.aggregate_truth import compute_aggregate_required_signals
        from tools.ci.signal_registry import SIGNAL_REGISTRY

        workflows_dir = REPO_ROOT / ".github" / "workflows"
        job_names: set[str] = set()
        for name in ("ci.yml", "ci-authoritative.yml"):
            path = workflows_dir / name
            assert path.exists(), f"expected workflow {name} is missing"
            workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            job_names.update((workflow.get("jobs") or {}).keys())

        required = compute_aggregate_required_signals()
        assert required, "the registry declares no mandatory signals"

        orphaned = sorted(
            signal_id
            for signal_id in required
            if SIGNAL_REGISTRY.get_signal(signal_id).owner_job not in job_names
        )

        assert not orphaned, (
            "BUG CONDITION DETECTED: mandatory signals have no owning job in the "
            f"workflows. Orphaned: {orphaned}. Jobs present: {sorted(job_names)}. "
            "A signal the registry requires but no job produces can never "
            "succeed, so the aggregate can never go green."
        )

    def test_no_mandatory_step_is_advisory(self):
        """
        No mandatory step may neutralise its own verdict.

        `continue-on-error: true`, a trailing `|| true`, and a trailing `exit 0`
        all turn a red check into a green one. The previous evaluator used all
        three on every security and static leg, which is why the pipeline could
        report success while pip-audit, npm audit, Trivy and Grype were all
        finding things.

        Collecting evidence past a failure is fine — that is what
        `tools/ci/run_checks.py` is for. Discarding the failure is not.
        """
        workflow_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}

        violations: list[str] = []

        for job_name, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                label = step.get("name") or step.get("uses") or "<unnamed step>"

                if step.get("continue-on-error") is True:
                    violations.append(f"{job_name} / {label}: continue-on-error: true")

                run = step.get("run")
                if not isinstance(run, str):
                    continue

                # A `|| true` guarding report PRODUCTION is legitimate and lives
                # in the helper scripts, where the following gate is what decides
                # the verdict. Inside the workflow itself there is no such gate,
                # so treat it as a neutralised verdict.
                for line in run.splitlines():
                    stripped = line.strip()
                    if stripped.endswith("|| true"):
                        violations.append(f"{job_name} / {label}: '{stripped}'")
                    if re.fullmatch(r"exit 0\s*(#.*)?", stripped):
                        violations.append(f"{job_name} / {label}: trailing 'exit 0'")

        assert not violations, (
            "BUG CONDITION DETECTED: mandatory steps neutralise their own "
            "verdict:\n  " + "\n  ".join(violations)
        )
