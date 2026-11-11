"""Property tests for the script runner's concurrency bound and cleanup.

Covers design Property 5 (task 12.9, Req 31.6, 36.6, 47.15, 20.11): for any set of
concurrent script calls with any mix of outcomes, at most 8 subprocesses run at
the same time, every started process is waited for (and killed when it did not
end by itself), and each call's temp folder is gone once the call ends.

Every call goes through :func:`run_command` with a keyed
:class:`FakeProcessFactory`, so no real subprocess starts. The sandbox lives in a
temporary directory created inside each example.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import (
    ScriptContext,
    ScriptResult,
    run_command,
)
from app.core.config import settings as app_settings
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_turn import FakeTurnPort
from tests.fakes.process_factory import FakeProcess, FakeProcessFactory, ProcessScript

# The bound from Req 36.6, restated here and not read from the module.
_MAX_CONCURRENT = 8

_VALID_COMMAND = f"python /skills/{BUILDER_SKILL_ID}/scripts/catalog_lookup.py overview"
_REFUSED_COMMAND = 'python -c "print(1)"'

# A call that must time out gets a short timeout; every other call gets a long
# one, so only the hanging scripts expire.
_SHORT_TIMEOUT = 0.02
_LONG_TIMEOUT = 30.0

Kind = Literal["ok", "nonzero", "timeout", "cancel", "refused", "start_error"]
_KINDS: tuple[Kind, ...] = (
    "ok",
    "nonzero",
    "timeout",
    "cancel",
    "refused",
    "start_error",
)
_RUNS_TO_END: frozenset[Kind] = frozenset({"ok", "nonzero"})

# (kind, milliseconds). For "ok" and "nonzero" the milliseconds are the time the
# process stays alive; for "cancel" they are the wait before the cancel.
_PLANS = st.lists(
    st.tuples(st.sampled_from(_KINDS), st.integers(min_value=0, max_value=25)),
    min_size=1,
    max_size=24,
)
# Plans that fill more than the bound with processes that overlap in time.
_BUSY_PLANS = st.lists(
    st.tuples(st.sampled_from(("ok", "nonzero")), st.integers(5, 25)),
    min_size=_MAX_CONCURRENT + 1,
    max_size=24,
)

Plan = Sequence[tuple[Kind, int]]


class _KeyedFactory(FakeProcessFactory):
    """A factory whose script depends on the call, not on the start order.

    Calls run concurrently, so the order of starts is not the order of the plan.
    The script is looked up by the call id, which names the call's temp folder
    and reaches the spawner as ``env["TMP"]``. The spawner also writes files into
    that folder, the way a script that produced output would, and records
    whether the folder existed when the process started.
    """

    def __init__(self, scripts: Mapping[str, ProcessScript]) -> None:
        super().__init__()
        self._scripts = scripts
        self.tmp_existed_at_start: dict[str, bool] = {}

    async def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]
    ) -> FakeProcess:
        tmp = Path(env["TMP"])
        self.tmp_existed_at_start[tmp.name] = tmp.is_dir()
        if tmp.is_dir():
            (tmp / "out.txt").write_text("partial output", encoding="utf-8")
            (tmp / "nested").mkdir()
            (tmp / "nested" / "data.bin").write_bytes(b"\x00" * 64)
        # Set before the base class's first await, so concurrent starts cannot
        # see each other's script.
        self._default = self._scripts[tmp.name]
        return await super().__call__(argv, cwd=cwd, env=env)


@dataclass(frozen=True)
class _Observed:
    """What one example left behind."""

    outcomes: list[tuple[Kind, ScriptResult | BaseException]]
    factory: _KeyedFactory
    call_ids: list[str]
    leftover_temp_entries: list[str]


def _script_for(kind: Kind, millis: int) -> ProcessScript:
    """Return the process script that plays ``kind`` for ``millis`` milliseconds."""
    if kind == "start_error":
        return ProcessScript(start_error=OSError("no interpreter"))
    if kind in _RUNS_TO_END:
        script = ProcessScript.with_text("out\n", exit_code=0 if kind == "ok" else 3)
        return replace(script, exit_delay=millis / 1000)
    # "timeout" and "cancel" processes never end on their own.
    return ProcessScript.with_text("partial\n", hang=True)


async def _drive(
    box: BuilderSandbox, skill_root: Path, plan: Plan, semaphore: asyncio.Semaphore
) -> tuple[list[tuple[Kind, ScriptResult | BaseException]], _KeyedFactory, list[str]]:
    """Start every call of ``plan`` at once and cancel the ``cancel`` calls."""
    call_ids = [uuid4().hex for _ in plan]
    scripts = {
        call_id: _script_for(kind, millis)
        for call_id, (kind, millis) in zip(call_ids, plan, strict=True)
    }
    factory = _KeyedFactory(scripts)
    base = ScriptContext(
        sandbox=box,
        skill_root=skill_root,
        gate=FakeGate(),
        turn=FakeTurnPort(),
        semaphore=semaphore,
        spawn=factory,
    )
    tasks: list[asyncio.Task[ScriptResult]] = []
    for call_id, (kind, _) in zip(call_ids, plan, strict=True):
        ctx = replace(
            base,
            call_id=call_id,
            timeout_seconds=_SHORT_TIMEOUT if kind == "timeout" else _LONG_TIMEOUT,
        )
        command = _REFUSED_COMMAND if kind == "refused" else _VALID_COMMAND
        tasks.append(asyncio.create_task(run_command(command, ctx)))
    for task, (kind, millis) in zip(tasks, plan, strict=True):
        if kind == "cancel":
            await asyncio.sleep(millis / 1000)
            task.cancel()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return (
        list(zip((kind for kind, _ in plan), results, strict=True)),
        factory,
        call_ids,
    )


def _observe(plan: Plan) -> _Observed:
    """Run ``plan`` in a sandbox made inside this call and report what is left."""
    with tempfile.TemporaryDirectory(prefix="builder-conc-") as base:
        root = Path(base)
        box = BuilderSandbox("conc-user", "conc-session", root=root / "sandboxes")
        box.ensure()
        skill_root = root / "skill"
        (skill_root / "scripts").mkdir(parents=True)
        # A fresh semaphore per example: an asyncio semaphore binds to the loop
        # of its first contended use, and every example runs its own loop.
        semaphore = asyncio.Semaphore(app_settings.BUILDER_MAX_CONCURRENT_SCRIPTS)
        outcomes, factory, call_ids = asyncio.run(
            _drive(box, skill_root, plan, semaphore)
        )
        leftover = sorted(p.name for p in (box.path / ".tmp").iterdir())
    return _Observed(outcomes, factory, call_ids, leftover)


# Feature: ai-workflow-builder, Property 5: Script calls are bounded and clean up after themselves
@settings(max_examples=100, deadline=None)
@given(plan=_PLANS)
def test_run_command_runs_at_most_eight_processes_when_calls_are_concurrent(
    plan: Plan,
) -> None:
    seen = _observe(plan)

    assert app_settings.BUILDER_MAX_CONCURRENT_SCRIPTS == _MAX_CONCURRENT
    assert seen.factory.max_active <= _MAX_CONCURRENT


# Feature: ai-workflow-builder, Property 5: Script calls are bounded and clean up after themselves
@settings(max_examples=100, deadline=None)
@given(plan=_BUSY_PLANS)
def test_run_command_waits_for_a_slot_when_more_than_eight_calls_overlap(
    plan: Plan,
) -> None:
    seen = _observe(plan)

    # Every call finishes (a 9th call waits; none is refused), and the bound
    # is reached, so the first property is not met by calls that never overlap.
    assert all(
        isinstance(result, ScriptResult) and result.status in ("ok", "error")
        for _, result in seen.outcomes
    )
    assert len(seen.factory.processes) == len(plan)
    assert seen.factory.max_active == _MAX_CONCURRENT


# Feature: ai-workflow-builder, Property 5: Script calls are bounded and clean up after themselves
@settings(max_examples=100, deadline=None)
@given(plan=_PLANS)
def test_run_command_removes_every_temp_folder_when_calls_end_in_any_way(
    plan: Plan,
) -> None:
    seen = _observe(plan)

    assert seen.leftover_temp_entries == []
    # The folders existed while the processes ran, so the empty result above
    # is a cleanup and not a folder that was never made.
    started = {
        call_id
        for call_id, (kind, _) in zip(seen.call_ids, plan, strict=True)
        if kind not in ("refused", "cancel")
    }
    assert all(seen.factory.tmp_existed_at_start.get(call) for call in started)


# Feature: ai-workflow-builder, Property 5: Script calls are bounded and clean up after themselves
@settings(max_examples=100, deadline=None)
@given(plan=_PLANS)
def test_run_command_ends_every_process_when_calls_time_out_or_are_cancelled(
    plan: Plan,
) -> None:
    seen = _observe(plan)

    assert seen.factory.active == 0
    for process in seen.factory.processes:
        assert process.returncode is not None
        assert process.wait_count >= 1
        if process.script.hang:
            assert process.kill_count >= 1


# Feature: ai-workflow-builder, Property 5: Script calls are bounded and clean up after themselves
@settings(max_examples=100, deadline=None)
@given(plan=_PLANS)
def test_run_command_reports_each_outcome_when_calls_are_concurrent(
    plan: Plan,
) -> None:
    seen = _observe(plan)

    for kind, result in seen.outcomes:
        if kind == "cancel":
            # A cancel that came after the call ended leaves its result.
            assert isinstance(result, (asyncio.CancelledError, ScriptResult))
            continue
        assert isinstance(result, ScriptResult)
        expected = {
            "ok": "ok",
            "nonzero": "error",
            "timeout": "timed_out",
            "refused": "refused",
            "start_error": "error",
        }[kind]
        assert result.status == expected
