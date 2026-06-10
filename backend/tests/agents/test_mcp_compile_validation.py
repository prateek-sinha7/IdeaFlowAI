"""MCP-03 Wave-0 acceptance: the compiler's tools.mcp server.tool compile-validation.

  * an ``unknown_server.tool`` reference → ``CompilerError`` naming the offending
    ``server.tool``;
  * a server.tool whose TOOL is not in the exposed-tool allow-list → CompilerError;
  * a reference missing the ``.`` separator → CompilerError;
  * a ``user_allowed=false`` server (filesystem) in a USER/DB manifest → CompilerError
    (CAP-03);
  * a valid read-scoped reference compiles cleanly (and lands on the Step's effective
    tools).
"""

from __future__ import annotations

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry, discover, register
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest

def _manifest_with_mcp(
    mcp_refs: list[str],
    *,
    gates: list | None = None,
    secrets: list | None = None,
    strategy: str = "single_shot",
) -> WorkflowManifest:
    tools: dict = {"mcp": list(mcp_refs)}
    if secrets is not None:
        tools["secrets"] = list(secrets)
    step: dict = {"agent": "demo-agent", "strategy": strategy, "tools": tools}
    if gates is not None:
        step["gates"] = list(gates)
    return WorkflowManifest(
        id="mcp-demo",
        steps=[step],
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


@pytest.fixture
def registry() -> CapabilityRegistry:
    discover()
    return CapabilityRegistry()


@pytest.fixture
def user_allowed_strategy():
    """Register a throwaway user_allowed strategy + restore the registry after.

    A USER/DB manifest must reference a user_allowed strategy or it trips the
    strategy trust check before reaching the mcp validation. We register one so the
    test isolates the mcp-specific CAP-03 rejection.
    """
    discover()
    known = set(registry_mod._KNOWN)
    impls = dict(registry_mod._IMPLS)
    trust = dict(registry_mod._TRUST)
    discovered = registry_mod._DISCOVERED

    @register("strategy", "user_ok_strategy", user_allowed=True)
    class _UserOkStrategy:
        name = "user_ok_strategy"

    try:
        yield "user_ok_strategy"
    finally:
        registry_mod._KNOWN.clear(); registry_mod._KNOWN.update(known)
        registry_mod._IMPLS.clear(); registry_mod._IMPLS.update(impls)
        registry_mod._TRUST.clear(); registry_mod._TRUST.update(trust)
        registry_mod._DISCOVERED = discovered


def test_unknown_server_tool_is_rejected(registry) -> None:
    manifest = _manifest_with_mcp(["unknown_server.do_thing"])
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, registry, trust="file")
    assert "unknown_server.do_thing" in str(exc.value)


def test_tool_not_in_exposed_allow_list_is_rejected(registry) -> None:
    # gitlab is registered + read-scoped, but `delete_everything` is not exposed.
    manifest = _manifest_with_mcp(["gitlab.delete_everything"])
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, registry, trust="file")
    assert "gitlab.delete_everything" in str(exc.value)


def test_missing_separator_is_rejected(registry) -> None:
    manifest = _manifest_with_mcp(["gitlab"])  # no `.tool`
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, registry, trust="file")
    assert "server.tool" in str(exc.value)


def test_user_manifest_rejects_not_user_allowed_server(registry, user_allowed_strategy) -> None:
    # filesystem is user_allowed=False → a USER manifest may not reference it. Use a
    # user_allowed strategy so the mcp CAP-03 rejection is what fires (not the strategy).
    # No security gate here — the `security` gate is itself not user_allowed and
    # would pre-empt the mcp check. The filesystem reference alone triggers the
    # mcp-CAP-03 rejection in a user manifest.
    manifest = _manifest_with_mcp(
        ["filesystem.read_file"],
        strategy=user_allowed_strategy,
    )
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, registry, trust="user")
    assert "filesystem" in str(exc.value)


def test_valid_read_scoped_reference_compiles(registry) -> None:
    # A valid read-scoped reference compiles WITHOUT error (the §8 least-privilege
    # ceiling collapses the effective tools.mcp to [] — the validation runs on the
    # declared grant, not the post-intersection ceiling; "compiles" is the acceptance).
    manifest = _manifest_with_mcp(["gitlab.list_issues"])
    compiled = WorkflowCompiler().compile(manifest, registry, trust="file")
    assert compiled.steps[0].agent_id == "demo-agent"


def test_valid_read_scoped_reference_compiles_in_user_manifest(registry, user_allowed_strategy) -> None:
    # A read-scoped (user_allowed=True) server is fine even in a user manifest.
    manifest = _manifest_with_mcp(["jira.search_issues"], strategy=user_allowed_strategy)
    compiled = WorkflowCompiler().compile(manifest, registry, trust="user")
    assert compiled.steps[0].agent_id == "demo-agent"
