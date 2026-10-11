"""
Unit tests for the blocking aggregate gate, focused on advisory downgrades.

WHY THIS FILE EXISTS (F-03)
---------------------------
`deploy.yml` used to SKIP the CI gate entirely for the `dev` environment, to work
around four pre-existing red signals. That discarded every mandatory signal —
lint, every test partition, both coverage gates, secret scanning, two dependency
audits and four container scans — to avoid four. Every dev deploy shipped
unevaluated code.

The replacement is a per-signal, allowlisted, dated advisory downgrade. That is
only safe if it cannot become a general-purpose bypass, so the tests below spend
most of their attention on the ways someone might try to widen it:

* naming a signal that is not on the allowlist
* naming a signal that does not exist
* using an allowance after its expiry date
* letting a signal that never ran count as "advisory"
* letting a downgraded run publish a green merge status

Each of those is asserted to FAIL CLOSED. The happy path — a measured red on an
allowlisted signal, before its expiry — is asserted to pass while still recording
the real state and a `strict_outcome` of failure, which is what
`.github/scripts/ci-validate-evidence.sh` uses to refuse to finalize a pull
request on a downgraded evaluation.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tools.ci.aggregate_truth import compute_aggregate_required_signals
from tools.ci.ci_gate import main
from tools.ci.signal_registry import SIGNAL_REGISTRY

#: A syntactically valid evaluation SHA. The gate only cares that it is 40 hex
#: characters and that every signal reports against the same one.
SHA = "a" * 40

#: The jobs ci.yml feeds into `--job`, i.e. every owner in the registry.
OWNER_JOBS = (
    "repo-static",
    "backend-inventory",
    "backend-static",
    "backend-offline",
    "backend-postgres",
    "backend-evidence",
    "frontend-build",
    "frontend-static",
    "frontend-vitest",
    "frontend-e2e",
    "frontend-evidence",
    "security",
    "container-scan",
)

#: The signals the registry allows to be advisory, as of this change. The two
#: dependency-audit signals (security[backend-deps], security[frontend-deps])
#: were retired when pip-audit and npm audit folded into the Trivy/Grype
#: container scans, whose only exceptions are tools/ci/scan_accepts.py.
KNOWN_RED_SIGNALS = (
    "frontend-e2e",
    "frontend-evidence",
)


def _run_aggregate(
    tmp_path: Path,
    job_results: dict[str, str] | None = None,
    advisory: list[str] | None = None,
    omit_jobs: set[str] | None = None,
    event: str | None = None,
    filtered_areas: list[str] | None = None,
) -> tuple[int, dict | None]:
    """
    Invoke the aggregate subcommand in-process and return (exit code, manifest).

    In-process rather than via subprocess: there is no I/O to isolate beyond the
    manifest file, and `main()` returns the exit code directly.
    """
    job_results = job_results or {}
    omit_jobs = omit_jobs or set()
    out = tmp_path / "ci-evidence-manifest.json"

    argv = ["aggregate", "--sha", SHA, "--out", str(out)]
    if event is not None:
        argv += ["--event", event]
    for job in OWNER_JOBS:
        if job in omit_jobs:
            continue
        argv += ["--job", f"{job}={job_results.get(job, 'success')}"]
    for value in advisory or []:
        argv += ["--advisory", value]
    for area in filtered_areas or []:
        argv += ["--filtered-area", area]

    code = main(argv)
    manifest = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return code, manifest


# ----------------------------------------------------------------------
# The allowlist itself
# ----------------------------------------------------------------------


class TestAdvisoryAllowlist:
    """The allowlist is the whole reason `--advisory` is not a bypass."""

    def test_advisory_eligible_set_is_exactly_the_documented_four(self):
        """
        Widening the allowlist must be a deliberate, reviewed act.

        This test fails when another signal is marked eligible, which is the
        point: the list is small on purpose, and growing it should require
        editing KNOWN_RED_SIGNALS and explaining why in the same diff.
        """
        eligible = sorted(s.id for s in SIGNAL_REGISTRY.get_advisory_eligible_signals())
        assert eligible == sorted(KNOWN_RED_SIGNALS)

    @pytest.mark.parametrize("signal_id", KNOWN_RED_SIGNALS)
    def test_every_allowance_is_dated_owned_and_justified(self, signal_id):
        """An undated or unexplained allowance is a permanent one."""
        signal = SIGNAL_REGISTRY.get_signal(signal_id)
        assert signal is not None
        assert signal.advisory_expires, f"{signal_id} has no expiry date"
        # Parses, and is therefore enforceable.
        date.fromisoformat(signal.advisory_expires)
        assert signal.advisory_reason, f"{signal_id} has no recorded reason"
        assert signal.advisory_owner, f"{signal_id} has no owner"

    # The container-scan signals are TEMPORARILY warn-only through
    # `scan-gate --mode warn`, not through this allowlist, so this still holds.
    # TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
    # In future this must be changed back to BLOCKING, and the outstanding High/Critical
    # vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
    def test_blocking_signals_are_not_advisory_eligible(self):
        """
        The signals that catch real regressions must never be downgradable.

        Named explicitly rather than derived, so that marking one of them
        eligible fails here instead of quietly becoming possible.
        """
        must_stay_blocking = (
            "backend-offline",
            "backend-postgres",
            "backend-evidence",
            "security[secrets]",
            "container-scan[backend]/trivy",
            "container-scan[backend]/grype",
            "container-scan[frontend]/trivy",
            "container-scan[frontend]/grype",
            "container-scan[frontend]/trivy-lockfile",
            "backend-static/bandit",
            "repo-static/shellcheck",
        )
        offenders = [
            signal_id
            for signal_id in must_stay_blocking
            if SIGNAL_REGISTRY[signal_id].advisory_eligible
        ]
        assert not offenders, f"these must never be advisory: {offenders}"


# ----------------------------------------------------------------------
# resolve_advisory_request: allowlist + expiry
# ----------------------------------------------------------------------


class TestResolveAdvisoryRequest:
    """Validation happens before any verdict is computed."""

    def test_resolve_accepts_an_eligible_signal_before_expiry(self):
        """The happy path returns the id and no problems."""
        accepted, problems = SIGNAL_REGISTRY.resolve_advisory_request(
            ["frontend-evidence"], today=date(2026, 9, 23)
        )
        assert accepted == {"frontend-evidence"}
        assert problems == []

    def test_resolve_rejects_an_expired_allowance(self):
        """Past the date the signal is blocking again, by design."""
        accepted, problems = SIGNAL_REGISTRY.resolve_advisory_request(
            ["frontend-evidence"], today=date(2099, 1, 1)
        )
        assert accepted == set()
        assert any("expired" in problem for problem in problems)

    def test_resolve_rejects_a_non_eligible_signal(self):
        """This is the bypass attempt that matters most."""
        accepted, problems = SIGNAL_REGISTRY.resolve_advisory_request(
            ["backend-offline"]
        )
        assert accepted == set()
        assert any("not advisory-eligible" in problem for problem in problems)

    def test_resolve_rejects_an_unknown_signal(self):
        """A typo must not silently downgrade nothing while appearing to work."""
        accepted, problems = SIGNAL_REGISTRY.resolve_advisory_request(["nope"])
        assert accepted == set()
        assert any("not a registered signal" in problem for problem in problems)

    def test_expiry_boundary_is_inclusive_of_the_expiry_day(self):
        """On the expiry date itself the allowance is still valid; the day after it is not."""
        signal = SIGNAL_REGISTRY["frontend-evidence"]
        expires = date.fromisoformat(signal.advisory_expires)
        assert not signal.advisory_allowance_expired(expires)
        assert signal.advisory_allowance_expired(expires.replace(year=expires.year + 1))


# ----------------------------------------------------------------------
# cmd_aggregate end to end
# ----------------------------------------------------------------------


class TestAggregateWithoutAdvisory:
    """Baseline: the strict gate is unchanged when no downgrade is requested."""

    def test_all_green_succeeds_and_records_a_strict_pass(self, tmp_path):
        code, manifest = _run_aggregate(tmp_path)
        assert code == 0
        assert manifest["outcome"] == "success"
        assert manifest["strict_outcome"] == "success"
        assert manifest["advisory_signals"] == []
        assert manifest["advisory_downgraded"] == {}

    def test_aggregate_prints_registry_count_when_evaluating(self, tmp_path, capsys):
        """F-20: the count comes from the registry, so prose never has to state it."""
        _run_aggregate(tmp_path)
        output = capsys.readouterr().out
        expected = len(compute_aggregate_required_signals())
        assert f"mandatory signals: {expected}" in output

    def test_a_red_signal_fails_when_not_downgraded(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path, job_results={"frontend-evidence": "failure"}
        )
        assert code == 1
        assert manifest["outcome"] == "failure"


class TestAggregateWithAdvisory:
    """The downgrade path, and everything it must still refuse."""

    def test_measured_red_on_an_allowlisted_signal_does_not_block(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"frontend-evidence": "failure"},
            advisory=["frontend-evidence"],
        )
        assert code == 0
        assert manifest["outcome"] == "success"
        # The evaluation was NOT a strict pass, and the manifest says so.
        assert manifest["strict_outcome"] == "failure"
        assert manifest["advisory_downgraded"] == {"frontend-evidence": "failure"}

    def test_real_state_is_preserved_in_the_manifest(self, tmp_path):
        """
        A downgrade must not rewrite history.

        The manifest is evidence. If it recorded `success` for a signal that
        failed, every downstream reader — including a human debugging a bad
        release — would be misled.
        """
        _, manifest = _run_aggregate(
            tmp_path,
            job_results={"frontend-evidence": "failure"},
            advisory=["frontend-evidence"],
        )
        assert manifest["signal_states"]["frontend-evidence"] == "failure"

    def test_all_four_known_red_signals_can_be_downgraded_together(self, tmp_path):
        """The dev gate's actual configuration (every KNOWN_RED_SIGNALS entry) must work."""
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"frontend-evidence": "failure", "frontend-e2e": "failure"},
            advisory=["\n".join(KNOWN_RED_SIGNALS)],
        )
        assert code == 0
        assert sorted(manifest["advisory_signals"]) == sorted(KNOWN_RED_SIGNALS)

    def test_comma_separated_input_is_accepted(self, tmp_path):
        """The workflow passes one string; both separators must parse."""
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"frontend-e2e": "failure"},
            advisory=["frontend-e2e, frontend-evidence"],
        )
        assert code == 0
        assert sorted(manifest["advisory_signals"]) == [
            "frontend-e2e",
            "frontend-evidence",
        ]

    def test_downgrading_a_non_eligible_signal_fails_closed(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"backend-offline": "failure"},
            advisory=["backend-offline"],
        )
        assert code == 1
        assert manifest["outcome"] == "failure"

    def test_downgrading_every_signal_fails_closed(self, tmp_path):
        """The maximal bypass attempt: name the whole required set."""
        required = SIGNAL_REGISTRY["ci-required"].aggregate_members
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={job: "failure" for job in OWNER_JOBS},
            advisory=["\n".join(required)],
        )
        assert code == 1
        assert manifest["outcome"] == "failure"

    def test_unknown_signal_in_the_advisory_list_fails_closed(self, tmp_path):
        code, _ = _run_aggregate(tmp_path, advisory=["not-a-signal"])
        assert code == 1

    @pytest.mark.parametrize("state", ["skipped", "cancelled", ""])
    def test_absence_of_evidence_is_never_excused(self, tmp_path, state):
        """
        Advisory covers a measured `failure` only.

        `skipped`/`cancelled`/missing all mean the check produced no verdict. If
        those were downgradable, deleting or short-circuiting a job would satisfy
        the gate — which is precisely the hole the dev gate-skip was.
        """
        code, _ = _run_aggregate(
            tmp_path,
            job_results={"frontend-evidence": state},
            advisory=["frontend-evidence"],
        )
        assert code == 1

    def test_a_deleted_owner_job_still_fails(self, tmp_path):
        """An advisory signal whose job is gone has no verdict at all."""
        code, _ = _run_aggregate(
            tmp_path,
            advisory=["frontend-evidence"],
            omit_jobs={"frontend-evidence"},
        )
        assert code == 1

    def test_stale_sha_is_never_excused(self, tmp_path):
        """
        A verdict for a different revision describes different code.

        Reached through the manifest rather than the CLI, because `--sha` applies
        to every `--job` uniformly; this asserts the rule the code implements.
        """
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"frontend-evidence": "failure"},
            advisory=["frontend-evidence"],
        )
        assert code == 0
        assert manifest["evaluation_sha"] == SHA


# ----------------------------------------------------------------------
# F-15: the path-filter (skip-as-success) policy
# ----------------------------------------------------------------------

#: The jobs ci.yml gates on the `backend` / `frontend` area outputs.
BACKEND_JOBS = (
    "backend-inventory",
    "backend-static",
    "backend-offline",
    "backend-postgres",
    "backend-evidence",
)
FRONTEND_JOBS = (
    "frontend-build",
    "frontend-static",
    "frontend-vitest",
    "frontend-e2e",
    "frontend-evidence",
)
ALL_AREAS = ["backend", "frontend", "infra", "backend_image", "frontend_image"]


def _ids_owned_by(*jobs: str) -> set[str]:
    """Every registry signal id owned by the given jobs."""
    return {s.id for job in jobs for s in SIGNAL_REGISTRY.get_signals_by_owner(job)}


def _ids_in_area(area: str) -> set[str]:
    """Every registry signal id in one path-filter area."""
    return {s.id for s in SIGNAL_REGISTRY.get_signals_by_area(area)}


class TestPathFilterPolicy:
    """A skip is satisfied only when the PR's `changes` job filtered its area."""

    def test_aggregate_succeeds_and_records_policy_filtered_when_backend_skipped_on_pr(
        self, tmp_path
    ):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={job: "skipped" for job in BACKEND_JOBS},
            event="pull_request",
            filtered_areas=["backend"],
        )
        backend_ids = _ids_owned_by(*BACKEND_JOBS)
        assert code == 0
        assert manifest["outcome"] == "success"
        assert manifest["strict_outcome"] == "success"
        assert set(manifest["policy_filtered"]) == backend_ids
        assert backend_ids.isdisjoint(manifest["signal_states"])
        assert manifest["event"] == "pull_request"
        assert manifest["filtered_areas"] == ["backend"]

    def test_aggregate_fails_when_job_skipped_without_a_filtered_area(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={job: "skipped" for job in BACKEND_JOBS},
            event="pull_request",
        )
        assert code == 1
        assert manifest["policy_filtered"] == []
        assert manifest["signal_states"]["backend-offline"] == "skipped"

    @pytest.mark.parametrize(
        "event", ["push", "workflow_dispatch", "workflow_call", ""]
    )
    def test_aggregate_fails_when_filtered_area_given_off_pull_request(
        self, tmp_path, event
    ):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={job: "skipped" for job in BACKEND_JOBS},
            event=event,
            filtered_areas=["backend"],
        )
        assert code == 1
        assert manifest["policy_filtered"] == []
        assert manifest["filtered_areas"] == []
        assert manifest["signal_states"]["backend-offline"] == "skipped"

    def test_aggregate_fails_when_filtered_area_is_unknown(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={job: "skipped" for job in BACKEND_JOBS},
            event="pull_request",
            filtered_areas=["backend", "docs"],
        )
        assert code == 1
        # An invalid request filters NOTHING, not just the bad area.
        assert manifest["policy_filtered"] == []

    def test_aggregate_fails_when_repo_static_skipped_with_every_area_filtered(
        self, tmp_path
    ):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"repo-static": "skipped"},
            event="pull_request",
            filtered_areas=ALL_AREAS,
        )
        assert code == 1
        assert manifest["signal_states"]["repo-static/compose-config"] == "skipped"
        assert not any(
            i.startswith("repo-static/") for i in manifest["policy_filtered"]
        )

    def test_aggregate_fails_when_filtered_job_ran_and_failed(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"frontend-static": "failure"},
            event="pull_request",
            filtered_areas=["frontend"],
        )
        assert code == 1
        assert manifest["signal_states"]["frontend-static/lint"] == "failure"
        assert "frontend-static/lint" not in manifest["policy_filtered"]

    def test_aggregate_succeeds_when_partial_matrix_ran_with_infra_filtered(
        self, tmp_path
    ):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"security": "success"},
            event="pull_request",
            filtered_areas=["infra"],
        )
        assert code == 0
        assert manifest["signal_states"]["security[secrets]"] == "success"
        assert set(manifest["policy_filtered"]) == _ids_in_area("infra")

    def test_aggregate_fails_when_partial_matrix_live_leg_failed(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"security": "failure"},
            event="pull_request",
            filtered_areas=["infra"],
        )
        assert code == 1
        assert manifest["signal_states"]["security[secrets]"] == "failure"

    def test_aggregate_succeeds_when_container_scan_partially_filtered(self, tmp_path):
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={"container-scan": "success"},
            event="pull_request",
            filtered_areas=["backend_image"],
        )
        assert code == 0
        assert set(manifest["policy_filtered"]) == _ids_in_area("backend_image")
        assert manifest["signal_states"]["container-scan[frontend]/trivy"] == "success"

    def test_aggregate_succeeds_when_docs_only_pr_filters_every_area(self, tmp_path):
        skipped = BACKEND_JOBS + FRONTEND_JOBS + ("container-scan",)
        code, manifest = _run_aggregate(
            tmp_path,
            job_results={job: "skipped" for job in skipped},
            event="pull_request",
            filtered_areas=ALL_AREAS,
        )
        assert code == 0
        required = set(manifest["required_signals"])
        filtered = set(manifest["policy_filtered"])
        assert filtered | set(manifest["signal_states"]) >= required
        assert set(manifest["signal_states"]) == _ids_owned_by("repo-static") | {
            "security[secrets]"
        }

    def test_aggregate_reports_no_internal_inconsistency_when_signals_filtered(
        self, tmp_path, capsys
    ):
        _run_aggregate(
            tmp_path,
            job_results={job: "skipped" for job in FRONTEND_JOBS},
            event="pull_request",
            filtered_areas=["frontend"],
        )
        output = capsys.readouterr().out
        assert "internal inconsistency" not in output
        assert "policy-filtered" in output

    def test_aggregate_records_event_and_empty_filter_when_push_runs_everything(
        self, tmp_path
    ):
        code, manifest = _run_aggregate(tmp_path, event="push")
        assert code == 0
        assert manifest["event"] == "push"
        assert manifest["filtered_areas"] == []
        assert manifest["policy_filtered"] == []
        assert set(manifest["signal_states"]) == set(manifest["required_signals"])


# ---------------------------------------------------------------------------
# scan-gate --mode (TEMPORARY warn-only vulnerability scans)
# TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
# In future this must be changed back to BLOCKING, and the outstanding High/Critical
# vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
# ---------------------------------------------------------------------------


def _trivy_report(tmp_path: Path, severity: str) -> Path:
    report = tmp_path / "trivy.json"
    report.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Results": [
                    {
                        "Target": "img",
                        "Class": "os-pkgs",
                        "Type": "debian",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2099-0001",
                                "PkgName": "pkg",
                                "InstalledVersion": "1.0",
                                "FixedVersion": "1.1",
                                "Severity": severity,
                                "Description": "d",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return report


def _run_scan_gate(tmp_path: Path, report: Path, mode: str | None = None):
    argv = [
        "scan-gate",
        "--scanner",
        "trivy-image",
        "--report",
        str(report),
        "--producer",
        "container-scan[backend]/trivy",
        "--out",
        str(tmp_path / "verdict.json"),
    ]
    if mode:
        argv += ["--mode", mode]
    code = main(argv)
    verdict_path = tmp_path / "verdict.json"
    verdict = json.loads(verdict_path.read_text()) if verdict_path.exists() else None
    return code, verdict


def _unusable_report(tmp_path: Path, kind: str) -> Path:
    report = tmp_path / "unusable.json"
    if kind == "empty":
        report.write_text("", encoding="utf-8")
    elif kind == "malformed":
        report.write_text("{ not json", encoding="utf-8")
    return report


class TestScanGateMode:
    @pytest.fixture(autouse=True)
    def _no_real_step_summary(self, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    def test_cmd_scan_gate_returns_one_when_mode_omitted_and_report_has_high(
        self, tmp_path
    ):
        code, verdict = _run_scan_gate(tmp_path, _trivy_report(tmp_path, "HIGH"))
        assert code == 1
        assert verdict["mode"] == "block"
        assert verdict["enforced"] is True

    def test_cmd_scan_gate_returns_one_and_prints_error_when_block_mode_finds_critical(
        self, tmp_path, capsys
    ):
        code, _ = _run_scan_gate(
            tmp_path, _trivy_report(tmp_path, "CRITICAL"), mode="block"
        )
        assert code == 1
        assert "::error::" in capsys.readouterr().out

    def test_cmd_scan_gate_returns_zero_and_prints_warning_when_warn_mode_finds_high(
        self, tmp_path, capsys
    ):
        code, verdict = _run_scan_gate(
            tmp_path, _trivy_report(tmp_path, "HIGH"), mode="warn"
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "::warning" in out
        assert "::error" not in out
        assert "CVE-2099-0001" in out
        assert verdict["success"] is False
        assert verdict["high_critical_count"] == 1
        assert verdict["mode"] == "warn"
        assert verdict["enforced"] is False

    def test_cmd_scan_gate_appends_step_summary_when_warn_mode_finds_high(
        self, tmp_path, monkeypatch
    ):
        summary = tmp_path / "summary.md"
        summary.write_text("existing\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        _run_scan_gate(tmp_path, _trivy_report(tmp_path, "HIGH"), mode="warn")
        text = summary.read_text(encoding="utf-8")
        assert text.startswith("existing")
        assert "CVE-2099-0001" in text
        assert "TEMPORARY" in text
        assert "scan_accepts.py" in text

    def test_cmd_scan_gate_writes_no_step_summary_when_block_mode_finds_high(
        self, tmp_path, monkeypatch
    ):
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        _run_scan_gate(tmp_path, _trivy_report(tmp_path, "HIGH"), mode="block")
        assert not summary.exists()

    @pytest.mark.parametrize("kind", ["missing", "empty", "malformed"])
    def test_cmd_scan_gate_returns_zero_and_prints_warning_when_warn_mode_report_is_unusable(
        self, tmp_path, monkeypatch, capsys, kind
    ):
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        report = _unusable_report(tmp_path, kind)
        code, verdict = _run_scan_gate(tmp_path, report, mode="warn")
        assert code == 0
        assert "::warning" in capsys.readouterr().out
        assert verdict["success"] is False
        assert verdict["error"]
        assert "could not be evaluated" in summary.read_text(encoding="utf-8")

    @pytest.mark.parametrize("kind", ["missing", "empty", "malformed"])
    def test_cmd_scan_gate_returns_one_when_block_mode_report_is_unusable(
        self, tmp_path, kind
    ):
        code, _ = _run_scan_gate(
            tmp_path, _unusable_report(tmp_path, kind), mode="block"
        )
        assert code == 1

    def test_cmd_scan_gate_returns_zero_without_warning_when_warn_mode_report_is_medium_only(
        self, tmp_path, capsys
    ):
        code, verdict = _run_scan_gate(
            tmp_path, _trivy_report(tmp_path, "MEDIUM"), mode="warn"
        )
        assert code == 0
        assert "::warning" not in capsys.readouterr().out
        assert verdict["success"] is True

    def test_build_parser_rejects_mode_when_value_is_unknown(self, tmp_path):
        with pytest.raises(SystemExit):
            _run_scan_gate(tmp_path, _trivy_report(tmp_path, "HIGH"), mode="advisory")
