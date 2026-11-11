"""Unit tests for ``app.agents.workflow_builder.launch_needs``.

Requirements: 7.13, 23.17 (launch needs derived from the manifest), 49.2.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.workflow_builder.events import LaunchNeed
from app.agents.workflow_builder.launch_needs import derive


def _step(**tools: Any) -> dict[str, Any]:
    return {"agent": "agent-a", "tools": tools}


def _pairs(manifest: dict[str, Any]) -> list[tuple[str, str | None]]:
    return [(n.kind, n.detail) for n in derive(manifest)]


def test_derive_returns_nothing_when_manifest_has_no_signals() -> None:
    assert derive({"steps": [{"agent": "agent-a"}]}) == []


def test_derive_returns_nothing_when_manifest_is_empty() -> None:
    assert derive({}) == []


def test_derive_asks_for_uploads_when_uploaded_files_provider_is_set() -> None:
    manifest = {"steps": [], "context_providers": ["uploaded_files"]}

    assert derive(manifest) == [LaunchNeed(kind="uploads")]


def test_derive_asks_for_uploads_when_step_uses_file_extract() -> None:
    manifest = {"steps": [_step(tool_sets=["file_extract"])]}

    assert _pairs(manifest) == [("uploads", None)]


def test_derive_asks_for_uploads_once_when_both_signals_are_present() -> None:
    manifest = {
        "context_providers": ["uploaded_files"],
        "steps": [_step(tool_sets=["file_extract"])],
    }

    assert _pairs(manifest) == [("uploads", None)]


def test_derive_asks_for_design_when_opendesign_provider_is_set() -> None:
    manifest = {"steps": [], "context_providers": ["opendesign"]}

    assert _pairs(manifest) == [("design", None)]


def test_derive_names_server_when_step_has_mcp_entry() -> None:
    manifest = {"steps": [_step(mcp=["docs.search"])]}

    assert _pairs(manifest) == [("connector", "docs")]


def test_derive_names_one_connector_when_two_entries_share_a_server() -> None:
    manifest = {"steps": [_step(mcp=["docs.search", "docs.fetch"])]}

    assert _pairs(manifest) == [("connector", "docs")]


@pytest.mark.parametrize(
    ("scope", "server"),
    [
        ("github_read", "github"),
        ("gitlab_read", "gitlab"),
        ("jira_read", "jira"),
        ("slack_post", "slack"),
        ("notion", "notion"),
    ],
)
def test_derive_maps_scope_to_server_when_step_has_integrations(
    scope: str, server: str
) -> None:
    manifest = {"steps": [_step(integrations=[scope])]}

    assert _pairs(manifest) == [("connector", server)]


def test_derive_merges_connectors_when_mcp_and_integration_name_one_server() -> None:
    manifest = {"steps": [_step(mcp=["github.search"], integrations=["github_read"])]}

    assert _pairs(manifest) == [("connector", "github")]


def test_derive_asks_for_source_run_when_seed_files_from_run_is_not_empty() -> None:
    manifest = {"steps": [], "seed_files": {"from_run": ["notes.md"]}}

    assert _pairs(manifest) == [("source_run", None)]


@pytest.mark.parametrize("seed_files", [{"from_run": []}, {}, "x", None])
def test_derive_skips_source_run_when_from_run_is_empty_or_malformed(
    seed_files: object,
) -> None:
    assert derive({"steps": [], "seed_files": seed_files}) == []


def test_derive_adds_no_need_when_previous_run_provider_is_set() -> None:
    manifest = {"steps": [], "context_providers": ["previous_run"]}

    assert derive(manifest) == []


def test_derive_orders_needs_when_every_signal_is_present() -> None:
    manifest = {
        "context_providers": ["opendesign", "uploaded_files"],
        "seed_files": {"from_run": ["a.md"]},
        "steps": [_step(mcp=["zeta.go", "alpha.go"])],
    }

    assert _pairs(manifest) == [
        ("uploads", None),
        ("design", None),
        ("connector", "alpha"),
        ("connector", "zeta"),
        ("source_run", None),
    ]


def test_derive_reads_nested_steps_when_signal_is_under_subagents() -> None:
    inner = _step(tool_sets=["file_extract"], mcp=["docs.search"])
    manifest = {
        "steps": [
            {"agent": "agent-a", "subagents": {"agent": "self", "steps": [inner]}}
        ]
    }

    assert _pairs(manifest) == [("uploads", None), ("connector", "docs")]


def test_derive_ignores_malformed_values_when_fields_have_wrong_types() -> None:
    manifest = {
        "context_providers": "uploaded_files",
        "steps": [
            "text",
            {"agent": "a", "tools": "x"},
            {"agent": "a", "tools": {"mcp": "docs.search", "tool_sets": [1]}},
        ],
    }

    assert derive(manifest) == []
