"""MCP-04 Wave-0 acceptance: security-gate + secrets gating for powerful MCP servers.

  * a powerful/write server (filesystem/postgres) without the ``security`` gate +
    a ``secrets`` grant → ``CompilerError`` (MCP-04);
  * the same powerful server WITH ``security`` gate + ``secrets`` compiles (in a
    TRUSTED manifest — a user manifest can never reference it at all, CAP-03);
  * a read-scoped server (gitlab_read / jira_read) binds UNGATED (no security gate,
    no secrets).
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest


def _manifest(mcp_refs: list[str], *, gates: list | None = None, secrets: list | None = None) -> WorkflowManifest:
    tools: dict = {"mcp": list(mcp_refs)}
    if secrets is not None:
        tools["secrets"] = list(secrets)
    step: dict = {"agent": "demo-agent", "strategy": "single_shot", "tools": tools}
    if gates is not None:
        step["gates"] = list(gates)
    return WorkflowManifest(
        id="mcp-gate-demo",
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


def test_powerful_server_without_security_and_secrets_is_rejected(registry) -> None:
    # filesystem is powerful → without security+secrets it must fail (TRUSTED manifest,
    # so CAP-03 does not pre-empt the gating check).
    manifest = _manifest(["filesystem.read_file"])
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, registry, trust="file")
    assert "MCP-04" in str(exc.value) or "powerful" in str(exc.value)


def test_powerful_server_with_security_but_no_secrets_is_rejected(registry) -> None:
    manifest = _manifest(["postgres.query"], gates=["security"])  # no secrets grant
    with pytest.raises(CompilerError):
        WorkflowCompiler().compile(manifest, registry, trust="file")


def test_powerful_server_with_security_and_secrets_compiles(registry) -> None:
    # WITH the security gate + a secrets grant, the powerful server passes the MCP-04
    # gate and the manifest compiles cleanly (the §8 ceiling then collapses the
    # effective tools.mcp to [] — gating is about acceptance, not the post-ceiling set).
    manifest = _manifest(
        ["filesystem.read_file"], gates=["security"], secrets=["filesystem"]
    )
    compiled = WorkflowCompiler().compile(manifest, registry, trust="file")
    assert "security" in (compiled.steps[0].gates or [])


def test_read_scoped_server_binds_ungated(registry) -> None:
    # gitlab_read binds with NO security gate and NO secrets — ungated (compiles clean).
    manifest = _manifest(["gitlab.list_issues"])
    compiled = WorkflowCompiler().compile(manifest, registry, trust="file")
    # It required no security gate.
    assert "security" not in (compiled.steps[0].gates or [])
