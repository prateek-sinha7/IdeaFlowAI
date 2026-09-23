"""tests/agents/test_validation_retry.py — STABILIZATION.md A1/A18: validation-retry-with-feedback.

Closes A1's Finding 1: a post-step ``validation`` gate's CRITICAL block used to be
event-only (``gate_blocked``, no halt) — the dispatch loop advanced to the next
step with the flawed artifact regardless, which is how STABILIZATION.md's failed
runs shipped bad artifacts. ``agents.execution_engine.engine``'s outer per-step
dispatch loop now:

  * re-dispatches the SAME step (feeding the validator's CRITICAL findings back
    through ``ectx.steering_notes`` — the same seam the declared-gate redo path
    uses) up to ``step.fix.max_attempts`` times, emitting one ``validation_retry``
    event per attempt;
  * fails the run CLOSED (a single ``pipeline_failed`` terminal — no downstream
    step ever dispatches) once attempts are exhausted, or immediately with zero
    retries when the step declares no ``fix:`` at all.

Offline — no live LLM. Driven end-to-end via the scripted-model harness
(``tests/agents/_scripted_model._drive``) against
``agents/workflows/ex_validation_retry/workflow.yaml`` (draft -> done), a fake
STATEFUL "blocks N times then clears" validator (the same registry-injection
recipe as ``tests/agents/test_gates.py::_register_fake_validator``), and a
``compile_for_run`` wrapper that attaches ``gates: [validation]`` +
``validators: [ex_flaky_validator]`` (+ an optional ``fix:`` policy) onto the
COMPILED ``draft`` step in-memory — the manifest on disk stays gate/validator-
free (compiles cleanly under the real, un-monkeypatched registry that
``test_manifest_coverage.py`` sweeps every workflow.yaml through), the same
deep-copy-then-mutate pattern ``_scripted_model._drive`` already uses for
``clarify.mode``/``require_render``.
"""

from __future__ import annotations

import copy

import pytest

import agents.capabilities.registry as registry_mod
import agents.execution_engine.engine as engine_mod
from agents.workflows.plan import FixPolicy
from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive


# ════════════════════════════════════════════════════════════════════════════
# Registry save/restore (test_gates.py precedent — 08-01 Issues-Encountered)
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
# Fake, STATEFUL validator — blocks (P0) on the first N calls, then clears.
# ════════════════════════════════════════════════════════════════════════════


class _Issue:
    def __init__(self, severity: str, message: str = "x") -> None:
        self.severity = severity
        self.message = message


class _FlakyValidator:
    """Blocks (P0/CRITICAL) on the first ``fail_times`` ``validate()`` calls, then
    clears (returns no issues) on every call after that."""

    name = "ex_flaky_validator"

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.calls = 0

    async def validate(self, target):
        self.calls += 1
        if self.calls <= self._fail_times:
            return [_Issue("P0", f"broken nav (attempt {self.calls})")]
        return []


def _register_flaky_validator(fail_times: int) -> _FlakyValidator:
    validator = _FlakyValidator(fail_times)
    registry_mod._KNOWN.add(("validator", "ex_flaky_validator"))
    registry_mod._IMPLS[("validator", "ex_flaky_validator")] = validator
    registry_mod._TRUST[("validator", "ex_flaky_validator")] = True
    return validator


def _default_scripts_for(agent_id: str) -> list[_ScriptedTurn]:
    """Every step just streams plain text — no tools, no decisions to script."""
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.fixture
def _captured_prompts():
    """Records the raw LangChain ``messages`` list of every model call made
    during the test, via a class-level wrap of ``ScriptedFakeChatModel._stream``
    (restored after)."""
    captured: list[list] = []
    orig_stream = _sm.ScriptedFakeChatModel._stream

    def _recording_stream(self, messages, stop=None, run_manager=None, **kwargs):
        captured.append(messages)
        yield from orig_stream(
            self, messages, stop=stop, run_manager=run_manager, **kwargs
        )

    _sm.ScriptedFakeChatModel._stream = _recording_stream
    try:
        yield captured
    finally:
        _sm.ScriptedFakeChatModel._stream = orig_stream


def _flat_text(messages: list) -> str:
    """Flatten a LangChain messages list to one searchable string (content only)."""
    parts: list[str] = []
    for m in messages:
        content = getattr(m, "content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
    return "\n".join(parts)


class _InstallDraftValidation:
    """Wraps ``engine_mod.compile_for_run`` to attach ``gates: [validation]`` +
    ``validators: [ex_flaky_validator]`` (+ an optional ``fix:`` policy) onto the
    compiled ``draft`` step IN-MEMORY — never on the on-disk manifest (see the
    module docstring for why). Deep-copies before mutating (the SAME
    already-``@lru_cache``d-return concern ``_scripted_model._drive`` documents
    for its own ``clarify.mode``/``require_render`` mutation) so this can never
    corrupt the shared compile cache for any other test in the same process.

    Installed BEFORE ``_drive()`` runs (which itself layers its OWN
    ``clarify.mode``/``require_render`` wrapper on top via the same "capture
    current compile_for_run as orig, restore in finally" idiom) and restored to
    the TRUE pre-test original afterward.
    """

    def __init__(self, max_attempts: int | None) -> None:
        self._max_attempts = max_attempts
        self._true_original = None

    def __enter__(self):
        self._true_original = engine_mod.compile_for_run
        max_attempts = self._max_attempts
        true_original = self._true_original

        def _wrapped(pipeline_type, _orig=true_original):
            compiled = copy.deepcopy(_orig(pipeline_type))
            for s in getattr(compiled, "steps", []) or []:
                if getattr(s, "instance_id", None) == "draft":
                    s.gates = ["validation"]
                    s.validators = ["ex_flaky_validator"]
                    if max_attempts is not None:
                        s.fix = FixPolicy(mode="gated", max_attempts=max_attempts)
            return compiled

        engine_mod.compile_for_run = _wrapped
        return self

    def __exit__(self, *exc):
        engine_mod.compile_for_run = self._true_original


async def _drive_with_fix_policy(max_attempts: int | None) -> list[dict]:
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _default_scripts_for
    try:
        with _InstallDraftValidation(max_attempts):
            return await _drive("ex_validation_retry")
    finally:
        _sm._scripts_for = orig_scripts_for


# ════════════════════════════════════════════════════════════════════════════
# (a) blocks once, retry passes → step completes, one validation_retry event,
#     the feedback reached the second attempt's prompt.
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_blocks_once_then_passes_retries_once_and_completes(_captured_prompts):
    validator = _register_flaky_validator(fail_times=1)
    events = await _drive_with_fix_policy(max_attempts=2)

    types = [e.get("type") for e in events]
    retries = [e for e in events if e.get("type") == "validation_retry"]
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    assert validator.calls == 2, f"expected 2 validation calls, got {validator.calls}: {types}"
    assert len(retries) == 1, f"expected exactly one validation_retry event: {types}"
    assert retries[0]["data"]["attempt"] == 1
    assert retries[0]["data"]["max"] == 2
    assert "broken nav" in retries[0]["data"]["feedback"]

    # draft ran twice (attempt 1 blocked, attempt 2 passed); done ran once — the
    # run DID advance once validation actually passed.
    assert starts.count("custom-agent:draft") == 2, starts
    assert starts.count("custom-agent:done") == 1, starts

    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert len(completes) == 1, types
    assert completes[0]["data"].get("status") != "degraded"

    # The SECOND attempt's prompt carried the validator's feedback text; the
    # FIRST did not (there was nothing to feed back yet).
    assert len(_captured_prompts) >= 2, "expected at least 2 model calls (2 draft attempts)"
    assert "broken nav" not in _flat_text(_captured_prompts[0])
    assert any("broken nav" in _flat_text(m) for m in _captured_prompts[1:]), (
        "the retry's feedback text never reached a later attempt's prompt"
    )


# ════════════════════════════════════════════════════════════════════════════
# (b) blocks max_attempts+1 times → step fails closed, run does not advance.
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exhausts_max_attempts_fails_closed_and_does_not_advance():
    validator = _register_flaky_validator(fail_times=999)  # always blocks
    events = await _drive_with_fix_policy(max_attempts=2)

    types = [e.get("type") for e in events]
    retries = [e for e in events if e.get("type") == "validation_retry"]
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    failed = [e for e in events if e.get("type") == "pipeline_failed"]
    completes = [e for e in events if e.get("type") == "pipeline_complete"]

    # fix.max_attempts=2 -> 2 validation_retry events (attempts 1 and 2), then a
    # 3rd block fails closed.
    assert len(retries) == 2, f"expected exactly 2 validation_retry events, got {len(retries)}: {types}"
    assert [r["data"]["attempt"] for r in retries] == [1, 2]
    assert validator.calls == 3, validator.calls

    # draft ran 3 times (initial + 2 retries); done NEVER ran — the run must not
    # advance to the next step with a known-bad artifact.
    assert starts.count("custom-agent:draft") == 3, starts
    assert "custom-agent:done" not in starts, starts

    assert len(failed) == 1, f"expected exactly one pipeline_failed terminal: {types}"
    assert len(completes) == 0, "must not report pipeline_complete after failing closed"
    agent_errors = [e for e in events if e.get("type") == "agent_error"]
    assert any(
        e["data"].get("agent_id") == "custom-agent:draft" for e in agent_errors
    ), agent_errors


# ════════════════════════════════════════════════════════════════════════════
# (c) no fix: declared + block → fails closed with 0 retries.
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_fix_declared_fails_closed_with_zero_retries():
    validator = _register_flaky_validator(fail_times=999)
    events = await _drive_with_fix_policy(max_attempts=None)  # no fix: at all

    types = [e.get("type") for e in events]
    retries = [e for e in events if e.get("type") == "validation_retry"]
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    failed = [e for e in events if e.get("type") == "pipeline_failed"]

    assert retries == [], f"a step with no fix: must get zero retries: {types}"
    assert validator.calls == 1, validator.calls
    assert starts.count("custom-agent:draft") == 1, starts
    assert "custom-agent:done" not in starts, starts
    assert len(failed) == 1, types


# ════════════════════════════════════════════════════════════════════════════
# (d) validator passes → zero retries, byte-parity with today.
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_validator_passes_zero_retries():
    validator = _register_flaky_validator(fail_times=0)  # never blocks
    events = await _drive_with_fix_policy(max_attempts=2)

    types = [e.get("type") for e in events]
    retries = [e for e in events if e.get("type") == "validation_retry"]
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    completes = [e for e in events if e.get("type") == "pipeline_complete"]

    assert validator.calls == 1, validator.calls
    assert retries == [], f"a clean validator pass must retry ZERO times: {types}"
    assert starts.count("custom-agent:draft") == 1, starts
    assert starts.count("custom-agent:done") == 1, starts
    assert len(completes) == 1, types
    assert completes[0]["data"].get("status") != "degraded"
