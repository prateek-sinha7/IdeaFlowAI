"""Unit tests for the spec 012 step-key allow-list + per-field validation (T4).

Covers R-01..R-06, R-09, F-03, F-11:
  - instance_id uniqueness is checked over the FLATTENED tree (F-03): a grandchild
    reusing a top-level id is rejected, not just siblings at the same level.
  - subagents nesting deeper than two levels is rejected (R-05).
  - subagents.mode == "fanout" requires subagents.task_source (R-04).
  - prompt is only valid on a custom-agent step (R-06).
  - subagents.steps must be a non-empty list (F-11).

This is VALIDATION ONLY — the compiler does not yet expand ``subagents`` into
child Steps (that is a later task); a valid ``subagents`` block simply compiles
without error.
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest


@pytest.fixture
def registry() -> CapabilityRegistry:
    discover()
    return CapabilityRegistry()


def _wf(steps: list, **overrides) -> WorkflowManifest:
    """Build a well-formed WorkflowManifest with the given raw steps."""
    base = dict(
        id="subagents-demo",
        steps=steps,
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )
    base.update(overrides)
    return WorkflowManifest(**base)


def test_duplicate_instance_id_across_levels_rejected(registry):
    raw = _wf(steps=[
        {"agent": "custom-agent", "instance_id": "dup", "prompt": "x"},
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "y",
         "subagents": {"mode": "parallel", "steps": [
             {"agent": "custom-agent", "instance_id": "dup", "prompt": "z"}]}},
    ])
    with pytest.raises(CompilerError, match="instance_id.*dup"):
        WorkflowCompiler().compile(raw, registry)


def test_three_level_nesting_rejected(registry):
    raw = _wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "steps": [
             {"agent": "custom-agent", "instance_id": "child", "prompt": "c",
              "subagents": {"mode": "parallel", "steps": [
                  {"agent": "custom-agent", "instance_id": "grandchild", "prompt": "g",
                   "subagents": {"mode": "parallel", "steps": [
                       {"agent": "custom-agent", "instance_id": "ggchild",
                        "prompt": "gg"},
                   ]}},
              ]}},
         ]}},
    ])
    with pytest.raises(CompilerError, match="nests deeper"):
        WorkflowCompiler().compile(raw, registry)


def test_fanout_without_task_source_rejected(registry):
    raw = _wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "fanout", "steps": [
             {"agent": "custom-agent", "instance_id": "child", "prompt": "c"},
         ]}},
    ])
    with pytest.raises(CompilerError, match="task_source"):
        WorkflowCompiler().compile(raw, registry)


def test_prompt_on_builtin_step_rejected(registry):
    raw = _wf(steps=[
        {"agent": "demo-agent", "prompt": "not allowed on a built-in step"},
    ])
    with pytest.raises(CompilerError, match="prompt"):
        WorkflowCompiler().compile(raw, registry)


def test_empty_subagent_steps_rejected(registry):
    raw = _wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "steps": []}},
    ])
    with pytest.raises(CompilerError, match="subagents.steps"):
        WorkflowCompiler().compile(raw, registry)


def test_three_custom_instances_get_distinct_agent_ids(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "custom-agent", "instance_id": n, "prompt": "x"} for n in ("a", "b", "c")
    ]), registry)
    assert [s.agent_id for s in compiled.steps] == [
        "custom-agent:a", "custom-agent:b", "custom-agent:c"]


def test_builtin_step_agent_id_unchanged(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "demo-agent"},
    ]), registry)
    assert compiled.steps[0].agent_id == "demo-agent"


# ---------------------------------------------------------------------------
# T12 — subagents compiles to steps plus edges
# ---------------------------------------------------------------------------


def test_children_precede_parent_in_compiled_order(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "steps": [
             {"agent": "custom-agent", "instance_id": "child-a", "prompt": "a"},
             {"agent": "custom-agent", "instance_id": "child-b", "prompt": "b"},
         ]}},
    ]), registry)
    ids = [s.agent_id for s in compiled.steps]
    assert ids == [
        "custom-agent:child-a", "custom-agent:child-b", "custom-agent:parent",
    ]


def test_parent_depends_on_every_child(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "steps": [
             {"agent": "custom-agent", "instance_id": "child-a", "prompt": "a"},
             {"agent": "custom-agent", "instance_id": "child-b", "prompt": "b"},
         ]}},
    ]), registry)
    parent = next(s for s in compiled.steps if s.agent_id == "custom-agent:parent")
    assert set(parent.depends_on) == {
        "custom-agent:child-a", "custom-agent:child-b",
    }


def test_two_level_tree_is_depth_first(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "steps": [
             {"agent": "custom-agent", "instance_id": "child", "prompt": "c",
              "subagents": {"mode": "parallel", "steps": [
                  {"agent": "custom-agent", "instance_id": "grandchild",
                   "prompt": "g"},
              ]}},
         ]}},
    ]), registry)
    ids = [s.agent_id for s in compiled.steps]
    assert ids == [
        "custom-agent:grandchild", "custom-agent:child", "custom-agent:parent",
    ]
    child = next(s for s in compiled.steps if s.agent_id == "custom-agent:child")
    parent = next(s for s in compiled.steps if s.agent_id == "custom-agent:parent")
    assert child.depends_on == ["custom-agent:grandchild"]
    assert parent.depends_on == ["custom-agent:child"]


def test_existing_parent_depends_on_is_preserved_not_overwritten(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "demo-agent"},
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "depends_on": ["demo-agent"],
         "subagents": {"mode": "parallel", "steps": [
             {"agent": "custom-agent", "instance_id": "child", "prompt": "c"},
         ]}},
    ]), registry)
    parent = next(s for s in compiled.steps if s.agent_id == "custom-agent:parent")
    assert set(parent.depends_on) == {"demo-agent", "custom-agent:child"}


# ---------------------------------------------------------------------------
# T13 — parallel and sequential semantics
# ---------------------------------------------------------------------------


def test_sequential_produces_a_sibling_chain_of_edges(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "sequential", "steps": [
             {"agent": "custom-agent", "instance_id": "child-a", "prompt": "a"},
             {"agent": "custom-agent", "instance_id": "child-b", "prompt": "b"},
             {"agent": "custom-agent", "instance_id": "child-c", "prompt": "c"},
         ]}},
    ]), registry)
    by_id = {s.agent_id: s for s in compiled.steps}
    assert by_id["custom-agent:child-a"].depends_on == []
    assert by_id["custom-agent:child-b"].depends_on == ["custom-agent:child-a"]
    assert by_id["custom-agent:child-c"].depends_on == ["custom-agent:child-b"]
    assert set(by_id["custom-agent:parent"].depends_on) == {
        "custom-agent:child-a", "custom-agent:child-b", "custom-agent:child-c",
    }


def test_parallel_produces_no_edges_between_siblings(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "steps": [
             {"agent": "custom-agent", "instance_id": "child-a", "prompt": "a"},
             {"agent": "custom-agent", "instance_id": "child-b", "prompt": "b"},
             {"agent": "custom-agent", "instance_id": "child-c", "prompt": "c"},
         ]}},
    ]), registry)
    by_id = {s.agent_id: s for s in compiled.steps}
    assert by_id["custom-agent:child-a"].depends_on == []
    assert by_id["custom-agent:child-b"].depends_on == []
    assert by_id["custom-agent:child-c"].depends_on == []


# ---------------------------------------------------------------------------
# T34 — a declared 'parallel' max_parallel is rejected, not silently ignored
# ---------------------------------------------------------------------------


def test_parallel_max_parallel_now_binds_the_fanout_semaphore(registry):
    """T34 rejected max_parallel on a 'parallel' group because nothing honored it.

    It now binds: the group compiles to a `parallel_group` step whose
    `FanoutSpec.max_parallel` becomes the kernel's `asyncio.Semaphore` bound
    (clamped to DEFAULT_MAX_CONCURRENCY at run time). Accepting a declared bound
    is only correct BECAUSE it is now honored — the old rejection was right for
    the old behavior.
    """
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "max_parallel": 3, "steps": [
             {"agent": "custom-agent", "instance_id": "child-a", "prompt": "a"},
             {"agent": "custom-agent", "instance_id": "child-b", "prompt": "b"},
         ]}},
    ]), registry)
    parent = next(s for s in compiled.steps if s.agent_id == "custom-agent:parent")
    assert parent.strategy == "parallel_group"
    assert parent.fanout is not None
    assert parent.fanout.max_parallel == 3
    assert parent.fanout.workers == ["custom-agent:child-a", "custom-agent:child-b"]

    # The children stay in the plan but leave the SERIAL dispatch — running them
    # both in the loop AND as spawned workers would run each twice.
    children = [s for s in compiled.steps if s.agent_id != "custom-agent:parent"]
    assert {c.agent_id for c in children} == {
        "custom-agent:child-a", "custom-agent:child-b"
    }
    assert all(c.dispatched_by == "custom-agent:parent" for c in children)

    # run_fanout rejects a named worker absent from allowed_workers before it
    # spawns, so the children must be auto-allow-listed or the run would raise.
    assert set(compiled.allowed_workers) >= {
        "custom-agent:child-a", "custom-agent:child-b"
    }


@pytest.mark.parametrize("bad", [0, -1, "3", 1.5, True])
def test_parallel_max_parallel_must_be_a_positive_int(registry, bad):
    """A nonsensical bound fails at compile time, not silently at run time.

    `True` is in the list on purpose: it is an `int` in Python, and without an
    explicit bool check `max_parallel: true` would compile to a semaphore of 1.
    """
    raw = _wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {"mode": "parallel", "max_parallel": bad, "steps": [
             {"agent": "custom-agent", "instance_id": "child-a", "prompt": "a"},
         ]}},
    ])
    with pytest.raises(CompilerError, match="max_parallel"):
        WorkflowCompiler().compile(raw, registry)


# ---------------------------------------------------------------------------
# T14 — fanout as an adapter over the existing FanoutSpec/run_fanout machinery
# ---------------------------------------------------------------------------


def test_fanout_group_materializes_fanout_spec_and_task_source(registry):
    compiled = WorkflowCompiler().compile(_wf(steps=[
        {"agent": "demo-agent", "instance_id": "plan"},
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {
             "mode": "fanout",
             "max_parallel": 5,
             "task_source": {
                 "kind": "parsed", "parser": "heading_tasks",
                 "target": "tasks.md", "source_step": "demo-agent",
             },
             "steps": [
                 {"agent": "custom-agent", "instance_id": "worker", "prompt": "w"},
             ],
         }},
    ]), registry)
    worker = next(s for s in compiled.steps if s.agent_id == "custom-agent:worker")
    assert worker.strategy == "fanout_batch"
    assert worker.fanout is not None
    assert worker.fanout.mode == "parallel"
    assert worker.fanout.max_parallel == 5
    assert worker.fanout.agent == "self"
    assert worker.task_source is not None
    assert worker.task_source.source_step == "demo-agent"
    parent = next(s for s in compiled.steps if s.agent_id == "custom-agent:parent")
    assert parent.depends_on == ["custom-agent:worker"]
    ids = [s.agent_id for s in compiled.steps]
    assert ids.index("custom-agent:worker") < ids.index("custom-agent:parent")


def test_fanout_group_with_multiple_children_rejected(registry):
    raw = _wf(steps=[
        {"agent": "custom-agent", "instance_id": "parent", "prompt": "p",
         "subagents": {
             "mode": "fanout",
             "task_source": {"kind": "parsed", "parser": "heading_tasks",
                              "target": "tasks.md"},
             "steps": [
                 {"agent": "custom-agent", "instance_id": "worker-a", "prompt": "a"},
                 {"agent": "custom-agent", "instance_id": "worker-b", "prompt": "b"},
             ],
         }},
    ])
    with pytest.raises(CompilerError, match="fanout"):
        WorkflowCompiler().compile(raw, registry)
