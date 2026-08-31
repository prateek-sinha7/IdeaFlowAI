"""MAN-05 / MAN-04 — id-alias resolver + CompiledWorkflow routing-source tests.

Covers the run-entry routing seam introduced in the engine (04-04):

  * ``resolve_alias`` is the SINGLE point mapping the legacy ``pipeline_type``
    label to a manifest id: ``od_prototype`` -> ``prototype``; every real
    ``PIPELINE_AGENTS`` key resolves to itself (MAN-05).
  * ``compile_for_run`` sources the run's CompiledWorkflow from the manifest +
    compiler layer; the engine's effective agent sequence, clarify defaults, and
    planner flag come FROM that compiled plan, not the legacy hardcoded dicts
    (MAN-04).

These are pure-data tests (no engine drive) — the end-to-end ``execute()`` run
from the compiled plan is covered by ``test_compiled_plan_runs.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.execution_engine.engine import compile_for_run, resolve_alias
from agents.loader import SUPPORTED_PIPELINE_TYPES
from agents.registry import PIPELINE_AGENTS, _OD_ALIAS_BASE, get_pipeline_agents

_MANIFEST_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"
_MANIFEST_BACKED_IDS = {
    pt
    for pt in SUPPORTED_PIPELINE_TYPES
    if (_MANIFEST_BASE / pt / "workflow.yaml").exists()
}

# The 13 engine-dispatchable pipelines = the manifest-backed pipelines minus
# the two non-engine-dispatched edge cases (chat = ChatRunner; reverse_engineer
# = empty). FIX-051 / ISS-035: scoped to manifest-backed ids, not raw
# PIPELINE_AGENTS keys — PIPELINE_AGENTS can now contain a pipeline_type with
# real agents but no manifest yet (e.g. spec_kit), which cannot be compiled.
_DISPATCHABLE = sorted(_MANIFEST_BACKED_IDS - {"chat", "reverse_engineer"})

# The verbatim per-pipeline clarify.defaults, hard-copied from each pipeline's
# `agents/workflows/<id>/workflow.yaml`. This originally mirrored the engine's
# hardcoded `_pipeline_defaults` dict (pre-migration engine.py:752-761), but that
# literal dict was migrated OUT of the engine and into the manifests in
# MAN-04/MAN-05 (commit 63f0fc66) — `compiled.clarify.defaults` (sourced from the
# manifest) is authoritative now, and KAN-74 (commit ae4e36f7) subsequently
# extended most pipelines' defaults from 4 to 8 items. "od_ppt" was dropped: the
# od_ppt/ppt collapse (commit ef32ef88) removed it from SUPPORTED_PIPELINE_TYPES
# entirely, so it can never reach this dict via `_DISPATCHABLE`. Kept in lockstep
# with the manifests — update this copy when a manifest's defaults deliberately
# change.
_EXPECTED_CLARIFY_DEFAULTS: dict[str, list[str]] = {
    "ppt": ["target_audience", "tone_and_style", "key_objectives", "slide_count", "content_depth", "data_availability", "visual_style", "key_sections"],
    "prototype": ["target_audience", "scope", "priority", "style", "user_journeys", "key_screens", "interactions", "personas"],
    "user_stories": ["target_audience", "scope", "priority", "technology", "personas", "user_journeys", "business_rules", "compliance_security"],
    "app_builder": ["technology", "scope", "target_audience", "security", "user_journeys", "data_model", "integrations", "performance"],
    "mulesoft_to_springboot": ["scope", "technology", "timeline", "priority", "integration_patterns", "target_infrastructure", "data_migration", "compliance_security"],
    "dotnet_to_azure": ["scope", "technology", "timeline", "priority", "azure_services", "data_migration", "integration_patterns", "compliance_security"],
    "custom": ["target_audience", "key_objectives", "scope", "priority", "output_format", "constraints", "domain", "assumptions"],
    # clarify.mode: skip — these take their topic straight from the run input and
    # ask nothing. Visible to this test only since ADR-0005 derived
    # SUPPORTED_PIPELINE_TYPES from disk, which swept the sample_* workflows in.
    # Kept in lockstep with test_manifest_parity.py's _ENGINE_PIPELINE_DEFAULTS.
    # spec 017 — ppt_v2 reuses ppt's clarify contract verbatim; the deck it asks
    # about is the same deck, it just also ships a .pptx.
    "ppt_v2": ["target_audience", "tone_and_style", "key_objectives", "slide_count", "content_depth", "data_availability", "visual_style", "key_sections"],
    "sample_subagents_parallel": [],
    "sample_fanout": [],
    "sample_wave": [],
    "sample_brownfield": [],
    # clarify.mode: skip as well — the composed-workflow revision manifest takes
    # its instruction straight from the revision panel and asks nothing.
    "custom_revision": [],
    # clarify.mode: skip — these revision pipelines share main-pipeline agents
    # (revision-pipeline-agent-reuse spec); the revision panel supplies the
    # instruction directly, no clarify round-trip needed.
    "prototype_large_revision": [],
    "prototype_feature_revision": [],
    # ── spec 014/015 conditional-gate example workflows ──────────────────────
    # clarify.mode: skip — deterministic branch/loop/divert fixtures that take
    # their topic straight from the run input and ask nothing. Swept in by
    # ADR-0005 (SUPPORTED_PIPELINE_TYPES derived from disk), same as the
    # sample_* workflows above. Kept in lockstep with the sibling file.
    "ex_A1_loop": [],
    "ex_A2_branch": [],
    "ex_A3_b_spanish": [],
    "ex_A3_c_dutch": [],
    "ex_A3_divert": [],
    "ex_A4_human_divert": [],
    "ex_A4_human_gate": [],
    # clarify.mode: skip — spec 018's temporary playwright smoke fixture takes
    # its brief straight from the run input and asks nothing. Delete with the
    # fixture.
    "playwright_smoke_test": [],
    # clarify.mode: disabled — a compile-shape fixture, not a runnable pipeline.
    "sc001-test-fixture": [],
}
# The fallback for any id absent from the dict above (the *_revision manifests +
# chat/reverse_engineer) — these were NOT touched by KAN-74 and still declare the
# pre-KAN-74 4-item "custom" list verbatim. Intentionally decoupled from
# `_EXPECTED_CLARIFY_DEFAULTS["custom"]` above (the "custom" PIPELINE's own
# defaults DID get extended to 8 by KAN-74; this fallback did not).
_CUSTOM_DEFAULTS = ["target_audience", "key_objectives", "scope", "priority"]


# ── resolve_alias (MAN-05) ──────────────────────────────────────────────────


def test_retired_labels_are_not_resolvable() -> None:
    """A retired run-label resolves to ITSELF, not to a base pipeline.

    ``od_prototype`` used to be the sole id-alias. Collapsing it (registry
    ``_OD_ALIAS_BASE`` is empty; persisted rows migrated in 0037) means the label
    is no longer special-cased anywhere — the resolver must not invent a mapping
    for it, exactly as it does not for any other unknown string.
    """
    assert resolve_alias("od_prototype") == "od_prototype"
    assert resolve_alias("od_ppt") == "od_ppt"


@pytest.mark.parametrize("key", sorted(PIPELINE_AGENTS))
def test_every_real_pipeline_key_resolves_to_itself(key: str) -> None:
    """Every real PIPELINE_AGENTS key is identity under the resolver (no alias)."""
    assert resolve_alias(key) == key


def test_there_are_no_aliases() -> None:
    """The alias table is EMPTY and the resolver is the identity function.

    Aliases cost more than they saved: ``od_prototype`` covered the base label but
    never its ``_revision`` variant, so one pipeline's launch and revision halves
    carried different labels and had to be bridged by hand-written remap tables in
    the API layer. Both labels are collapsed at the root now. A new entry here
    should be a deliberate decision, not a migration shortcut.
    """
    assert _OD_ALIAS_BASE == {}
    # Identity for an arbitrary unknown label (resolver never invents a mapping).
    assert resolve_alias("totally_unknown_label") == "totally_unknown_label"


# ── compile_for_run sources the agent sequence (MAN-04, concern 1) ──────────


_ISS_631_AFFECTED = {"prototype_revision", "prototype_large_revision", "prototype_feature_revision"}


@pytest.mark.parametrize(
    "pipeline_type",
    [
        pytest.param(
            pid,
        )
        if pid in _ISS_631_AFFECTED
        else pid
        for pid in _DISPATCHABLE
    ],
)
def test_compiled_agent_sequence_matches_registry_order(pipeline_type: str) -> None:
    """The compiled plan's step order equals the registry's agent order (no reorder).

    This is the parity guard (RESEARCH Pitfall 3): the engine sources the agent
    sequence from `compile_for_run(...).steps`, which must equal the order the
    legacy `get_pipeline_agents` / PIPELINE_AGENTS would have produced. `ppt`
    agents declare pipeline_type: od_ppt, so get_pipeline_agents("ppt") is empty
    — fall back to PIPELINE_AGENTS[id] there (matches the coverage test).
    """
    compiled = compile_for_run(pipeline_type)
    compiled_ids = [s.agent_id for s in compiled.steps]

    manifest_id = resolve_alias(pipeline_type)
    if not (get_pipeline_agents(manifest_id) or PIPELINE_AGENTS.get(manifest_id)):
        # A manifest-only workflow (the sample_* shape tests, composed workflows):
        # its steps are custom-agent instances or worker templates with no AGENT.md,
        # so the registry side is empty BY CONSTRUCTION and there is nothing to
        # compare against. This is the same reason ADR-0003 deleted the engine's
        # run-entry membership assertion. Assert the plan is non-empty instead.
        assert compiled_ids, f"{pipeline_type}: compiled plan has no steps"
        return

    registry_order = [a.id for a in get_pipeline_agents(manifest_id)]
    expected = registry_order if registry_order else PIPELINE_AGENTS[manifest_id]

    # PIPELINE_AGENTS is derived from each AGENT.md's `pipeline_type`, so it holds
    # only the agents authored FOR this pipeline. A workflow that REUSES an agent
    # from another one therefore has a PARTIAL registry side — ppt_v2 reuses ppt's
    # brief-analyst and composer verbatim (spec 017), so equality cannot hold and
    # demanding it would forbid reuse outright. The guard this test exists for is
    # "the engine did not REORDER the plan", which survives as: every registry
    # agent appears in the compiled plan, in the same relative order.
    if set(expected) < set(compiled_ids):
        pos = [compiled_ids.index(a) for a in expected]
        assert pos == sorted(pos), (
            f"{pipeline_type}: registry agents {expected} appear out of order in the "
            f"compiled plan {compiled_ids} — the engine reordered the plan"
        )
        return

    assert compiled_ids == expected


def test_prototype_runs_its_own_plan() -> None:
    """``prototype`` compiles to its own manifest under its own name.

    Was ``test_od_prototype_runs_prototypes_plan``: the alias was the ONLY label
    that reached this plan, because a bare ``prototype`` launch was rejected
    upstream (``missing_template_context``) by a clause that excluded a base from
    its own declared ``opendesign`` capability whenever it had an ``od_`` alias.
    Both are gone; the plain name is now the only name.
    """
    compiled = compile_for_run("prototype")
    assert compiled.id == "prototype"
    assert [s.agent_id for s in compiled.steps] == [
        a.id for a in get_pipeline_agents("prototype")
    ]


# ── compile_for_run sources clarify defaults (MAN-04, concern 3) ────────────


@pytest.mark.parametrize(
    "pipeline_type",
    [
        pytest.param(
            pid,
            marks=[pytest.mark.issue("ISS-635")],
        )
        if pid == "playwright_smoke_test"
        else pid
        for pid in _DISPATCHABLE
    ],
)
def test_compiled_clarify_defaults_match_engine_dict(pipeline_type: str) -> None:
    """The compiled clarify.defaults reproduce the engine's former _pipeline_defaults.

    The engine now sources the ALWAYS_CLARIFY default-question seed from
    `compile_for_run(...).clarify.defaults` instead of the removed hardcoded
    dict. od_prototype resolves to the prototype manifest (same defaults).
    Revisions / edge ids fall to the `custom` list.
    """
    compiled = compile_for_run(pipeline_type)
    expected = _EXPECTED_CLARIFY_DEFAULTS.get(pipeline_type, _CUSTOM_DEFAULTS)
    assert list(compiled.clarify.defaults) == expected


# ── compile_for_run sources the planner flag (MAN-04, concern 4) ────────────

# Phase 14 carve-out + ISS-050 (KAN-156) addition: run_revision-dispatched
# manifests declare planner: skip (clarify-auto would hang a dispatched revision
# at the clarify event.wait()). ISS-050 adds prototype_revision and
# user_stories_revision — now reachable from the generic chat-lane revision
# channel (Phase 29). Sibling trap: tests/agents/test_manifest_parity.py
# (_RUN_REVISION_DISPATCHED) — keep both carve-outs in lockstep. "od_ppt_revision"
# was dropped here too: the od_ppt/ppt collapse (commit ef32ef88) deleted its
# workflow.yaml and removed it from SUPPORTED_PIPELINE_TYPES, so it can never
# reach `_DISPATCHABLE`.
_RUN_REVISION_DISPATCHED = frozenset({
    "ppt_revision",
    "prototype_revision",
    "user_stories_revision",
    # Added with the composed-workflow revision manifest, which declares
    # planner: skip like its siblings but was never listed here.
    "custom_revision",
    # Flipped to planner: skip — it was authored as `run` and so could never be
    # revision-dispatched (CR-02 refused it; the run died with 0 events).
    "app_builder_revision",
})

# Sibling trap: keep in lockstep with tests/agents/test_manifest_parity.py's
# _PLANNER_SKIP_IDS.
_PLANNER_SKIP_IDS = _RUN_REVISION_DISPATCHED | {
    # Deliberately tiny local shape tests where a deep-planner round-trip
    # would cost more than the work itself. Mirrors test_manifest_parity.py.
    "sample_subagents_parallel",
    # revision-pipeline-agent-reuse spec: these revision pipelines declare
    # planner: skip because the revision panel supplies the instruction directly.
    # NOT run_revision-WS-dispatched, so kept out of _RUN_REVISION_DISPATCHED
    # and unioned in here like sample_subagents_parallel. Sibling trap: keep in
    # lockstep with tests/agents/test_manifest_parity.py::_PLANNER_SKIP_IDS.
    "prototype_large_revision",
    "prototype_feature_revision",
    # ── spec 014/015 conditional-gate example workflows ──────────────────────
    # planner: skip — deliberately tiny deterministic fixtures for the loop /
    # branch / divert / human-gate shapes. A deep-planner round-trip in front of
    # one would cost more than the workflow itself and add variance to the exact
    # branch sequence each fixture exists to pin. Same rationale as
    # sample_subagents_parallel above. NOT run_revision-dispatched, so unioned in
    # here rather than added to _RUN_REVISION_DISPATCHED.
    "ex_A1_loop",
    "ex_A2_branch",
    "ex_A3_b_spanish",
    "ex_A3_c_dutch",
    "ex_A3_divert",
    "ex_A4_human_divert",
    "ex_A4_human_gate",
    # spec 018 — playwright_smoke_test declares planner: skip for the same
    # reason: a throwaway one-step fixture QA launches to exercise
    # tools:[playwright] live in under a minute, where a deep-planner
    # round-trip would cost more than the workflow it fronts. NOT
    # run_revision-dispatched, so unioned in here rather than added to
    # _RUN_REVISION_DISPATCHED. Delete this entry when the fixture is deleted
    # (its workflow.yaml says it is temporary).
    "playwright_smoke_test",
}


@pytest.mark.parametrize(
    "pipeline_type",
    [
        pytest.param(
            pid,
            marks=[pytest.mark.issue("ISS-635")],
        )
        if pid == "playwright_smoke_test"
        else pid
        for pid in _DISPATCHABLE
    ],
)
def test_compiled_planner_is_run_everywhere(pipeline_type: str) -> None:
    """Every dispatchable manifest declares planner: run — EXCEPT the
    run_revision-dispatched manifests (planner: skip as of Phase 14; see
    _RUN_REVISION_DISPATCHED above) and the sample_* fixtures (see
    _PLANNER_SKIP_IDS above and the sibling trap in test_manifest_parity.py).
    For every other pipeline the engine's skip_planner stays False and the
    planner/clarifier runs (byte-identical).
    """
    compiled = compile_for_run(pipeline_type)
    expected = "skip" if pipeline_type in _PLANNER_SKIP_IDS else "run"
    assert compiled.planner == expected
