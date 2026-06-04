"""Phase 7c — FROZEN characterization of the /flowin-handoff pipeline event contract.

This is the **contract-locking regression net** for the handoff-subsystem migration
(specs/002-deepagents-migration/plan.md §5 "Phase 7c", task 7c-1). It freezes the WS
event contract + the persisted ``pipeline_output`` shape of
``app.services.handoff_pipeline.run_handoff_pipeline`` **before** the four handoff agents
are migrated off ``BaseAgent`` (sibling task 7c-2), so 7c-4 can prove the migration is
contract-faithful by re-running these exact assertions.

────────────────────────────────────────────────────────────────────────────────────
WHY THE PIPELINE OWNS THE ENTIRE CONTRACT
────────────────────────────────────────────────────────────────────────────────────
``run_handoff_pipeline`` is a hand-written async generator that yields WS-shaped event
dicts ``{"type", "chunk", "section", "data"}`` (the ``_event(...)`` envelope). The
WebSocket handler (``app.api.websocket_handoff.dispatch_event``) and the REST background
task (``app.api.handoff._run_pipeline_background``) forward those dicts **verbatim** to
the browser — so the PIPELINE, not any agent or transport, owns the event vocabulary,
the per-``section`` values, the ``agent_complete`` report shapes, AND the terminal
``pipeline_complete.data`` payload that becomes ``HandoffSession.pipeline_output``
(the frontend refresh-hydration path reads ``resolved_mode`` / ``branch_name`` /
``pr_url`` / ``pr_number`` straight off that row — see ``app/api/handoff.py:399-402``).

The handoff agents (``classify_task`` / ``CodingAgent`` / ``TestAgent`` /
``ComplianceAgent``) are the ONLY non-deterministic, network/LLM-touching pieces; the
git side-effects all live in ``handoff_github``. 7c-2 changes ONLY the agents' internal
LLM-call mechanism (``BaseAgent`` → ``build_model().ainvoke``); the pipeline and
``handoff_github`` are untouched. So with the agents + ``handoff_github`` mocked, the
pipeline is fully deterministic and its contract is frozen here.

────────────────────────────────────────────────────────────────────────────────────
THE MOCK SEAM (determinism — no network / no git / no LLM)
────────────────────────────────────────────────────────────────────────────────────
The pipeline binds the agent symbols at import time
(``from app.agents.handoff import CodingAgent, ComplianceAgent, TestAgent, classify_task``)
and the git helpers as a module (``from app.services import handoff_github as gh``). We
therefore patch:

  * ``app.services.handoff_pipeline.{CodingAgent,TestAgent,ComplianceAgent,classify_task}``
    → scripted fakes returning FIXED dicts (the same JSON-plan shapes the real agents'
    ``setdefault`` contracts guarantee). This patches the names AS BOUND IN THE PIPELINE,
    so it is **agnostic to how the agents construct their model** — it locks identically
    against today's ``BaseAgent`` agents and against 7c-2's ``build_model`` agents (this is
    exactly what makes 7c-4's re-run valid).
  * ``app.services.handoff_github.{clone,get_repo_metadata,checkout_new_branch,stage_all,
    commit,push,wipe_credentialed_remote,create_pull_request,cleanup_workspace}`` → fakes:
    ``clone`` populates a temp workspace with a couple of files; the git mutators return a
    success ``GitResult``; ``create_pull_request`` returns ``{url,number}``;
    ``get_repo_metadata`` returns ``{"default_branch":"main"}``; ``cleanup_workspace``
    really ``rmtree``s the temp root (faithful to the production cleanup, so nothing leaks).

The pipeline still calls ``tempfile.mkdtemp`` for real and ``_walk_repo`` /
``_apply_edits`` operate on the real workspace ``clone`` created — that is the pipeline's
genuine behaviour and is what makes ``edit_results`` / the diff preview real (not stubbed).
The only filesystem touched is a self-contained temp dir that the faked ``cleanup_workspace``
deletes in the generator's ``finally``.

────────────────────────────────────────────────────────────────────────────────────
NON-DETERMINISM, NORMALISED OUT
────────────────────────────────────────────────────────────────────────────────────
Two values are inherently non-deterministic and are projected to sentinels by
``_normalise`` before comparison (the rest of the contract is frozen byte-for-byte):
  * the ``phase_end section="clone"`` ``data["workspace"]`` (the real temp path), and
  * ``pipeline_output``'s ``started_at`` / ``completed_at`` ISO timestamps.
``branch_name`` is deterministic (derived from ``handoff_id`` + a slug of the task) and is
asserted verbatim.

────────────────────────────────────────────────────────────────────────────────────
THE FACTORY SEAM (how 7c-4 re-runs this golden post-migration)
────────────────────────────────────────────────────────────────────────────────────
``_build_pipeline(...)`` is the migration seam, mirroring ``test_chat_contract.py``'s
``FACTORY``. It returns a zero-arg callable that, when awaited via ``collect_events``,
drives the REAL ``run_handoff_pipeline`` under the mock seam above. 7c-4 re-runs THIS FILE
unchanged: the pipeline is identical and the agents are mocked at the pipeline boundary, so
the migrated (``build_model``) agents never run — the frozen golden must still pass, proving
the migration preserved the contract.
"""

from __future__ import annotations

import contextlib
import inspect
import os
import shutil
from typing import Any, Callable
from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic scripted agent outputs (the "scripted LLM").
#
# These are fixed JSON-plan dicts shaped exactly like the real agents return after
# their ``setdefault`` normalisation (coding_agent.py:153-159, test_agent.py:139-144,
# compliance_agent.py:155-158). They are deliberately small so the pipeline's
# 16 KiB-per-side edit-preview trim is a no-op (preview == original), keeping the
# ``agent_complete`` / ``coding_summary`` literals exact.
# ─────────────────────────────────────────────────────────────────────────────

# A modify edit whose ``old_string`` matches FILES_ON_CLONE["app/main.py"] EXACTLY ONCE,
# so ``_apply_edits`` returns status="applied" (drives the commit/push/PR branch).
_EDIT = {
    "path": "app/main.py",
    "operation": "modify",
    "old_string": "def add(a, b):\n    return a + b\n",
    "new_string": "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
}

CODING_PLAN: dict[str, Any] = {
    "summary": "Add subtract function",
    "rationale": "Implements subtraction as requested.",
    "edits": [dict(_EDIT)],
    "tests_added": ["app/test_main.py"],
    "follow_ups": [],
}

TEST_REPORT: dict[str, Any] = {
    "summary": "Tests cover happy path.",
    "verdict": "concerns",
    "tests_present": [{"path": "app/test_main.py", "covers": "add"}],
    "missing_coverage": [{"area": "subtract", "suggested_test": "test_subtract"}],
    "quality_issues": [],
    "recommended_additions": ["add a subtract test"],
}

COMPLIANCE_REPORT: dict[str, Any] = {
    "summary": "No security issues.",
    "verdict": "approve_with_changes",
    "findings": [
        {
            "category": "best_practices",
            "severity": "low",
            "location": "app/main.py",
            "issue": "x",
            "recommendation": "y",
        }
    ],
    "positives": ["clean diff"],
}

# The trimmed edit-preview the pipeline ships to the FE / persists in pipeline_output.
# For our small edit this equals the original edit (the trim is a no-op), so we reuse it.
_PREVIEW_EDIT = dict(_EDIT)

# Files the fake ``clone`` writes into the workspace. ``_apply_edits`` rewrites main.py;
# ``_select_test_files`` picks test_main.py; the README is always pulled in by
# ``_select_relevant_files``. These are the inputs that make ``edit_results`` real.
FILES_ON_CLONE: dict[str, str] = {
    "README.md": "# Demo\nA demo repo.\n",
    "app/main.py": "def add(a, b):\n    return a + b\n",
    "app/test_main.py": "def test_add():\n    assert True\n",
}

# Stable pipeline inputs (chosen so the derived branch slug is deterministic + readable).
HANDOFF_ID = "abc12345-1111-2222-3333-444455556666"
HANDOFF_TOKEN = "tok"
TASK = "Add a subtract function"
REPO_URL = "https://github.com/acme/widgets"
ISSUER_EMAIL = "dev@example.com"
HANDOFF_PUBLIC_URL = "https://flowin.example/handoff/tok"

# Deterministic derived values (frozen — NOT normalised).
BRANCH_NAME = "flowin-handoff/abc12345-add-a-subtract-function"
PR_URL = "https://github.com/acme/widgets/pull/42"
PR_NUMBER = 42
DEFAULT_BRANCH = "main"

# Sentinels for the two non-deterministic fields (see module docstring).
_WORKSPACE_SENTINEL = "<WORKSPACE>"
_TS_SENTINEL = "<TIMESTAMP>"


# ─────────────────────────────────────────────────────────────────────────────
# Fakes for handoff_github. The pipeline calls clone/checkout/stage/commit/push via
# ``asyncio.to_thread`` (so they must be plain sync callables) and
# get_repo_metadata/create_pull_request directly with ``await`` (so they must be async).
# parse_github_url is NOT patched — the real parser runs (deterministic, no I/O).
# ─────────────────────────────────────────────────────────────────────────────


class _FakeGitResult:
    """Stand-in for ``handoff_github.GitResult`` (returncode/stdout/stderr)."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_clone(target, pat, dest_dir, branch=None) -> _FakeGitResult:
    """Materialise a deterministic workspace under ``dest_dir/workspace``.

    Mirrors the real ``clone`` contract: it creates the ``workspace`` subdir the
    pipeline then walks/edits. No network, no git.
    """
    workspace = os.path.join(dest_dir, "workspace")
    for rel, content in FILES_ON_CLONE.items():
        full = os.path.join(workspace, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
    return _FakeGitResult(0)


async def _fake_get_repo_metadata(target, pat) -> dict[str, str]:
    return {"default_branch": DEFAULT_BRANCH}


async def _fake_create_pull_request(**kwargs) -> dict[str, object]:
    return {"url": PR_URL, "number": PR_NUMBER}


def _fake_cleanup_workspace(workspace_root: str) -> None:
    # Faithful to production cleanup_workspace: really delete the temp tree so the
    # only real-FS touch (the mkdtemp root) never leaks.
    shutil.rmtree(workspace_root, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# Scripted agent fakes. Each instance method returns a FRESH copy of the fixed dict
# (so the pipeline's in-place mutations — e.g. trimming — never corrupt the golden).
# ─────────────────────────────────────────────────────────────────────────────


class _FakeCodingAgent:
    """Drop-in for ``CodingAgent`` — instantiated no-arg, exposes ``propose_edits``."""

    def __init__(self, *, raises: BaseException | None = None) -> None:
        self._raises = raises

    async def propose_edits(self, **kwargs) -> dict[str, Any]:
        if self._raises is not None:
            raise self._raises
        return _deepish_copy(CODING_PLAN)


class _FakeTestAgent:
    def __init__(self, *, raises: BaseException | None = None) -> None:
        self._raises = raises

    async def analyse(self, **kwargs) -> dict[str, Any]:
        if self._raises is not None:
            raise self._raises
        return _deepish_copy(TEST_REPORT)


class _FakeComplianceAgent:
    def __init__(self, *, raises: BaseException | None = None) -> None:
        self._raises = raises

    async def review(self, **kwargs) -> dict[str, Any]:
        if self._raises is not None:
            raise self._raises
        return _deepish_copy(COMPLIANCE_REPORT)


def _deepish_copy(obj: Any) -> Any:
    """Cheap deep copy for our JSON-ish fixtures (dict/list/scalars only)."""
    if isinstance(obj, dict):
        return {k: _deepish_copy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deepish_copy(v) for v in obj]
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# THE PIPELINE FACTORY — the migration seam (mirrors test_chat_contract.py's FACTORY).
#
# Returns a zero-arg awaitable-returning callable that drives the REAL
# ``run_handoff_pipeline`` under the full mock seam. ``failing_agent`` injects an
# exception into one agent to drive the error path. Imports are LAZY (function-local)
# so this module stays free of any module-level ``handoff_pipeline`` / ``BaseAgent``
# token — keeping the widened ``test_no_baseagent.py`` (7c-3) green when it scans this
# tree, and keeping the golden literals a pure-data island.
# ─────────────────────────────────────────────────────────────────────────────


def _build_pipeline(
    *,
    requested_mode: str,
    classify_returns: str = "coding",
    failing_agent: str | None = None,
    failure_exc: BaseException | None = None,
) -> Callable[[], Any]:
    """Build a zero-arg callable returning the patched ``run_handoff_pipeline`` generator.

    ``classify_returns`` is what the mocked ``classify_task`` resolves to (only consulted
    when ``requested_mode == "auto"``). ``failing_agent`` is one of
    ``"coding_agent"`` / ``"test_agent"`` / ``"compliance_agent"``; its agent raises
    ``failure_exc`` to exercise the ``agent_error`` + re-raise path.
    """

    def _factory():
        # Lazy imports — see the function docstring (no module-level pipeline/legacy token).
        from app.services import handoff_github as gh
        from app.services import handoff_pipeline as hp

        coding_raises = failure_exc if failing_agent == "coding_agent" else None
        test_raises = failure_exc if failing_agent == "test_agent" else None
        comp_raises = failure_exc if failing_agent == "compliance_agent" else None

        async def _fake_classify(task_description, transcript_excerpt=None) -> str:
            return classify_returns

        stack = contextlib.ExitStack()
        # handoff_github fakes (patch on the real module; the pipeline calls gh.<fn>).
        stack.enter_context(patch.object(gh, "clone", _fake_clone))
        stack.enter_context(patch.object(gh, "get_repo_metadata", _fake_get_repo_metadata))
        stack.enter_context(patch.object(gh, "create_pull_request", _fake_create_pull_request))
        stack.enter_context(patch.object(gh, "checkout_new_branch", lambda ws, b: _FakeGitResult(0)))
        stack.enter_context(patch.object(gh, "stage_all", lambda ws: _FakeGitResult(0)))
        stack.enter_context(patch.object(gh, "commit", lambda ws, m: _FakeGitResult(0)))
        stack.enter_context(patch.object(gh, "push", lambda t, p, ws, b: _FakeGitResult(0)))
        stack.enter_context(patch.object(gh, "wipe_credentialed_remote", lambda ws: None))
        stack.enter_context(patch.object(gh, "cleanup_workspace", _fake_cleanup_workspace))
        # Agent fakes (patch the symbols AS BOUND IN THE PIPELINE — migration-agnostic).
        stack.enter_context(
            patch.object(hp, "CodingAgent", lambda: _FakeCodingAgent(raises=coding_raises))
        )
        stack.enter_context(
            patch.object(hp, "TestAgent", lambda: _FakeTestAgent(raises=test_raises))
        )
        stack.enter_context(
            patch.object(hp, "ComplianceAgent", lambda: _FakeComplianceAgent(raises=comp_raises))
        )
        stack.enter_context(patch.object(hp, "classify_task", _fake_classify))

        generator = hp.run_handoff_pipeline(
            handoff_id=HANDOFF_ID,
            handoff_token=HANDOFF_TOKEN,
            task_description=TASK,
            transcript_excerpt=None,
            repo_url=REPO_URL,
            requested_mode=requested_mode,
            source_branch=None,
            pat="github_pat_fake_value",
            issuer_email=ISSUER_EMAIL,
            handoff_public_url=HANDOFF_PUBLIC_URL,
        )
        # Bind the ExitStack to the generator so patches stay live for its whole life
        # and are torn down when ``collect_events`` closes it (finally → aclose).
        return _PatchedGenerator(generator, stack)

    return _factory


class _PatchedGenerator:
    """Wrap the pipeline generator + its patch ExitStack as one async iterator.

    Keeps the unittest.mock patches active for the generator's entire lifetime and
    cleans them up (plus the temp workspace, via the faked cleanup in the pipeline's
    own ``finally``) when iteration completes or the consumer aborts.
    """

    def __init__(self, generator, stack: contextlib.ExitStack) -> None:
        self._gen = generator
        self._stack = stack

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self._gen.__anext__()
        except StopAsyncIteration:
            self._stack.close()
            raise
        except BaseException:
            # Pipeline re-raised (error path): drain its ``finally`` then drop patches.
            with contextlib.suppress(Exception):
                await self._gen.aclose()
            self._stack.close()
            raise

    async def aclose(self):
        with contextlib.suppress(Exception):
            await self._gen.aclose()
        self._stack.close()


async def collect_events(pipeline_factory: Callable[[], Any]) -> list[dict]:
    """Drive a pipeline factory's generator and return the full ordered event list.

    Provider-agnostic: ``pipeline_factory()`` drives the REAL ``run_handoff_pipeline``
    today (``BaseAgent`` agents, mocked) and after 7c-2 (``build_model`` agents, mocked) —
    the same frozen golden proves byte-fidelity. Returns the raw WS payloads
    (``{type, chunk, section, data}``) in emission order.
    """
    gen = pipeline_factory()
    events: list[dict] = []
    async for event in gen:
        events.append(event)
    return events


async def collect_events_expecting_raise(
    pipeline_factory: Callable[[], Any],
) -> tuple[list[dict], BaseException]:
    """Drive a factory whose pipeline RE-RAISES (error path); capture events + the exc.

    The handoff pipeline yields an ``agent_error`` / ``handoff_error`` event and then
    re-raises so the caller (``_run_pipeline_background``) marks the session FAILED. This
    helper returns the events emitted before the raise plus the propagated exception.
    """
    gen = pipeline_factory()
    events: list[dict] = []
    raised: BaseException | None = None
    try:
        async for event in gen:
            events.append(event)
    except BaseException as exc:  # noqa: BLE001 — characterizing the re-raise is the point
        raised = exc
    assert raised is not None, "expected the pipeline to re-raise on the error path"
    return events, raised


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation: reduce a raw event to the FROZEN-ASSERTED shape.
#
# We assert the full (type, section, data) of every event. ``chunk`` is ALWAYS None for
# this pipeline (no token streaming — agents are one-shot), asserted separately by
# ``test_chunk_is_always_none``. The two non-deterministic values (clone workspace path,
# pipeline_output timestamps) are projected to sentinels here.
# ─────────────────────────────────────────────────────────────────────────────


def _normalise(event: dict) -> dict:
    """Project a raw WS event onto the frozen-comparable shape (sentinels for non-determinism)."""
    data = event.get("data")
    norm_data: Any = data
    if isinstance(data, dict):
        norm_data = dict(data)
        # clone phase_end carries the real temp workspace path.
        if event["type"] == "phase_end" and event["section"] == "clone" and "workspace" in norm_data:
            norm_data["workspace"] = _WORKSPACE_SENTINEL
        # pipeline_complete carries the started_at/completed_at ISO timestamps.
        if event["type"] == "pipeline_complete":
            if "started_at" in norm_data:
                norm_data["started_at"] = _TS_SENTINEL
            if "completed_at" in norm_data:
                norm_data["completed_at"] = _TS_SENTINEL
    return {"type": event["type"], "section": event["section"], "data": norm_data}


def _normalise_all(events: list[dict]) -> list[dict]:
    return [_normalise(e) for e in events]


# ═════════════════════════════════════════════════════════════════════════════
# THE FROZEN GOLDEN — single source of truth (pure literals, zero pipeline imports).
#
# Captured from the REAL ``run_handoff_pipeline`` under the mock seam (verified by the
# tests below). Each entry is the normalised event. Any drift — by the pipeline now, or
# by 7c-4's re-run against the migrated agents — fails the assertion.
# ═════════════════════════════════════════════════════════════════════════════

# ── Shared opening: setup → clone ────────────────────────────────────────────
def _setup_clone_block() -> list[dict]:
    return [
        {
            "type": "phase_start",
            "section": "setup",
            "data": {"task": TASK, "repo": "acme/widgets"},
        },
        {
            "type": "phase_end",
            "section": "setup",
            "data": {"default_branch": DEFAULT_BRANCH, "base_branch": DEFAULT_BRANCH},
        },
        {"type": "phase_start", "section": "clone", "data": {"branch": DEFAULT_BRANCH}},
        {"type": "phase_end", "section": "clone", "data": {"workspace": _WORKSPACE_SENTINEL}},
    ]


# ── Shared coding block (mode="coding"): thinking → complete → apply_edits ────
def _coding_block() -> list[dict]:
    return [
        {
            "type": "agent_thinking",
            "section": None,
            "data": {
                "agent_id": "coding_agent",
                "thinking": "Reading relevant files and planning the change...",
            },
        },
        {
            "type": "agent_complete",
            "section": None,
            "data": {
                "agent_id": "coding_agent",
                "summary": "Add subtract function",
                "rationale": "Implements subtraction as requested.",
                "edit_count": 1,
                "edits": [dict(_PREVIEW_EDIT)],
                "tests_added": ["app/test_main.py"],
                "follow_ups": [],
            },
        },
        {
            "type": "phase_end",
            "section": "apply_edits",
            "data": {
                "results": [{"path": "app/main.py", "operation": "modify", "status": "applied"}]
            },
        },
    ]


# ── Shared test + compliance block (both modes) ──────────────────────────────
def _test_and_compliance_block() -> list[dict]:
    return [
        {
            "type": "agent_thinking",
            "section": None,
            "data": {"agent_id": "test_agent", "thinking": "Analysing test coverage..."},
        },
        {
            "type": "agent_complete",
            "section": None,
            "data": {"agent_id": "test_agent", "report": _deepish_copy(TEST_REPORT)},
        },
        {
            "type": "agent_thinking",
            "section": None,
            "data": {
                "agent_id": "compliance_agent",
                "thinking": "Reviewing for security and best practices...",
            },
        },
        {
            "type": "agent_complete",
            "section": None,
            "data": {"agent_id": "compliance_agent", "report": _deepish_copy(COMPLIANCE_REPORT)},
        },
    ]


# ── Shared commit → push → open_pr → pr_created block (mode="coding") ─────────
def _commit_push_pr_block() -> list[dict]:
    return [
        {"type": "phase_start", "section": "commit", "data": {"branch": BRANCH_NAME}},
        {
            "type": "phase_end",
            "section": "commit",
            "data": {"committed": True, "message": "Add subtract function"},
        },
        {"type": "phase_start", "section": "push", "data": {"branch": BRANCH_NAME}},
        {"type": "phase_end", "section": "push", "data": {"pushed": True, "branch": BRANCH_NAME}},
        {
            "type": "phase_start",
            "section": "open_pr",
            "data": {"head": BRANCH_NAME, "base": DEFAULT_BRANCH},
        },
        {"type": "pr_created", "section": None, "data": {"url": PR_URL, "number": PR_NUMBER}},
    ]


# ── The frozen pipeline_output for mode="coding" (full path incl. PR) ─────────
# This is the EXACT dict persisted to HandoffSession.pipeline_output; the FE refresh-
# hydration path reads resolved_mode / branch_name / pr_url / pr_number off it.
GOLDEN_PIPELINE_OUTPUT_CODING: dict[str, Any] = {
    "handoff_id": HANDOFF_ID,
    "started_at": _TS_SENTINEL,
    "branch_name": BRANCH_NAME,
    "edit_results": [{"path": "app/main.py", "operation": "modify", "status": "applied"}],
    "base_branch": DEFAULT_BRANCH,
    "default_branch": DEFAULT_BRANCH,
    "resolved_mode": "coding",
    "coding_summary": {
        "summary": "Add subtract function",
        "rationale": "Implements subtraction as requested.",
        "edits": [dict(_PREVIEW_EDIT)],
        "edit_count": 1,
        "tests_added": ["app/test_main.py"],
        "follow_ups": [],
    },
    "test_report": _deepish_copy(TEST_REPORT),
    "compliance_report": _deepish_copy(COMPLIANCE_REPORT),
    "pr_url": PR_URL,
    "pr_number": PR_NUMBER,
    "completed_at": _TS_SENTINEL,
}

# ── The frozen pipeline_output for mode="test" (no coding / commit / push / PR) ──
# Note: NO coding_summary / pr_url / pr_number keys (the coding + PR branches never run);
# edit_results stays the empty list it was initialised with.
GOLDEN_PIPELINE_OUTPUT_TEST: dict[str, Any] = {
    "handoff_id": HANDOFF_ID,
    "started_at": _TS_SENTINEL,
    "branch_name": BRANCH_NAME,
    "edit_results": [],
    "base_branch": DEFAULT_BRANCH,
    "default_branch": DEFAULT_BRANCH,
    "resolved_mode": "test",
    "test_report": _deepish_copy(TEST_REPORT),
    "compliance_report": _deepish_copy(COMPLIANCE_REPORT),
    "completed_at": _TS_SENTINEL,
}


# ── Scenario (a): mode="coding" — full path (setup→clone→code→test→compliance→
#    commit→push→open_pr→pr_created→pipeline_complete). ─────────────────────────
GOLDEN_CODING: list[dict] = (
    _setup_clone_block()
    + _coding_block()
    + _test_and_compliance_block()
    + _commit_push_pr_block()
    + [{"type": "pipeline_complete", "section": None, "data": GOLDEN_PIPELINE_OUTPUT_CODING}]
)


# ── Scenario (b): mode="test" — NO coding step, NO commit/push/PR; the commit
#    section emits a SINGLE phase_end (committed=False, no phase_start) then the
#    terminal pipeline_complete with the test-mode output. ──────────────────────
GOLDEN_TEST: list[dict] = (
    _setup_clone_block()
    + _test_and_compliance_block()
    + [
        {
            "type": "phase_end",
            "section": "commit",
            "data": {
                "committed": False,
                "message": "No file changes were applied (test-only run or no edits accepted).",
            },
        },
        {"type": "pipeline_complete", "section": None, "data": GOLDEN_PIPELINE_OUTPUT_TEST},
    ]
)


# ── Scenario (c): mode="auto" resolving to "test" — same as GOLDEN_TEST but with
#    the classify phase (phase_start/phase_end section="classify") spliced in after
#    clone. Locks the classify branch + that the resolved mode threads everywhere. ─
GOLDEN_AUTO_TEST: list[dict] = (
    _setup_clone_block()
    + [
        {"type": "phase_start", "section": "classify", "data": None},
        {"type": "phase_end", "section": "classify", "data": {"resolved_mode": "test"}},
    ]
    + _test_and_compliance_block()
    + [
        {
            "type": "phase_end",
            "section": "commit",
            "data": {
                "committed": False,
                "message": "No file changes were applied (test-only run or no edits accepted).",
            },
        },
        {"type": "pipeline_complete", "section": None, "data": GOLDEN_PIPELINE_OUTPUT_TEST},
    ]
)


# ── Scenario (d): the CodingAgent raises → ``agent_error`` then the generator
#    re-raises (no pipeline_complete). Locks the per-agent error envelope + the
#    "surface the error event, then propagate" contract. ────────────────────────
_CODING_FAILURE_MESSAGE = "scripted coding failure"
GOLDEN_CODING_ERROR_EVENTS: list[dict] = _setup_clone_block() + [
    {
        "type": "agent_thinking",
        "section": None,
        "data": {
            "agent_id": "coding_agent",
            "thinking": "Reading relevant files and planning the change...",
        },
    },
    {
        "type": "agent_error",
        "section": None,
        "data": {"agent_id": "coding_agent", "error": _CODING_FAILURE_MESSAGE},
    },
]


# ═════════════════════════════════════════════════════════════════════════════
# TESTS — assert each scenario's full ordered event stream + the pipeline_output
# shape against the frozen golden.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_contract_coding_mode() -> None:
    """(a) mode="coding" → the full clone→code→test→compliance→commit→push→PR stream."""
    factory = _build_pipeline(requested_mode="coding")
    events = await collect_events(factory)
    assert _normalise_all(events) == GOLDEN_CODING


@pytest.mark.asyncio
async def test_contract_test_mode() -> None:
    """(b) mode="test" → no coding step, no commit/push/PR; terminal committed=False."""
    factory = _build_pipeline(requested_mode="test")
    events = await collect_events(factory)
    assert _normalise_all(events) == GOLDEN_TEST


@pytest.mark.asyncio
async def test_contract_auto_mode_resolves_to_test() -> None:
    """(c) mode="auto" → a classify phase is emitted; resolved mode drives the rest."""
    factory = _build_pipeline(requested_mode="auto", classify_returns="test")
    events = await collect_events(factory)
    assert _normalise_all(events) == GOLDEN_AUTO_TEST


@pytest.mark.asyncio
async def test_contract_coding_agent_error_then_reraise() -> None:
    """(d) A handoff agent raising emits ``agent_error`` then the pipeline re-raises.

    Locks: the ``agent_error`` envelope (``{agent_id, error}``); that it sits right after
    the agent's ``agent_thinking``; that NO ``pipeline_complete`` is emitted; and that the
    generator propagates the original exception (so the REST background task marks the
    session FAILED). The pipeline's ``finally`` still runs (cleanup), proven by no leak.
    """
    factory = _build_pipeline(
        requested_mode="coding",
        failing_agent="coding_agent",
        failure_exc=RuntimeError(_CODING_FAILURE_MESSAGE),
    )
    events, raised = await collect_events_expecting_raise(factory)
    assert _normalise_all(events) == GOLDEN_CODING_ERROR_EVENTS
    assert isinstance(raised, RuntimeError)
    assert str(raised) == _CODING_FAILURE_MESSAGE
    # No terminal event on the error path.
    assert all(e["type"] != "pipeline_complete" for e in events)


# ═════════════════════════════════════════════════════════════════════════════
# pipeline_output SHAPE — the FE refresh-hydration contract (asserted directly,
# not just via the event golden, because a downstream row reads these keys).
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_output_coding_shape() -> None:
    """The terminal ``pipeline_complete.data`` (= HandoffSession.pipeline_output) for coding.

    Asserts the EXACT key set + values (timestamps normalised). The four FE/REST-read keys
    (``resolved_mode`` / ``branch_name`` / ``pr_url`` / ``pr_number`` — handoff.py:399-402)
    are present and correct.
    """
    factory = _build_pipeline(requested_mode="coding")
    events = await collect_events(factory)
    terminal = events[-1]
    assert terminal["type"] == "pipeline_complete"
    output = _normalise(terminal)["data"]
    assert output == GOLDEN_PIPELINE_OUTPUT_CODING
    assert set(output.keys()) == {
        "handoff_id",
        "started_at",
        "branch_name",
        "edit_results",
        "base_branch",
        "default_branch",
        "resolved_mode",
        "coding_summary",
        "test_report",
        "compliance_report",
        "pr_url",
        "pr_number",
        "completed_at",
    }
    # FE/REST-read hydration keys.
    assert output["resolved_mode"] == "coding"
    assert output["branch_name"] == BRANCH_NAME
    assert output["pr_url"] == PR_URL
    assert output["pr_number"] == PR_NUMBER


@pytest.mark.asyncio
async def test_pipeline_output_test_shape() -> None:
    """The test-mode ``pipeline_output`` OMITS coding_summary / pr_url / pr_number.

    A refresh after a test-only run must hydrate with ``resolved_mode="test"``,
    ``edit_results=[]``, and no PR fields — exactly what the FE keys off to render the
    test-only (no-diff, no-PR) view.
    """
    factory = _build_pipeline(requested_mode="test")
    events = await collect_events(factory)
    terminal = events[-1]
    assert terminal["type"] == "pipeline_complete"
    output = _normalise(terminal)["data"]
    assert output == GOLDEN_PIPELINE_OUTPUT_TEST
    assert set(output.keys()) == {
        "handoff_id",
        "started_at",
        "branch_name",
        "edit_results",
        "base_branch",
        "default_branch",
        "resolved_mode",
        "test_report",
        "compliance_report",
        "completed_at",
    }
    assert "coding_summary" not in output
    assert "pr_url" not in output
    assert "pr_number" not in output
    assert output["resolved_mode"] == "test"
    assert output["edit_results"] == []


# ═════════════════════════════════════════════════════════════════════════════
# STRUCTURAL INVARIANTS — assert the contract's shape rules directly (not just the
# data). These are migration-critical: drift here silently breaks the FE handoff view.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_event_shape_is_ws_envelope() -> None:
    """Every event has exactly the ``{type, chunk, section, data}`` keys (the WS envelope)."""
    factory = _build_pipeline(requested_mode="coding")
    events = await collect_events(factory)
    assert events, "expected a non-empty event stream"
    for ev in events:
        assert set(ev.keys()) == {"type", "chunk", "section", "data"}, ev


@pytest.mark.asyncio
async def test_chunk_is_always_none() -> None:
    """The handoff pipeline never token-streams — ``chunk`` is None on every event.

    (Agents are one-shot ``.run``/``.ainvoke`` calls, so there is no ``chunk`` channel;
    the FE handoff view keys on ``type`` + ``data`` only. Distinguishes this contract from
    the free-chat ``stream`` contract.)
    """
    for mode in ("coding", "test"):
        factory = _build_pipeline(requested_mode=mode)
        events = await collect_events(factory)
        for ev in events:
            assert ev["chunk"] is None, ev


@pytest.mark.asyncio
async def test_phase_envelope_pairing_coding() -> None:
    """The phase envelope has THREE shapes — all load-bearing contract facts.

    The handoff pipeline is NOT uniformly bracketed; pinning the exact asymmetry guards the
    FE renderer through the migration:
      * **Bracketed** (phase_start → phase_end): ``setup``, ``clone``, ``commit`` (when it
        actually commits), ``push``.
      * **Lone ``phase_end``** (a report-only end with NO preceding phase_start):
        ``apply_edits`` (coding path, handoff_pipeline.py:478) and ``commit`` on the
        no-edits/test path (the "nothing to commit" branch, :585).
      * **Lone ``phase_start``** closed by a sibling event, NOT a phase_end: ``open_pr``
        (:568) is terminated by the ``pr_created`` event (:581) — there is no
        ``phase_end section="open_pr"``.
    This walk asserts: no nested phase_starts; every ``phase_end`` closes the open section
    or is an allowed lone-phase_end; ``open_pr`` opens and is closed by ``pr_created``; and
    the bracketed sections appear in the exact order.
    """
    _LONE_PHASE_END_SECTIONS = {"apply_edits", "commit"}
    _PR_EVENT_CLOSES = "open_pr"  # open_pr's phase_start is closed by pr_created, not phase_end
    factory = _build_pipeline(requested_mode="coding")
    events = await collect_events(factory)

    # pipeline_complete is last and unique.
    assert events[-1]["type"] == "pipeline_complete"
    assert sum(1 for e in events if e["type"] == "pipeline_complete") == 1

    open_section: str | None = None
    bracketed_starts: list[str] = []
    lone_ends: list[str] = []
    pr_starts: list[str] = []
    for ev in events:
        t = ev["type"]
        if t == "phase_start":
            assert open_section is None, f"nested phase_start in {open_section}"
            open_section = ev["section"]
            if open_section == _PR_EVENT_CLOSES:
                pr_starts.append(open_section)
            else:
                bracketed_starts.append(open_section)
        elif t == "phase_end":
            if open_section is None:
                # A lone phase_end is only allowed for the two report-only sections.
                assert ev["section"] in _LONE_PHASE_END_SECTIONS, (
                    f"lone phase_end for unexpected section {ev['section']!r}"
                )
                lone_ends.append(ev["section"])
            else:
                assert open_section == ev["section"], (
                    f"phase_end {ev['section']!r} != open {open_section!r}"
                )
                open_section = None
        elif t == "pr_created":
            # pr_created terminates the open_pr phase_start (no phase_end for open_pr).
            assert open_section == _PR_EVENT_CLOSES, (
                f"pr_created without an open {_PR_EVENT_CLOSES!r} phase (open={open_section!r})"
            )
            open_section = None
        # other agent_* / pipeline_complete events are not part of the phase envelope.
    assert open_section is None, "unclosed phase envelope"
    # coding path → these BRACKETED phased sections in this exact order ...
    assert bracketed_starts == ["setup", "clone", "commit", "push"]
    # ... the lone ``apply_edits`` phase_end (coding path emits exactly one) ...
    assert lone_ends == ["apply_edits"]
    # ... and the single pr_created-terminated ``open_pr`` phase.
    assert pr_starts == ["open_pr"]


@pytest.mark.asyncio
async def test_agent_complete_report_shapes() -> None:
    """The ``agent_complete`` report shapes are frozen (the FE renders these verbatim).

    * coding_agent → flat keys ``{agent_id, summary, rationale, edit_count, edits,
      tests_added, follow_ups}`` (NOT a nested ``report``);
    * test_agent / compliance_agent → ``{agent_id, report:{...}}`` with the report's own
      verdict/finding keys. This asymmetry is load-bearing for the FE tabs.
    """
    factory = _build_pipeline(requested_mode="coding")
    events = await collect_events(factory)
    completes = {
        e["data"]["agent_id"]: e["data"]
        for e in events
        if e["type"] == "agent_complete"
    }
    assert set(completes) == {"coding_agent", "test_agent", "compliance_agent"}

    coding = completes["coding_agent"]
    assert set(coding.keys()) == {
        "agent_id",
        "summary",
        "rationale",
        "edit_count",
        "edits",
        "tests_added",
        "follow_ups",
    }
    assert "report" not in coding

    for agent_id in ("test_agent", "compliance_agent"):
        ac = completes[agent_id]
        assert set(ac.keys()) == {"agent_id", "report"}
        assert isinstance(ac["report"], dict)
    assert completes["test_agent"]["report"]["verdict"] == "concerns"
    assert completes["compliance_agent"]["report"]["verdict"] == "approve_with_changes"


@pytest.mark.asyncio
async def test_event_type_vocabulary_is_frozen() -> None:
    """The union of event ``type`` values across coding + test + auto + error is frozen.

    Drift (a new/renamed event type) is the single most likely way a migration silently
    breaks the FE handoff renderer — this pins the whole vocabulary.
    """
    seen: set[str] = set()
    for factory in (
        _build_pipeline(requested_mode="coding"),
        _build_pipeline(requested_mode="test"),
        _build_pipeline(requested_mode="auto", classify_returns="test"),
    ):
        events = await collect_events(factory)
        seen.update(e["type"] for e in events)
    # Add the error path's events.
    err_factory = _build_pipeline(
        requested_mode="coding",
        failing_agent="coding_agent",
        failure_exc=RuntimeError(_CODING_FAILURE_MESSAGE),
    )
    err_events, _ = await collect_events_expecting_raise(err_factory)
    seen.update(e["type"] for e in err_events)

    assert seen == {
        "phase_start",
        "phase_end",
        "agent_thinking",
        "agent_complete",
        "agent_error",
        "pr_created",
        "pipeline_complete",
    }


# ═════════════════════════════════════════════════════════════════════════════
# META — guard the freeze itself: the golden must stay a pure-data island, and the
# factory seam must stay re-pointable so 7c-4 re-runs this file unchanged.
# ═════════════════════════════════════════════════════════════════════════════


def test_goldens_are_plain_literals_no_pipeline_import() -> None:
    """The frozen goldens are pure data and the module has no top-level pipeline import.

    Guarantees this file stays a contract island: the only ``handoff_pipeline`` /
    ``handoff_github`` references are inside ``_build_pipeline`` (which imports lazily), and
    there is NO module-level ``from app.services.handoff_pipeline`` / ``import BaseAgent``
    token — so when 7c-3 deletes ``base.py`` and widens ``test_no_baseagent.py`` to scan
    this tree, this module stays clean, and the golden remains the single source of truth.
    """
    for golden in (GOLDEN_CODING, GOLDEN_TEST, GOLDEN_AUTO_TEST, GOLDEN_CODING_ERROR_EVENTS):
        assert isinstance(golden, list) and golden
    assert GOLDEN_CODING[-1]["type"] == "pipeline_complete"
    assert GOLDEN_TEST[-1]["type"] == "pipeline_complete"
    assert GOLDEN_CODING_ERROR_EVENTS[-1]["type"] == "agent_error"

    # Parse the module's AST and assert NO *module-level* (top-level) import statement
    # binds the pipeline / handoff-agents / BaseAgent stack. Using the AST (not substring
    # matching) makes this immune to the forbidden names merely appearing in docstrings or
    # comments — only real top-level imports fail. Imports nested inside ``_build_pipeline``
    # are function-level (not module nodes) and so are correctly allowed.
    import ast

    module = inspect.getmodule(test_goldens_are_plain_literals_no_pipeline_import)
    tree = ast.parse(inspect.getsource(module))
    _FORBIDDEN_MODULES = {
        "app.services.handoff_pipeline",
        "app.agents.handoff",
        "app.agents.base",
    }
    for node in tree.body:  # tree.body == module-level statements only
        if isinstance(node, ast.ImportFrom):
            assert node.module not in _FORBIDDEN_MODULES, (
                f"module-level import from {node.module!r} leaks the pipeline stack"
            )
            assert all(
                alias.name != "BaseAgent" for alias in node.names
            ), "module-level BaseAgent import leaks the legacy stack"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in _FORBIDDEN_MODULES, (
                    f"module-level import {alias.name!r} leaks the pipeline stack"
                )


def test_collect_events_is_factory_agnostic() -> None:
    """``collect_events`` depends only on the factory protocol, not the pipeline class.

    This is the seam 7c-4 re-uses unchanged: it takes any zero-arg ``pipeline_factory``
    whose product is an async iterator of WS event dicts.
    """
    sig = inspect.signature(collect_events)
    assert list(sig.parameters) == ["pipeline_factory"]
