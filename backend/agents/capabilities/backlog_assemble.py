"""agents/capabilities/backlog_assemble.py — the ``mechanical: assemble_backlog``
step kind (spec 021-backlog, FR-050..FR-055).

Code, not a model, turns the Backlog Planner's hierarchy and the Story Writers' per-epic
JSON files into the backlog:

  1. read ``build/backlog-plan.json`` (the hierarchy), ``build/solution/*.json`` (the
     coverage items: features, screens, entities, integrations, roles, nfrs, platform)
     and every ``stories/<task id>.json`` the Story Writers wrote;
  2. check every story against the §6.6 shape, EARS (§7.2) and Gherkin (§7.3) rules,
     and check the hierarchy and coverage themselves (duplicate ids, an epic with no
     stories, a coverage item no story covers, a requirement no scenario tags);
  3. render ``backlog.md`` (the deliverable), ``backlog.csv`` (Jira import), ``backlog.json``,
     ``build/coverage.json``, and the full-application documents (§14.4) —
     ``data-model.md``, ``schema.json``, ``api.md``, ``openapi.json``, ``integrations.md``,
     ``screens.md`` — always all ten, even when the run is about to fail — and
     ``build-order.md``, the order to build it in, computed from the epics' ``depends_on``;
  4. in ``final`` mode (``build/review.json`` present) below the 85% evidenced-coverage
     threshold, or when no ``stories/*.json`` file parsed at all, FAIL the run, naming
     what is missing. ``draft`` mode (no ``build/review.json``) never fails on coverage.

Why this exists: FR-050 requires the totals in ``build/coverage.json`` to be computed
by code from the lists, never typed by a model, and the same three writing standards
(§6.6/§7.2/§7.3) apply to every story regardless of which Story Writer wrote it — a
single mechanical checker is the only way both hold across a fanned-out wave.

Mirrors ``assemble_step.py``: the strategy adapter is constructed by the engine per
dispatch for a step declaring ``mechanical: "assemble_backlog"`` — it is never
resolved through ``registry.resolve("strategy", ...)``. The kind IS registered under
``("mechanical", "assemble_backlog")`` (a no-arg stub below) so the capability
palette and the composer's Capabilities tab can list and select it. Pure stdlib;
reaches the sandbox only through ``ctx.runner.sandbox.read``/``.write`` (import-linter:
agents.capabilities must never import app.*).

Discovering the story files: ``build/story-tasks.json`` (§6.5, the ``json_tasks`` shape
the Backlog Planner wrote) already names every task id, and each Story Writer's target
is exactly ``stories/<task id>.json`` (FR-040). Reading that task list — rather than
listing the ``stories/`` directory — needs only ``sandbox.read``, matches how
``assemble_prototype`` derives its own file list from an upstream inventory
(``build/screens.json``) instead of globbing ``parts/``, and needs no sandbox listing
method at all. The Reviewer's additions, ``stories/review-<epic id>.json``, are derived
from the plan's epics the same way. The trade-off: a ``stories/<id>.json`` under any
other name cannot be discovered.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import Counter
from typing import Any, AsyncIterator, Callable

from agents.capabilities.registry import register

BACKLOG_PLAN_PATH = "build/backlog-plan.json"
SOLUTION_DIR = "build/solution"
SOLUTION_KINDS = ("features", "screens", "entities", "integrations", "roles", "nfrs", "platform",
                   "rules", "endpoints", "glossary")
# §14.2 — every kind is a coverage item except glossary.
NON_COVERAGE_KINDS = {"glossary"}
STORY_TASKS_PATH = "build/story-tasks.json"
STORIES_DIR = "stories"
REVIEW_PATH = "build/review.json"
COVERAGE_PATH = "build/coverage.json"
DEFAULT_DELIVERABLE = "backlog.md"
COVERAGE_THRESHOLD = 0.85
ARCHITECTURE_PATH = "architecture.md"
BUILD_ORDER_PATH = "build-order.md"
# The final assembly's list of coverage items no story covers (only when there are any).
GAPS_PATH = "gaps.md"
# §14.4 — the six documents rendered by this step, beyond backlog.md/.csv/.json/coverage.json.
NEW_DOCUMENT_FILES = ("data-model.md", "schema.json", "api.md", "openapi.json",
                        "integrations.md", "screens.md")

# §14.4 attribute/field type → JSON Schema {"type", "format"}.
_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "string": ("string", None), "text": ("string", None),
    "int": ("integer", None), "integer": ("integer", None),
    "number": ("number", None), "decimal": ("number", None),
    "money": ("number", None), "currency": ("number", None),
    "boolean": ("boolean", None),
    "date": ("string", "date"),
    "datetime": ("string", "date-time"), "timestamp": ("string", "date-time"),
    "email": ("string", "email"),
}

# §7.2 — the pattern keyword IS the first word; ubiquitous has no condition, so its
# text just opens "The system shall …".
EARS_PATTERN_FIRST_WORD = {
    "ubiquitous": "The", "event": "When", "state": "While", "unwanted": "If", "optional": "Where",
}
_SHALL_RE = re.compile(r"\bshall\b")
_BANNED_MODAL_RE = re.compile(r"\b(should|may|might|could|will|must)\b", re.IGNORECASE)
# A quoted message is copied from the source character for character, so its words are
# the product's, not the requirement's: `show "Name must be unique"` is well formed.
# Run c4cbd381 left 13 such requirements flagged that no Reviewer could fix.
_QUOTED_RE = re.compile(r'"[^"]*"|“[^”]*”|(?<![A-Za-z])\'[^\']*\'(?![A-Za-z])')
_PRIORITY_JIRA = {"P0": "Highest", "P1": "High", "P2": "Medium"}

CSV_COLUMNS = [
    "Issue Id", "Parent Id", "Issue Type", "Summary", "Description",
    "Acceptance Criteria", "Priority", "Story Points", "Labels", "Component",
    "Milestone", "Order", "Depends On",
]


class AssembleBacklogFailed(Exception):
    """The backlog is below the final-mode coverage threshold, or no story file
    parsed at all. ``backlog.md``, ``backlog.csv``, ``backlog.json`` and
    ``build/coverage.json`` are still written so the failure is inspectable; the
    message names every uncovered evidenced item (FR-054) or explains why nothing
    parsed (FR-055)."""


# ── parsing (pure) ──────────────────────────────────────────────────────────────────

def _parse_json(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_backlog_plan(text: str | None) -> dict:
    """§6.4 shape, defensively defaulted — a missing/unparsable plan becomes an empty
    one (no epics, no features) rather than a hard failure; every downstream story then
    reports its epic as missing (checked by ``check_hierarchy``), which is visible in
    ``coverage.json`` without crashing the step. Only FR-054 and FR-055 raise."""
    data = _parse_json(text)
    if not isinstance(data, dict):
        data = {}
    return {
        "shape": data.get("shape") or "epic-story",
        "product": data.get("product") or "",
        "personas": data.get("personas") or [],
        "features": data.get("features") or [],
        "epics": data.get("epics") or [],
        "unassigned": data.get("unassigned") or [],
        "walking_skeleton": data.get("walking_skeleton") if isinstance(data.get("walking_skeleton"), dict) else {},
        "definition_of_ready": data.get("definition_of_ready") or [],
        "definition_of_done": data.get("definition_of_done") or [],
    }


def _text_lists(value: Any) -> Any:
    """Every list item that is a bare number or bool becomes its text, recursively.

    Model-written JSON puts numbers where the renderers expect labels — a select's
    ``options: [12, 24, 48]`` crashed ``", ".join`` and with it the whole assembly
    (run 05832e65). Converting once at parse time covers every join; scalar fields
    (``points``) are left as they are."""
    if isinstance(value, dict):
        return {k: _text_lists(v) for k, v in value.items()}
    if isinstance(value, list):
        return [str(v) if isinstance(v, (int, float, bool)) else _text_lists(v) for v in value]
    return value


def parse_solution_kind(text: str | None) -> list[dict]:
    """§6.3 — ``{"items": [...]}``; a missing or unparsable file is no items."""
    data = _parse_json(text)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    return [_text_lists(it) for it in items if isinstance(it, dict)] if isinstance(items, list) else []


def collect_coverage_items(solution: dict[str, list[dict]]) -> dict[str, dict]:
    items: dict[str, dict] = {}
    for kind, lst in solution.items():
        if kind in NON_COVERAGE_KINDS:
            continue
        for it in lst:
            item_id = it.get("id")
            if not item_id:
                continue
            entry = dict(it)
            entry["kind"] = kind
            items[item_id] = entry
    return items


def list_story_task_ids(text: str | None) -> list[str]:
    """§6.5 ``json_tasks`` shape → the ordered list of task ids, each naming
    ``stories/<id>.json``."""
    data = _parse_json(text)
    if not isinstance(data, dict):
        return []
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [t.get("id") for t in tasks if isinstance(t, dict) and t.get("id")]


def parse_story_file(text: str | None) -> list[dict] | None:
    """§6.6 ``{"epic": ..., "stories": [...]}`` → the stories list, or ``None`` when
    the file is absent, not valid JSON, or not that shape (FR-055 "does not parse")."""
    data = _parse_json(text)
    if not isinstance(data, dict):
        return None
    stories = data.get("stories")
    if not isinstance(stories, list):
        return None
    return [_text_lists(s) for s in stories if isinstance(s, dict)]


# ── EARS (§7.2) ──────────────────────────────────────────────────────────────────────

def check_ears(story_id: str, req: dict) -> list[dict]:
    """One requirement → its ``story_errors`` entries. Each violation gets its own,
    distinctly named check so a reviewer sees exactly what is wrong."""
    errors: list[dict] = []
    pattern = req.get("pattern")
    text = req.get("text") or ""
    req_id = req.get("id", "?")
    stripped = text.strip()
    if pattern not in EARS_PATTERN_FIRST_WORD:
        errors.append({"story": story_id, "check": "ears.unknown_pattern",
                        "detail": f"requirement {req_id}: unknown pattern {pattern!r}"})
    else:
        expected = EARS_PATTERN_FIRST_WORD[pattern]
        first_word = stripped.split(" ", 1)[0].rstrip(",") if stripped else ""
        if first_word != expected:
            errors.append({"story": story_id, "check": "ears.pattern_word",
                            "detail": f"requirement {req_id}: pattern {pattern!r} expects text starting "
                                      f"with {expected!r}, got {first_word!r}"})
    unquoted = _QUOTED_RE.sub('""', text)
    shall_count = len(_SHALL_RE.findall(unquoted))
    if shall_count == 0:
        errors.append({"story": story_id, "check": "ears.shall_zero",
                        "detail": f"requirement {req_id}: no 'shall'"})
    elif shall_count > 1:
        errors.append({"story": story_id, "check": "ears.shall_multiple",
                        "detail": f"requirement {req_id}: 'shall' appears {shall_count} times"})
    modals = sorted({m.lower() for m in _BANNED_MODAL_RE.findall(unquoted)})
    if modals:
        errors.append({"story": story_id, "check": "ears.banned_modal",
                        "detail": f"requirement {req_id}: banned modal verb(s) {', '.join(modals)}"})
    return errors


# ── Gherkin (§7.3) ───────────────────────────────────────────────────────────────────

_SCENARIO_RE = re.compile(r"^(Scenario Outline|Scenario)\s*:\s*(.*)$")
_STEP_RE = re.compile(r"^(Given|When|Then)\b")


def parse_gherkin(lines: list[str]) -> dict:
    """A story's ``gherkin`` line list → ``{"has_feature": bool, "background_given": bool,
    "scenarios": [...]}``, each scenario ``{"type", "title", "tags" (without "@"), "given",
    "when", "then", "examples"}``. A tags line is any line of only ``@token`` tokens; it
    applies to the next ``Scenario``/``Scenario Outline`` line and is dropped by anything
    else. ``background_given`` is True when a ``Background:`` block carries a Given, which
    every scenario of the feature inherits."""
    has_feature = any(line.strip().startswith("Feature:") for line in lines)
    scenarios: list[dict] = []
    pending_tags: list[str] = []
    background = {"given": False, "when": False, "then": False}
    current: dict | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("@"):
            pending_tags.extend(tok[1:] for tok in line.split() if tok.startswith("@") and len(tok) > 1)
            continue
        if line.startswith("Background:"):
            current = background
            pending_tags = []
            continue
        m = _SCENARIO_RE.match(line)
        if m:
            current = {"type": m.group(1), "title": m.group(2).strip(), "tags": pending_tags,
                       "given": False, "when": False, "then": False, "examples": False}
            scenarios.append(current)
            pending_tags = []
            continue
        if line.startswith("Examples"):
            if current is not None:
                current["examples"] = True
            pending_tags = []
            continue
        step = _STEP_RE.match(line)
        if step and current is not None:
            current[step.group(1).lower()] = True
            continue
        pending_tags = []
    return {"has_feature": has_feature, "background_given": background["given"], "scenarios": scenarios}


def check_gherkin(story: dict) -> tuple[list[dict], list[dict], set[str]]:
    """One story → ``(story_errors, scenarios_without_requirement, requirement ids a
    scenario validly tags)``. The last two feed the coverage-level lists FR-052 wants."""
    story_id = story.get("id", "?")
    parsed = parse_gherkin(story.get("gherkin") or [])
    req_ids = {r.get("id") for r in (story.get("requirements") or []) if isinstance(r, dict) and r.get("id")}
    errors: list[dict] = []
    scenarios_without_requirement: list[dict] = []
    covered_req_ids: set[str] = set()
    if not parsed["has_feature"]:
        errors.append({"story": story_id, "check": "gherkin.no_feature", "detail": "no 'Feature:' line"})
    for sc in parsed["scenarios"]:
        missing_steps = [k for k in ("given", "when", "then")
                         if not sc[k] and not (k == "given" and parsed["background_given"])]
        if missing_steps:
            errors.append({"story": story_id, "check": "gherkin.missing_steps",
                            "detail": f"scenario {sc['title']!r} missing {'/'.join(missing_steps)}"})
        if sc["type"] == "Scenario Outline" and not sc["examples"]:
            errors.append({"story": story_id, "check": "gherkin.outline_without_examples",
                            "detail": f"scenario outline {sc['title']!r} has no Examples"})
        req_tags = [t for t in sc["tags"] if t.startswith("REQ-")]
        if not req_tags:
            errors.append({"story": story_id, "check": "gherkin.missing_req_tag",
                            "detail": f"scenario {sc['title']!r} carries no @REQ- tag"})
            scenarios_without_requirement.append({"story": story_id, "scenario": sc["title"]})
            continue
        valid = [t for t in req_tags if t in req_ids]
        bad = [t for t in req_tags if t not in req_ids]
        covered_req_ids.update(valid)
        if bad:
            errors.append({"story": story_id, "check": "gherkin.unknown_req_tag",
                            "detail": f"scenario {sc['title']!r} tags {', '.join(bad)}, "
                                      f"not a requirement of this story"})
        if not valid:
            scenarios_without_requirement.append({"story": story_id, "scenario": sc["title"]})
    return errors, scenarios_without_requirement, covered_req_ids


# ── api (§14.3) ──────────────────────────────────────────────────────────────────────

def check_api(story_id: str, api_ids: list, endpoint_ids: set[str]) -> list[dict]:
    """A story's ``api`` ids not present in ``endpoints.json`` → ``api.unknown_endpoint``."""
    return [{"story": story_id, "check": "api.unknown_endpoint",
              "detail": f"api id {aid!r} does not exist in endpoints"}
             for aid in api_ids if aid not in endpoint_ids]


# ── duplicates and hierarchy ────────────────────────────────────────────────────────

def check_duplicates(all_stories: list[dict]) -> list[dict]:
    errors: list[dict] = []
    story_ids = [s.get("id") for s in all_stories if s.get("id")]
    counts = Counter(story_ids)
    for sid in sorted(i for i, n in counts.items() if n > 1):
        errors.append({"story": sid, "check": "duplicate.story_id",
                        "detail": f"story id {sid!r} appears {counts[sid]} times"})
    owners: dict[str, list[str]] = {}
    for s in all_stories:
        for r in (s.get("requirements") or []):
            rid = r.get("id") if isinstance(r, dict) else None
            if rid:
                owners.setdefault(rid, []).append(s.get("id", "?"))
    for rid in sorted(owners):
        group = owners[rid]
        if len(group) > 1:
            for owner in group:
                others = ", ".join(o for o in group if o != owner)
                errors.append({"story": owner, "check": "duplicate.requirement_id",
                                "detail": f"requirement id {rid!r} also used by {others}"})
    return errors


def _epics_by_id(plan: dict) -> dict[str, dict]:
    return {e["id"]: e for e in plan["epics"] if isinstance(e, dict) and e.get("id")}


def check_hierarchy(plan: dict, all_stories: list[dict]) -> list[dict]:
    """§6.4 integrity: every story's epic exists; in ``feature-epic-story`` every epic
    has a feature; no epic has zero stories."""
    errors: list[dict] = []
    epics = _epics_by_id(plan)
    story_counts: Counter = Counter(s.get("epic") for s in all_stories if s.get("epic") in epics)
    for s in all_stories:
        eid = s.get("epic")
        if eid not in epics:
            errors.append({"id": s.get("id", "?"), "error": f"epic {eid!r} does not exist"})
    for eid, epic in epics.items():
        if story_counts.get(eid, 0) == 0:
            errors.append({"id": eid, "error": "no stories"})
        if plan["shape"] == "feature-epic-story" and not epic.get("feature"):
            errors.append({"id": eid, "error": "no feature"})
    return errors


# ── coverage (FR-052, FR-054) ────────────────────────────────────────────────────────

def compute_coverage(coverage_items: dict[str, dict], all_stories: list[dict]) -> tuple[list[dict], dict]:
    covered_ids: set[str] = set()
    for s in all_stories:
        covered_ids.update(s.get("covers") or [])
    uncovered: list[dict] = []
    evidenced_total = 0
    evidenced_covered = 0
    for item_id in sorted(coverage_items):
        item = coverage_items[item_id]
        provenance = item.get("provenance", "evidenced")
        is_covered = item_id in covered_ids
        if provenance == "evidenced":
            evidenced_total += 1
            if is_covered:
                evidenced_covered += 1
        if not is_covered:
            uncovered.append({"item": item_id, "provenance": provenance})
    totals = {
        "coverage_items": len(coverage_items),
        "covered": sum(1 for i in coverage_items if i in covered_ids),
        "evidenced": evidenced_total,
        "evidenced_covered": evidenced_covered,
    }
    return uncovered, totals


def run_checks(plan: dict, solution: dict[str, list[dict]], all_stories: list[dict]) -> dict:
    """Every §6/§7 check, assembled into the §6.7 ``coverage.json`` shape (minus
    ``mode``/``shape``, added by the caller). Totals are computed here, from the
    lists — never typed by a model (FR-050)."""
    coverage_items = collect_coverage_items(solution)
    endpoint_ids = {it.get("id") for it in solution.get("endpoints", []) if it.get("id")}
    story_errors: list[dict] = check_duplicates(all_stories)
    requirements_without_scenario: list[str] = []
    scenarios_without_requirement: list[dict] = []

    for story in all_stories:
        sid = story.get("id", "?")
        for req in story.get("requirements") or []:
            if isinstance(req, dict):
                story_errors.extend(check_ears(sid, req))
        g_errors, g_missing, g_covered = check_gherkin(story)
        story_errors.extend(g_errors)
        scenarios_without_requirement.extend(g_missing)
        story_errors.extend(check_api(sid, story.get("api") or [], endpoint_ids))
        for req in story.get("requirements") or []:
            if isinstance(req, dict):
                rid = req.get("id")
                if rid and rid not in g_covered:
                    requirements_without_scenario.append(rid)

    hierarchy_errors = check_hierarchy(plan, all_stories)
    build = compute_build_order(plan, all_stories)
    story_errors.extend(build["story_errors"])
    hierarchy_errors.extend(build["hierarchy_errors"])
    uncovered, totals = compute_coverage(coverage_items, all_stories)

    return {
        "uncovered": uncovered,
        "requirements_without_scenario": requirements_without_scenario,
        "scenarios_without_requirement": scenarios_without_requirement,
        "story_errors": story_errors,
        "hierarchy_errors": hierarchy_errors,
        "totals": totals,
    }


# ── build order (build-order.md) ────────────────────────────────────────────────────
#
# The Backlog Planner declares what each epic needs first ("depends_on") and names the
# walking skeleton; everything below is computed from that graph, so the order can never
# disagree with it. Milestone 1 is the skeleton and every epic it needs, milestone 2 the
# rest of the first release, milestone 3 the later release. An epic's priority follows
# its milestone (P0, P1, P2), and no story is above its epic's.

MILESTONES = {1: "Walking skeleton", 2: "First release", 3: "Later release"}
MILESTONE_PRIORITY = {1: "P0", 2: "P1", 3: "P2"}
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}


def _cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Each distinct cycle once, as a closed path (``[a, b, a]``)."""
    state: dict[str, int] = {}
    path: list[str] = []
    found: list[list[str]] = []
    seen: set[frozenset] = set()

    def visit(node: str) -> None:
        state[node] = 1
        path.append(node)
        for dep in graph.get(node, ()):
            if state.get(dep) == 1:
                cycle = path[path.index(dep):] + [dep]
                if frozenset(cycle) not in seen:
                    seen.add(frozenset(cycle))
                    found.append(cycle)
            elif dep in graph and dep not in state:
                visit(dep)
        path.pop()
        state[node] = 2

    for node in sorted(graph):
        if node not in state:
            visit(node)
    return found


def _levels(graph: dict[str, list[str]]) -> dict[str, int]:
    """Node → 1 + its longest chain of dependencies. A cycle (reported elsewhere) is
    broken at its smallest id, so every node still gets a level."""
    remaining = {n: [d for d in deps if d in graph and d != n] for n, deps in graph.items()}
    level: dict[str, int] = {}
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if all(d in level for d in deps))
        if not ready:
            stuck = min(remaining)
            remaining[stuck] = [d for d in remaining[stuck] if d in level]
            continue
        for n in ready:
            level[n] = 1 + max((level[d] for d in remaining.pop(n)), default=0)
    return level


def _closure(graph: dict[str, list[str]], roots: list[str]) -> set[str]:
    out: set[str] = set()
    todo = [r for r in roots if r in graph]
    while todo:
        node = todo.pop()
        if node not in out:
            out.add(node)
            todo.extend(d for d in graph[node] if d in graph)
    return out


def compute_build_order(plan: dict, all_stories: list[dict]) -> dict:
    """The build order and the errors in the graph behind it.

    Returns ``{"epics": {id: {"milestone", "wave", "priority", "points"}}, "stories":
    {id: {"milestone", "wave", "order"}}, "sequence": [epic ids in build order],
    "critical_path": [epic ids], "skeleton": {"flow", "epics"}, "story_errors": [...],
    "hierarchy_errors": [...]}``. ``priority`` is ``None`` for every epic when the plan
    names no walking skeleton — a plan from before build order carries no priority tiers,
    so its stories are not held to one."""
    epics = _epics_by_id(plan)
    graph = {eid: [d for d in (e.get("depends_on") or []) if isinstance(d, str)] for eid, e in epics.items()}
    hierarchy_errors: list[dict] = []
    for eid, deps in graph.items():
        for dep in deps:
            if dep == eid:
                hierarchy_errors.append({"id": eid, "error": "depends_on names the epic itself"})
            elif dep not in epics:
                hierarchy_errors.append({"id": eid, "error": f"depends_on names {dep!r}, which is no epic"})
            elif epics[eid].get("release") != "later" and epics[dep].get("release") == "later":
                hierarchy_errors.append({"id": eid, "error": f"a first-release epic depends on {dep}, "
                                                              f"a later-release epic"})
    # Only real edges from here on: an unknown or self id is reported above, once.
    graph = {eid: [d for d in deps if d in epics and d != eid] for eid, deps in graph.items()}
    for cycle in _cycles(graph):
        hierarchy_errors.append({"id": cycle[0], "error": "depends_on cycle: " + " -> ".join(cycle)})

    skeleton = plan.get("walking_skeleton") if isinstance(plan.get("walking_skeleton"), dict) else {}
    skeleton_roots = [e for e in (skeleton.get("epics") or []) if isinstance(e, str)]
    for eid in skeleton_roots:
        if eid not in epics:
            hierarchy_errors.append({"id": "walking_skeleton", "error": f"names {eid!r}, which is no epic"})
    in_skeleton = _closure(graph, skeleton_roots)
    has_skeleton = bool(in_skeleton)

    by_epic: dict[str, list[dict]] = {}
    for s in all_stories:
        if s.get("epic") in epics and s.get("id"):
            by_epic.setdefault(s["epic"], []).append(s)

    level = _levels(graph)
    info: dict[str, dict] = {}
    for eid, epic in epics.items():
        milestone = 1 if eid in in_skeleton else (3 if epic.get("release") == "later" else 2)
        points = sum(s.get("points") for s in by_epic.get(eid, []) if isinstance(s.get("points"), int))
        info[eid] = {"milestone": milestone, "priority": MILESTONE_PRIORITY[milestone] if has_skeleton else None,
                     "points": points}
    for m in MILESTONES:
        m_levels = sorted({level[e] for e in epics if info[e]["milestone"] == m})
        for eid in epics:
            if info[eid]["milestone"] == m:
                info[eid]["wave"] = m_levels.index(level[eid]) + 1
    sequence = sorted(epics, key=lambda e: (info[e]["milestone"], info[e]["wave"], e))

    story_ids = {s.get("id") for s in all_stories if s.get("id")}
    epic_of = {s.get("id"): s.get("epic") for s in all_stories if s.get("id")}
    story_errors: list[dict] = []
    story_graph: dict[str, list[str]] = {}
    for s in all_stories:
        sid = s.get("id")
        if not sid:
            continue
        deps = [d for d in (s.get("dependencies") or []) if isinstance(d, str)]
        for dep in deps:
            if dep not in story_ids and dep not in epics:
                story_errors.append({"story": sid, "check": "dependencies.unknown",
                                      "detail": f"dependency {dep!r} is no story or epic"})
        story_graph[sid] = [d for d in deps if d in story_ids]
    for cycle in _cycles(story_graph):
        for sid in cycle[:-1]:
            story_errors.append({"story": sid, "check": "dependencies.cycle",
                                  "detail": "dependency cycle: " + " -> ".join(cycle)})

    stories: dict[str, dict] = {}
    order = 0
    for eid in sequence:
        members = by_epic.get(eid, [])
        member_ids = {s["id"] for s in members}
        s_level = _levels({s["id"]: [d for d in story_graph.get(s["id"], []) if d in member_ids] for s in members})
        for s in sorted(members, key=lambda s: (s_level[s["id"]], s["id"])):
            order += 1
            stories[s["id"]] = {"milestone": info[eid]["milestone"], "wave": info[eid]["wave"], "order": order}
    position = {e: i for i, e in enumerate(sequence)}
    for s in all_stories:
        sid, eid = s.get("id"), s.get("epic")
        if sid not in stories:
            continue
        for dep in (d for d in s.get("dependencies") or [] if isinstance(d, str)):
            later = (dep in stories and stories[dep]["order"] > stories[sid]["order"] and epic_of[dep] != eid) \
                or (dep in position and position[dep] > position[eid])
            if later:
                story_errors.append({"story": sid, "check": "dependencies.later",
                                      "detail": f"dependency {dep} is built after this story: its epic "
                                                f"needs a depends_on"})
        epic_priority = info[eid]["priority"]
        if epic_priority and _PRIORITY_RANK.get(s.get("priority"), 9) < _PRIORITY_RANK[epic_priority]:
            story_errors.append({"story": sid, "check": "priority.above_epic",
                                  "detail": f"priority {s.get('priority')} is above its epic's {epic_priority}"})

    critical = _critical_path(graph, level, {e: info[e]["points"] for e in epics})
    return {"epics": info, "stories": stories, "sequence": sequence, "critical_path": critical,
            "skeleton": {"flow": skeleton.get("flow") or "", "epics": sorted(in_skeleton)},
            "story_errors": story_errors, "hierarchy_errors": hierarchy_errors}


def _critical_path(graph: dict[str, list[str]], level: dict[str, int], weight: dict[str, int]) -> list[str]:
    """The heaviest chain of epics by story points: none of it can start before the one
    before it is done, so it bounds how soon the whole backlog can finish."""
    best: dict[str, int] = {}
    prev: dict[str, str | None] = {}
    for node in sorted(graph, key=lambda n: (level[n], n)):
        deps = [d for d in graph[node] if d in best and level[d] < level[node]]
        before = max(deps, key=lambda d: (best[d], d), default=None)
        best[node] = weight.get(node, 0) + (best[before] if before else 0)
        prev[node] = before
    if not best:
        return []
    node: str | None = max(best, key=lambda n: (best[n], n))
    chain: list[str] = []
    while node:
        chain.append(node)
        node = prev[node]
    return list(reversed(chain))


# ── hierarchy walk shared by markdown / csv / json rendering ───────────────────────

def group_stories(plan: dict, all_stories: list[dict]) -> tuple[list[dict], list[dict]]:
    """``(groups, orphans)``. Each group is ``{"feature": dict|None, "epic": dict,
    "stories": [dict, ...]}`` in hierarchy order (feature → its epics, then any epic no
    feature claims); ``orphans`` are stories whose ``epic`` names no epic in the plan
    (a ``check_hierarchy`` "does not exist" case) — they are never silently dropped."""
    epics = _epics_by_id(plan)
    by_epic: dict[str, list[dict]] = {}
    orphans: list[dict] = []
    for s in all_stories:
        eid = s.get("epic")
        if eid in epics:
            by_epic.setdefault(eid, []).append(s)
        else:
            orphans.append(s)
    for lst in by_epic.values():
        lst.sort(key=lambda s: s.get("id") or "")

    groups: list[dict] = []
    seen_epics: set[str] = set()
    if plan["shape"] == "feature-epic-story":
        for feat in plan["features"]:
            if not isinstance(feat, dict) or not feat.get("id"):
                continue
            for eid in feat.get("epics") or []:
                epic = epics.get(eid)
                if epic is None:
                    continue
                groups.append({"feature": feat, "epic": epic, "stories": by_epic.get(eid, [])})
                seen_epics.add(eid)
        for eid, epic in epics.items():
            if eid not in seen_epics:
                groups.append({"feature": None, "epic": epic, "stories": by_epic.get(eid, [])})
    else:
        for epic in plan["epics"]:
            if isinstance(epic, dict) and epic.get("id"):
                groups.append({"feature": None, "epic": epic, "stories": by_epic.get(epic["id"], [])})
    return groups, orphans


# ── backlog.md (§8.1) ────────────────────────────────────────────────────────────────

def render_overview(plan: dict, solution: dict[str, list[dict]], all_stories: list[dict], mode: str) -> list[str]:
    lines = ["## Overview", "",
              f"- Product: {plan['product'] or '(untitled)'}",
              f"- Mode: {mode}",
              f"- Shape: {plan['shape']}",
              f"- Stories: {len(all_stories)}",
              f"- Coverage items: {sum(len(v) for v in solution.values())}", ""]
    if plan["personas"]:
        lines.append("Personas:")
        for p in plan["personas"]:
            lines.append(f"- **{p.get('id','')}** {p.get('name','')} — {p.get('goal','')}")
        lines.append("")
    groups, orphans = group_stories(plan, all_stories)
    three_level = plan["shape"] == "feature-epic-story"
    lines.append("Hierarchy:")
    seen_features: set[str] = set()
    for g in groups:
        feat, epic, stories = g["feature"], g["epic"], g["stories"]
        indent = ""
        if three_level:
            if feat and feat.get("id") not in seen_features:
                seen_features.add(feat["id"])
                lines.append(f"- {feat['id']} {feat.get('name','')}")
            indent = "  " if feat else ""
        lines.append(f"{indent}- {epic.get('id','')} {epic.get('name','')}")
        for s in stories:
            lines.append(f"{indent}  - {s.get('id','')} {s.get('title','')}")
    if orphans:
        lines.append("- (ungrouped)")
        for s in orphans:
            lines.append(f"  - {s.get('id','')} {s.get('title','')}")
    lines.append("")
    return lines


def render_story_block(story: dict, level: int, endpoints_by_id: dict[str, dict] | None = None) -> list[str]:
    endpoints_by_id = endpoints_by_id or {}
    hashes = "#" * level
    lines = [f"{hashes} {story.get('id','?')} {story.get('title','')}", "",
              f"As a {story.get('persona','')}, I want {story.get('i_want','')}, "
              f"so that {story.get('so_that','')}.", ""]
    if story.get("description"):
        lines.append(story["description"])
        lines.append("")
    if story.get("preconditions"):
        lines.append("Preconditions:")
        lines.extend(f"- {p}" for p in story["preconditions"])
        lines.append("")
    reqs = story.get("requirements") or []
    if reqs:
        lines += ["| id | pattern | text |", "|---|---|---|"]
        lines += [f"| {r.get('id','')} | {r.get('pattern','')} | {r.get('text','')} |" for r in reqs]
        lines.append("")
    if story.get("gherkin"):
        lines.append("```gherkin")
        lines.extend(story["gherkin"])
        lines.append("```")
        lines.append("")
    ui = story.get("ui") or []
    if ui:
        lines += ["| screen | field | control | required | validation | example | options |",
                   "|---|---|---|---|---|---|---|"]
        for f in ui:
            opts = _join(f.get("options"))
            lines.append(f"| {f.get('screen','')} | {f.get('field','')} | {f.get('control','')} | "
                          f"{f.get('required','')} | {f.get('validation','')} | {f.get('example','')} | {opts} |")
        lines.append("")
    if story.get("data"):
        lines.append("Data:")
        lines.extend(f"- {d.get('entity','')} {d.get('operation','')}: "
                      f"{_join(d.get('attributes'))}" for d in story["data"])
        lines.append("")
    if story.get("integrations"):
        lines.append("Integrations:")
        lines.extend(f"- {i.get('integration','')}: {i.get('behaviour','')}" for i in story["integrations"])
        lines.append("")
    if story.get("api"):
        for aid in story["api"]:
            ep = endpoints_by_id.get(aid)
            if ep:
                lines.append(f"API: {ep.get('method','')} {ep.get('path','')} — {ep.get('summary','')}")
            else:
                lines.append(f"API: {aid}")
        lines.append("")
    if story.get("business_rules"):
        lines.append("Business rules:")
        lines.extend(f"- {b}" for b in story["business_rules"])
        lines.append("")
    if story.get("nfr"):
        lines.append(f"NFRs: {', '.join(story['nfr'])}")
        lines.append("")
    if story.get("dependencies"):
        lines.append(f"Dependencies: {', '.join(story['dependencies'])}")
        lines.append("")
    lines.append(f"Priority: {story.get('priority','')} · Points: {story.get('points','')} · "
                  f"Labels: {_join(story.get('labels'))}")
    lines.append(f"Provenance: {story.get('provenance','')} · Sources: {_join(story.get('sources'))}")
    lines.append("")
    return lines


def render_backlog_section(plan: dict, all_stories: list[dict],
                            endpoints_by_id: dict[str, dict] | None = None) -> list[str]:
    """``## FEAT-… → ### EPIC-… → #### US-…`` (or ``## EPIC → ### US``), §8.1 bullet 2.
    An epic no feature claims still nests under a heading (never a bare ``###``), and
    orphan stories (epic missing) get their own top-level section — every heading level
    is reached by exactly one level, never skipped."""
    lines: list[str] = []
    groups, orphans = group_stories(plan, all_stories)
    three_level = plan["shape"] == "feature-epic-story"
    seen_features: set[str] = set()
    emitted_no_feature = False
    for g in groups:
        feat, epic, stories = g["feature"], g["epic"], g["stories"]
        if three_level:
            if feat:
                if feat.get("id") not in seen_features:
                    seen_features.add(feat["id"])
                    lines += [f"## {feat['id']} {feat.get('name','')}", ""]
            elif not emitted_no_feature:
                lines += ["## (no feature)", ""]
                emitted_no_feature = True
            lines += [f"### {epic['id']} {epic.get('name','')}", ""]
            for s in stories:
                lines.extend(render_story_block(s, 4, endpoints_by_id))
        else:
            lines += [f"## {epic['id']} {epic.get('name','')}", ""]
            for s in stories:
                lines.extend(render_story_block(s, 3, endpoints_by_id))
    if orphans:
        lines += ["## Ungrouped stories", ""]
        for s in orphans:
            lines.extend(render_story_block(s, 3, endpoints_by_id))
    return lines


def render_appendix_a(solution: dict[str, list[dict]]) -> list[str]:
    lines = ["## Appendix A — Data Model", ""]
    entities = solution.get("entities", [])
    for e in entities:
        lines += [f"### {e.get('id','')} {e.get('name','')}", ""]
        attrs = e.get("attributes") or []
        if attrs:
            lines += ["| name | type | required | validation | example |", "|---|---|---|---|---|"]
            lines += [f"| {a.get('name','')} | {a.get('type','')} | {a.get('required','')} | "
                      f"{a.get('validation','')} | {a.get('example','')} |" for a in attrs]
            lines.append("")
    if entities:
        lines += ["```mermaid", "erDiagram"]
        card = {"1-1": "||--||", "1-n": "||--o{", "n-n": "}o--o{"}
        for e in entities:
            for rel in e.get("relationships") or []:
                lines.append(f"    {e.get('id','')} {card.get(rel.get('kind'), '||--||')} "
                              f"{rel.get('to','')} : {rel.get('via','')}")
        lines += ["```", ""]
    return lines


def render_appendix_b(solution: dict[str, list[dict]]) -> list[str]:
    lines = ["## Appendix B — Integration Catalogue", ""]
    ints = solution.get("integrations", [])
    if ints:
        lines += ["| id | system | direction | trigger | data | failure |", "|---|---|---|---|---|---|"]
        lines += [f"| {i.get('id','')} | {i.get('system','')} | {i.get('direction','')} | "
                  f"{i.get('trigger','')} | {i.get('data','')} | {i.get('failure','')} |" for i in ints]
        lines.append("")
    return lines


def render_appendix_c(solution: dict[str, list[dict]]) -> list[str]:
    lines = ["## Appendix C — Role-Permission Matrix", ""]
    for r in solution.get("roles", []):
        lines += [f"### {r.get('id','')} {r.get('name','')}", ""]
        perms = r.get("permissions") or []
        if perms:
            lines += ["| on | actions |", "|---|---|"]
            lines += [f"| {p.get('on','')} | {', '.join(p.get('actions') or [])} |" for p in perms]
        lines.append("")
    return lines


def render_appendix_d(solution: dict[str, list[dict]]) -> list[str]:
    lines = ["## Appendix D — NFRs", ""]
    nfrs = solution.get("nfrs", [])
    if nfrs:
        lines += ["| id | category | statement |", "|---|---|---|"]
        lines += [f"| {n.get('id','')} | {n.get('category','')} | {n.get('statement','')} |" for n in nfrs]
        lines.append("")
    return lines


def render_appendix_e(all_stories: list[dict]) -> list[str]:
    lines = ["## Appendix E — Traceability", "",
              "| source | coverage item | story | requirement | scenario |", "|---|---|---|---|---|"]
    for s in all_stories:
        parsed = parse_gherkin(s.get("gherkin") or [])
        req = (s.get("requirements") or [{}])[0].get("id", "") if s.get("requirements") else ""
        scenario = parsed["scenarios"][0]["title"] if parsed["scenarios"] else ""
        source = _join(s.get("sources"))
        for item in (s.get("covers") or []):
            lines.append(f"| {source} | {item} | {s.get('id','')} | {req} | {scenario} |")
    lines.append("")
    return lines


def render_appendix_f(solution: dict[str, list[dict]], all_stories: list[dict]) -> list[str]:
    lines = ["## Appendix F — Inferred Items and Open Questions", ""]
    inferred_items = [it for items in solution.values() for it in items if it.get("provenance") == "inferred"]
    if inferred_items:
        lines.append("Inferred items:")
        lines.extend(f"- {it.get('id','')} {it.get('name','')}" for it in inferred_items)
        lines.append("")
    inferred_stories = [s for s in all_stories if s.get("provenance") == "inferred"]
    if inferred_stories:
        lines.append("Inferred stories:")
        lines.extend(f"- {s.get('id','')} {s.get('title','')}" for s in inferred_stories)
        lines.append("")
    open_qs = [(s.get("id", ""), q) for s in all_stories for q in (s.get("open_questions") or [])]
    if open_qs:
        lines.append("Open questions:")
        lines.extend(f"- {sid}: {q}" for sid, q in open_qs)
        lines.append("")
    return lines


def render_appendix_g(coverage: dict) -> list[str]:
    totals = coverage.get("totals", {})
    return ["## Appendix G — Coverage Summary", "",
             f"- Coverage items: {totals.get('coverage_items', 0)}",
             f"- Covered: {totals.get('covered', 0)}",
             f"- Evidenced: {totals.get('evidenced', 0)}",
             f"- Evidenced covered: {totals.get('evidenced_covered', 0)}",
             f"- Uncovered: {len(coverage.get('uncovered', []))}",
             f"- Requirements without scenario: {len(coverage.get('requirements_without_scenario', []))}",
             f"- Scenarios without requirement: {len(coverage.get('scenarios_without_requirement', []))}",
             f"- Story errors: {len(coverage.get('story_errors', []))}",
             f"- Hierarchy errors: {len(coverage.get('hierarchy_errors', []))}", ""]


def render_appendix_h(solution: dict[str, list[dict]], all_stories: list[dict]) -> list[str]:
    lines = ["## Appendix H — Business Rules", ""]
    rules = solution.get("rules", [])
    if rules:
        by_rule = {r.get("id"): [st.get("id", "") for st in all_stories if r.get("id") in (st.get("covers") or [])]
                   for r in rules}
        lines += ["| id | statement | applies to | message | stories |", "|---|---|---|---|---|"]
        lines += [f"| {r.get('id','')} | {r.get('statement','')} | {', '.join(r.get('applies_to') or [])} | "
                  f"{r.get('message') or ''} | {', '.join(by_rule.get(r.get('id'), []))} |" for r in rules]
        lines.append("")
    return lines


def render_appendix_i(solution: dict[str, list[dict]]) -> list[str]:
    lines = ["## Appendix I — Glossary", ""]
    terms = solution.get("glossary", [])
    if terms:
        lines += ["| term | definition |", "|---|---|"]
        lines += [f"| {t.get('term','')} | {t.get('definition','')} |" for t in terms]
        lines.append("")
    return lines


def render_release_plan(plan: dict, all_stories: list[dict]) -> list[str]:
    """§14.4 — after the Overview: P0, then P1, then P2, stories grouped by epic with
    each story's points, and a points total per priority computed from the stories.
    A story whose epic does not exist (a ``check_hierarchy`` error) is never silently
    dropped — it lands in its own "(no epic)" bucket, same trade-off as ``group_stories``'
    ``orphans``."""
    epics = _epics_by_id(plan)
    lines = ["## Release plan", ""]
    for priority in ("P0", "P1", "P2"):
        stories = [s for s in all_stories if s.get("priority") == priority]
        lines.append(f"### {priority}")
        lines.append("")
        by_epic: dict[str, list[dict]] = {}
        no_epic: list[dict] = []
        for s in stories:
            eid = s.get("epic")
            if eid in epics:
                by_epic.setdefault(eid, []).append(s)
            else:
                no_epic.append(s)
        for eid, epic in epics.items():
            group = by_epic.get(eid)
            if not group:
                continue
            lines.append(f"- {eid} {epic.get('name','')}")
            for s in sorted(group, key=lambda s: s.get("id") or ""):
                lines.append(f"  - {s.get('id','')} {s.get('title','')} ({s.get('points','')} pts)")
        if no_epic:
            lines.append("- (no epic)")
            for s in sorted(no_epic, key=lambda s: s.get("id") or ""):
                lines.append(f"  - {s.get('id','')} {s.get('title','')} ({s.get('points','')} pts)")
        lines.append("")
        lines.append(f"Points: {sum(s.get('points') or 0 for s in stories)}")
        lines.append("")
    return lines


def _mermaid_label(text: str) -> str:
    return (text or "").replace('"', "'").replace(";", ",")


_SLICE_RE = re.compile(r"^US-([0-9]+[a-z]*)-")


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# A generated diagram stays readable: at most this many boxes and arrows in one chart,
# in a shape the PDF prints at (nearly) full size (``_shape``). A bigger graph is drawn
# in parts. An arrow to a box drawn in another part keeps a dashed copy of that box, so
# every arrow of the whole graph is still drawn.
_DIAGRAM_MAX_NODES = 15
_DIAGRAM_MAX_EDGES = 20
# Measured on run 78e185fb's PDF (A4, a ~631 px text column, charts at most 215 mm tall):
# a left-to-right chart is ~300 px per column of boxes, so 2 columns print at full size
# and 3 already shrink to ~0.67; a row of boxes is ~110-130 px tall. A top-down chart is
# ~110 px per rank, and its width is only predictable while it is at most 2 boxes wide.
_LR_MAX_ROWS = 8
_TD_MAX_RANKS = 7


def _layout(nodes: list[str], arrows: list[tuple[str, str]]) -> tuple[int, int, int]:
    """(ranks, the widest rank, the widest rank counting the bends of arrows that skip a
    rank), ranked as the renderer does: the arrows that close a cycle dropped, each box on
    its longest path from a source."""
    out: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in arrows:
        if a != b:
            out[a].append(b)
    state: dict[str, int] = {}
    kept: list[tuple[str, str]] = []

    def visit(n: str) -> None:  # depth ≤ _DIAGRAM_MAX_NODES
        state[n] = 1
        for m in out[n]:
            if state.get(m) == 1:
                continue  # closes a cycle
            kept.append((n, m))
            if m not in state:
                visit(m)
        state[n] = 2

    for n in nodes:
        if n not in state:
            visit(n)
    level = dict.fromkeys(nodes, 0)
    for _ in nodes:
        moved = False
        for a, b in kept:
            if level[b] < level[a] + 1:
                level[b], moved = level[a] + 1, True
        if not moved:
            break
    ranks = max(level.values(), default=0) + 1
    width = Counter(level.values())
    bends = Counter(width)
    for a, b in kept:
        for r in range(level[a] + 1, level[b]):
            bends[r] += 1
    return ranks, max(width.values(), default=1), max(bends.values(), default=1)


def _shape(nodes: list[str], arrows: list[tuple[str, str]]) -> str | None:
    """The direction a chart prints readably in, or None: left to right when it is at most
    two columns of boxes and ``_LR_MAX_ROWS`` rows, top down when it is a chain at most two
    boxes wide and ``_TD_MAX_RANKS`` deep."""
    ranks, widest, bent = _layout(nodes, arrows)
    if ranks <= 2 and widest <= _LR_MAX_ROWS:
        return "LR"
    if bent <= 2 and ranks <= _TD_MAX_RANKS:
        return "TD"
    return None


def _fits(members: list[str], links: dict[str, list[str]], outgoing: bool = False) -> bool:
    inside = list(dict.fromkeys(members))
    others = list(dict.fromkeys(o for m in inside for o in links.get(m, ()) if o not in set(inside)))
    edges = sum(len(links.get(m, ())) for m in inside)
    if len(inside) + len(others) > _DIAGRAM_MAX_NODES or edges > _DIAGRAM_MAX_EDGES:
        return False
    arrows = [(m, o) if outgoing else (o, m) for m in inside for o in links.get(m, ())]
    return _shape(inside + others, arrows) is not None


def diagram_parts(units: list[list[str]], links: dict[str, list[str]],
                  outgoing: bool = False) -> list[list[tuple[str, list[str]]]]:
    """Split a graph into charts that each fit the limits above.

    ``units`` are the nodes in reading order, grouped (a wave, a slice): consecutive units
    share a chart while they fit, a unit too big alone is split node by node, and a node
    with too many arrows alone is drawn over several charts. ``links[n]`` are the other
    ends of the arrows drawn with ``n`` (arrows point to them when ``outgoing``, else from
    them). Each part is ``[(node, the links it draws), …]``, so every arrow is drawn once."""
    links = {n: list(dict.fromkeys(ends)) for n, ends in links.items()}
    packed: list[list[str]] = []
    cur: list[str] = []
    for unit in units:
        if _fits(cur + unit, links, outgoing):
            cur = cur + unit
            continue
        if cur:
            packed.append(cur)
            cur = []
        if _fits(unit, links, outgoing):
            cur = list(unit)
            continue
        for node in unit:
            if cur and not _fits(cur + [node], links, outgoing):
                packed.append(cur)
                cur = []
            cur.append(node)
    if cur:
        packed.append(cur)
    per_chart = min(_DIAGRAM_MAX_EDGES, _DIAGRAM_MAX_NODES - 1, _LR_MAX_ROWS)
    parts: list[list[tuple[str, list[str]]]] = []
    for members in packed:
        if len(members) == 1 and not _fits(members, links, outgoing):
            node, ends = members[0], list(links.get(members[0], ()))
            parts += [[(node, ends[i:i + per_chart])] for i in range(0, len(ends), per_chart)]
        else:
            parts.append([(node, list(links.get(node, ()))) for node in members])
    return parts


def _flowchart(part: list[tuple[str, list[str]]], label: Callable[[str], str],
               stub_label: Callable[[str], str], outgoing: bool = False,
               solid: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """One chart of a part: its nodes, a dashed box for each other end drawn elsewhere,
    and its arrows (node → other end when ``outgoing``, else other end → node). An other
    end in ``solid`` lives in this chart: a plain box, not a dashed copy."""
    inside = {node for node, _ in part}
    stubs = list(dict.fromkeys(o for _, ends in part for o in ends if o not in inside))
    arrows = list(dict.fromkeys((n, o) if outgoing else (o, n) for n, ends in part for o in ends))
    lines = ["```mermaid", f"flowchart {_shape([n for n, _ in part] + stubs, arrows) or 'LR'}"]
    lines += [f'  {_sanitize_mermaid_id(n)}["{_mermaid_label(label(n))}"]' for n, _ in part]
    lines += [f'  {_sanitize_mermaid_id(o)}["{_mermaid_label(label(o))}"]' if o in solid
              else f'  {_sanitize_mermaid_id(o)}["{_mermaid_label(stub_label(o))}"]:::external' for o in stubs]
    lines += list(dict.fromkeys(f"  {_sanitize_mermaid_id(a)} --> {_sanitize_mermaid_id(b)}" for a, b in arrows))
    if any(o not in solid for o in stubs):
        lines.append("  classDef external stroke-dasharray: 5 5")
    return lines + ["```", ""]


def _numbered(labels: list[str]) -> list[str]:
    """Part headings made unique: one that repeats gets "(part i of n)"."""
    total, seen, out = Counter(labels), Counter(), []
    for label in labels:
        if total[label] > 1:
            seen[label] += 1
            label = f"{label} (part {seen[label]} of {total[label]})"
        out.append(label)
    return out


def _span(word: str, values: list) -> str:
    """"wave 2" or "waves 2–4": the first and last of ``values``, in order."""
    values = list(dict.fromkeys(values))
    return f"{word} {values[0]}" if len(values) == 1 else f"{word}s {values[0]}–{values[-1]}"


def render_feature_dependencies(plan: dict) -> list[str]:
    """Feature B → feature A when an epic of A depends on an epic of B (feature-epic-story)."""
    epics = _epics_by_id(plan)
    features = [f for f in plan.get("features") or [] if isinstance(f, dict) and f.get("id")]
    if plan.get("shape") != "feature-epic-story" or not features:
        return []
    feature_of = {eid: e.get("feature") for eid, e in epics.items() if e.get("feature")}
    for f in features:
        for eid in f.get("epics") or []:
            feature_of.setdefault(eid, f["id"])
    edges: list[tuple[str, str]] = []
    for eid, epic in epics.items():
        for dep in epic.get("depends_on") or []:
            a, b = feature_of.get(eid), feature_of.get(dep)
            if a and b and a != b and (b, a) not in edges:
                edges.append((b, a))
    links: dict[str, list[str]] = {f["id"]: [] for f in features}
    for b, a in edges:
        links.setdefault(a, []).append(b)
    names = {f["id"]: f"{f['id']} {f.get('name', '')}".strip() for f in features}
    parts = diagram_parts([[n] for n in links], links)
    home: dict[str, int] = {}
    for i, part in enumerate(parts, 1):
        for n, _ in part:
            home.setdefault(n, i)
    lines = ["## Feature dependencies", "", "An arrow points from a feature to one whose epics need it.", ""]
    for i, part in enumerate(parts, 1):
        if len(parts) > 1:
            lines += [f"### Part {i} of {len(parts)}", ""]
        lines += _flowchart(part, lambda n: names.get(n, n),
                            lambda n: names.get(n, n) + (f" (part {home[n]})" if n in home else ""))
    return lines


def render_story_dependencies(plan: dict, all_stories: list[dict]) -> list[str]:
    """One graph per epic whose stories have dependencies, drawn in parts when big
    (``diagram_parts``); a story of another epic, or drawn in another part, is a dashed box."""
    epic_of = {s["id"]: s.get("epic") for s in all_stories if s.get("id")}
    by_epic: dict[str, list[dict]] = {}
    for s in all_stories:
        if s.get("id") and s.get("epic"):
            by_epic.setdefault(s["epic"], []).append(s)
    names = {eid: f"{eid} {e.get('name', '')}".strip() for eid, e in _epics_by_id(plan).items()}
    out: list[str] = []
    for eid, stories in by_epic.items():
        if not any(s.get("dependencies") for s in stories):
            continue
        title = {s["id"]: s.get("title") for s in stories}
        links = {s["id"]: list(dict.fromkeys(d for d in s.get("dependencies") or []
                                              if isinstance(d, str) and d != s["id"])) for s in stories}
        slice_of: dict[str, str] = {}
        units: dict[str, list[str]] = {}
        for s in stories:
            m = _SLICE_RE.match(s["id"])
            slice_of[s["id"]] = m.group(1) if m else ""
            units.setdefault(slice_of[s["id"]], []).append(s["id"])
        # A part that draws no arrow says nothing about dependencies.
        parts = [p for p in diagram_parts(list(units.values()), links) if any(ends for _, ends in p)]
        home: dict[str, int] = {}
        for i, part in enumerate(parts, 1):
            for n, _ in part:
                home.setdefault(n, i)

        def where(n: str, eid: str = eid, home: dict = home, parts: list = parts) -> str:
            if epic_of.get(n) == eid and n in home and len(parts) > 1:
                return f"{n} (part {home[n]})"
            return n + (f" ({epic_of[n]})" if n in epic_of else "")

        labels = []
        for p in parts:
            sliced = [slice_of[n] for n, _ in p if slice_of[n]]
            labels.append(names.get(eid, eid) + (" — " + _span("slice", sliced)
                                                 if sliced and len(units) > 1 and len(parts) > 1 else ""))
        for part, label in zip(parts, _numbered(labels), strict=False):
            out += [f"### {label}", ""] + _flowchart(part, lambda n, title=title: f"{n} {_short(title.get(n))}", where)
    if not out:
        return []
    return ["## Story dependencies", "",
            "An arrow points from a story to one that needs it. A dashed box is a story of another epic, "
            "or one drawn in another part.", ""] + out


def render_build_order_md(plan: dict, all_stories: list[dict], build: dict, ready: dict[str, bool]) -> str:
    """``build-order.md`` — what an engineer builds first: the epic graph, the critical
    path, then each milestone's waves, epics and stories in order."""
    epics = _epics_by_id(plan)
    info = build["epics"]
    names = {eid: f"{eid} {epics[eid].get('name', '')}".strip() for eid in epics}
    stories = [s for s in all_stories if s.get("id") in build["stories"]]
    stories.sort(key=lambda s: build["stories"][s["id"]]["order"])
    lines = [f"# Build order — {plan['product'] or 'Backlog'}", "",
             "Build the milestones in order. Inside a milestone, build the waves in order: the epics "
             "in one wave do not depend on each other and can be built side by side. Inside an epic, "
             "build the stories in the order listed.", ""]

    lines += render_feature_dependencies(plan)
    lines += ["## Dependency graph", "",
              "An arrow points from an epic to one that needs it. Each milestone is drawn on its own, a "
              "big one in parts by wave; a dashed box is an epic drawn in another part.", ""]
    deps_of = {e: list(dict.fromkeys(d for d in epics[e].get("depends_on") or [] if d in epics and d != e))
               for e in build["sequence"]}
    for m, title in MILESTONES.items():
        members = [e for e in build["sequence"] if info[e]["milestone"] == m]
        if not members:
            continue
        waves = sorted({info[e]["wave"] for e in members})
        parts = diagram_parts([[e for e in members if info[e]["wave"] == w] for w in waves], deps_of)
        base = f"Milestone {m} — {title}"
        labels = [base if len(parts) == 1 else f"{base}, " + _span("wave", [info[e]["wave"] for e, _ in p])
                  for p in parts]
        for part, label in zip(parts, _numbered(labels), strict=False):
            lines += [f"### {label}", ""] + _flowchart(
                part, lambda e: names[e],
                lambda e: names[e] + (f" (Milestone {info[e]['milestone']}, wave {info[e]['wave']})"
                                      if e in info else ""))
    lines += render_story_dependencies(plan, all_stories)

    if len(build["critical_path"]) > 1:
        total = sum(info[e]["points"] for e in build["critical_path"])
        lines += ["## Critical path", "",
                  " → ".join(names[e] for e in build["critical_path"]) + f" — {total} points.", "",
                  "The heaviest chain of epics by story points. None of it can start before the epic "
                  "before it is done, so it bounds how soon the backlog can be finished.", ""]

    for m, title in MILESTONES.items():
        members = [e for e in build["sequence"] if info[e]["milestone"] == m]
        if not members:
            continue
        heading = f"## Milestone {m} — {title}"
        if m == 1 and build["skeleton"]["flow"]:
            heading += f": {build['skeleton']['flow']}"
        lines += [heading, ""]
        for wave in sorted({info[e]["wave"] for e in members}):
            lines += [f"### Wave {wave}", ""]
            for eid in (e for e in members if info[e]["wave"] == wave):
                epic = epics[eid]
                mine = [s for s in stories if s.get("epic") == eid]
                facts = [epic.get("type") or "", info[eid]["priority"] or "",
                         f"{len(mine)} stories", f"{info[eid]['points']} points"]
                lines += [f"#### {names[eid]}", "", " · ".join(f for f in facts if f), "",
                          f"Needs first: {', '.join(d for d in epic.get('depends_on') or [] if d in epics) or 'nothing'}", ""]
                if mine:
                    lines += ["| Order | Story | Priority | Points | Ready | Depends on |",
                              "|---|---|---|---|---|---|"]
                    for s in mine:
                        title = str(s.get("title", "")).replace("|", "\\|")
                        lines.append(f"| {build['stories'][s['id']]['order']} | {s['id']} {title} | "
                                     f"{s.get('priority', '')} | {s.get('points', '')} | "
                                     f"{'yes' if ready.get(s['id']) else 'no'} | "
                                     f"{', '.join(s.get('dependencies') or []) or '—'} |")
                    lines.append("")

    for key, title in (("definition_of_ready", "Definition of Ready"), ("definition_of_done", "Definition of Done")):
        items = [i for i in (plan.get(key) or []) if isinstance(i, str)]
        if items:
            lines += [f"## {title}", ""] + [f"- {i}" for i in items] + [""]

    problems = [f"{e['id']}: {e['error']}" for e in build["hierarchy_errors"]]
    problems += [f"{e['story']}: {e['detail']}" for e in build["story_errors"]]
    if not build["skeleton"]["epics"]:
        problems.append("The plan names no walking skeleton: no epic is marked as the first thing to build.")
    not_ready = sum(1 for s in stories if not ready.get(s["id"]))
    if not_ready:
        problems.append(f"Not ready: {not_ready} of {len(stories)} stories still carry an open question "
                        f"or a story error (see build/coverage.json).")
    orphans = [s for s in all_stories if s.get("id") and s.get("id") not in build["stories"]]
    if orphans:
        problems.append("Stories with no epic, so no place in the order: " + ", ".join(s["id"] for s in orphans))
    if problems:
        lines += ["## Problems", ""] + [f"- {p}" for p in problems] + [""]
    return "\n".join(lines) + "\n"


def render_documents_section(has_architecture: bool) -> list[str]:
    """§14.4 — links every new document this step always writes, plus ``architecture.md``
    only when the Architect wrote it."""
    lines = ["## Documents", "", f"- [{BUILD_ORDER_PATH}]({BUILD_ORDER_PATH}) — what to build first, and in what order"]
    lines.extend(f"- [{name}]({name})" for name in NEW_DOCUMENT_FILES)
    if has_architecture:
        lines.append(f"- [{ARCHITECTURE_PATH}]({ARCHITECTURE_PATH})")
    lines.append("")
    return lines


def render_markdown(plan: dict, solution: dict[str, list[dict]], all_stories: list[dict],
                     coverage: dict, mode: str, endpoints_by_id: dict[str, dict],
                     has_architecture: bool) -> str:
    lines = [f"# {plan['product'] or 'User Story Backlog'}", ""]
    lines += render_overview(plan, solution, all_stories, mode)
    lines += render_release_plan(plan, all_stories)
    lines += render_documents_section(has_architecture)
    lines += render_backlog_section(plan, all_stories, endpoints_by_id)
    lines += render_appendix_a(solution)
    lines += render_appendix_b(solution)
    lines += render_appendix_c(solution)
    lines += render_appendix_d(solution)
    lines += render_appendix_e(all_stories)
    lines += render_appendix_f(solution, all_stories)
    lines += render_appendix_g(coverage)
    lines += render_appendix_h(solution, all_stories)
    lines += render_appendix_i(solution)
    return "\n".join(lines) + "\n"


# ── backlog.csv (§8.2) ───────────────────────────────────────────────────────────────

def _story_description(story: dict) -> str:
    parts = [f"As a {story.get('persona','')}, I want {story.get('i_want','')}, "
             f"so that {story.get('so_that','')}."]
    if story.get("description"):
        parts.append(story["description"])
    reqs = story.get("requirements") or []
    if reqs:
        parts.append("Requirements:")
        parts.extend(f"- [{r.get('id','?')}] ({r.get('pattern','?')}) {r.get('text','')}" for r in reqs)
    return "\n".join(parts)


def _milestone_name(milestone: int | None) -> str:
    return f"{milestone} {MILESTONES[milestone]}" if milestone in MILESTONES else ""


def _story_row(story: dict, epic_id: str, feature_name: str, placed: dict | None = None) -> dict:
    labels = list(story.get("labels") or [])
    if story.get("type") == "enabler" and "enabler" not in labels:
        labels.append("enabler")
    priority = story.get("priority")
    return {
        "Issue Id": story.get("id", ""), "Parent Id": epic_id, "Issue Type": "Story",
        "Summary": story.get("title", ""), "Description": _story_description(story),
        "Acceptance Criteria": "\n".join(story.get("gherkin") or []),
        "Priority": _PRIORITY_JIRA.get(priority, priority or ""),
        "Story Points": story.get("points", ""), "Labels": _join(labels, " "),
        "Component": feature_name,
        "Milestone": _milestone_name((placed or {}).get("milestone")), "Order": (placed or {}).get("order", ""),
        "Depends On": _join(story.get("dependencies"), " "),
    }


def render_csv_rows(plan: dict, all_stories: list[dict], build: dict | None = None) -> list[dict]:
    groups, orphans = group_stories(plan, all_stories)
    epic_info = (build or {}).get("epics", {})
    placed = (build or {}).get("stories", {})
    rows: list[dict] = []
    seen_features: set[str] = set()
    for g in groups:
        feat, epic, stories = g["feature"], g["epic"], g["stories"]
        feature_name = feat.get("name", "") if feat else ""
        if feat and feat.get("id") not in seen_features:
            seen_features.add(feat["id"])
            rows.append({"Issue Id": feat["id"], "Parent Id": "", "Issue Type": "Feature",
                          "Summary": feat.get("name", ""), "Description": "", "Acceptance Criteria": "",
                          "Priority": "", "Story Points": "", "Labels": "", "Component": feature_name,
                          "Milestone": "", "Order": "", "Depends On": ""})
        info = epic_info.get(epic["id"], {})
        rows.append({"Issue Id": epic["id"], "Parent Id": feat["id"] if feat else "", "Issue Type": "Epic",
                      "Summary": epic.get("name", ""), "Description": "", "Acceptance Criteria": "",
                      "Priority": _PRIORITY_JIRA.get(info.get("priority"), ""), "Story Points": "", "Labels": "",
                      "Component": feature_name, "Milestone": _milestone_name(info.get("milestone")), "Order": "",
                      "Depends On": _join(epic.get("depends_on"), " ")})
        for s in stories:
            rows.append(_story_row(s, epic["id"], feature_name, placed.get(s.get("id"))))
    for s in orphans:
        rows.append(_story_row(s, s.get("epic") or "", ""))
    return rows


def render_csv(plan: dict, all_stories: list[dict], build: dict | None = None) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(render_csv_rows(plan, all_stories, build))
    return buf.getvalue()


# ── backlog.json (§8.3) ──────────────────────────────────────────────────────────────

def render_backlog_json(plan: dict, solution: dict[str, list[dict]], all_stories: list[dict],
                         coverage: dict, build: dict | None = None, ready: dict[str, bool] | None = None) -> str:
    """The plan, the model, every story and the coverage report. With a build order, each
    epic also carries its milestone, wave and priority, and each story its milestone,
    wave, order and whether it is ready — copies, the inputs are not changed."""
    groups, orphans = group_stories(plan, all_stories)
    ordered: list[dict] = [s for g in groups for s in g["stories"]] + orphans
    if build is not None:
        epic_info = build["epics"]
        plan = {**plan, "epics": [{**e, **epic_info[e["id"]]} if isinstance(e, dict) and e.get("id") in epic_info
                                  else e for e in plan["epics"]]}
        ordered = [{**s, **build["stories"].get(s.get("id"), {}), "ready": bool((ready or {}).get(s.get("id")))}
                   for s in ordered]
    payload = {"backlog": plan, "solution": solution, "stories": ordered, "coverage": coverage}
    return json.dumps(payload, indent=2)


# ── the full-application documents (§14.4) ──────────────────────────────────────────

def _pascal(name: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[^A-Za-z0-9]+", name or "") if w) or "Entity"


def _sanitize_mermaid_id(value: str) -> str:
    """A mermaid node/state id may not contain a hyphen (or most other punctuation);
    the real id still appears in the label/text, this is identifier-only."""
    return re.sub(r"[^A-Za-z0-9_]", "_", value or "")


def _json_schema_type(attr_type: str | None) -> dict:
    kind, fmt = _TYPE_MAP.get((attr_type or "").lower(), ("string", None))
    out: dict = {"type": kind}
    if fmt:
        out["format"] = fmt
    return out


def _entity_schema(entity: dict) -> dict:
    props: dict = {}
    required: list[str] = []
    for a in entity.get("attributes") or []:
        name = a.get("name", "")
        prop = _json_schema_type(a.get("type"))
        if a.get("enum"):
            prop["enum"] = a["enum"]
        if a.get("default") is not None:
            prop["default"] = a["default"]
        if a.get("validation"):
            prop["description"] = a["validation"]
        props[name] = prop
        if a.get("required"):
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


# ── data-model.md ────────────────────────────────────────────────────────────────────

def render_data_model_md(solution: dict[str, list[dict]]) -> str:
    """§14.4 — one table per entity, its relationships and indexes, a ``stateDiagram-v2``
    per entity with two or more lifecycle statuses, a Reference data section (every
    attribute-level enum with its values), and one ``erDiagram`` for all entities."""
    entities = solution.get("entities", [])
    lines = ["# Data Model", ""]
    for e in entities:
        lines += [f"## {e.get('id','')} {e.get('name','')}", ""]
        attrs = e.get("attributes") or []
        if attrs:
            lines += ["| Attribute | Type | Key | Required | Unique | Default | Enum or validation | Example |",
                       "|---|---|---|---|---|---|---|---|"]
            for a in attrs:
                enum_or_validation = _join(a["enum"]) if a.get("enum") else (a.get("validation") or "")
                default = a.get("default") if a.get("default") is not None else ""
                lines.append(f"| {a.get('name','')} | {a.get('type','')} | {a.get('key') or ''} | "
                              f"{_yn(a.get('required'))} | {_yn(a.get('unique'))} | {default} | "
                              f"{enum_or_validation} | {a.get('example','')} |")
            lines.append("")
        rels = e.get("relationships") or []
        if rels:
            lines.append("Relationships:")
            lines.extend(f"- {r.get('kind','')} {r.get('to','')} via {r.get('via','')}" for r in rels)
            lines.append("")
        indexes = e.get("indexes") or []
        if indexes:
            lines.append("Indexes:")
            lines.extend(f"- {', '.join(idx)}" for idx in indexes)
            lines.append("")
        lifecycle = e.get("lifecycle") or []
        if len(lifecycle) >= 2:
            lines += ["```mermaid", "stateDiagram-v2", f"    [*] --> {_sanitize_mermaid_id(lifecycle[0])}"]
            lines.extend(f"    {_sanitize_mermaid_id(a)} --> {_sanitize_mermaid_id(b)}"
                          for a, b in zip(lifecycle, lifecycle[1:], strict=False))
            lines += ["```", ""]
    enum_attrs = [(e, a) for e in entities for a in (e.get("attributes") or []) if a.get("enum")]
    if enum_attrs:
        lines += ["## Reference data", ""]
        lines.extend(f"- {e.get('name','')}.{a.get('name','')}: {', '.join(a['enum'])}" for e, a in enum_attrs)
        lines.append("")
    if entities:
        lines += ["```mermaid", "erDiagram"]
        card = {"1-1": "||--||", "1-n": "||--o{", "n-n": "}o--o{"}
        for e in entities:
            eid = _sanitize_mermaid_id(e.get("id") or e.get("name") or "")
            for rel in e.get("relationships") or []:
                to = _sanitize_mermaid_id(rel.get("to") or "")
                lines.append(f"    {eid} {card.get(rel.get('kind'), '||--||')} {to} : {rel.get('via','')}")
        lines += ["```", ""]
    return "\n".join(lines) + "\n"


# ── schema.json ──────────────────────────────────────────────────────────────────────

def render_schema_json(solution: dict[str, list[dict]]) -> str:
    """§14.4 — JSON Schema 2020-12, one ``$defs`` entry per entity (PascalCase name)."""
    defs = {_pascal(e.get("name") or e.get("id") or ""): _entity_schema(e) for e in solution.get("entities", [])}
    return json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs}, indent=2)


# ── openapi.json ─────────────────────────────────────────────────────────────────────

_PATH_PARAM_RE = re.compile(r"\{([^{}]+)\}")
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_ERROR_SCHEMA = {
    "type": "object",
    "properties": {"error": {"type": "object",
                              "properties": {"code": {"type": "string"}, "message": {"type": "string"},
                                             "details": {"type": "object"}},
                              "required": ["code", "message"]}},
    "required": ["error"],
}


def _openapi_parameters(endpoint: dict) -> list[dict]:
    declared = {p.get("name"): p for p in (endpoint.get("request") or {}).get("params") or []}
    params: list[dict] = []
    seen: set[str] = set()
    for name in _PATH_PARAM_RE.findall(endpoint.get("path", "")):
        d = declared.get(name) or {}
        params.append({"name": name, "in": "path", "required": True, "schema": _json_schema_type(d.get("type"))})
        seen.add(name)
    for p in declared.values():
        if p.get("name") in seen:
            continue
        param = {"name": p.get("name"), "in": p.get("in") or "query", "required": bool(p.get("required")),
                  "schema": _json_schema_type(p.get("type"))}
        if p.get("description"):
            param["description"] = p["description"]
        params.append(param)
    method = (endpoint.get("method") or "").upper()
    if method in _MUTATING_METHODS and endpoint.get("idempotent"):
        params.append({"name": "Idempotency-Key", "in": "header", "required": False, "schema": {"type": "string"}})
    return params


def _openapi_request_body(endpoint: dict) -> dict | None:
    body = (endpoint.get("request") or {}).get("body") or []
    if not body:
        return None
    props, required, example = {}, [], {}
    for f in body:
        name = f.get("name", "")
        props[name] = _json_schema_type(f.get("type"))
        if f.get("required"):
            required.append(name)
        if f.get("example") is not None:
            example[name] = f["example"]
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    content: dict = {"schema": schema}
    if example:
        content["example"] = example
    return {"required": True, "content": {"application/json": content}}


def _openapi_responses(endpoint: dict) -> dict:
    responses: dict = {}
    resp = endpoint.get("response") or {}
    props, example = {}, {}
    for f in resp.get("body") or []:
        name = f.get("name", "")
        props[name] = _json_schema_type(f.get("type"))
        if f.get("example") is not None:
            example[name] = f["example"]
    content = {"schema": {"type": "object", "properties": props}}
    if example:
        content["example"] = example
    responses[str(resp.get("status") or 200)] = {
        "description": endpoint.get("summary") or "", "content": {"application/json": content},
    }
    for err in endpoint.get("errors") or []:
        status = str(err.get("status") or "")
        if not status:
            continue
        err_example = {"error": {"code": err.get("code", ""), "message": err.get("message", "")}}
        responses[status] = {
            "description": err.get("message") or "",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}, "example": err_example}},
        }
    return responses


def render_openapi_json(plan: dict, solution: dict[str, list[dict]]) -> str:
    """§14.4 — OpenAPI 3.1: paths from the endpoints, entity schemas + the shared
    ``Error`` envelope, ``bearerAuth`` applied to every ``auth: required`` operation."""
    entities = solution.get("entities", [])
    schemas = {_pascal(e.get("name") or e.get("id") or ""): _entity_schema(e) for e in entities}
    schemas["Error"] = _ERROR_SCHEMA
    paths: dict[str, dict] = {}
    for ep in solution.get("endpoints", []):
        entity_name = None
        if ep.get("entity"):
            match = next((e for e in entities if e.get("id") == ep["entity"]), None)
            entity_name = (match or {}).get("name") or ep["entity"]
        operation: dict = {
            "operationId": ep.get("id", ""),
            "summary": ep.get("summary", ""),
            "parameters": _openapi_parameters(ep),
            "responses": _openapi_responses(ep),
        }
        if entity_name:
            operation["tags"] = [entity_name]
        body = _openapi_request_body(ep)
        if body:
            operation["requestBody"] = body
        if ep.get("auth") == "required":
            operation["security"] = [{"bearerAuth": []}]
        paths.setdefault(ep.get("path", ""), {})[(ep.get("method") or "get").lower()] = operation
    doc = {
        "openapi": "3.1.0",
        "info": {"title": plan.get("product") or "API", "version": "1.0.0"},
        "paths": paths,
        "components": {"schemas": schemas, "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
    }
    return json.dumps(doc, indent=2)


# ── api.md ───────────────────────────────────────────────────────────────────────────

def _join(values: Any, sep: str = ", ") -> str:
    """Join a model-written list for a table cell; a model writes numbers as often as text."""
    return sep.join(str(v) for v in (values or []))


def _yn(value: Any) -> str:
    """A table cell for a boolean: yes / no (anything else as given)."""
    return "yes" if value is True else "no" if value is False else ("" if value is None else str(value))


def _render_endpoint_block(ep: dict, all_stories: list[dict]) -> list[str]:
    lines = [f"### {ep.get('method','')} {ep.get('path','')} — {ep.get('summary','')}", "",
              f"Auth: {ep.get('auth','')} · Roles: {_join(ep.get('roles'))}", ""]
    params = (ep.get("request") or {}).get("params") or []
    if params:
        lines += ["**Parameters**", "", "| name | in | type | required | description |", "|---|---|---|---|---|"]
        lines += [f"| {p.get('name','')} | {p.get('in','')} | {p.get('type','')} | {_yn(p.get('required'))} | "
                  f"{p.get('description','')} |" for p in params]
        lines.append("")
    body = (ep.get("request") or {}).get("body") or []
    if body:
        lines += ["**Request body**", "", "| name | type | required | validation | example |", "|---|---|---|---|---|"]
        lines += [f"| {b.get('name','')} | {b.get('type','')} | {_yn(b.get('required'))} | "
                  f"{b.get('validation','')} | {b.get('example','')} |" for b in body]
        lines.append("")
    resp = ep.get("response") or {}
    lines += [f"**Response {resp.get('status','')}**", ""]
    rbody = resp.get("body") or []
    if rbody:
        lines += ["| name | type | example |", "|---|---|---|"]
        lines += [f"| {b.get('name','')} | {b.get('type','')} | {b.get('example','')} |" for b in rbody]
    lines.append("")
    errors = ep.get("errors") or []
    if errors:
        lines += ["**Errors**", "", "| status | code | message | when |", "|---|---|---|---|"]
        lines += [f"| {er.get('status','')} | {er.get('code','')} | {er.get('message','')} | {er.get('when','')} |"
                  for er in errors]
        lines.append("")
    if ep.get("rules"):
        lines.append(f"Rules: {', '.join(ep['rules'])}")
        lines.append("")
    if ep.get("integrations"):
        lines.append(f"Integrations: {', '.join(ep['integrations'])}")
        lines.append("")
    lines.append(f"Idempotent: {_yn(ep.get('idempotent', False))} · Paginated: {_yn(ep.get('paginated', False))}")
    lines.append("")
    story_ids = sorted({s.get("id", "") for s in all_stories
                          if ep.get("id") in (s.get("api") or []) or ep.get("id") in (s.get("covers") or [])})
    lines.append(f"Stories: {', '.join(story_ids)}")
    lines.append("")
    return lines


def render_api_md(solution: dict[str, list[dict]], all_stories: list[dict]) -> str:
    """§14.4 — endpoints grouped by entity (a group per ENT, then "Other")."""
    entities = solution.get("entities", [])
    endpoints = solution.get("endpoints", [])
    by_entity: dict[str, list[dict]] = {}
    other: list[dict] = []
    for ep in endpoints:
        (by_entity.setdefault(ep["entity"], []) if ep.get("entity") else other).append(ep)
    lines = ["# API", ""]
    for e in entities:
        eps = by_entity.get(e.get("id"), [])
        if not eps:
            continue
        lines += [f"## {e.get('name','')}", ""]
        for ep in eps:
            lines += _render_endpoint_block(ep, all_stories)
    if other:
        lines += ["## Other", ""]
        for ep in other:
            lines += _render_endpoint_block(ep, all_stories)
    return "\n".join(lines) + "\n"


# ── integrations.md ──────────────────────────────────────────────────────────────────

def render_integrations_md(solution: dict[str, list[dict]], all_stories: list[dict]) -> str:
    lines = ["# Integrations", ""]
    for i in solution.get("integrations", []):
        lines += [f"## {i.get('id','')} {i.get('name','')}", "",
                   f"System: {i.get('system','')} · Direction: {i.get('direction','')} · "
                   f"Trigger: {i.get('trigger','')}",
                   f"Auth: {i.get('auth','')} · Protocol: {i.get('protocol','')}", ""]
        calls = i.get("calls") or []
        if calls:
            lines += ["| operation | method | endpoint | request | response |", "|---|---|---|---|---|"]
            lines += [f"| {c.get('operation','')} | {c.get('method','')} | {c.get('endpoint','')} | "
                      f"{c.get('request','')} | {c.get('response','')} |" for c in calls]
            lines.append("")
        mapping = i.get("mapping") or []
        if mapping:
            lines += ["| from | to |", "|---|---|"]
            lines += [f"| {m.get('from','')} | {m.get('to','')} |" for m in mapping]
            lines.append("")
        lines.append(f"Retry: {i.get('retry','')} · Idempotency: {i.get('idempotency','')} · "
                      f"Failure: {i.get('failure','')}")
        lines.append(f"Monitoring: {i.get('monitoring','')}")
        lines.append("")
        story_ids = sorted({s.get("id", "") for s in all_stories for si in (s.get("integrations") or [])
                              if isinstance(si, dict) and si.get("integration") == i.get("id")})
        lines.append(f"Stories: {', '.join(story_ids)}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ── screens.md ───────────────────────────────────────────────────────────────────────

def render_screens_md(solution: dict[str, list[dict]], all_stories: list[dict]) -> str:
    """§14.4 — a ``flowchart`` navigation map from ``navigates_to``, then per screen its
    fields table, actions table, states and covering stories."""
    screens = solution.get("screens", [])
    lines = ["# Screens", ""]
    if screens:
        names: dict[str, str] = {}
        links: dict[str, list[str]] = {}
        for s in screens:  # a repeated id keeps its first name and every arrow
            sid = s.get("id", "")
            names.setdefault(sid, f'{sid} {s.get("name", "")}')
            links.setdefault(sid, []).extend(
                a["navigates_to"] for a in s.get("actions") or []
                if isinstance(a.get("navigates_to"), str) and a["navigates_to"])
        # A screen that opens nothing is drawn in the first part that opens it; a screen no
        # arrow touches says nothing about navigation and is named under the map.
        targets = {t for ends in links.values() for t in ends}
        alone = [n for n in names if not links[n] and n not in targets]
        parts = diagram_parts([[n] for n in names if links[n]], links, outgoing=True)
        home: dict[str, int] = {}
        for i, part in enumerate(parts, 1):
            for n, _ in part:
                home.setdefault(n, i)
        for i, part in enumerate(parts, 1):
            for _, ends in part:
                for t in ends:
                    if t in names and not links[t]:
                        home.setdefault(t, i)
        if len(parts) > 1:
            lines += ["The navigation map, in parts: an arrow points from a screen to one it opens; a dashed "
                      "box is a screen drawn in another part.", ""]
        for i, part in enumerate(parts, 1):
            if len(parts) > 1:
                lines += [f"### Navigation, part {i} of {len(parts)}", ""]
            lines += _flowchart(part, lambda n: names.get(n, n),
                                lambda n: names[n] + (f" (part {home[n]})" if n in home else "")
                                if n in names else f"{n} (no such screen)",
                                outgoing=True,
                                solid={t for _, ends in part for t in ends if home.get(t) == i and not links.get(t)})
        if alone:
            lines += ["No screen opens these, and they open none: " + ", ".join(names[n] for n in alone) + ".", ""]
    for s in screens:
        lines += [f"## {s.get('id','')} {s.get('name','')}", ""]
        fields = s.get("fields") or []
        if fields:
            lines += ["| name | control | required | validation | example | options |", "|---|---|---|---|---|---|"]
            for f in fields:
                opts = _join(f.get("options"))
                lines.append(f"| {f.get('name','')} | {f.get('control','')} | {_yn(f.get('required'))} | "
                              f"{f.get('validation','')} | {f.get('example','')} | {opts} |")
            lines.append("")
        actions = s.get("actions") or []
        if actions:
            lines += ["| label | result | navigates_to |", "|---|---|---|"]
            lines += [f"| {a.get('label','')} | {a.get('result','')} | {a.get('navigates_to','')} |"
                      for a in actions]
            lines.append("")
        states = s.get("states") or []
        if states:
            lines.append(f"States: {', '.join(states)}")
            lines.append("")
        story_ids = sorted({st.get("id", "") for st in all_stories if s.get("id") in (st.get("covers") or [])})
        lines.append(f"Stories: {', '.join(story_ids)}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ── the step ─────────────────────────────────────────────────────────────────────────

def _item_title(item: dict) -> str:
    for key in ("name", "title", "summary", "text", "statement", "description"):
        if isinstance(item.get(key), str) and item[key].strip():
            return item[key].strip()
    method, path = item.get("method"), item.get("path")
    return f"{method} {path}" if method and path else ""


def render_gaps_md(coverage_items: dict[str, dict], coverage: dict) -> str:
    """Every coverage item no story covers, with the coverage numbers."""
    totals = coverage["totals"]
    evidenced, evidenced_covered = totals["evidenced"], totals["evidenced_covered"]
    ratio = (evidenced_covered / evidenced) if evidenced else 1.0
    lines = [
        "# Coverage gaps", "",
        f"- Evidenced coverage: {evidenced_covered}/{evidenced} ({ratio:.0%}; the target is "
        f"{COVERAGE_THRESHOLD:.0%})",
        f"- All coverage items: {totals['covered']}/{totals['coverage_items']} covered",
        f"- Uncovered: {len(coverage['uncovered'])}", "",
        "| Id | Type | Title | Provenance |", "| --- | --- | --- | --- |",
    ]
    for gap in coverage["uncovered"]:
        item = coverage_items.get(gap["item"], {})
        title = _item_title(item).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {gap['item']} | {item.get('kind', '')} | {title} | {gap['provenance']} |")
    lines += ["", "The backlog is usable as it is. These items have no story yet; close the gaps "
              "by revising the run.", ""]
    return "\n".join(lines)


def assemble_backlog(ctx: Any) -> str:
    """Engine entry: read from / write to ``ctx.runner.sandbox``; return the reply text."""
    sandbox = ctx.runner.sandbox
    mode = "final" if sandbox.read(REVIEW_PATH) is not None else "draft"

    plan = parse_backlog_plan(sandbox.read(BACKLOG_PLAN_PATH))
    solution = {kind: parse_solution_kind(sandbox.read(f"{SOLUTION_DIR}/{kind}.json")) for kind in SOLUTION_KINDS}

    task_ids = list_story_task_ids(sandbox.read(STORY_TASKS_PATH))
    # The Reviewer adds stories in stories/review-<epic id>.json (one file per epic) —
    # names no task lists, so they are derived from the plan's epics.
    review_ids = [f"review-{e['id']}" for e in plan["epics"] if isinstance(e, dict) and e.get("id")]
    all_stories: list[dict] = []
    parsed_files = 0
    for task_id in task_ids + review_ids:
        stories = parse_story_file(sandbox.read(f"{STORIES_DIR}/{task_id}.json"))
        if stories is None:
            continue
        parsed_files += 1
        all_stories.extend(stories)

    checks = run_checks(plan, solution, all_stories)
    coverage = {"mode": mode, "shape": plan["shape"], **checks}

    endpoints_by_id = {it["id"]: it for it in solution.get("endpoints", []) if it.get("id")}
    has_architecture = sandbox.read(ARCHITECTURE_PATH) is not None

    # A story is ready when nothing is left open on it: no open question, no story error.
    build = compute_build_order(plan, all_stories)
    errored = {e.get("story") for e in coverage["story_errors"]}
    ready = {s["id"]: not s.get("open_questions") and s["id"] not in errored for s in all_stories if s.get("id")}

    markdown = render_markdown(plan, solution, all_stories, coverage, mode, endpoints_by_id, has_architecture)
    csv_text = render_csv(plan, all_stories, build)
    json_text = render_backlog_json(plan, solution, all_stories, coverage, build, ready)
    build_order_md = render_build_order_md(plan, all_stories, build, ready)
    data_model_md = render_data_model_md(solution)
    schema_json = render_schema_json(solution)
    api_md = render_api_md(solution, all_stories)
    openapi_json = render_openapi_json(plan, solution)
    integrations_md = render_integrations_md(solution, all_stories)
    screens_md = render_screens_md(solution, all_stories)

    deliverable = getattr(ctx, "deliverable", None)
    name = (getattr(deliverable, "text_name", None) or getattr(deliverable, "name", None)
            or DEFAULT_DELIVERABLE)
    sandbox.write(name, markdown)
    sandbox.write("backlog.csv", csv_text)
    sandbox.write("backlog.json", json_text)
    sandbox.write(COVERAGE_PATH, json.dumps(coverage, indent=2))
    sandbox.write("data-model.md", data_model_md)
    sandbox.write("schema.json", schema_json)
    sandbox.write("api.md", api_md)
    sandbox.write("openapi.json", openapi_json)
    sandbox.write("integrations.md", integrations_md)
    sandbox.write("screens.md", screens_md)
    sandbox.write(BUILD_ORDER_PATH, build_order_md)

    totals = coverage["totals"]
    summary = (f"Assembled {name} ({mode}): {len(all_stories)} stories from {parsed_files} file(s), "
               f"{totals['covered']}/{totals['coverage_items']} coverage items covered "
               f"({totals['evidenced_covered']}/{totals['evidenced']} evidenced). "
               f"{len(coverage['story_errors'])} story error(s), "
               f"{len(coverage['hierarchy_errors'])} hierarchy error(s). Details: {COVERAGE_PATH}.")

    if parsed_files == 0:
        raise AssembleBacklogFailed(
            f"assemble_backlog: no stories/*.json file parsed — {summary} The files were written; "
            f"fix the Story Writers' output and rerun."
        )

    if mode == "final":
        # Coverage is reported, never a failure: the backlog is always assembled and
        # packaged, and what no story covers is listed in gaps.md (run 3976f8ce failed
        # its last step at 83% and delivered nothing).
        if coverage["uncovered"]:
            evidenced, evidenced_covered = totals["evidenced"], totals["evidenced_covered"]
            ratio = (evidenced_covered / evidenced) if evidenced else 1.0
            sandbox.write(GAPS_PATH, render_gaps_md(collect_coverage_items(solution), coverage))
            summary += (f" Coverage warning: evidenced coverage {ratio:.0%} ({evidenced_covered}/"
                        f"{evidenced}, target {COVERAGE_THRESHOLD:.0%}); {len(coverage['uncovered'])} "
                        f"uncovered item(s) are listed in {GAPS_PATH}.")
        elif sandbox.read(GAPS_PATH) is not None:  # a previous assembly's list, now closed
            sandbox.path_for(GAPS_PATH).unlink(missing_ok=True)
    return summary


@register("mechanical", "assemble_backlog", user_allowed=True, description=(
    "Turns the epic/story files the Story Writers wrote into one backlog: backlog.md "
    "(the deliverable), backlog.csv (Jira import), backlog.json and a coverage report, "
    "plus build-order.md, data-model.md, schema.json, api.md, openapi.json, integrations.md and screens.md. "
    "Pure code, no AI: every story is checked against the EARS/Gherkin writing rules, "
    "every coverage item is checked against the stories that claim it, and nothing is "
    "silently dropped. Needs an earlier step that plans the hierarchy "
    "(build/backlog-plan.json, build/story-tasks.json) and writer steps that write one "
    "file per epic slice (stories/<task id>.json)."
), reads=[
    "build/backlog-plan.json", "build/story-tasks.json", "stories/", "build/solution/",
    "build/review.json", "architecture.md", "solution.md", "ui.md", "ux.md",
], process=(
    "Checks every story against the EARS and Gherkin rules and every coverage item against "
    "the stories that claim it, orders the epics and stories by what each needs first, "
    "then writes the backlog, build-order.md and the companion documents. Once "
    "build/review.json exists it also packages Backlog.pdf and Backlog.zip, and lists "
    "any coverage item no story covers in gaps.md."
), writes=[
    "backlog.md", "backlog.csv", "backlog.json", "build/coverage.json", "data-model.md",
    "schema.json", "api.md", "openapi.json", "integrations.md", "screens.md", "build-order.md",
    "gaps.md", "Backlog.pdf", "Backlog.zip", ".gitignore",
])
class _AssembleBacklogRegistryStub:
    """Thin stub for registry purposes only (capability palette discovery).

    The actual strategy dispatch uses MechanicalAssembleBacklogStrategy per-invocation
    with per-dispatch arguments (spec/index/total/results). This stub is registered for
    the palette and describes the capability; it is never executed.
    """
    name = "assemble_backlog"


class MechanicalAssembleBacklogStrategy:
    """``strategy``-shaped adapter for ``mechanical: assemble_backlog`` (see assemble_step)."""

    name = "assemble_backlog"

    def __init__(self, *, spec: Any, index: int, total: int, results: list) -> None:
        self._spec = spec
        self._index = index
        self._total = total
        self._results = results

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        spec = self._spec
        yield {
            "type": "agent_start",
            "data": {"agent_id": spec.id, "name": spec.name, "role": getattr(spec, "role", None),
                     "icon": getattr(spec, "icon", None), "index": self._index, "total": self._total},
        }
        started = time.time()
        # The backlog's other code steps ride this step kind; the instance id picks the
        # job (backlog_prep.BACKLOG_CODE_JOBS). Every other instance assembles.
        from agents.capabilities.backlog_prep import BACKLOG_CODE_JOBS, tidy_json

        sandbox = ctx.runner.sandbox
        job = BACKLOG_CODE_JOBS.get(str(spec.id).rsplit(":", 1)[-1])
        try:
            content = job(sandbox) if job else assemble_backlog(ctx)
        except (AssembleBacklogFailed, ValueError) as exc:
            yield {
                "type": "agent_error",
                "data": {"agent_id": spec.id, "error": str(exc), "recoverable": False},
            }
            raise
        # Models write JSON on one line whatever the prompt says; every backlog code
        # step re-indents the JSON on disk so far (same content).
        tidied = tidy_json(sandbox)
        if tidied:
            content = f"{content} Indented {tidied} JSON file(s)."
        # The final assembly (after the Reviewer) also packages the deliverables:
        # Backlog.pdf for a person, Backlog.zip for an agent.
        if job is None and sandbox.read(REVIEW_PATH) is not None:
            from agents.capabilities.backlog_export import export_backlog

            content = f"{content} {await export_backlog(sandbox)}"
            if sandbox.read(GAPS_PATH) is not None:
                yield {"type": "validation_warning", "data": {"step": spec.id, "issues": [{
                    "validator": "coverage", "severity": "MEDIUM", "warning": True,
                    "message": "Coverage warning: " + content.split("Coverage warning: ", 1)[-1]
                    .split(GAPS_PATH, 1)[0] + GAPS_PATH + ".",
                }]}}
        yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": content}}
        duration = time.time() - started
        self._results.append({
            "agent_id": spec.id, "name": spec.name, "role": getattr(spec, "role", None),
            "icon": getattr(spec, "icon", None), "output": content, "duration": duration,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
        })
        yield {
            "type": "agent_complete",
            "data": {"agent_id": spec.id, "name": spec.name, "duration": round(duration, 2),
                     "output_length": len(content), "index": self._index, "total": self._total,
                     "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
