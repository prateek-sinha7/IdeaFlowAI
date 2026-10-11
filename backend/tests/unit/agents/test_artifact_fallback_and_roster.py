"""spec 012 T16/T17 — the artifact guarantee + the roster block (engine.py).

Offline unit tests against the two ``ExecutionEngine`` helper methods the
per-step dispatch loop calls (no live model, no full ``execute()`` drive —
both helpers are pure w.r.t. a fake ``ectx``/``Step`` and a real, temp-dir
``RunSandbox``):

  * ``ExecutionEngine._check_artifact_fallback`` (T16 / R-20 / D-06 / F-06):
    after a custom-agent step completes, the engine verifies its artifact
    landed in the sandbox; if not, it writes the streamed text there itself
    and reports the filename so the caller can emit ``artifact_fallback``.
  * ``ExecutionEngine._build_roster`` (T17 / R-15 / D-05 / R-21): before a
    parent step with children runs, the engine builds its roster block from
    the artifacts that ACTUALLY exist in the sandbox — never the manifest —
    so a failed child (no artifact) simply has no line.
"""

from __future__ import annotations

from types import SimpleNamespace

from agents.execution_engine.engine import ExecutionEngine
from agents.workflows.artifacts import artifact_name, topic_slug
from agents.workflows.plan import Step, ToolPermissions
from app.agents.sandbox import RunSandbox


def _sandbox(tmp_path, name: str) -> RunSandbox:
    return RunSandbox("t012-user", name, runs_root=str(tmp_path))


# ---------------------------------------------------------------------------
# T16 — _check_artifact_fallback
# ---------------------------------------------------------------------------


def test_artifact_fallback_writes_missing_file_and_returns_filename(tmp_path):
    """An agent that streams and writes nothing still leaves the file — the
    engine writes the streamed text to the exact filename artifact_name()
    produces and reports it fired."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-1")
    ectx = SimpleNamespace(topic="crm-rollout")

    result = engine._check_artifact_fallback(
        ectx,
        "custom-agent:research-a",
        "the streamed text",
        sandbox,
        "Build a CRM",
    )

    expected = artifact_name("research-a", "crm-rollout")
    assert result == expected
    assert sandbox.read(expected) == "the streamed text"


def test_artifact_fallback_noop_when_file_already_exists(tmp_path):
    """When the agent DID write its file, the engine leaves it alone and
    reports no fallback fired (never overwrites a real deliverable)."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-2")
    ectx = SimpleNamespace(topic="crm-rollout")
    filename = artifact_name("research-a", "crm-rollout")
    sandbox.write(filename, "the agent's real deliverable")

    result = engine._check_artifact_fallback(
        ectx,
        "custom-agent:research-a",
        "streamed text (should be ignored)",
        sandbox,
        "Build a CRM",
    )

    assert result is None
    assert sandbox.read(filename) == "the agent's real deliverable"


def test_artifact_fallback_noop_for_non_custom_agent_step(tmp_path):
    """A built-in agent step is untouched — R-16 parity, the guarantee is
    custom-agent-only."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-3")
    ectx = SimpleNamespace(topic="crm-rollout")

    result = engine._check_artifact_fallback(
        ectx,
        "domain-analyst",
        "streamed text",
        sandbox,
        "Build a CRM",
    )

    assert result is None


def test_artifact_fallback_computes_topic_when_ectx_carries_none(tmp_path):
    """Defensive fallback: an ectx without ``.topic`` set (e.g. a direct
    unit-style call) still resolves via ``topic_slug(user_message)``."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-4")
    ectx = SimpleNamespace()  # no .topic attribute at all

    result = engine._check_artifact_fallback(
        ectx,
        "custom-agent:research-a",
        "streamed text",
        sandbox,
        "Build a CRM!",
    )

    assert result == artifact_name("research-a", topic_slug("Build a CRM!"))


def test_artifact_fallback_skips_write_when_publish_from_glob_declared(tmp_path):
    """A workflow that declares deliverable.publish_from_glob (e.g.
    pdf_to_prototype) publishes its named deliverable mechanically at end of
    run — the fallback must not clobber that exact filename with agent
    narration. It still reports the filename (diagnosable via
    artifact_fallback) but leaves the sandbox untouched."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-5")
    deliverable = SimpleNamespace(
        name="prototype.html",
        publish_from_glob="draft.v*.html",
    )
    ectx = SimpleNamespace(topic="crm-rollout", deliverable=deliverable)

    result = engine._check_artifact_fallback(
        ectx,
        "custom-agent:story-layer",
        "narration text",
        sandbox,
        "Build a CRM",
        deliverable_filename="prototype.html",
    )

    assert result == "prototype.html"
    assert sandbox.read("prototype.html") is None


def test_artifact_fallback_writes_when_no_publish_from_glob_declared(tmp_path):
    """Unchanged behaviour: a deliverable with no publish_from_glob (or no
    deliverable at all) still gets the fallback write."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-6")
    deliverable = SimpleNamespace(name="prototype.html", publish_from_glob=None)
    ectx = SimpleNamespace(topic="crm-rollout", deliverable=deliverable)

    result = engine._check_artifact_fallback(
        ectx,
        "custom-agent:story-layer",
        "narration text",
        sandbox,
        "Build a CRM",
        deliverable_filename="prototype.html",
    )

    assert result == "prototype.html"
    assert sandbox.read("prototype.html") == "narration text"


def test_artifact_fallback_overwrites_on_retry_when_step_cannot_write(tmp_path):
    """L4 gap: a looped/retried step (R-06/R-07, e.g. ex_A1_loop's `greet`) has
    ``tools: {write_files: false}`` and re-dispatches with the SAME filename every
    pass. Pass 1's fallback write must not make passes 2+ silently no-op — the
    model has no write tool, so it can never be the one who "already wrote" the
    file; the existing content is always stale fallback residue from an earlier
    pass and must be replaced with this pass's output."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-retry")
    step = Step(
        agent_id="custom-agent:greet",
        instance_id="greet",
        tools=ToolPermissions(write_files=False),
    )
    ectx = SimpleNamespace(topic="loop", current_step=step)
    filename = artifact_name("greet", "loop")
    sandbox.write(filename, "pass 1: plain greeting, no joke")

    result = engine._check_artifact_fallback(
        ectx,
        "custom-agent:greet",
        "pass 2: greeting with a joke this time",
        sandbox,
        "loop",
    )

    assert result == filename
    assert sandbox.read(filename) == "pass 2: greeting with a joke this time"


def test_artifact_fallback_noop_when_file_exists_and_step_can_write(tmp_path):
    """Control for the retry fix above: a step whose effective tools DO grant
    ``write_files`` keeps the original guarantee — an existing file is trusted as
    the model's own deliverable and is never stomped on."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-canwrite")
    step = Step(
        agent_id="custom-agent:research-a",
        instance_id="research-a",
        tools=ToolPermissions(write_files=True),
    )
    ectx = SimpleNamespace(topic="crm-rollout", current_step=step)
    filename = artifact_name("research-a", "crm-rollout")
    sandbox.write(filename, "the agent's real deliverable")

    result = engine._check_artifact_fallback(
        ectx,
        "custom-agent:research-a",
        "streamed text (should be ignored)",
        sandbox,
        "Build a CRM",
    )

    assert result is None
    assert sandbox.read(filename) == "the agent's real deliverable"


# ---------------------------------------------------------------------------
# T17 — _build_roster
# ---------------------------------------------------------------------------


def _children_and_parent():
    child_a = Step(
        agent_id="custom-agent:research-a",
        instance_id="research-a",
        display_name="Research A",
    )
    child_b = Step(
        agent_id="custom-agent:research-b",
        instance_id="research-b",
        display_name="Research B",
    )
    parent = Step(
        agent_id="custom-agent:synthesis",
        instance_id="synthesis",
        display_name="Synthesis",
        depends_on=[child_a.agent_id, child_b.agent_id],
    )
    return child_a, child_b, parent


def test_roster_lists_child_display_names_and_filenames(tmp_path):
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-5")
    child_a, child_b, parent = _children_and_parent()
    topic = "crm-rollout"
    sandbox.write(artifact_name("research-a", topic), "a's output")
    sandbox.write(artifact_name("research-b", topic), "b's output")
    ectx = SimpleNamespace(
        current_step=parent,
        steps_by_agent={
            child_a.agent_id: child_a,
            child_b.agent_id: child_b,
            parent.agent_id: parent,
        },
    )

    roster = engine._build_roster(ectx, topic, sandbox)

    assert roster == (
        "Earlier steps produced:\n"
        "- Research A → research-a-crm-rollout.md\n"
        "- Research B → research-b-crm-rollout.md\n"
        "Read the files you need before you start."
    )


def test_roster_label_changes_when_a_child_is_renamed(tmp_path):
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-6")
    child_a, child_b, parent = _children_and_parent()
    child_a.display_name = "Competitive Landscape Research"
    topic = "crm-rollout"
    sandbox.write(artifact_name("research-a", topic), "a's output")
    sandbox.write(artifact_name("research-b", topic), "b's output")
    ectx = SimpleNamespace(
        current_step=parent,
        steps_by_agent={
            child_a.agent_id: child_a,
            child_b.agent_id: child_b,
            parent.agent_id: parent,
        },
    )

    roster = engine._build_roster(ectx, topic, sandbox)

    assert "Competitive Landscape Research → research-a-crm-rollout.md" in roster
    assert "Research A" not in roster


def test_roster_omits_a_failed_childs_line(tmp_path):
    """A failed child produced no artifact — its line is simply absent (R-21);
    the roster still lists the sibling that succeeded."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-7")
    child_a, child_b, parent = _children_and_parent()
    topic = "crm-rollout"
    # Only child_a wrote its artifact — child_b "failed" (no file at all).
    sandbox.write(artifact_name("research-a", topic), "a's output")
    ectx = SimpleNamespace(
        current_step=parent,
        steps_by_agent={
            child_a.agent_id: child_a,
            child_b.agent_id: child_b,
            parent.agent_id: parent,
        },
    )

    roster = engine._build_roster(ectx, topic, sandbox)

    assert "Research A → research-a-crm-rollout.md" in roster
    assert "Research B" not in roster
    assert "research-b" not in roster


def test_roster_empty_when_step_has_no_children(tmp_path):
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-8")
    leaf = Step(agent_id="custom-agent:solo", instance_id="solo", display_name="Solo")
    ectx = SimpleNamespace(current_step=leaf, steps_by_agent={leaf.agent_id: leaf})

    roster = engine._build_roster(ectx, "crm-rollout", sandbox)

    assert roster == ""


def test_roster_ignores_non_custom_agent_dependencies(tmp_path):
    """A declared depends_on entry that isn't a custom-agent instance (e.g. a
    built-in agent) never contributes a roster line."""
    engine = ExecutionEngine()
    sandbox = _sandbox(tmp_path, "run-9")
    parent = Step(
        agent_id="custom-agent:synthesis",
        instance_id="synthesis",
        display_name="Synthesis",
        depends_on=["domain-analyst"],
    )
    ectx = SimpleNamespace(
        current_step=parent,
        steps_by_agent={"domain-analyst": Step(agent_id="domain-analyst")},
    )

    roster = engine._build_roster(ectx, "crm-rollout", sandbox)

    assert roster == ""
