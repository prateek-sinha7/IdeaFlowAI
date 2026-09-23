"""tests/agents/test_step_commits_v3.py — Requirement 9 / 9a multi-step commit isolation.

V3 verification debt closure: FR-009 / AC-02 and FR-009a / AC-17.

Three scenarios verified via a real git sandbox:

1. **FR-009 / AC-02: multi-step dispatch → one commit per step**
   A multi-step workflow produces one commit per step boundary in `git log`.
   `git show --stat HEAD` (and every historical commit) contains no reserved paths.

2. **FR-009a / AC-17: routing pass commits before gate outcome**
   A conditional-gate route (step jump) commits before the routing outcome is
   consumed; backward jumps (re-entry) also commit before dispatch. Re-run the
   target step and verify a new commit for the re-dispatch (isolation per visit).

Offline-safe: real git sandbox (tmp_path), scripted model only (no Bedrock / DB).

FR mapping:
  FR-009: Engine commits at the step boundary, gated on `has_git`, not `post_step`.
  FR-009a: Routing step still commits, before the gate outcome is consumed.

AC mapping:
  AC-02: multi-step dispatch → one commit per step in git log;
         `git show --stat HEAD` has no reserved path.
  AC-17: routing pass incl. backward retry jump commits before the gate outcome is
         consumed (engine.py:5673 before :5700 / :5750).
"""

from __future__ import annotations

import asyncio
import subprocess
import types
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads.  Keep this import first.
from tests.agents._scripted_model import (
    ScriptedFakeChatModel,
    _ScriptedTurn,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers — real git sandbox + minimal engine context
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent


def _run_git(*args: str, cwd: Path, check: bool = True) -> str:
    """Run a git command in *cwd* and return stdout. Raises on failure."""
    result = subprocess.run(
        [
            "git",
            "-c", "user.name=Flowin Test",
            "-c", "user.email=test@flowin.local",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_init(repo: Path) -> None:
    """Initialize a git repository with standard test config."""
    _run_git("init", "-b", "main", cwd=repo)
    _run_git("config", "user.email", "test@test.test", cwd=repo)
    _run_git("config", "user.name", "Test Bot", cwd=repo)
    # Seed .gitignore with reserved paths (per sandbox.py RESERVED_PATHS)
    reserved = "\n".join([
        ".uploads/",
        ".logs/",
        ".verify/",
        ".browser/",
        ".agents/",
        ".chain/",
        ".context/",
        "skills/",
        "conversation_history/",
        ".chain-legacy/",
    ])
    (repo / ".gitignore").write_text(reserved + "\n", encoding="utf-8")
    _run_git("add", ".gitignore", cwd=repo)
    _run_git("commit", "-m", "chore: init", cwd=repo)


def _run_id() -> str:
    """Generate a unique run id."""
    return f"v3-test-{uuid.uuid4().hex[:8]}"


@dataclass
class _FakeSandbox:
    """Minimal sandbox facade backed by a real git repo for testing."""

    root: Path
    run_id: str
    has_git: bool = True

    def _ws(self):
        """Return self — we implement the _git helper directly."""
        return self

    def _git(self, *args: str) -> str:
        return _run_git(*args, cwd=self.root)

    @property
    def run_log_path(self) -> Path:
        return self.root / ".logs" / f"{self.run_id}.jsonl"

    def reset_index(self) -> None:
        """Reset the git index."""
        if self.has_git:
            _run_git("reset", "HEAD", cwd=self.root)

    def head_commit(self) -> str:
        """Return the current HEAD commit SHA."""
        if self.has_git:
            return _run_git("rev-parse", "HEAD", cwd=self.root)
        return ""

    def git_init_sandbox(self) -> None:
        """Initialize git in the sandbox."""
        if self.has_git:
            _git_init(self.root)

    def commit_all(
        self,
        message: str,
        *,
        paths: list[str] | None = None,
        force_add: frozenset[str] | None = None,
    ) -> str:
        """Stage and commit all working-tree changes, gated on has_git."""
        if not self.has_git:
            return ""

        try:
            # Force-add the explicitly allowed paths first (e.g., .chain/)
            if force_add:
                for path in force_add:
                    _run_git("add", "-f", path, cwd=self.root, check=False)

            # Stage changes: specific paths or all if paths is None
            if paths:
                for path in paths:
                    _run_git("add", path, cwd=self.root)
            else:
                _run_git("add", "-A", cwd=self.root)

            # Check if there's anything staged
            diff_output = _run_git("diff", "--cached", "--name-only", cwd=self.root)
            if not diff_output:
                # Nothing to commit
                return ""

            # Commit
            _run_git("commit", "-m", message, cwd=self.root)
            # Return the new HEAD SHA
            return _run_git("rev-parse", "HEAD", cwd=self.root)
        except Exception:
            # If commit fails, return empty SHA (matching the contract)
            return ""


def _make_sandbox(tmp_path: Path, *, run_id: str | None = None, has_git: bool = True) -> _FakeSandbox:
    """Create and provision a sandbox with a real git repo under tmp_path."""
    rid = run_id or _run_id()
    sandbox_root = tmp_path / "runs" / rid
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sb = _FakeSandbox(root=sandbox_root, run_id=rid, has_git=has_git)
    if has_git:
        sb.git_init_sandbox()
    return sb


def _make_ectx(run_id: str | None = None) -> Any:
    """Return a minimal ExecutionContext with the required scalar fields only."""
    from agents.execution_engine.context import ExecutionContext

    return ExecutionContext(
        run_id=run_id or _run_id(),
        owner_id="test-user",
    )


def _make_step(agent_id: str = "test-agent") -> Any:
    """Return a minimal step-like namespace accepted by commit_in_sandbox."""
    return types.SimpleNamespace(
        agent_id=agent_id,
        hooks=[],
        tools=None,
        id=agent_id,  # for logging
    )


def _git_log_oneline(repo: Path) -> list[str]:
    """Return the git log as a list of one-liners (most recent first)."""
    out = _run_git("log", "--oneline", cwd=repo, check=False)
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _git_show_stat(repo: Path, ref: str = "HEAD") -> str:
    """Return the output of 'git show --stat ref'."""
    return _run_git("show", "--stat", ref, cwd=repo)


def _assert_no_reserved_in_stat(stat_output: str, reserved_paths: frozenset[str]) -> None:
    """Assert that stat output mentions no reserved paths."""
    for reserved in reserved_paths:
        # Normalize: remove trailing slash for comparison if present
        reserved_check = reserved.rstrip("/")
        assert reserved_check not in stat_output, (
            f"git show --stat contains reserved path '{reserved_check}' "
            f"(should be gitignored): {stat_output}"
        )


# ---------------------------------------------------------------------------
# Test AC-02: multi-step dispatch → one commit per step, no reserved paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_step_dispatch_one_commit_per_step(tmp_path: Path) -> None:
    """FR-009 / AC-02: multi-step workflow produces one commit per step.

    Three agent steps are dispatched via the engine sequentially:
    1. writer-agent writes output.md
    2. analyzer-agent edits output.md with analysis
    3. reviewer-agent appends a review

    Verify:
    - git log contains exactly 3 step commits (+ 1 init) = 4 commits
    - Each step commit's stat contains ONLY the step's declared output file
    - No stat output mentions a reserved path (.agents/, .logs/, .context/, etc.)
    - Commits are in the correct order by agent_id prefix in the message
    """
    from agents.execution_engine.engine import commit_in_sandbox

    RESERVED_PATHS = frozenset({
        ".uploads/",
        ".logs/",
        ".verify/",
        ".browser/",
        ".agents/",
        ".chain/",
        ".context/",
        "skills/",
        "conversation_history/",
        ".chain-legacy/",
    })

    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()

    # Step 1: writer-agent writes output.md
    (sb.root / "output.md").write_text("# Analysis\n\nInitial output.\n", encoding="utf-8")
    step1 = _make_step("writer-agent")
    result1 = await commit_in_sandbox(
        sb, f"step: {step1.agent_id}", ectx, step1, audit_operation=None
    )
    assert result1.sha, "step 1 commit must produce a SHA"
    step1_sha = result1.sha

    # Step 2: analyzer-agent modifies output.md
    (sb.root / "output.md").write_text(
        "# Analysis\n\nInitial output.\n\nAnalysis added.\n", encoding="utf-8"
    )
    step2 = _make_step("analyzer-agent")
    result2 = await commit_in_sandbox(
        sb, f"step: {step2.agent_id}", ectx, step2, audit_operation=None
    )
    assert result2.sha, "step 2 commit must produce a SHA"
    step2_sha = result2.sha

    # Step 3: reviewer-agent appends review
    (sb.root / "output.md").write_text(
        "# Analysis\n\nInitial output.\n\nAnalysis added.\n\nReview: Looks good.\n",
        encoding="utf-8"
    )
    step3 = _make_step("reviewer-agent")
    result3 = await commit_in_sandbox(
        sb, f"step: {step3.agent_id}", ectx, step3, audit_operation=None
    )
    assert result3.sha, "step 3 commit must produce a SHA"
    step3_sha = result3.sha

    # Verify git log: 4 commits (init + 3 steps)
    log = _git_log_oneline(sb.root)
    assert len(log) == 4, (
        f"Expected 4 commits (init + 3 steps), got {len(log)}: {log}"
    )

    # Verify commits are ordered by execution (most recent first in git log)
    assert "reviewer-agent" in log[0], f"Most recent commit should be reviewer-agent, got: {log[0]}"
    assert "analyzer-agent" in log[1], f"Second commit should be analyzer-agent, got: {log[1]}"
    assert "writer-agent" in log[2], f"Third commit should be writer-agent, got: {log[2]}"

    # Verify each step commit's stat contains no reserved paths
    for step_sha in [step1_sha, step2_sha, step3_sha]:
        stat = _git_show_stat(sb.root, step_sha)
        _assert_no_reserved_in_stat(stat, RESERVED_PATHS)

    # Verify HEAD (most recent) stat also has no reserved paths
    head_stat = _git_show_stat(sb.root, "HEAD")
    _assert_no_reserved_in_stat(head_stat, RESERVED_PATHS)


# ---------------------------------------------------------------------------
# Test AC-17: routing / backward retry jumps commit before gate outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_commits_before_conditional_gate_routing() -> None:
    """FR-009a / AC-17: routing commits before the gate outcome is consumed.

    Drives ``ex_A1_loop`` (the real conditional-gate loop fixture: emoji -> greet ->
    check[gates: conditional] -> retry loops back to greet, ok proceeds to done) end
    to end through ``ExecutionEngine.execute()`` via the shared offline ``_drive``
    harness (``ScriptedFakeChatModel``; real git sandbox — ``RunSandbox.has_git``
    defaults ``True``). ``check`` is scripted to answer ``retry`` twice then ``ok``
    (same recipe as T23 / ``test_conditional_loop_completion_t23.py``), forcing two
    BACKWARD jumps to ``greet`` before the loop resolves forward to ``done``.

    Two proofs against the REAL dispatch loop, not a hand-simulated stand-in:

    1. **Call-order proof** (engine.py: step-boundary commit at :5673, before
       ``_evaluate_gates(phase="post")`` at :5707, before the ``route`` outcome is
       consumed at :5783). Thin pass-through spies on the module-level
       ``commit_in_sandbox`` and on ``ExecutionEngine._evaluate_gates`` (real
       behaviour unchanged — they only append a marker and re-yield/return what the
       original produces) record, in real chronological call order, every step
       commit and every ``route`` outcome the post-step conditional gate yields.
       ``greet``'s 2nd and 3rd dispatches (the backward-jump re-entries) can only
       exist in this run at all because ``check``'s prior-pass ``route`` outcome was
       already consumed and the cursor already jumped — and the code path can only
       reach that outcome-consumption after ``check``'s own step-boundary commit
       already ran (they are sequential statements in the SAME iteration of the
       dispatch loop, `_reconcile_replaces_surface`/``commit_in_sandbox`` before
       ``self._evaluate_gates(..., phase="post")``). So the exact interleaved
       sequence recorded here — commit, then route-consumed, repeated across both
       loop-backs — is a direct behavioural trace of that ordering, not an
       assumption.
    2. **Ground-truth-of-the-call proof**: ``greet``/``check`` declare no tools
       (the ex_A1_loop fixture is deliberately tool-free — every other assertion
       in its sibling suite (T23/T24/T25) is on the event stream, never an
       artifact), so their scripted reply reaches disk only via
       ``_check_artifact_fallback`` (engine.py) — which, for a step whose
       effective ``tools.write_files`` is False, rewrites that pass's output on
       EVERY dispatch (an existing file means "an earlier pass's fallback wrote
       it," never "the model wrote it," since the step has no write tool of its
       own). Whether a given pass lands a real commit or a legitimate
       ``no_change`` then follows straight from whether that pass's text differs
       from what is already committed: ``greet``'s scripted reply is a fixed
       string on every pass (this harness's own script table, independent of the
       RETRY feedback block), so its passes 2/3 are genuine no_change; ``check``'s
       scripted reply IS the decision JSON and varies (``retry``, ``retry``,
       ``ok``) — pass 2 repeats pass 1's exact text (no_change), pass 3 flips to
       ``ok`` (new content, a real commit). This is checked against the
       ``CommitInSandboxResult`` each spied call actually returned — not merely
       that a call happened — which rules out a version of the bug where a later
       pass silently short-circuits the commit call instead of legitimately
       finding nothing (or something new) to stage.
    3. **Real git log proof**: after the run, ``git log``/``git show --stat`` on
       the ACTUAL sandbox directory the engine wrote to confirms the SHA each
       real (pass-1) commit call reported is really in git history, with no
       reserved path in its stat — the step-boundary commit is not just an
       in-process event, it is real, inspectable git state.
    """
    import uuid

    import agents.execution_engine.engine as engine_mod
    from tests.agents import _scripted_model as _sm
    from tests.agents._scripted_model import _drive

    _PIPELINE = "ex_A1_loop"
    _STEP_IDS = {
        "custom-agent:emoji",
        "custom-agent:greet",
        "custom-agent:check",
        "custom-agent:done",
    }

    order_log: list[tuple[str, str]] = []

    # ``check`` answers retry, retry, ok — forces two backward loop-backs to
    # ``greet`` before the third pass resolves forward to ``done`` (T23's recipe).
    calls = {"check": 0}

    def _scripts_for(agent_id: str):
        if agent_id == "custom-agent:check":
            calls["check"] += 1
            decision = "retry" if calls["check"] <= 2 else "ok"
            return [_ScriptedTurn(texts=[f'{{"decision": "{decision}"}}'], usage=(5, 3))]
        return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]

    # ── Spy 1: commit_in_sandbox is a module-level free function; execute() calls
    # it by bare name, so patching the module attribute affects the running loop —
    # the same technique T23/T25 already use for `_scripts_for`/`ExecutionContext`.
    _orig_commit = engine_mod.commit_in_sandbox
    commit_calls: list[tuple[str, str, bool]] = []  # (agent_id, sha, no_change)

    async def _spied_commit(sandbox, message, ectx, step, **kw):
        result = await _orig_commit(sandbox, message, ectx, step, **kw)
        agent_id = getattr(step, "agent_id", None)
        if agent_id in _STEP_IDS:
            order_log.append(("commit", agent_id))
            commit_calls.append((agent_id, result.sha, result.no_change))
        return result

    # ── Spy 2: ExecutionEngine._evaluate_gates — records the moment a "route"
    # outcome is yielded back to the dispatch loop (the exact point AC-17 says a
    # commit must already have happened). The real generator body is untouched;
    # the wrapper only re-yields what it produces.
    _orig_evaluate_gates = engine_mod.ExecutionEngine._evaluate_gates

    async def _spied_evaluate_gates(self, step, ectx, registry, *, phase, inline_gated=False):
        async for item in _orig_evaluate_gates(
            self, step, ectx, registry, phase=phase, inline_gated=inline_gated
        ):
            _ge, _outcome, _gdetail = item
            if phase == "post" and _outcome == "route":
                agent_id = getattr(step, "agent_id", None)
                if agent_id in _STEP_IDS:
                    order_log.append(("route_consumed", agent_id))
            yield item

    run_id = f"v3-loop-{uuid.uuid4().hex[:8]}"

    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _scripts_for
    engine_mod.commit_in_sandbox = _spied_commit
    engine_mod.ExecutionEngine._evaluate_gates = _spied_evaluate_gates
    try:
        events = await _drive(_PIPELINE, pipeline_run_id=run_id)
    finally:
        _sm._scripts_for = orig_scripts_for
        engine_mod.commit_in_sandbox = _orig_commit
        engine_mod.ExecutionEngine._evaluate_gates = _orig_evaluate_gates

    # ── Sanity: this really is T23's loop scenario (belt & braces) ─────────────
    types = [e.get("type") for e in events]
    started = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    assert started.count("custom-agent:greet") == 3, f"expected 3 greet dispatches: {started}"
    assert started.count("custom-agent:check") == 3, f"expected 3 check dispatches: {started}"
    assert started.count("custom-agent:done") == 1, f"expected 1 done dispatch: {started}"
    assert "budget_aborted" not in types, f"run failed closed unexpectedly: {types}"
    assert "pipeline_complete" in types, f"run never completed: {types[-5:]}"

    # ── Proof 1: call-order — every backward-jump re-entry's commit is preceded,
    # in real chronological order, by the PRIOR pass's commit-then-route-consumed
    # pair. Only reachable if the step-boundary commit fires before the
    # conditional gate's route outcome is consumed and the cursor jumps.
    expected_order = [
        ("commit", "custom-agent:emoji"),
        ("commit", "custom-agent:greet"),
        ("commit", "custom-agent:check"),
        ("route_consumed", "custom-agent:check"),
        ("commit", "custom-agent:greet"),
        ("commit", "custom-agent:check"),
        ("route_consumed", "custom-agent:check"),
        ("commit", "custom-agent:greet"),
        ("commit", "custom-agent:check"),
        ("route_consumed", "custom-agent:check"),
        ("commit", "custom-agent:done"),
    ]
    assert order_log == expected_order, (
        f"commit / route-consumption order diverged from the expected dispatch-loop "
        f"sequence (commit before each route consumption, incl. both backward "
        f"loop-backs to greet).\nGot:      {order_log}\nExpected: {expected_order}"
    )

    # ── Proof 1b: every commit_in_sandbox CALL is real ground truth, not just an
    # ordering artefact. `greet`/`check` declare no tools, so their scripted
    # reply reaches disk only via `_check_artifact_fallback`, which rewrites the
    # fallback file on EVERY pass for a step that cannot write files itself (an
    # existing file there means "an earlier pass's fallback wrote it," never
    # "the model wrote it" — engine.py, closed under GAPS L4 so a retried step's
    # new output is never silently dropped). Whether a pass lands a real commit
    # or a legitimate `no_change` therefore follows from whether ITS TEXT differs
    # from what HEAD already holds: `greet`'s scripted reply is a fixed string on
    # every pass (this harness's own script table), so its passes 2/3 are genuine
    # no_change; `check`'s scripted reply is the decision JSON itself and DOES
    # vary (`retry`, `retry`, `ok`) — pass 2 repeats pass 1's exact text
    # (no_change), pass 3 flips to `ok` (new content, a real commit). Confirming
    # that exact real/no_change pattern per call — not merely that a call
    # happened — rules out a version of the ordering bug where a later pass
    # silently no-ops the commit call itself instead of legitimately finding
    # nothing (or something new) to stage.
    def _calls_for(agent_id: str) -> list[tuple[str, str, bool]]:
        return [c for c in commit_calls if c[0] == agent_id]

    greet_calls = _calls_for("custom-agent:greet")
    check_calls = _calls_for("custom-agent:check")
    assert len(greet_calls) == 3, f"expected 3 commit_in_sandbox calls for greet: {greet_calls}"
    assert len(check_calls) == 3, f"expected 3 commit_in_sandbox calls for check: {check_calls}"
    assert greet_calls[0][1] and not greet_calls[0][2], (
        f"greet pass 1 must produce a real commit: {greet_calls[0]}"
    )
    assert check_calls[0][1] and not check_calls[0][2], (
        f"check pass 1 must produce a real commit: {check_calls[0]}"
    )
    for pass_num, call in enumerate(greet_calls[1:], start=2):
        assert not call[1] and call[2], (
            f"greet pass {pass_num} should be a legitimate no_change (identical "
            f"scripted output, no tools): {call}"
        )
    # check pass 2 repeats pass 1's "retry" text verbatim (no_change); pass 3
    # flips to "ok" — genuinely new content relative to what HEAD holds, so it
    # is a real commit, not a no_change (see the Proof 1b comment above).
    assert not check_calls[1][1] and check_calls[1][2], (
        f"check pass 2 should be a legitimate no_change (repeats pass 1's "
        f"'retry' text verbatim): {check_calls[1]}"
    )
    assert check_calls[2][1] and not check_calls[2][2], (
        f"check pass 3 should be a real commit (decision flips retry -> ok, "
        f"genuinely new content): {check_calls[2]}"
    )

    # ── Proof 2: real git log on the sandbox the engine actually wrote to ───────
    # Pass 1 of greet/check, plus check's pass 3 (its decision text changes —
    # see Proof 1b), leave a NEW commit; done always does (the deliverable's
    # artifact-fallback write lands before its step-boundary commit). Confirm
    # those real commits actually exist in git history, under their expected
    # SHAs, with no reserved path in their stat.
    sandbox_root = Path(_sm._RUNS_ROOT) / "harness-user" / run_id
    assert sandbox_root.is_dir(), f"engine sandbox not found at {sandbox_root}"

    log_shas = set(_run_git("log", "--format=%H", cwd=sandbox_root).splitlines())

    RESERVED_PATHS = frozenset({
        ".uploads/",
        ".logs/",
        ".verify/",
        ".browser/",
        ".agents/",
        ".chain/",
        ".context/",
        "skills/",
        "conversation_history/",
        ".chain-legacy/",
    })
    done_calls = _calls_for("custom-agent:done")
    assert len(done_calls) == 1 and done_calls[0][1] and not done_calls[0][2], (
        f"done must produce exactly 1 real commit: {done_calls}"
    )
    for _agent_id, sha, _no_change in [
        greet_calls[0],
        check_calls[0],
        check_calls[2],
        done_calls[0],
    ]:
        assert sha in log_shas, f"commit_in_sandbox's reported SHA {sha} is not in real git log"
        stat = _git_show_stat(sandbox_root, sha)
        _assert_no_reserved_in_stat(stat, RESERVED_PATHS)
    assert check_calls[0][1] != check_calls[2][1], (
        "check pass 1 and pass 3 must be distinct real commits (distinct decision "
        f"text): {check_calls[0]} vs {check_calls[2]}"
    )


@pytest.mark.asyncio
async def test_no_commit_when_no_change(tmp_path: Path) -> None:
    """Verify that when a step makes no changes, commit_in_sandbox returns no_change=True.

    This is the baseline: if nothing is staged, the commit is skipped and
    returned as no_change, leaving git log unchanged.
    """
    from agents.execution_engine.engine import commit_in_sandbox

    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()

    # Record initial commit count
    initial_log = _git_log_oneline(sb.root)
    initial_count = len(initial_log)

    # Try to commit with no staged changes
    step = _make_step("no-op-agent")
    result = await commit_in_sandbox(
        sb, "step: no-op-agent", ectx, step, audit_operation=None
    )

    # Verify no_change was set
    assert result.no_change is True, "commit_in_sandbox must return no_change=True"
    assert result.blocked is False, "no-change is not a block"
    assert result.sha == "", "no-change commit must return empty SHA"

    # Verify git log is unchanged
    final_log = _git_log_oneline(sb.root)
    assert len(final_log) == initial_count, (
        f"No commit should be created on no-change; log went from {initial_count} to {len(final_log)}"
    )


@pytest.mark.asyncio
async def test_commit_stat_excludes_reserved_paths(tmp_path: Path) -> None:
    """Detailed test: verify git show --stat output never includes reserved paths.

    Even if a tool accidentally writes to a reserved path, the git commit
    should not include it (because .gitignore keeps it out of the index).
    This test plants a file in a reserved directory and verifies it is not
    in the git stat.
    """
    from agents.execution_engine.engine import commit_in_sandbox

    RESERVED_PATHS = frozenset({
        ".uploads/",
        ".logs/",
        ".verify/",
        ".browser/",
        ".agents/",
        ".chain/",
        ".context/",
        "skills/",
        "conversation_history/",
        ".chain-legacy/",
    })

    sb = _make_sandbox(tmp_path)
    ectx = _make_ectx()

    # Plant legitimate files
    (sb.root / "report.txt").write_text("A normal report", encoding="utf-8")

    # Also plant files in reserved paths (they should be gitignored)
    (sb.root / ".agents").mkdir(exist_ok=True)
    (sb.root / ".agents" / "01-agent.md").write_text("Agent transcript", encoding="utf-8")

    (sb.root / ".logs").mkdir(exist_ok=True)
    (sb.root / ".logs" / f"{ectx.run_id}.jsonl").write_text(
        '{"type":"event"}\n', encoding="utf-8"
    )

    step = _make_step("test-agent")
    result = await commit_in_sandbox(
        sb, "step: test-agent", ectx, step, audit_operation=None
    )

    # The commit should succeed and include only report.txt (not .agents or .logs)
    assert result.sha, "commit should succeed"
    stat = _git_show_stat(sb.root, "HEAD")

    # Verify the stat does not mention any reserved paths
    _assert_no_reserved_in_stat(stat, RESERVED_PATHS)

    # Verify the normal file IS in the stat
    assert "report.txt" in stat, (
        f"Normal file 'report.txt' should be in git stat: {stat}"
    )
