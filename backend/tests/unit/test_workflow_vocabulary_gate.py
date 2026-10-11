"""ADR-0002 Option 3 — `pipeline_type` is the permanent on-disk / on-wire name.

ADR-0002 originally decided that the legacy `pipeline` vocabulary would be
removed from the files it governs. That rename was formally deferred
indefinitely (2026-09-03, Option 3) because:

  1. DB columns carry the `pipeline_type` name (`base_pipeline_type`,
     `overrides_pipeline_type`) and column renames are non-additive,
     violating the project's additive-only migrations invariant.
  2. The identifier is the public wire-protocol key (SSE event payloads)
     consumed across the frontend and by external clients — renaming it is a
     breaking API change requiring a coordinated versioned release.

This file used to hold the old "no `pipeline` vocabulary" gate under a
permanent ``@pytest.mark.skip``. A permanently skipped test checks nothing and
counts as a failure in CI's mandatory offline partition, so it is rewritten to
pin the decision Option 3 actually made: the load-bearing `pipeline_type` names
stay. A partial, unplanned rename — the failure mode Option 3 exists to prevent —
fails here instead of breaking the wire contract or requiring a
non-additive migration.

New surfaces may still use `workflow` vocabulary; this only guards the
existing names ADR-0002 Option 3 declared permanent.
"""

from __future__ import annotations

import pytest


@pytest.mark.issue("ADR-0002")
@pytest.mark.parametrize("column", ["base_pipeline_type", "overrides_pipeline_type"])
def test_workflow_definition_keeps_pipeline_type_column_when_rename_is_deferred(
    column: str,
) -> None:
    """The saved-workflow table keeps its `pipeline_type`-named columns.

    Renaming either needs a non-additive migration, which the additive-only
    invariant forbids (ADR-0002 Option 3, reason 1).
    """
    from app.models.workflow_definition import WorkflowDefinition

    columns = {c.name for c in WorkflowDefinition.__table__.columns}
    assert column in columns, (
        f"workflows.{column} is gone — ADR-0002 Option 3 keeps it permanently; a "
        "rename is a non-additive migration and needs a superseding ADR"
    )


@pytest.mark.issue("ADR-0002")
def test_pipeline_complete_contract_keeps_pipeline_type_when_rename_is_deferred() -> (
    None
):
    """The documented wire contract still requires `pipeline_type` on completion.

    Clients read it off this event; dropping or renaming it is a breaking API
    change (ADR-0002 Option 3, reason 2).
    """
    from tests.unit.agents.test_phase3_cutover_verify import _REQUIRED_DATA_KEYS

    assert "pipeline_type" in _REQUIRED_DATA_KEYS["pipeline_complete"], (
        "pipeline_complete no longer requires 'pipeline_type' in the documented "
        "wire contract — ADR-0002 Option 3 keeps it permanently"
    )


@pytest.mark.issue("ADR-0002")
def test_pipeline_start_golden_keeps_pipeline_type_when_rename_is_deferred() -> None:
    """The committed characterization golden pins `pipeline_type` on pipeline_start.

    ``pipeline_start`` is not in the required-keys table, so the golden (INV-3,
    byte-identical) is the contract that pins its payload.
    """
    from tests.agents.characterization._normalize import load_events_golden

    golden = load_events_golden("prototype.events.json")
    assert golden, "prototype.events.json golden missing"
    starts = [e for e in golden if e.get("type") == "pipeline_start"]
    assert starts, "prototype golden has no pipeline_start event"
    assert all("pipeline_type" in e.get("data", {}) for e in starts), (
        "pipeline_start lost its 'pipeline_type' key — ADR-0002 Option 3 keeps it "
        "permanently on the wire"
    )
