"""``_project`` must report a MANIFEST row's composition, not the legacy column.

The Saved Workflows card renders ``row.agent_ids.length``
(SavedWorkflowsPage.tsx:329), and the page's "total agents" stat sums the same
field. Both read what ``_project`` puts in ``agent_ids``.

For a Composer (manifest-shaped) workflow that number was frozen at create time:
``saveUserWorkflow`` (frontend lib/api.ts:1801) strips ``agent_ids`` on every
update because PATCH treats the composition as immutable post-create — true for
an ``agent_ids``-backed row, false for a Composer one, where adding, removing and
nesting steps persists through ``manifest_json`` alone.

Live evidence: the "PDF to Prototype" workflow's ``agents`` column held
``["oa2v5f-g5exi0", "oa2v5f-ujt02v", "oa2v5f-l85qm8", "oa2v5f-10piec"]`` — four
ids from its first save, none of which still existed in the composition — while
``manifest_json.steps`` held 12 steps. The card read "4 agents" for a 12-step
workflow.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.user_workflows import _project


def _row(*, agents=None, manifest_json=None):
    """The attribute surface ``_project`` actually reads."""
    return SimpleNamespace(
        id="wf-1",
        name="PDF to Prototype",
        description=None,
        base_pipeline_type="custom",
        agents=agents,
        manifest_json=manifest_json,
        model_overrides=None,
        attached_skills=None,
        attached_hooks=None,
        overrides_pipeline_type=None,
        override_enabled=False,
        base_version=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _step(agent, instance_id=None, **kw):
    s = {"agent": agent, **kw}
    if instance_id:
        s["instance_id"] = instance_id
    return s


# The real shape of the workflow that exposed this, trimmed to its identities.
_PDF_TO_PROTOTYPE_STEPS = [
    _step("custom-agent", "oa2v5f-rk5oy0", name="Document Ingest"),
    _step("custom-agent", "oa2v5f-1fib5c", name="Reading Supervisor"),
    _step("custom-agent", "oa2v5f-wmvl34", name="Synthesizer"),
    _step("custom-agent", "oa2v5f-y16vzf", name="Coverage Check"),
    _step("custom-agent", "oa2v5f-7bvqht", name="Journey Designer"),
    _step("prototype-specify"),
    _step("prototype-plan"),
    _step("prototype-analyze"),
    _step("prototype-build"),
    _step("prototype-validate"),
    _step("custom-agent", "oa2v5f-o7giy7", name="Fidelity Check"),
    _step("custom-agent", "oa2v5f-31tx21", name="Prototype Presenter"),
]

# What the row actually carried — frozen at create, four ids that no longer exist.
_STALE_AGENTS_COLUMN = (
    '["oa2v5f-g5exi0", "oa2v5f-ujt02v", "oa2v5f-l85qm8", "oa2v5f-10piec"]'
)


def test_manifest_row_counts_its_steps_not_the_stale_column():
    """The reported bug: "4 agents" on a 12-step workflow."""
    out = _project(
        _row(
            agents=_STALE_AGENTS_COLUMN,
            manifest_json={"steps": _PDF_TO_PROTOTYPE_STEPS},
        )
    )

    assert len(out.agent_ids) == 12, "the card would show the stale column's 4"
    assert "oa2v5f-g5exi0" not in out.agent_ids, "a stale id leaked through"


def test_ids_match_the_engine_step_ids():
    """`{agent}:{instance_id}` — the exact form the manifest's depends_on uses."""
    out = _project(
        _row(
            agents=_STALE_AGENTS_COLUMN,
            manifest_json={"steps": _PDF_TO_PROTOTYPE_STEPS},
        )
    )

    assert out.agent_ids[0] == "custom-agent:oa2v5f-rk5oy0"
    assert out.agent_ids[5] == "prototype-specify", "a built-in step has no instance"
    assert out.agent_ids[-1] == "custom-agent:oa2v5f-31tx21"


def test_every_id_is_distinct():
    """Every custom step shares the literal agent name "custom-agent".

    Keying on `agent` alone collapses all seven of them into one repeated entry,
    which is why the instance id is folded in.
    """
    out = _project(_row(manifest_json={"steps": _PDF_TO_PROTOTYPE_STEPS}))
    assert len(set(out.agent_ids)) == len(out.agent_ids)


def test_agent_ids_backed_row_is_unchanged():
    """INV: no manifest ⇒ the legacy column still wins, byte-identically."""
    out = _project(_row(agents='["market-research-agent", "domain-analyst"]'))
    assert out.agent_ids == ["market-research-agent", "domain-analyst"]


def test_a_selections_map_is_not_mistaken_for_a_manifest():
    """``manifest_json`` is overloaded — a selections map has no "steps" key."""
    out = _project(
        _row(
            agents='["domain-analyst"]',
            manifest_json={"domain-analyst": {"depth": "deep"}},
        )
    )
    assert out.agent_ids == ["domain-analyst"]
    assert out.selections == {"domain-analyst": {"depth": "deep"}}
    assert out.manifest is None


def test_malformed_steps_are_skipped_not_fatal():
    """A step with no agent, or a non-dict, must not break the listing."""
    out = _project(
        _row(
            manifest_json={
                "steps": [
                    _step("custom-agent", "aaa"),
                    {"name": "no agent here"},
                    "not a dict",
                    None,
                    _step("prototype-build"),
                ]
            }
        )
    )
    assert out.agent_ids == ["custom-agent:aaa", "prototype-build"]


def test_empty_steps_reports_zero_rather_than_the_stale_count():
    out = _project(_row(agents=_STALE_AGENTS_COLUMN, manifest_json={"steps": []}))
    assert out.agent_ids == []


def test_unparseable_legacy_column_still_degrades_to_empty():
    out = _project(_row(agents="{not json"))
    assert out.agent_ids == []
