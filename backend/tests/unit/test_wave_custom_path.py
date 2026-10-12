"""Spec 022 revision 7: a wave step's ``custom_path`` task source reads exactly one file.

``kind: custom_path`` + ``path`` (``{revision_n}`` = the highest numbered revisions/
folder) — no fallback to build/tasks.json or to the producer step's reply. Every other
task source keeps today's target → build/tasks.json → reply order.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.capabilities.strategies.wave_scheduler import (
    WaveSchedulerStrategy,
    latest_revision_number,
    read_custom_path,
    resolve_revision_path,
)
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.plan import TaskSource

PATH = "revisions/{revision_n}/tasks.json"
# blr-plan replies with one line of prose; the task list is the file it wrote.
PLAN_REPLY = "Wrote 2 tasks: T1 and T2."


def _step(task_source):
    return SimpleNamespace(agent_id="custom-agent:blr-write", name="Revision Writers",
                           task_source=task_source)


CUSTOM = _step(TaskSource(kind="custom_path", path=PATH, parser="json_tasks",
                          source_step="custom-agent:blr-plan"))


class DiskSandbox:
    def __init__(self, root):
        self.root = root

    def path_for(self, rel):
        return self.root / rel

    def read(self, rel):
        p = self.root / rel
        return p.read_text() if p.is_file() else None

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


class _Runner:
    """The ctx.runner a wave step needs, with the fan-out calls recorded."""

    def __init__(self, sandbox, reply=PLAN_REPLY):
        self.sandbox = sandbox
        self.reply = reply
        self.dispatched = []

    def latest_typed_content(self, _step):
        return self.reply

    async def read_wave_runs(self):
        return []

    async def record_wave_run(self, *, step, wave_index, task_ids, status):
        return f"row-{wave_index}"

    async def update_wave_run(self, row_id, *, status):
        pass

    async def run_fanout(self, requests, ctx, *, step=None, event_queue=None):
        self.dispatched.extend(requests)
        for i, _request in enumerate(requests):
            yield {"type": "subagent_spawned",
                   "data": {"worker": i, "agent": "w", "isolation": "shared_read", "depth": 0}}
        for i, _request in enumerate(requests):
            yield {"type": "subagent_result",
                   "data": {"worker": i, "agent": "w", "row_id": f"r{i}", "status": "complete"}}


def _task_list(*ids):
    return json.dumps({"tasks": [
        {"id": i, "title": i, "targets": [f"{i}.md"], "depends_on": [], "body": f"body of {i}"} for i in ids
    ]})


def _write_task_list(disk, path, *ids):
    """A task list at ``path``, one task per id, and the file each task targets."""
    disk.write(path, _task_list(*ids))
    for i in ids:
        disk.write(f"{i}.md", "x")


def _mkdirs(root, *names):
    for name in names:
        (root / "revisions" / name).mkdir(parents=True)


async def _run(runner, step=CUSTOM):
    ctx = SimpleNamespace(runner=runner, is_resuming=False)
    return [event async for event in WaveSchedulerStrategy().run(step, ctx)]


def _dispatched(runner):
    return [(r["task_author_id"], r["input"]) for r in runner.dispatched]


# ── 1. the revision number ───────────────────────────────────────────────────────────

def test_no_revisions_folder_has_no_latest_revision(tmp_path):
    assert latest_revision_number(DiskSandbox(tmp_path)) is None


def test_the_latest_revision_is_the_highest_number_and_non_digit_names_are_ignored(tmp_path):
    _mkdirs(tmp_path, "1", "2", "10", "fix-all-diagrams")
    assert latest_revision_number(DiskSandbox(tmp_path)) == 10


def test_a_file_named_like_a_revision_is_not_a_revision(tmp_path):
    _mkdirs(tmp_path, "1")
    (tmp_path / "revisions" / "99").write_text("x")
    assert latest_revision_number(DiskSandbox(tmp_path)) == 1


def test_the_revision_token_resolves_to_the_latest_revision(tmp_path):
    _mkdirs(tmp_path, "1", "2", "10")
    assert resolve_revision_path(PATH, DiskSandbox(tmp_path)) == "revisions/10/tasks.json"


def test_the_revision_token_needs_a_revisions_folder(tmp_path):
    with pytest.raises(ValueError, match="no revisions/<n>/ folder"):
        resolve_revision_path(PATH, DiskSandbox(tmp_path))


# ── 2. read_custom_path ──────────────────────────────────────────────────────────────

def test_a_plain_custom_path_is_read_as_it_is(tmp_path):
    disk = DiskSandbox(tmp_path)
    disk.write("plans/tasks.json", "[]")
    assert read_custom_path("plans/tasks.json", disk) == "[]"


@pytest.mark.parametrize("text", [None, "", "  \n"])
def test_a_missing_or_empty_custom_path_stops_the_step(tmp_path, text):
    disk = DiskSandbox(tmp_path)
    if text is not None:
        disk.write("plans/tasks.json", text)
    with pytest.raises(ValueError, match="plans/tasks.json"):
        read_custom_path("plans/tasks.json", disk)


# ── 3. WaveSchedulerStrategy.run ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_custom_path_dispatches_the_latest_revisions_tasks_not_build_tasks(tmp_path):
    disk = DiskSandbox(tmp_path)
    _write_task_list(disk, "build/tasks.json", "PARENT")
    _write_task_list(disk, "revisions/1/tasks.json", "OLD")
    _write_task_list(disk, "revisions/2/tasks.json", "T1", "T2")
    runner = _Runner(disk)

    await _run(runner)

    assert _dispatched(runner) == [("T1", "body of T1"), ("T2", "body of T2")]


@pytest.mark.asyncio
async def test_custom_path_never_falls_back_to_build_tasks_or_the_reply(tmp_path):
    disk = DiskSandbox(tmp_path)
    _write_task_list(disk, "build/tasks.json", "PARENT")
    _mkdirs(tmp_path, "2")  # revisions/2/ exists, tasks.json does not
    # Even a reply that IS a valid task list is never read for a custom_path source.
    runner = _Runner(disk, reply=_task_list("REPLY"))

    with pytest.raises(ValueError) as raised:
        await _run(runner)

    assert "revisions/2/tasks.json" in str(raised.value)
    assert runner.dispatched == []


@pytest.mark.asyncio
async def test_a_parsed_target_still_falls_back_to_build_tasks(tmp_path):
    # The existing option is untouched: target first, then build/tasks.json.
    disk = DiskSandbox(tmp_path)
    _write_task_list(disk, "build/tasks.json", "PARENT")
    runner = _Runner(disk)
    step = _step(TaskSource(kind="parsed", parser="json_tasks", target="missing.json",
                            source_step="custom-agent:blr-plan"))

    await _run(runner, step)

    assert _dispatched(runner) == [("PARENT", "body of PARENT")]


# ── 4. the compiler ──────────────────────────────────────────────────────────────────

def _compile_task_source(raw):
    return WorkflowCompiler()._compile_task_source(raw, "step blr-write", None, True)


def test_custom_path_compiles_with_its_path():
    ts = _compile_task_source({"kind": "custom_path", "path": PATH, "source_step": "custom-agent:blr-plan"})
    assert (ts.kind, ts.path, ts.target) == ("custom_path", PATH, None)


@pytest.mark.parametrize("raw", [{"kind": "custom_path"}, {"kind": "custom_path", "path": "  "}])
def test_custom_path_without_a_path_fails_compilation(raw):
    with pytest.raises(CompilerError, match="needs a 'path'"):
        _compile_task_source(raw)


def test_a_parsed_source_compiles_as_before():
    ts = _compile_task_source({"kind": "parsed", "target": "build/tasks.json"})
    assert (ts.kind, ts.target, ts.path) == ("parsed", "build/tasks.json", None)
