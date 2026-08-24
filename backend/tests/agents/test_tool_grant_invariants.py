"""Tool-permission invariants — the manifest decides, the cap bounds it.

WHAT THIS PINS
--------------
Tool access is resolved from the **workflow manifest**, not from a conditional in
application code:

```
step ``tools:``  ──intersect──▶  cap (permission_caps.PERMISSION_CAP_INDEX)
                                   │
                                   ▼
                          Step.tools (effective)
                                   │  engine threads it onto AgentContext
                                   ▼
                    factory.denied_tools  ──▶  DeepAgentRunner(denied_tools=…)
                                                        │
                                                        ▼
                                            tools the model is offered
```

Three properties, one per seam:

1. **The cap bounds the request.** A step cannot obtain a privilege its trust
   level's cap withholds. The cap lives in ONE file and nothing else may declare
   a ceiling.
2. **The grant flows.** What the manifest asks for is what reaches the factory,
   and the factory denies exactly the tool names the permissions do not grant.
3. **Absent means unrestricted, not denied.** An invocation with no compiled step
   (revision agents, fix agents, direct `create_runner` in tests) narrows nothing
   — otherwise this change would silently strip tools from every path that does
   not thread a Step through.

WHY IT EXISTS
-------------
Spec 012's R-22 grant bound the filesystem to every agent declaring `tools: []`,
regardless of what any manifest said. `story-estimator` — whose job is story
points — wrote a 20 KB backlog into the sandbox instead of returning it, where
the `streamed_text` deliverable could not see it. The failure was that **no
manifest had a say**: the decision was a constant in `_resolve_runner_tools`.

These tests exist to keep the decision in the manifest.

NOT PINNED HERE
---------------
Whether a given agent *should* be granted write — that is a workflow authoring
choice now, deliberately not a code invariant. `agents/workflows/user_stories/
workflow.yaml` is currently set to REPRODUCE (write granted) for the A/B; that is
a config state, not a regression.
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest
from agents.workflows.permission_caps import (
    GATED_TOOLS,
    PERMISSION_CAP_INDEX,
    PERMISSION_TOOLS,
    cap_for_trust,
    cap_key_for_trust,
    denied_tools,
    granted_tools,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compile(tools: dict | None, *, trust: str = "file", agent: str = "custom-agent"):
    """Compile a one-step manifest and return the step's EFFECTIVE permissions."""
    step: dict = {"agent": agent, "strategy": "single_shot"}
    if tools is not None:
        step["tools"] = tools
    manifest = WorkflowManifest(
        id="perm-test",
        steps=[step],
        deliverable={},
        planner="skip",
        clarify={"mode": "skip", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust=trust)
    return compiled.steps[0].tools


# ===========================================================================
# §1 — The cap bounds the request
# ===========================================================================


def test_the_cap_index_is_the_only_ceiling() -> None:
    """Exactly two caps exist, and both are declared in ``permission_caps``.

    The point of extracting the ceiling into its own module is that you can read
    one table instead of grepping the compiler. If a third cap key appears, or a
    key is renamed, that is a design change that should be made deliberately.
    """
    assert set(PERMISSION_CAP_INDEX) == {"trusted", "untrusted"}


def test_unknown_trust_falls_to_the_restrictive_cap() -> None:
    """Fail closed. An unrecognised trust level must never resolve to ``trusted``."""
    for trust in (None, "", "nonsense", "USER", "File"):
        assert cap_key_for_trust(trust) == "untrusted", trust


@pytest.mark.parametrize("trust", ["file", "builtin"])
def test_engineer_authored_manifests_may_hold_privileged_capabilities(trust: str) -> None:
    """The trusted cap PERMITS exec/spawn — it does not grant them.

    Permitted-by-cap and granted-to-a-step are different things: a step still has
    to ask, and `ToolPermissions` defaults these off.
    """
    cap = cap_for_trust(trust)
    assert cap.exec is True
    assert cap.spawn_subagents is True


@pytest.mark.parametrize("trust", ["user", "db"])
def test_user_authored_manifests_cannot_hold_privileged_capabilities(trust: str) -> None:
    """The untrusted cap withholds the privileges that escape the sandbox."""
    cap = cap_for_trust(trust)
    assert cap.exec is False
    assert cap.spawn_subagents is False


def test_write_is_permitted_under_both_caps() -> None:
    """Writes are sandbox-confined (``FilesystemBackend(virtual_mode=True)``).

    A Composer-authored workflow must be able to grant its agents write, or
    composed workflows cannot produce files at all. This is the property that
    makes the cap a *ceiling* rather than a blanket denial.
    """
    assert cap_for_trust("file").write_files is True
    assert cap_for_trust("user").write_files is True


def test_a_step_cannot_exceed_its_cap() -> None:
    """The intersection can only narrow.

    ``exec`` is rejected outright for untrusted manifests by an upstream guard
    (fail-loud, naming the offending grant) — assert that rather than a silent
    downgrade, since a silent one would hide an authoring mistake.
    """
    with pytest.raises(CompilerError) as exc:
        _compile({"read_files": True, "exec": True}, trust="user")
    assert "exec" in str(exc.value)


def test_a_step_gets_what_it_asks_for_within_the_cap() -> None:
    """The whole point: the manifest decides."""
    perms = _compile({"read_files": True, "write_files": True}, trust="user")
    assert perms.read_files is True
    assert perms.write_files is True


def test_a_step_declaring_nothing_is_read_only() -> None:
    """Least privilege: absent means read, never write."""
    perms = _compile(None)
    assert perms.read_files is True
    assert perms.write_files is False
    assert perms.exec is False


# ===========================================================================
# §2 — The grant reaches the tools
# ===========================================================================


def test_every_gated_tool_is_claimed_by_exactly_one_permission() -> None:
    """The mapping table must not double-gate or silently drop a tool."""
    seen: set[str] = set()
    for tools in PERMISSION_TOOLS.values():
        assert not (seen & tools), f"tool gated by two permissions: {seen & tools}"
        seen |= tools
    assert seen == GATED_TOOLS


def test_ungranted_write_denies_the_write_tools() -> None:
    """A read-only step cannot reach ``write_file`` / ``edit_file``.

    This is the defect, stated as an assertion: `story-estimator` under a
    read-only grant must not be able to write its output to the sandbox.
    """
    denied = denied_tools(_compile({"read_files": True}))
    assert "write_file" in denied
    assert "edit_file" in denied
    assert "read_file" not in denied


def test_granted_write_leaves_the_write_tools_bound() -> None:
    """And the reproduce case: granted write really is granted."""
    denied = denied_tools(_compile({"read_files": True, "write_files": True}))
    assert "write_file" not in denied
    assert "edit_file" not in denied


def test_ungranted_read_denies_the_read_tools() -> None:
    """Read is a permission like any other, not an unconditional floor."""
    denied = denied_tools(_compile({"read_files": False}))
    assert {"read_file", "ls", "glob", "grep"} <= denied


def test_no_compiled_step_narrows_nothing() -> None:
    """Back-compat, and the reason this change is safe to land.

    Revision agents, fix agents and every test that calls ``create_runner``
    directly bind no compiled Step. Those paths must behave exactly as they did
    before permissions were threaded through — otherwise this silently strips
    tools from code that never opted in.
    """
    assert denied_tools(None) == frozenset()


# ===========================================================================
# §3 — The declared workflows still resolve
# ===========================================================================


def test_every_builtin_workflow_compiles_and_writers_keep_write() -> None:
    """Every shipped workflow compiles, and no agent that writes lost its grant.

    Guards the migration: an agent whose ``AGENT.md`` declares a filesystem tool
    set needs a matching ``tools:`` grant on its step, or it silently degrades to
    read-only and produces nothing. Derived from what is on disk, so a newly
    added writing agent is covered without editing this test.
    """
    import re
    from pathlib import Path

    import yaml

    from agents.execution_engine.engine import compile_for_run

    prompts = Path("agents/prompts")
    declares_fs: set[str] = set()
    for agent_md in prompts.glob("*/AGENT.md"):
        match = re.search(r"^---\n(.*?)\n---", agent_md.read_text(encoding="utf-8"), re.S)
        frontmatter = yaml.safe_load(match.group(1)) if match else {}
        if frontmatter.get("tools"):
            declares_fs.add(agent_md.parent.name)

    missing: list[str] = []
    for workflow_yaml in sorted(Path("agents/workflows").glob("*/workflow.yaml")):
        pipeline = workflow_yaml.parent.name
        compiled = compile_for_run(pipeline)
        for step in compiled.steps:
            if step.agent_id in declares_fs and not step.tools.write_files:
                missing.append(f"{pipeline}:{step.agent_id}")

    assert not missing, (
        "these agents declare a filesystem tool set but their workflow step does "
        f"not grant write — they will silently produce nothing: {missing}"
    )
