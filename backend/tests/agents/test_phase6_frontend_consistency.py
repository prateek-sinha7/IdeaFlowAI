"""Phase 6 (T6 verify gate) — FRONTEND ⇄ BACKEND cross-registry consistency.

This is the durable, re-runnable form of the one-off check T4 performed by hand:
the static frontend ``AgentLibraryData.ts`` (``LIBRARY_AGENTS``) must stay
consistent with the engine's REAL ``agents.registry`` for the two categories the
agent-selector / Review-gates UI actually exposes and that the reconciliation
touched — ``prototype`` and ``ppt`` (the only pipelines that had diverged).

The reconciliation's whole point is a single source of truth. If someone edits a
prototype/ppt agent's id, ``gate`` frontmatter, or pipeline membership on the
backend without regenerating ``AgentLibraryData.ts``, the front/back drift that
Phase 6 fixed silently returns:

  * a stale id in a non-null ``gate_agent_ids`` would DISABLE the real default
    gates (the frontend would name agents the backend's ``_should_gate`` set
    never contains), and
  * the agent-selector would again show fictional agents.

So this test parses the ``.ts`` file (a lightweight, dependency-free parse of the
``LIBRARY_AGENTS`` object literal — we do NOT execute TS) and asserts, per
category:

  * the id SET matches the real registry's pipeline ids exactly, and
  * each agent's ``gate`` value matches the real ``AgentSpec.gate`` (mapping the
    TS literal ``null`` ⇄ Python ``None``).

It also pins the absence of every retired/stale id anywhere in the file, and the
``PIPELINE_CATEGORIES`` counts for the reconciled categories. These guard the
exact regressions Phase 6 closed.

NOTE on the ``ppt`` mapping: the frontend keeps ``pipeline_type: "ppt"`` as the
category key the selector filters on, while the real agents are the shared
od-ppt-* specs that live in BOTH ``PIPELINE_AGENTS["ppt"]`` and
``PIPELINE_AGENTS["od_ppt"]`` (identical membership — asserted below). The
LOADABLE specs (with ``gate`` frontmatter) only resolve through the ``od_ppt``
pipeline, though, because ``get_pipeline_agents`` discovers agents by their
AGENT.md ``pipeline_type`` frontmatter and the od-ppt files declare ``od_ppt``
(NOT ``ppt``). So we compare the frontend ``ppt`` block against the real
``od_ppt`` loaded specs — which is exactly the comparison the Phase 6 plan
(T6 #6) specifies ("for ppt assert ids == the real od_ppt ids").

DOCUMENTED FINDING (pinned by ``TestPptEndpointResolutionQuirk`` below):
``get_pipeline_agents("ppt")`` returns ``[]`` (the frontmatter is ``od_ppt``),
so ``GET /api/agents/pipelines/ppt`` serves an EMPTY agent list while
``/pipelines/od_ppt`` serves the three agents. This is a *pre-existing*
condition (``get_pipeline_agents`` + the od-ppt frontmatter both predate Phase 6;
Phase 6 added only the flat-list/by-id/allow-list helpers, none of which are
affected). It has no live-UI impact in this build — the frontend reads the
static ``LIBRARY_AGENTS`` everywhere and never fetches ``/pipelines/{type}`` —
but it matters for the noted Phase-7 "migrate to live fetch" follow-on, so it is
asserted here as a known characteristic rather than left implicit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agents.registry import PIPELINE_AGENTS, get_pipeline_agents

# ---------------------------------------------------------------------------
# Locate the frontend data file relative to the repo root (…/backend/../frontend)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]  # …/flowin
_AGENT_LIBRARY_TS = (
    _REPO_ROOT
    / "frontend"
    / "src"
    / "components"
    / "workflow"
    / "AgentLibraryData.ts"
)


def _require_ts_file() -> str:
    if not _AGENT_LIBRARY_TS.exists():
        pytest.skip(f"frontend AgentLibraryData.ts not found at {_AGENT_LIBRARY_TS}")
    return _AGENT_LIBRARY_TS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Minimal, dependency-free parser for the LIBRARY_AGENTS object literals.
#
# Each agent is a single-line `{ id: "...", ..., gate: "..."|null }` entry in the
# `export const LIBRARY_AGENTS: AgentDef[] = [ ... ];` block. We extract every
# object literal inside that block and pull `id`, `pipeline_type`, and `gate`.
# This deliberately does NOT run TypeScript — it pattern-matches the generated
# data, which is the artefact under test.
# ---------------------------------------------------------------------------

_FIELD_STR = lambda key: re.compile(rf"""\b{key}\s*:\s*"([^"]*)\"""")  # noqa: E731
_GATE_RE = re.compile(r"""\bgate\s*:\s*(null|"([^"]*)")""")
_ID_RE = _FIELD_STR("id")
_PTYPE_RE = _FIELD_STR("pipeline_type")


def _extract_block(src: str, const_name: str) -> str:
    """Return the text between the `[` and the matching `]` of
    `export const <const_name>[: <type>] = [ ... ];` (bracket-balanced).

    Tolerates both an explicit `: AgentDef[]` annotation (LIBRARY_AGENTS) and a
    bare `export const X = [` (PIPELINE_CATEGORIES, which uses `as const`).
    """
    m = re.search(rf"export const {const_name}\b[^=]*=\s*\[", src)
    assert m, f"could not find `export const {const_name}` in AgentLibraryData.ts"
    start = m.end() - 1  # position of the opening '['
    depth = 0
    for i in range(start, len(src)):
        c = src[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return src[start + 1 : i]
    raise AssertionError(f"unbalanced brackets for {const_name}")


def _parse_agents(block: str) -> list[dict]:
    """Parse each `{ ... }` object literal in a LIBRARY_AGENTS block into a dict
    with keys: id, pipeline_type, gate (gate is None for the TS literal `null`)."""
    agents: list[dict] = []
    depth = 0
    obj_start: int | None = None
    for i, c in enumerate(block):
        if c == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                literal = block[obj_start : i + 1]
                id_m = _ID_RE.search(literal)
                pt_m = _PTYPE_RE.search(literal)
                gate_m = _GATE_RE.search(literal)
                assert id_m, f"agent literal without an id: {literal[:80]}…"
                assert pt_m, f"agent literal without a pipeline_type: {literal[:80]}…"
                assert gate_m, f"agent literal without a gate field: {literal[:80]}…"
                gate_val = None if gate_m.group(1) == "null" else gate_m.group(2)
                agents.append(
                    {
                        "id": id_m.group(1),
                        "pipeline_type": pt_m.group(1),
                        "gate": gate_val,
                    }
                )
                obj_start = None
    return agents


@pytest.fixture(scope="module")
def frontend_agents() -> list[dict]:
    src = _require_ts_file()
    block = _extract_block(src, "LIBRARY_AGENTS")
    agents = _parse_agents(block)
    assert agents, "parsed zero agents from LIBRARY_AGENTS — parser or data broke"
    return agents


# ---------------------------------------------------------------------------
# Sanity: the parser actually works (guards against a silently-empty parse that
# would make every membership assertion below vacuously pass).
# ---------------------------------------------------------------------------


class TestParserSanity:
    def test_every_entry_has_a_gate_field(self, frontend_agents):
        """Every LIBRARY_AGENTS entry carries an explicit `gate` (string or
        null) — a regenerated-data invariant the gate toggle relies on."""
        # If any literal lacked `gate`, _parse_agents would have asserted; this
        # re-states the guarantee at the value level (None is allowed).
        assert all("gate" in a for a in frontend_agents)

    def test_parser_finds_the_reconciled_categories(self, frontend_agents):
        ptypes = {a["pipeline_type"] for a in frontend_agents}
        assert {"prototype", "ppt"} <= ptypes


# ---------------------------------------------------------------------------
# The heart of the reconciliation: prototype + ppt ids and gate match the REAL
# backend registry.
# ---------------------------------------------------------------------------


# Map the frontend CATEGORY key to the backend pipeline whose AGENT.md files
# actually carry the loadable specs (with gate frontmatter). The frontend uses
# "ppt" as the selector category, but the od-ppt AGENT.md files declare
# pipeline_type: od_ppt, so the loadable specs resolve through "od_ppt".
_CATEGORY_TO_LOADABLE_PIPELINE = {
    "prototype": "prototype",
    "ppt": "od_ppt",
}


def _real_gate_by_id(category: str) -> dict[str, str | None]:
    pipeline = _CATEGORY_TO_LOADABLE_PIPELINE[category]
    return {s.id: s.gate for s in get_pipeline_agents(pipeline)}


@pytest.mark.parametrize("category", ["prototype", "ppt"])
class TestFrontendMatchesRealRegistry:
    def test_id_set_matches_real_registry(self, frontend_agents, category):
        fe_ids = {a["id"] for a in frontend_agents if a["pipeline_type"] == category}
        be_ids = set(_real_gate_by_id(category).keys())
        assert be_ids, f"real registry returned no agents for {category!r}"
        assert fe_ids == be_ids, (
            f"{category}: frontend ids != real registry ids — "
            f"frontend-only={fe_ids - be_ids}, backend-only={be_ids - fe_ids}"
        )

    def test_gate_values_match_real_registry(self, frontend_agents, category):
        fe_gate = {
            a["id"]: a["gate"]
            for a in frontend_agents
            if a["pipeline_type"] == category
        }
        be_gate = _real_gate_by_id(category)
        assert fe_gate == be_gate, (
            f"{category}: gate values diverge between frontend and real "
            f"registry — frontend={fe_gate}, backend={be_gate}"
        )


class TestPrototypeAndPptSpecifics:
    """Explicit pins for the two reconciled pipelines (belt-and-braces on top of
    the parametrized set/gate equality above)."""

    def test_prototype_real_ids_and_human_gate(self, frontend_agents):
        fe = {
            a["id"]: a["gate"]
            for a in frontend_agents
            if a["pipeline_type"] == "prototype"
        }
        assert set(fe) == {
            "prototype-specify",
            "prototype-plan",
            "prototype-build",
            "prototype-validate",
        }
        # specify + plan are the only Human_Gate agents; build + validate are None.
        assert fe["prototype-specify"] == "Human_Gate"
        assert fe["prototype-plan"] == "Human_Gate"
        assert fe["prototype-build"] is None
        assert fe["prototype-validate"] is None

    def test_ppt_real_od_ids(self, frontend_agents):
        fe_ids = {a["id"] for a in frontend_agents if a["pipeline_type"] == "ppt"}
        assert fe_ids == {
            "od-ppt-brief-analyst",
            "od-ppt-composer",
            "od-ppt-validator",
        }

    def test_real_ppt_and_od_ppt_pipelines_have_identical_membership(self):
        """The frontend folds od_ppt agents under the `ppt` category key; this
        is only safe because the two real pipelines share membership."""
        assert set(PIPELINE_AGENTS["ppt"]) == set(PIPELINE_AGENTS["od_ppt"])


class TestPptEndpointResolutionQuirk:
    """Pins the DOCUMENTED (pre-existing, non-Phase-6) finding that the
    ``ppt`` *pipeline endpoint* resolves to an empty agent list because the
    od-ppt AGENT.md files declare ``pipeline_type: od_ppt`` (not ``ppt``),
    while the od-ppt category content is fully reachable via ``od_ppt`` and via
    the flat list / allow-list. See the module docstring.

    This is a characterization test: it documents current behavior so a future
    change (e.g. the Phase-7 live-fetch migration, which would call
    ``GET /api/agents/pipelines/ppt``) trips this and forces a conscious
    decision rather than silently shipping an empty PPT agent list.
    """

    def test_get_pipeline_agents_ppt_is_empty_but_od_ppt_is_not(self):
        assert get_pipeline_agents("ppt") == [], (
            "get_pipeline_agents('ppt') unexpectedly non-empty — the od-ppt "
            "AGENT.md frontmatter may have been switched to pipeline_type: ppt; "
            "if so, update this characterization test and the docstring."
        )
        od_ppt_ids = [s.id for s in get_pipeline_agents("od_ppt")]
        assert od_ppt_ids == [
            "od-ppt-brief-analyst",
            "od-ppt-composer",
            "od-ppt-validator",
        ]

    def test_od_ppt_category_content_reachable_via_other_helpers(self):
        """Despite the empty ``ppt`` endpoint, the od-ppt agents ARE reachable
        through the helpers Phase 6 added — so the reconciliation's data is
        complete; only the (unused-by-the-UI) ppt pipeline endpoint is empty."""
        from agents.registry import allowed_custom_agent_ids, get_all_agents_flat

        flat_ids = {s.id for s in get_all_agents_flat()}
        od_ppt = {"od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"}
        assert od_ppt <= flat_ids
        assert od_ppt <= allowed_custom_agent_ids("ppt")
        assert od_ppt <= allowed_custom_agent_ids("od_ppt")


# ---------------------------------------------------------------------------
# No stale / retired ids may appear ANYWHERE in the file (the pre-Phase-6 drift).
# ---------------------------------------------------------------------------


class TestNoStaleIds:
    # Retired prototype_v1 ids + the old PPT pipeline ids that the legacy
    # registry used to serve. None of these may survive in the regenerated data.
    STALE_IDS = (
        "requirements-analyst",
        "html-prototype-builder",
        "prototype-polisher",
        "prototype-finalizer",
        "ppt-content-strategist",
        "ppt-visual-designer",
        "ppt-data-storyteller",
        "ppt-deck-builder",
    )

    def test_no_stale_id_string_in_file(self):
        src = _require_ts_file()
        present = [sid for sid in self.STALE_IDS if f'"{sid}"' in src]
        assert not present, f"stale agent ids still present in AgentLibraryData.ts: {present}"

    def test_no_stale_id_in_parsed_agents(self, frontend_agents):
        fe_ids = {a["id"] for a in frontend_agents}
        leaked = set(self.STALE_IDS) & fe_ids
        assert not leaked, f"stale ids leaked into LIBRARY_AGENTS: {leaked}"


# ---------------------------------------------------------------------------
# PIPELINE_CATEGORIES counts for the reconciled categories (ppt 4→3, total 55→54).
# ---------------------------------------------------------------------------


class TestPipelineCategoryCounts:
    def _categories(self) -> dict[str, int]:
        src = _require_ts_file()
        block = _extract_block(src, "PIPELINE_CATEGORIES")
        cats: dict[str, int] = {}
        # Each entry: { key: "ppt", label: "PPT", count: 3 }
        for m in re.finditer(
            r"""\{\s*key:\s*"([^"]+)"\s*,\s*label:\s*"[^"]*"\s*,\s*count:\s*(\d+)\s*\}""",
            block,
        ):
            cats[m.group(1)] = int(m.group(2))
        assert cats, "failed to parse PIPELINE_CATEGORIES"
        return cats

    def test_ppt_and_prototype_counts_reconciled(self):
        cats = self._categories()
        assert cats["ppt"] == 3, "ppt category count must be 3 (od_ppt agents)"
        assert cats["prototype"] == 4, "prototype category count must be 4 (spec-kit)"

    def test_category_counts_match_real_registry(self):
        """For prototype + ppt, the declared category count equals the real
        registry pipeline length — the counts can't silently drift. (ppt maps
        to the loadable ``od_ppt`` pipeline per the module docstring.)"""
        cats = self._categories()
        assert cats["prototype"] == len(get_pipeline_agents("prototype"))
        assert cats["ppt"] == len(get_pipeline_agents("od_ppt"))

    def test_category_count_equals_library_agents_membership(self):
        """Each concrete category count equals the number of LIBRARY_AGENTS
        entries with that ``pipeline_type`` — i.e. the tab counts can't drift
        from the data they label. (``custom`` is a SEPARATE ``CUSTOM_AGENTS``
        array, not part of LIBRARY_AGENTS, so it is excluded here.)"""
        src = _require_ts_file()
        block = _extract_block(src, "LIBRARY_AGENTS")
        members = _parse_agents(block)
        from collections import Counter

        by_type = Counter(a["pipeline_type"] for a in members)
        cats = self._categories()
        for key, count in cats.items():
            if key in ("all", "custom"):
                continue
            assert count == by_type.get(key, 0), (
                f"category {key!r} count {count} != LIBRARY_AGENTS membership "
                f"{by_type.get(key, 0)}"
            )

    def test_all_count_equals_library_agents_length(self):
        """The `all` tab counts the LIBRARY_AGENTS array (the selector's pool,
        which excludes the separate CUSTOM_AGENTS), i.e. the sum of the
        non-`custom` category counts. This is the ppt 4→3 / total 55→54 fix."""
        cats = self._categories()
        src = _require_ts_file()
        members = _parse_agents(_extract_block(src, "LIBRARY_AGENTS"))
        assert cats["all"] == len(members), (
            f"`all` count {cats['all']} != len(LIBRARY_AGENTS) {len(members)}"
        )
        # And that equals the sum of every non-`all`, non-`custom` category.
        per_category_sum = sum(
            v for k, v in cats.items() if k not in ("all", "custom")
        )
        assert cats["all"] == per_category_sum, (
            f"`all` count {cats['all']} != sum of non-custom categories "
            f"{per_category_sum}"
        )
