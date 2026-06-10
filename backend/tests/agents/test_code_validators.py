"""tests/agents/test_code_validators.py — the EXEC-02 code validators (10-04).

Covers VALIDATORS + VALIDATOR-DENY (SPEC requirement 7) and the SC-001 EXEC-02
proof (Task 2):

  * ``code_compile`` / ``code_test`` PASS against the local ``sample_python_repo``
    fixture under an exec-GRANTED LocalWorkspace, OFFLINE, writing validation_results
    rows — proving a validator reaches exec ONLY via the runner/workspace handle.
  * ``code_compile`` flags a seeded SyntaxError as a P0 issue naming the file.
  * ``code_lint`` flags the seeded ruff violation (>=1 issue) with a severity label
    that came through the SINGLE ``map_severity`` (NOT a locally-derived string).
  * VALIDATOR-DENY: under an exec-DENIED policy (or ``ws is None``) each validator
    returns >=1 refusal Issue naming the missing exec grant, spawns ZERO processes
    (a subprocess.run tripwire fails the test if reached), and lets no
    PermissionError escape.
  * The exec-granting ``sample_exec_workflow`` manifest compiles at file trust to a
    Step with ``tools.exec is True`` and ``security``+``approval`` gates (GRANT-PATH
    + D-01), and the EXEC-02 offline proof requires ZERO edits under
    ``backend/agents/execution_engine/`` (SC-001 discipline).

OFFLINE — no live LLM / Bedrock. The validators' subprocesses are bounded by the
10-01 policy caps; pytest is invoked with ``-p no:cacheprovider`` (RESEARCH
Pitfall 2). Run via the targeted offline suite, never full pytest.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry
from agents.capabilities.validators.severity import _SEVERITY_LABELS, map_severity

_FIXTURE_REPO = Path(__file__).resolve().parent / "fixtures" / "sample_python_repo"
_FIXTURE_EXEC_WF = Path(__file__).resolve().parent / "fixtures" / "sample_exec_workflow"
_ENGINE_DIR = Path(__file__).resolve().parents[2] / "agents" / "execution_engine"


# ════════════════════════════════════════════════════════════════════════════
# Registry save/restore (snapshot AFTER discover — 08-01 Issues-Encountered)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_registry():
    registry_mod.discover()
    known = set(registry_mod._KNOWN)
    impls = dict(registry_mod._IMPLS)
    trust = dict(registry_mod._TRUST)
    discovered = registry_mod._DISCOVERED
    try:
        yield
    finally:
        registry_mod._KNOWN.clear()
        registry_mod._KNOWN.update(known)
        registry_mod._IMPLS.clear()
        registry_mod._IMPLS.update(impls)
        registry_mod._TRUST.clear()
        registry_mod._TRUST.update(trust)
        registry_mod._DISCOVERED = discovered


# ════════════════════════════════════════════════════════════════════════════
# Fakes — a recording runner exposing .workspace + record_validation_result, and
# a minimal validation target (the DeliverableContext shape the validators read).
# ════════════════════════════════════════════════════════════════════════════


class _RecordingRunner:
    """Minimal ctx.runner handle: holds a bound workspace + records validation rows."""

    def __init__(self, workspace=None) -> None:
        self.workspace = workspace
        self.validation_rows: list[dict] = []

    async def record_validation_result(
        self, step, validator, *, severity=None, attempt=0, issues=None
    ):
        self.validation_rows.append(
            {
                "step": step,
                "validator": validator,
                "severity": severity,
                "attempt": attempt,
                "issues": issues or [],
            }
        )
        return f"vr-{len(self.validation_rows)}"


class _Target:
    """The kernel-pure validation target (the DeliverableContext shape)."""

    def __init__(self, runner, path=None, step="build") -> None:
        self.runner = runner
        self.path = path
        self.step = step
        self.task_meta: dict = {}
        self.content = ""


def _exec_workspace(tmp_path: Path, *, exec_granted: bool):
    """A LocalWorkspace rooted at ``tmp_path/runs/...`` with exec on/off, plus a recorder."""
    from app.agents.runtime.local import (
        DEFAULT_EXEC_PROFILE,
        LocalExecutionPolicy,
        LocalSandboxRuntime,
        LocalWorkspace,
    )
    from app.agents.sandbox import RunSandbox
    import app.core.config as config_module

    config_module.settings.RUNS_ROOT = str(tmp_path / "runs")
    if exec_granted:
        policy = LocalExecutionPolicy(
            exec=True,
            network=False,
            secrets=[],
            exec_allow=DEFAULT_EXEC_PROFILE.exec_allow,
            exec_deny=DEFAULT_EXEC_PROFILE.exec_deny,
            cpu_seconds=DEFAULT_EXEC_PROFILE.cpu_seconds,
            mem_mb=DEFAULT_EXEC_PROFILE.mem_mb,
            wall_seconds=DEFAULT_EXEC_PROFILE.wall_seconds,
        )
    else:
        policy = LocalExecutionPolicy(exec=False, network=False, secrets=[])

    runtime = LocalSandboxRuntime()
    sandbox = RunSandbox("anon", "ws-codeval", runs_root=config_module.settings.RUNS_ROOT)
    recorded: list[dict] = []
    ws = LocalWorkspace(
        owner_id="anon",
        workspace_id="ws-codeval",
        runtime=runtime,
        policy=policy,
        sandbox=sandbox,
    )
    ws._recorder = lambda argv, **kw: recorded.append({"argv": argv, **kw})
    return ws, recorded


def _seed_fixture_into(ws, *files: str) -> None:
    """Copy the named fixture files into the workspace root (the validators' cwd)."""
    root = ws._root
    for name in files:
        shutil.copy2(_FIXTURE_REPO / name, root / name)


def _resolve(name: str):
    """Resolve a registered code validator impl from the discovered registry."""
    return CapabilityRegistry().resolve("validator", name)


# Skip the live-exec suite when the toolchain isn't resolvable offline (defensive;
# the dev runtime ships python3.11/pytest/ruff — see backend/CLAUDE.md).
def _tool_available(argv: list[str]) -> bool:
    try:
        subprocess.run(argv, capture_output=True, timeout=20)
        return True
    except Exception:  # noqa: BLE001
        return False


_PYTEST_OK = _tool_available([sys.executable, "-m", "pytest", "--version"])
_RUFF_OK = shutil.which("ruff") is not None


# ════════════════════════════════════════════════════════════════════════════
# VALIDATORS — compile + test PASS on the fixture; compile FAIL; lint flags seed
# ════════════════════════════════════════════════════════════════════════════


def test_code_compile_pass_on_fixture(tmp_path):
    ws, _ = _exec_workspace(tmp_path, exec_granted=True)
    _seed_fixture_into(ws, "calc.py", "test_calc.py", "lint_seed.py")
    runner = _RecordingRunner(workspace=ws)
    target = _Target(runner)

    issues = asyncio.run(_resolve("code_compile").validate(target))

    assert [i for i in issues if i.severity in ("P0", "P1")] == [], issues
    assert runner.validation_rows, "code_compile must write a validation_results row"
    assert runner.validation_rows[-1]["validator"] == "code_compile"


def test_code_compile_flags_syntax_error(tmp_path):
    ws, _ = _exec_workspace(tmp_path, exec_granted=True)
    _seed_fixture_into(ws, "calc.py")
    # Seed a file with a syntax error directly in the workspace.
    (ws._root / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    runner = _RecordingRunner(workspace=ws)
    target = _Target(runner)

    issues = asyncio.run(_resolve("code_compile").validate(target))

    p0 = [i for i in issues if i.severity == "P0"]
    assert p0, f"expected a P0 compile failure, got {issues}"
    assert any("broken.py" in i.message for i in p0), p0


@pytest.mark.skipif(not _PYTEST_OK, reason="pytest not resolvable offline")
def test_code_test_pass_on_fixture(tmp_path):
    ws, _ = _exec_workspace(tmp_path, exec_granted=True)
    _seed_fixture_into(ws, "calc.py", "test_calc.py")
    runner = _RecordingRunner(workspace=ws)
    target = _Target(runner)

    issues = asyncio.run(_resolve("code_test").validate(target))

    assert [i for i in issues if i.severity == "P0"] == [], issues
    assert runner.validation_rows, "code_test must write a validation_results row"
    assert runner.validation_rows[-1]["validator"] == "code_test"


@pytest.mark.skipif(not _RUFF_OK, reason="ruff not on PATH offline")
def test_code_lint_flags_seeded_error_with_mapped_severity(tmp_path):
    ws, _ = _exec_workspace(tmp_path, exec_granted=True)
    _seed_fixture_into(ws, "lint_seed.py")
    runner = _RecordingRunner(workspace=ws)
    target = _Target(runner)

    issues = asyncio.run(_resolve("code_lint").validate(target))

    assert issues, "code_lint must flag the seeded ruff violation"
    # The recorded label must be one map_severity produces (NOT a locally-derived
    # string) — assert the row severity is in the single source's label set.
    row = runner.validation_rows[-1]
    assert row["severity"] in set(_SEVERITY_LABELS.values()), row
    # And each issue's internal severity maps cleanly through the single source.
    for issue in issues:
        assert map_severity(issue.severity) in set(_SEVERITY_LABELS.values())


# ════════════════════════════════════════════════════════════════════════════
# VALIDATOR-DENY — exec-denied → refusal, ZERO spawns, no escaping PermissionError
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("validator_name", ["code_compile", "code_test", "code_lint"])
def test_validator_deny_under_exec_denied_policy(tmp_path, monkeypatch, validator_name):
    ws, _ = _exec_workspace(tmp_path, exec_granted=False)  # policy.exec OFF
    _seed_fixture_into(ws, "calc.py")
    runner = _RecordingRunner(workspace=ws)
    target = _Target(runner)

    # A tripwire: if any validator spawns a process under the denied policy, fail.
    spawned = {"hit": False}
    orig_run = subprocess.run

    def _tripwire(*a, **k):
        spawned["hit"] = True
        return orig_run(*a, **k)

    monkeypatch.setattr(subprocess, "run", _tripwire)

    # No PermissionError must escape.
    issues = asyncio.run(_resolve(validator_name).validate(target))

    assert issues, f"{validator_name} must return >=1 refusal Issue under exec-denied"
    assert any(
        "exec not granted" in i.message or "exec denied" in i.message for i in issues
    ), issues
    assert spawned["hit"] is False, f"{validator_name} must NOT spawn under exec-denied"
    assert runner.validation_rows, f"{validator_name} must still record the refusal"


@pytest.mark.parametrize("validator_name", ["code_compile", "code_test", "code_lint"])
def test_validator_deny_when_no_workspace(validator_name):
    """``ws is None`` (no workspace bound on the runner) → refusal, zero spawns."""
    runner = _RecordingRunner(workspace=None)
    target = _Target(runner)

    issues = asyncio.run(_resolve(validator_name).validate(target))

    assert issues, f"{validator_name} must refuse when no workspace is bound"
    assert any("exec not granted" in i.message for i in issues), issues


# ════════════════════════════════════════════════════════════════════════════
# Registry membership — the three code validators are reachable by name; count 53
# ════════════════════════════════════════════════════════════════════════════


def test_code_validators_registered():
    reg = CapabilityRegistry()
    for name in ("code_compile", "code_test", "code_lint"):
        assert reg.is_registered("validator", name) is True
    assert ("validator", "code_compile") in registry_mod._KNOWN
    assert ("validator", "code_test") in registry_mod._KNOWN
    assert ("validator", "code_lint") in registry_mod._KNOWN


def test_registry_count_is_fifty_three():
    assert len(registry_mod._KNOWN) == 53


# ════════════════════════════════════════════════════════════════════════════
# Task 2 — the exec-granting sample manifest compiles (GRANT-PATH + D-01); EXEC-02
# offline proof requires ZERO edits under backend/agents/execution_engine/.
# ════════════════════════════════════════════════════════════════════════════


def _compile_exec_manifest():
    from agents.workflows.manifest import load_manifest
    from agents.workflows.compiler import WorkflowCompiler

    registry_mod.discover()
    manifest = load_manifest("sample_exec_workflow", _FIXTURE_EXEC_WF.parent)
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
    return compiled


def test_exec_manifest_compiles_with_exec_and_required_gates():
    compiled = _compile_exec_manifest()
    # Find the exec-granting step.
    exec_steps = [s for s in compiled.steps if s.tools.exec]
    assert exec_steps, "the manifest must compile an exec-granted step (tools.exec is True)"
    step = exec_steps[0]
    assert step.tools.exec is True
    assert "security" in step.gates and "approval" in step.gates, step.gates
    # It declares the code validators that drive gated exec.
    assert "code_compile" in step.validators
    assert "code_test" in step.validators


@pytest.mark.skipif(not _PYTEST_OK, reason="pytest not resolvable offline")
def test_exec02_offline_proof_zero_engine_edits(tmp_path):
    """EXEC-02: code_compile + code_test PASS against sample_python_repo via the
    exec-granted workspace — and a new exec-capable workflow needed ZERO edits under
    backend/agents/execution_engine/ for THIS plan's working tree (SC-001)."""
    # 1) The manifest compiles to an exec-granted step (the authoring path).
    compiled = _compile_exec_manifest()
    assert any(s.tools.exec for s in compiled.steps)

    # 2) The capability (NOT engine code) carries the exec: compile + test PASS.
    ws, _ = _exec_workspace(tmp_path, exec_granted=True)
    _seed_fixture_into(ws, "calc.py", "test_calc.py")
    runner = _RecordingRunner(workspace=ws)
    target = _Target(runner)

    compile_issues = asyncio.run(_resolve("code_compile").validate(target))
    test_issues = asyncio.run(_resolve("code_test").validate(target))
    assert [i for i in compile_issues if i.severity == "P0"] == [], compile_issues
    assert [i for i in test_issues if i.severity == "P0"] == [], test_issues

    # 3) SC-001 discipline: no edits under backend/agents/execution_engine/ for this
    #    plan's working tree (the exec-capable workflow is authored by manifest +
    #    capability only). A git diff over that dir is clean for this plan's work.
    diff = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", str(_ENGINE_DIR)],
        cwd=str(_ENGINE_DIR.parents[1]),
        capture_output=True,
        text=True,
    )
    changed = [ln for ln in diff.stdout.splitlines() if ln.strip()]
    assert changed == [], f"SC-001 violated: engine edits required: {changed}"
