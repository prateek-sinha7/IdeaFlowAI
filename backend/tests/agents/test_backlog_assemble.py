"""Unit tests for agents/capabilities/backlog_assemble.py."""

from __future__ import annotations

import csv
import io
import json
import re

import pytest

from agents.capabilities.backlog_assemble import (
    COVERAGE_THRESHOLD,
    CSV_COLUMNS,
    AssembleBacklogFailed,
    MechanicalAssembleBacklogStrategy,
    assemble_backlog,
    check_api,
    check_duplicates,
    check_ears,
    check_gherkin,
    check_hierarchy,
    _layout,
    compute_build_order,
    diagram_parts,
    parse_gherkin,
    parse_story_file,
    render_build_order_md,
    render_screens_md,
    render_story_block,
)


# ── fake sandbox / ctx ──────────────────────────────────────────────────────────────

class FakeSandbox:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[str, str] = dict(files or {})

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def write(self, path: str, text: str) -> None:
        self.files[path] = text


class FakeRunner:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox


class FakeDeliverable:
    def __init__(self, name: str = "backlog.md") -> None:
        self.name = name


class FakeCtx:
    def __init__(self, sandbox: FakeSandbox, deliverable_name: str = "backlog.md") -> None:
        self.runner = FakeRunner(sandbox)
        self.deliverable = FakeDeliverable(deliverable_name)


def _write_json(sandbox: FakeSandbox, path: str, data) -> None:
    sandbox.files[path] = json.dumps(data)


# ── story / requirement builders ────────────────────────────────────────────────────

def _requirement(**overrides) -> dict:
    req = {"id": "REQ-01-001", "pattern": "event",
           "text": "When the agent submits the quote form, the system shall create a quote record."}
    req.update(overrides)
    return req


def _story(**overrides) -> dict:
    story = {
        "id": "US-01-01", "feature": None, "epic": "EPIC-01", "type": "story",
        "title": "Create a quote", "persona": "PER-01", "as_a": "agent",
        "i_want": "to create a quote", "so_that": "I can send it to the client",
        "description": "Creates a new quote record.", "preconditions": ["Agent is signed in"],
        "requirements": [_requirement()],
        "gherkin": [
            "Feature: Quote creation",
            "  @US-01-01 @REQ-01-001 @P0",
            "  Scenario: Agent creates a quote",
            "    Given the agent is signed in",
            "    When the agent submits the quote form",
            "    Then a quote record is created",
        ],
        "ui": [{"screen": "SCR-anchor", "field": "Effective Date", "control": "date", "required": True,
                "validation": "not in the past", "example": "2026-10-01", "options": []}],
        "data": [], "integrations": [], "business_rules": [], "nfr": [], "dependencies": [],
        "priority": "P0", "points": 3, "labels": [], "provenance": "evidenced",
        "sources": ["doc p.1"], "covers": ["SCR-anchor"], "open_questions": [],
    }
    story.update(overrides)
    return story


# ── two-level fixture ───────────────────────────────────────────────────────────────

def _two_level_sandbox() -> FakeSandbox:
    sandbox = FakeSandbox()
    _write_json(sandbox, "build/backlog-plan.json", {
        "shape": "epic-story", "product": "Acme Quoting",
        "personas": [{"id": "PER-01", "name": "Agent", "goal": "quote fast"}],
        "features": [],
        "epics": [{"id": "EPIC-01", "name": "Quoting", "type": "functional", "feature": None,
                    "provenance": "evidenced", "covers": ["SCR-anchor"]}],
        "unassigned": [],
    })
    _write_json(sandbox, "build/solution/screens.json", {"items": [
        {"id": "SCR-anchor", "name": "Anchor", "provenance": "evidenced", "sources": ["doc p.1"],
         "fields": [], "actions": [], "states": []},
    ]})
    _write_json(sandbox, "build/story-tasks.json", {"tasks": [
        {"id": "EPIC-01", "title": "Quoting stories", "targets": ["stories/EPIC-01.json"], "depends_on": []},
    ]})
    _write_json(sandbox, "stories/EPIC-01.json", {"epic": "EPIC-01", "stories": [_story()]})
    return sandbox


def test_two_level_fixture_writes_all_four_files_and_renders_sections():
    sandbox = _two_level_sandbox()
    ctx = FakeCtx(sandbox)
    summary = assemble_backlog(ctx)
    assert "Assembled backlog.md" in summary

    for path in ("backlog.md", "backlog.csv", "backlog.json", "build/coverage.json"):
        assert path in sandbox.files

    md = sandbox.files["backlog.md"]
    title_lines = [l for l in md.splitlines() if l.startswith("# ")]
    assert len(title_lines) == 1
    assert "## Overview" in md
    assert "## EPIC-01 Quoting" in md
    assert "### US-01-01 Create a quote" in md
    for letter, name in [("A", "Data Model"), ("B", "Integration Catalogue"), ("C", "Role-Permission Matrix"),
                          ("D", "NFRs"), ("E", "Traceability"), ("F", "Inferred Items and Open Questions"),
                          ("G", "Coverage Summary")]:
        assert f"## Appendix {letter} — {name}" in md

    coverage = json.loads(sandbox.files["build/coverage.json"])
    assert coverage["mode"] == "draft"
    assert coverage["story_errors"] == []
    assert coverage["hierarchy_errors"] == []
    assert coverage["uncovered"] == []


def test_reviewer_story_file_is_picked_up_by_epic_name():
    # The Reviewer writes stories/review-<epic id>.json — a name no story task lists.
    sandbox = _two_level_sandbox()
    added = _story(id="US-R-01", requirements=[_requirement(id="REQ-R-001")], gherkin=[
        "Feature: Quote cancellation",
        "  @US-R-01 @REQ-R-001 @P1",
        "  Scenario: Agent cancels a quote",
        "    Given a quote is open",
        "    When the agent submits the quote form",
        "    Then a quote record is created",
    ])
    _write_json(sandbox, "stories/review-EPIC-01.json", {"epic": "EPIC-01", "stories": [added]})
    summary = assemble_backlog(FakeCtx(sandbox))
    assert "2 stories from 2 file(s)" in summary
    assert "US-R-01" in sandbox.files["backlog.md"]


# ── three-level fixture ─────────────────────────────────────────────────────────────

def _three_level_sandbox() -> FakeSandbox:
    sandbox = FakeSandbox()
    _write_json(sandbox, "build/backlog-plan.json", {
        "shape": "feature-epic-story", "product": "Acme Suite",
        "personas": [{"id": "PER-01", "name": "Agent", "goal": "quote fast"}],
        "features": [{"id": "FEAT-01", "name": "Quoting", "epics": ["EPIC-01"]}],
        "epics": [{"id": "EPIC-01", "name": "Quoting Epic", "type": "functional", "feature": "FEAT-01",
                    "provenance": "evidenced", "covers": ["SCR-anchor"]}],
        "unassigned": [],
    })
    _write_json(sandbox, "build/solution/screens.json", {"items": [
        {"id": "SCR-anchor", "name": "Anchor", "provenance": "evidenced", "sources": ["doc p.1"],
         "fields": [], "actions": [], "states": []},
    ]})
    _write_json(sandbox, "build/story-tasks.json", {"tasks": [
        {"id": "EPIC-01a", "title": "Quoting stories", "targets": ["stories/EPIC-01a.json"], "depends_on": []},
    ]})
    story = _story(id="US-01a-01", feature="FEAT-01", requirements=[_requirement(id="REQ-01a-001")],
                    gherkin=[
                        "Feature: Quote creation",
                        "  @US-01a-01 @REQ-01a-001 @P0",
                        "  Scenario: Agent creates a quote",
                        "    Given the agent is signed in",
                        "    When the agent submits the quote form",
                        "    Then a quote record is created",
                    ])
    _write_json(sandbox, "stories/EPIC-01a.json", {"epic": "EPIC-01", "stories": [story]})
    return sandbox


def test_three_level_fixture_has_feature_headings_and_csv_parent_chain():
    sandbox = _three_level_sandbox()
    ctx = FakeCtx(sandbox)
    assemble_backlog(ctx)

    md = sandbox.files["backlog.md"]
    assert "## FEAT-01 Quoting" in md
    assert "### EPIC-01 Quoting Epic" in md
    assert "#### US-01a-01 Create a quote" in md

    reader = csv.DictReader(io.StringIO(sandbox.files["backlog.csv"]))
    rows = {row["Issue Id"]: row for row in reader}
    assert rows["FEAT-01"]["Issue Type"] == "Feature"
    assert rows["FEAT-01"]["Parent Id"] == ""
    assert rows["EPIC-01"]["Issue Type"] == "Epic"
    assert rows["EPIC-01"]["Parent Id"] == "FEAT-01"
    assert rows["US-01a-01"]["Issue Type"] == "Story"
    assert rows["US-01a-01"]["Parent Id"] == "EPIC-01"


# ── CSV round-trip ───────────────────────────────────────────────────────────────────

def test_csv_round_trips_with_commas_quotes_and_newlines():
    sandbox = _two_level_sandbox()
    tricky_gherkin = [
        "Feature: Quote creation",
        "  @US-01-01 @REQ-01-001 @P0",
        'Scenario: Quote with a "special" note, and a comma',
        "    Given the note is \"hello, world\"",
        "    When the agent submits the quote form",
        "    Then a quote record is created",
    ]
    story = json.loads(sandbox.files["stories/EPIC-01.json"])["stories"][0]
    story["gherkin"] = tricky_gherkin
    sandbox.files["stories/EPIC-01.json"] = json.dumps({"epic": "EPIC-01", "stories": [story]})

    ctx = FakeCtx(sandbox)
    assemble_backlog(ctx)

    reader = csv.DictReader(io.StringIO(sandbox.files["backlog.csv"]))
    assert reader.fieldnames == CSV_COLUMNS
    rows = list(reader)
    story_row = next(r for r in rows if r["Issue Id"] == "US-01-01")
    assert story_row["Acceptance Criteria"] == "\n".join(tricky_gherkin)


# ── EARS violations ──────────────────────────────────────────────────────────────────

def test_each_ears_violation_recorded_with_a_distinct_check_name():
    sandbox = _two_level_sandbox()
    stories = [
        _story(id="US-01-01",
               requirements=[_requirement(id="REQ-01-001", pattern="event",
                                            text="If the agent submits, the system shall create a record.")],
               covers=[]),
        _story(id="US-01-02",
               requirements=[_requirement(id="REQ-01-002", pattern="event",
                                            text="When the agent submits, the record is created.")],
               covers=[], gherkin=["Feature: x", "@US-01-02 @REQ-01-002 @P0",
                                     "Scenario: s", "Given g", "When w", "Then t"]),
        _story(id="US-01-03",
               requirements=[_requirement(id="REQ-01-003", pattern="event",
                                            text="When the agent submits, the system shall create a record and the system shall log it.")],
               covers=[], gherkin=["Feature: x", "@US-01-03 @REQ-01-003 @P0",
                                     "Scenario: s", "Given g", "When w", "Then t"]),
        _story(id="US-01-04",
               requirements=[_requirement(id="REQ-01-004", pattern="event",
                                            text="When the agent submits, the system should create a record.")],
               covers=[], gherkin=["Feature: x", "@US-01-04 @REQ-01-004 @P0",
                                     "Scenario: s", "Given g", "When w", "Then t"]),
        _story(id="US-01-05",
               requirements=[_requirement(id="REQ-01-005", pattern="always",
                                            text="The system shall do a thing.")],
               covers=[], gherkin=["Feature: x", "@US-01-05 @REQ-01-005 @P0",
                                     "Scenario: s", "Given g", "When w", "Then t"]),
    ]
    _write_json(sandbox, "stories/EPIC-01.json", {"epic": "EPIC-01", "stories": stories})

    ctx = FakeCtx(sandbox)
    assemble_backlog(ctx)
    coverage = json.loads(sandbox.files["build/coverage.json"])
    checks = {e["check"] for e in coverage["story_errors"]}
    assert "ears.pattern_word" in checks
    assert "ears.shall_zero" in checks
    assert "ears.shall_multiple" in checks
    assert "ears.banned_modal" in checks
    assert "ears.unknown_pattern" in checks


def test_numeric_options_render_instead_of_crashing_the_assembly():
    # Run 05832e65: a select with options [12, 24, 48] crashed ", ".join and with
    # it the whole backlog assembly. Numbers inside lists become text at parse time;
    # scalar numbers such as points are left alone.
    text = json.dumps({"epic": "EPIC-27a", "stories": [{
        "id": "US-27a-01", "points": 3,
        "ui": [{"screen": "SCR-1", "field": "leadHours", "control": "select",
                "options": [12, 24, 48]}]}]})
    [story] = parse_story_file(text)

    assert story["ui"][0]["options"] == ["12", "24", "48"]
    assert story["points"] == 3
    assert any("12, 24, 48" in line for line in render_story_block(story, 4, {}))


def test_check_ears_pure_function():
    assert any(e["check"] == "ears.pattern_word" for e in
               check_ears("US-1", _requirement(pattern="state", text="When x, the system shall y.")))
    assert any(e["check"] == "ears.shall_zero" for e in
               check_ears("US-1", _requirement(text="When x, the system creates y.")))
    assert any(e["check"] == "ears.shall_multiple" for e in
               check_ears("US-1", _requirement(text="When x, the system shall y and the system shall z.")))
    assert any(e["check"] == "ears.banned_modal" for e in
               check_ears("US-1", _requirement(text="When x, the system shall y and must z.")))
    assert any(e["check"] == "ears.unknown_pattern" for e in
               check_ears("US-1", _requirement(pattern="bogus")))


# ── Gherkin violations ───────────────────────────────────────────────────────────────

def test_each_gherkin_violation_recorded_with_a_distinct_check_name():
    sandbox = _two_level_sandbox()
    stories = [
        _story(id="US-02-01", requirements=[_requirement(id="REQ-02-001")],
               gherkin=["@US-02-01 @REQ-02-001 @P0", "Scenario: no feature line",
                        "Given g", "When w", "Then t"]),
        _story(id="US-02-02", requirements=[_requirement(id="REQ-02-002")],
               gherkin=["Feature: x", "@US-02-02 @REQ-02-002 @P0",
                        "Scenario: missing when", "Given g", "Then t"]),
        _story(id="US-02-03", requirements=[_requirement(id="REQ-02-003")],
               gherkin=["Feature: x", "@US-02-03 @REQ-02-003 @P0",
                        "Scenario Outline: no examples", "Given g", "When w", "Then t"]),
        _story(id="US-02-04", requirements=[_requirement(id="REQ-02-004")],
               gherkin=["Feature: x", "@US-02-04 @P0",
                        "Scenario: no req tag", "Given g", "When w", "Then t"]),
        _story(id="US-02-05", requirements=[_requirement(id="REQ-02-005")],
               gherkin=["Feature: x", "@US-02-05 @REQ-99-999 @P0",
                        "Scenario: unknown req", "Given g", "When w", "Then t"]),
    ]
    _write_json(sandbox, "stories/EPIC-01.json", {"epic": "EPIC-01", "stories": stories})

    ctx = FakeCtx(sandbox)
    assemble_backlog(ctx)
    coverage = json.loads(sandbox.files["build/coverage.json"])
    checks = {e["check"] for e in coverage["story_errors"]}
    assert "gherkin.no_feature" in checks
    assert "gherkin.missing_steps" in checks
    assert "gherkin.outline_without_examples" in checks
    assert "gherkin.missing_req_tag" in checks
    assert "gherkin.unknown_req_tag" in checks


def test_check_gherkin_pure_function():
    story = _story(gherkin=["Feature: x", "@US-01-01 @P0", "Scenario: s", "Given g", "When w", "Then t"])
    errors, missing_req, covered = check_gherkin(story)
    assert any(e["check"] == "gherkin.missing_req_tag" for e in errors)
    assert missing_req == [{"story": "US-01-01", "scenario": "s"}]
    assert covered == set()


def test_a_background_given_satisfies_every_scenario():
    """Valid Gherkin: scenarios inherit the Background's Given. A live run flagged 266 such
    scenarios as missing a Given and the Reviewer burned its whole step budget on them."""
    background = ["Feature: x", "Background:", "Given the user is signed in",
                  "@US-01-01 @REQ-01-001 @P0", "Scenario: s", "When w", "Then t"]
    errors, _, _ = check_gherkin(_story(requirements=[_requirement(id="REQ-01-001")], gherkin=background))
    assert not any(e["check"] == "gherkin.missing_steps" for e in errors)

    no_background = ["Feature: x", "@US-01-01 @REQ-01-001 @P0", "Scenario: s", "When w", "Then t"]
    errors, _, _ = check_gherkin(_story(requirements=[_requirement(id="REQ-01-001")], gherkin=no_background))
    assert any(e["check"] == "gherkin.missing_steps" for e in errors)


def test_parse_gherkin_extracts_tags_and_steps():
    parsed = parse_gherkin([
        "Feature: x", "  @US-1 @REQ-1 @P0", "  Scenario: s",
        "    Given g", "    When w", "    Then t",
    ])
    assert parsed["has_feature"] is True
    assert len(parsed["scenarios"]) == 1
    sc = parsed["scenarios"][0]
    assert sc["tags"] == ["US-1", "REQ-1", "P0"]
    assert sc["given"] and sc["when"] and sc["then"]


# ── duplicates ───────────────────────────────────────────────────────────────────────

def test_duplicate_story_and_requirement_ids_recorded():
    sandbox = _two_level_sandbox()
    stories = [
        _story(id="US-03-01", requirements=[_requirement(id="REQ-DUP-001")]),
        _story(id="US-03-01", requirements=[_requirement(id="REQ-03-002")],
               gherkin=["Feature: x", "@US-03-01 @REQ-03-002 @P0",
                        "Scenario: s", "Given g", "When w", "Then t"]),
        _story(id="US-03-02", requirements=[_requirement(id="REQ-DUP-001")],
               gherkin=["Feature: x", "@US-03-02 @REQ-DUP-001 @P0",
                        "Scenario: s", "Given g", "When w", "Then t"]),
    ]
    _write_json(sandbox, "stories/EPIC-01.json", {"epic": "EPIC-01", "stories": stories})

    ctx = FakeCtx(sandbox)
    assemble_backlog(ctx)
    coverage = json.loads(sandbox.files["build/coverage.json"])
    checks = {e["check"] for e in coverage["story_errors"]}
    assert "duplicate.story_id" in checks
    assert "duplicate.requirement_id" in checks


def test_check_duplicates_pure_function():
    errors = check_duplicates([_story(id="A"), _story(id="A")])
    assert any(e["check"] == "duplicate.story_id" for e in errors)


# ── hierarchy errors ─────────────────────────────────────────────────────────────────

def test_hierarchy_errors_epic_missing_no_feature_no_stories():
    sandbox = _three_level_sandbox()
    plan = json.loads(sandbox.files["build/backlog-plan.json"])
    plan["epics"].append({"id": "EPIC-02", "name": "No feature epic", "type": "data", "feature": None,
                           "provenance": "evidenced", "covers": []})
    plan["epics"].append({"id": "EPIC-03", "name": "Empty epic", "type": "data", "feature": "FEAT-01",
                           "provenance": "evidenced", "covers": []})
    plan["features"][0]["epics"].append("EPIC-03")
    _write_json(sandbox, "build/backlog-plan.json", plan)

    story_task = json.loads(sandbox.files["stories/EPIC-01a.json"])
    story_task["stories"].append(_story(id="US-99-01", epic="EPIC-99",
                                          requirements=[_requirement(id="REQ-99-001")],
                                          gherkin=["Feature: x", "@US-99-01 @REQ-99-001 @P0",
                                                    "Scenario: s", "Given g", "When w", "Then t"]))
    _write_json(sandbox, "stories/EPIC-01a.json", story_task)

    ctx = FakeCtx(sandbox)
    assemble_backlog(ctx)
    coverage = json.loads(sandbox.files["build/coverage.json"])
    errors_by_id = {(e["id"], e["error"]) for e in coverage["hierarchy_errors"]}
    assert ("US-99-01", "epic 'EPIC-99' does not exist") in errors_by_id
    assert ("EPIC-02", "no feature") in errors_by_id
    assert ("EPIC-02", "no stories") in errors_by_id
    assert ("EPIC-03", "no stories") in errors_by_id


def test_check_hierarchy_pure_function():
    plan = {"shape": "epic-story", "epics": [{"id": "EPIC-01", "name": "e", "feature": None}]}
    errors = check_hierarchy(plan, [_story(epic="EPIC-99")])
    assert {"id": "US-01-01", "error": "epic 'EPIC-99' does not exist"} in errors
    assert {"id": "EPIC-01", "error": "no stories"} in errors


# ── uncovered items / requirements without scenario ─────────────────────────────────

def test_uncovered_item_and_requirement_without_scenario_listed_and_totals_match():
    sandbox = _two_level_sandbox()
    solution = json.loads(sandbox.files["build/solution/screens.json"])
    solution["items"].append({"id": "SCR-orphan", "name": "Orphan", "provenance": "evidenced",
                                "sources": ["doc p.2"], "fields": [], "actions": [], "states": []})
    _write_json(sandbox, "build/solution/screens.json", solution)

    story = json.loads(sandbox.files["stories/EPIC-01.json"])["stories"][0]
    story["requirements"].append(_requirement(id="REQ-01-002", pattern="state",
                                                 text="While the form is open, the system shall autosave it."))
    _write_json(sandbox, "stories/EPIC-01.json", {"epic": "EPIC-01", "stories": [story]})

    ctx = FakeCtx(sandbox)
    assemble_backlog(ctx)
    coverage = json.loads(sandbox.files["build/coverage.json"])

    assert {"item": "SCR-orphan", "provenance": "evidenced"} in coverage["uncovered"]
    assert "REQ-01-002" in coverage["requirements_without_scenario"]
    totals = coverage["totals"]
    assert totals["coverage_items"] == 2
    assert totals["evidenced"] == 2
    assert totals["covered"] == 1
    assert totals["evidenced_covered"] == 1
    assert len(coverage["uncovered"]) == totals["coverage_items"] - totals["covered"]


# ── draft vs final mode / coverage threshold ─────────────────────────────────────────

def _sandbox_with_evidenced_items(total: int, covered: int) -> FakeSandbox:
    sandbox = FakeSandbox()
    item_ids = [f"SCR-{i:02d}" for i in range(total)]
    _write_json(sandbox, "build/backlog-plan.json", {
        "shape": "epic-story", "product": "Acme", "personas": [],
        "features": [], "epics": [{"id": "EPIC-01", "name": "Epic", "type": "functional", "feature": None,
                                     "provenance": "evidenced", "covers": item_ids}],
        "unassigned": [],
    })
    _write_json(sandbox, "build/solution/screens.json", {"items": [
        {"id": i, "name": i, "provenance": "evidenced", "sources": ["doc p.1"],
         "fields": [], "actions": [], "states": []} for i in item_ids
    ]})
    _write_json(sandbox, "build/story-tasks.json", {"tasks": [
        {"id": "EPIC-01", "title": "stories", "targets": ["stories/EPIC-01.json"], "depends_on": []},
    ]})
    story = _story(covers=item_ids[:covered])
    _write_json(sandbox, "stories/EPIC-01.json", {"epic": "EPIC-01", "stories": [story]})
    return sandbox


def test_draft_mode_never_raises_on_bad_coverage():
    sandbox = _sandbox_with_evidenced_items(total=20, covered=1)
    ctx = FakeCtx(sandbox)
    summary = assemble_backlog(ctx)
    assert "Assembled" in summary
    assert "backlog.md" in sandbox.files


def test_final_mode_below_threshold_assembles_and_lists_the_gaps():
    # Run 3976f8ce: 83% failed the last step and delivered nothing. Coverage is now
    # reported: everything is assembled, and the uncovered items go to gaps.md.
    sandbox = _sandbox_with_evidenced_items(total=20, covered=10)  # 50% < 85%
    _write_json(sandbox, "build/review.json", {"rounds": 1, "fixed": [], "open": []})
    summary = assemble_backlog(FakeCtx(sandbox))
    for path in ("backlog.md", "backlog.csv", "backlog.json", "build/coverage.json", "gaps.md"):
        assert path in sandbox.files
    gaps = sandbox.files["gaps.md"]
    assert "Evidenced coverage: 10/20 (50%; the target is 85%)" in gaps
    for i in range(10, 20):
        assert f"| SCR-{i:02d} | screens | SCR-{i:02d} | evidenced |" in gaps
    assert "| SCR-00 |" not in gaps  # covered items are not gaps
    assert "usable as it is" in gaps and "revising the run" in gaps
    assert "Coverage warning: evidenced coverage 50% (10/20, target 85%); 10 uncovered item(s) are listed in gaps.md." in summary


def test_final_mode_with_full_coverage_writes_no_gaps_file():
    sandbox = _sandbox_with_evidenced_items(total=20, covered=20)
    _write_json(sandbox, "build/review.json", {"rounds": 1, "fixed": [], "open": []})
    summary = assemble_backlog(FakeCtx(sandbox))
    assert "gaps.md" not in sandbox.files and "Coverage warning" not in summary


def test_draft_mode_never_writes_gaps():
    sandbox = _sandbox_with_evidenced_items(total=20, covered=10)
    assemble_backlog(FakeCtx(sandbox))
    assert "gaps.md" not in sandbox.files


def test_final_mode_does_not_raise_at_or_above_threshold():
    sandbox = _sandbox_with_evidenced_items(total=20, covered=17)  # exactly 85%
    _write_json(sandbox, "build/review.json", {"rounds": 1, "fixed": [], "open": []})
    ctx = FakeCtx(sandbox)
    summary = assemble_backlog(ctx)
    assert "Assembled" in summary
    coverage = json.loads(sandbox.files["build/coverage.json"])
    assert coverage["mode"] == "final"
    assert coverage["totals"]["evidenced_covered"] / coverage["totals"]["evidenced"] >= COVERAGE_THRESHOLD


# ── no parsable story file ───────────────────────────────────────────────────────────

def test_no_parsable_story_file_raises():
    sandbox = _two_level_sandbox()
    sandbox.files["stories/EPIC-01.json"] = "{not valid json"
    ctx = FakeCtx(sandbox)
    with pytest.raises(AssembleBacklogFailed):
        assemble_backlog(ctx)
    for path in ("backlog.md", "backlog.csv", "backlog.json", "build/coverage.json"):
        assert path in sandbox.files


def test_no_story_tasks_file_at_all_raises():
    sandbox = _two_level_sandbox()
    del sandbox.files["build/story-tasks.json"]
    ctx = FakeCtx(sandbox)
    with pytest.raises(AssembleBacklogFailed):
        assemble_backlog(ctx)


# ── full-application documents (§14.2-§14.4) fixture ────────────────────────────────

NEW_DOCUMENTS = ("data-model.md", "schema.json", "api.md", "openapi.json", "integrations.md", "screens.md")


def _full_app_sandbox(low_coverage: bool = False) -> FakeSandbox:
    """Epic-story shape with every §14.2 solution kind populated: two entities (ENT-01
    with pk/fk/unique/default/enum/3-status lifecycle/audit, ENT-02 reference_data), one
    integration (calls/mapping/retry), two endpoints (a POST with body+errors+idempotent,
    a GET with a path param+paginated), one rule, one glossary term, two screens with a
    navigates_to link, and stories whose ``api``/``covers`` name them."""
    sandbox = FakeSandbox()
    _write_json(sandbox, "build/backlog-plan.json", {
        "shape": "epic-story", "product": "Acme Quoting",
        "personas": [{"id": "PER-01", "name": "Agent", "goal": "quote fast"}],
        "features": [],
        "epics": [{"id": "EPIC-01", "name": "Quoting", "type": "functional", "feature": None,
                    "provenance": "evidenced", "covers": ["SCR-anchor"]}],
        "unassigned": [],
    })
    _write_json(sandbox, "build/solution/screens.json", {"items": [
        {"id": "SCR-anchor", "name": "Anchor", "provenance": "evidenced", "sources": ["doc p.1"],
         "fields": [{"name": "Effective Date", "control": "date", "required": True,
                     "validation": "not in the past", "example": "2026-10-01", "options": []}],
         "actions": [{"label": "Begin Quote", "result": "creates quote", "navigates_to": "SCR-beacon"}],
         "states": ["default"]},
        {"id": "SCR-beacon", "name": "Beacon", "provenance": "evidenced", "sources": ["doc p.2"],
         "fields": [], "actions": [], "states": []},
    ]})
    _write_json(sandbox, "build/solution/entities.json", {"items": [
        {"id": "ENT-01", "name": "Quote", "provenance": "evidenced", "sources": ["doc p.1"],
         "attributes": [
             {"name": "id", "type": "string", "required": True, "validation": "", "example": "Q-1",
              "key": "pk", "references": None, "unique": True, "default": None, "enum": None},
             {"name": "policy_type", "type": "string", "required": True, "validation": "",
              "example": "Auto", "key": None, "references": None, "unique": False,
              "default": "Auto", "enum": ["Auto", "Home", "Renters", "Umbrella"]},
             {"name": "customer_id", "type": "string", "required": True, "validation": "",
              "example": "C-1", "key": "fk", "references": "ENT-02", "unique": False,
              "default": None, "enum": None},
             {"name": "effective_date", "type": "date", "required": True, "validation": "",
              "example": "2026-10-01", "key": None, "references": None, "unique": False,
              "default": None, "enum": None},
         ],
         "relationships": [{"to": "ENT-02", "kind": "1-1", "via": "customer_id"}],
         "lifecycle": ["draft", "submitted", "bound"],
         "indexes": [["customer_id"]], "audit": True, "reference_data": False},
        {"id": "ENT-02", "name": "Customer", "provenance": "evidenced", "sources": ["doc p.1"],
         "attributes": [{"name": "id", "type": "string", "required": True, "validation": "",
                          "example": "C-1", "key": "pk", "references": None, "unique": True,
                          "default": None, "enum": None}],
         "relationships": [], "lifecycle": [], "indexes": [], "audit": False, "reference_data": True},
    ]})
    _write_json(sandbox, "build/solution/integrations.json", {"items": [
        {"id": "INT-01", "name": "Payments", "provenance": "evidenced", "sources": ["doc p.3"],
         "system": "Stripe", "direction": "out", "trigger": "quote bound", "data": "amount",
         "failure": "retry 3x", "auth": "api_key", "protocol": "https",
         "calls": [{"operation": "charge", "method": "POST", "endpoint": "/v1/charges",
                     "request": "amount, currency", "response": "charge id"}],
         "mapping": [{"from": "quote.amount", "to": "charge.amount"}],
         "retry": "exponential backoff", "idempotency": "idempotency key", "monitoring": "datadog"},
    ]})
    _write_json(sandbox, "build/solution/roles.json", {"items": [
        {"id": "ROL-01", "name": "Agent", "provenance": "evidenced", "sources": ["doc p.1"],
         "permissions": [{"on": "ENT-01", "actions": ["create", "read"]}]},
    ]})
    _write_json(sandbox, "build/solution/nfrs.json", {"items": []})
    _write_json(sandbox, "build/solution/platform.json", {"items": [
        {"id": f"PLT-{i:02d}", "name": f"Platform {i}", "provenance": "evidenced", "sources": ["doc p.1"],
         "capability": "audit log"} for i in range(10)
    ] if low_coverage else []})
    _write_json(sandbox, "build/solution/rules.json", {"items": [
        {"id": "BR-01", "name": "No past date", "provenance": "evidenced", "sources": ["doc p.1"],
         "statement": "Effective date cannot be in the past", "applies_to": ["SCR-anchor", "ENT-01"],
         "message": "Effective Date cannot be in the past"},
    ]})
    _write_json(sandbox, "build/solution/glossary.json", {"items": [
        {"id": "GL-01", "name": "Quote", "term": "Quote", "definition": "An offer of insurance",
         "provenance": "evidenced", "sources": ["doc p.1"]},
    ]})
    _write_json(sandbox, "build/solution/endpoints.json", {"items": [
        {"id": "API-01", "name": "Create quote", "provenance": "evidenced", "sources": ["doc p.1"],
         "method": "POST", "path": "/v1/quotes", "summary": "Create a quote", "auth": "required",
         "roles": ["ROL-01"], "entity": "ENT-01", "screens": ["SCR-anchor"],
         "request": {"params": [], "body": [{"name": "policy_type", "type": "string", "required": True,
                                               "validation": "one of the enum", "example": "Auto"}]},
         "response": {"status": 201, "body": [{"name": "id", "type": "string", "example": "Q-1"}]},
         "errors": [{"status": 400, "code": "invalid_policy_type", "message": "Invalid policy type",
                      "when": "policy_type not in enum"}],
         "idempotent": True, "paginated": False, "rules": ["BR-01"], "integrations": ["INT-01"]},
        {"id": "API-02", "name": "Get quote", "provenance": "evidenced", "sources": ["doc p.1"],
         "method": "GET", "path": "/v1/quotes/{id}", "summary": "Get a quote", "auth": "required",
         "roles": ["ROL-01"], "entity": "ENT-01", "screens": ["SCR-anchor"],
         "request": {"params": [{"name": "id", "in": "path", "type": "string", "required": True,
                                   "description": "quote id"}], "body": []},
         "response": {"status": 200, "body": [{"name": "id", "type": "string", "example": "Q-1"}]},
         "errors": [{"status": 404, "code": "not_found", "message": "Quote not found", "when": "no such id"}],
         "idempotent": False, "paginated": True, "rules": [], "integrations": []},
    ]})
    _write_json(sandbox, "build/story-tasks.json", {"tasks": [
        {"id": "EPIC-01", "title": "Quoting stories", "targets": ["stories/EPIC-01.json"], "depends_on": []},
    ]})
    story = _story(
        id="US-01-01", covers=["SCR-anchor", "ENT-01", "INT-01", "ROL-01", "BR-01", "API-01", "API-02"],
        api=["API-01", "API-02"], priority="P0", points=3,
        data=[{"entity": "ENT-01", "operation": "create", "attributes": ["policy_type"]}],
        integrations=[{"integration": "INT-01", "behaviour": "charges the customer"}],
    )
    story2 = _story(
        id="US-01-02", title="Get a quote", priority="P1", points=2,
        covers=["SCR-beacon", "ENT-02", "API-02"], api=["API-02"],
        requirements=[_requirement(id="REQ-01-002", text="When the agent opens a quote, "
                                                            "the system shall show it.")],
        gherkin=["Feature: Quote view", "  @US-01-02 @REQ-01-002 @P1",
                  "  Scenario: Agent views a quote",
                  "    Given a quote exists", "    When the agent opens it", "    Then the quote is shown"],
    )
    story_bad = _story(
        id="US-01-03", title="Bad api", priority="P2", points=1, covers=[], api=["API-99"],
        requirements=[_requirement(id="REQ-01-003", text="When x, the system shall y.")],
        gherkin=["Feature: x", "  @US-01-03 @REQ-01-003 @P2", "  Scenario: s",
                  "    Given g", "    When w", "    Then t"],
    )
    _write_json(sandbox, "stories/EPIC-01.json", {"epic": "EPIC-01", "stories": [story, story2, story_bad]})
    return sandbox


def test_all_new_documents_written_in_draft_and_when_final_raises():
    draft_sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(draft_sandbox))
    for name in NEW_DOCUMENTS:
        assert name in draft_sandbox.files

    final_sandbox = _full_app_sandbox(low_coverage=True)
    _write_json(final_sandbox, "build/review.json", {"rounds": 1, "fixed": [], "open": []})
    assemble_backlog(FakeCtx(final_sandbox))  # low coverage is reported, not raised
    assert "gaps.md" in final_sandbox.files
    for name in NEW_DOCUMENTS:
        assert name in final_sandbox.files


def test_data_model_md_has_entity_table_er_diagram_and_state_diagram():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    md = sandbox.files["data-model.md"]
    assert "| policy_type | string |  | yes | no | Auto | Auto, Home, Renters, Umbrella | Auto |" in md
    assert "```mermaid\nerDiagram" in md
    assert "ENT_01 ||--|| ENT_02" in md
    assert "stateDiagram-v2" in md
    assert "draft --> submitted" in md
    assert "submitted --> bound" in md


def test_schema_json_parses_with_defs_enum_date_format_and_required():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    schema = json.loads(sandbox.files["schema.json"])
    defs = schema["$defs"]
    assert set(defs) == {"Quote", "Customer"}
    assert defs["Quote"]["properties"]["policy_type"]["enum"] == ["Auto", "Home", "Renters", "Umbrella"]
    assert defs["Quote"]["properties"]["effective_date"]["format"] == "date"
    assert defs["Quote"]["required"] == ["id", "policy_type", "customer_id", "effective_date"]


def test_openapi_json_parses_with_paths_params_body_errors_schemas_and_security():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    doc = json.loads(sandbox.files["openapi.json"])
    assert doc["openapi"] == "3.1.0"
    assert "/v1/quotes" in doc["paths"] and "/v1/quotes/{id}" in doc["paths"]

    get_op = doc["paths"]["/v1/quotes/{id}"]["get"]
    path_params = [p for p in get_op["parameters"] if p["in"] == "path"]
    assert any(p["name"] == "id" for p in path_params)

    post_op = doc["paths"]["/v1/quotes"]["post"]
    assert "requestBody" in post_op
    assert post_op["responses"]["400"]["content"]["application/json"]["schema"] == \
        {"$ref": "#/components/schemas/Error"}

    schemas = doc["components"]["schemas"]
    assert "Error" in schemas and "Quote" in schemas and "Customer" in schemas
    assert post_op["security"] == [{"bearerAuth": []}]


def test_api_md_lists_endpoint_headings_error_tables_and_covering_stories():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    md = sandbox.files["api.md"]
    assert "### POST /v1/quotes" in md
    assert "### GET /v1/quotes/{id}" in md
    assert "| 400 | invalid_policy_type | Invalid policy type | policy_type not in enum |" in md
    assert "| 404 | not_found | Quote not found | no such id |" in md
    assert "Stories: US-01-01" in md
    assert "Stories: US-01-01, US-01-02" in md


def test_integrations_md_shows_calls_and_mapping_and_screens_md_shows_flowchart_and_fields():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    integrations_md = sandbox.files["integrations.md"]
    assert "| charge | POST | /v1/charges | amount, currency | charge id |" in integrations_md
    assert "| quote.amount | charge.amount |" in integrations_md

    screens_md = sandbox.files["screens.md"]
    assert "```mermaid\nflowchart LR" in screens_md  # two columns: drawn left to right (spec §11.7)
    assert "SCR_anchor" in screens_md and "SCR_beacon" in screens_md
    assert "SCR_anchor --> SCR_beacon" in screens_md
    assert "| Effective Date | date | yes | not in the past | 2026-10-01 |  |" in screens_md


def test_backlog_md_release_plan_totals_and_documents_section():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    md = sandbox.files["backlog.md"]
    assert "## Release plan" in md
    assert "### P0" in md and "Points: 3" in md
    assert "### P1" in md and "Points: 2" in md
    assert "### P2" in md and "Points: 1" in md
    assert "## Documents" in md
    for name in NEW_DOCUMENTS:
        assert f"[{name}]({name})" in md
    assert "architecture.md" not in md

    sandbox2 = _full_app_sandbox()
    sandbox2.files["architecture.md"] = "# Architecture\n"
    assemble_backlog(FakeCtx(sandbox2))
    assert "[architecture.md](architecture.md)" in sandbox2.files["backlog.md"]


def test_unknown_api_id_recorded_as_story_error():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    coverage = json.loads(sandbox.files["build/coverage.json"])
    errors = [e for e in coverage["story_errors"] if e["check"] == "api.unknown_endpoint"]
    assert any(e["story"] == "US-01-03" for e in errors)


def test_rules_and_endpoints_count_as_coverage_glossary_does_not():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    coverage = json.loads(sandbox.files["build/coverage.json"])
    # screens(2) + entities(2) + integrations(1) + roles(1) + rules(1) + endpoints(2) = 9;
    # glossary's GL-01 is excluded.
    assert coverage["totals"]["coverage_items"] == 9
    assert not any(u["item"] == "GL-01" for u in coverage["uncovered"])


def test_check_api_pure_function():
    errors = check_api("US-1", ["API-01", "API-99"], {"API-01"})
    assert errors == [{"story": "US-1", "check": "api.unknown_endpoint",
                         "detail": "api id 'API-99' does not exist in endpoints"}]


# ── strategy adapter ─────────────────────────────────────────────────────────────────

class _Spec:
    id = "us-assemble"
    name = "Assemble"
    role = "Assembler"
    icon = "🧩"


@pytest.mark.asyncio
async def test_strategy_adapter_emits_events_and_records_result():
    sandbox = _two_level_sandbox()
    ctx = FakeCtx(sandbox)
    results: list = []
    strategy = MechanicalAssembleBacklogStrategy(spec=_Spec(), index=0, total=1, results=results)
    events = [e async for e in strategy.run(step=None, ctx=ctx)]
    types = [e["type"] for e in events]
    assert types == ["agent_start", "agent_chunk", "agent_complete"]
    assert len(results) == 1
    assert results[0]["agent_id"] == "us-assemble"


@pytest.mark.asyncio
async def test_strategy_adapter_emits_agent_error_and_reraises_on_failure():
    sandbox = _sandbox_with_evidenced_items(total=20, covered=1)
    _write_json(sandbox, "build/review.json", {"rounds": 1, "fixed": [], "open": []})
    sandbox.files["stories/EPIC-01.json"] = "{not valid json"  # no story file parses
    ctx = FakeCtx(sandbox)
    results: list = []
    strategy = MechanicalAssembleBacklogStrategy(spec=_Spec(), index=0, total=1, results=results)
    events = []
    with pytest.raises(AssembleBacklogFailed):
        async for e in strategy.run(step=None, ctx=ctx):
            events.append(e)
    assert events[-1]["type"] == "agent_error"
    assert results == []


def test_backlog_md_renders_business_rules_and_glossary_appendices():
    sandbox = _full_app_sandbox()
    assemble_backlog(FakeCtx(sandbox))
    md = sandbox.files["backlog.md"]
    rules = md[md.index("## Appendix H — Business Rules"):md.index("## Appendix I — Glossary")]
    assert "| BR-01 |" in rules and "US-01-01" in rules  # rule row names the story that covers it
    glossary = md[md.index("## Appendix I — Glossary"):]
    assert "| Quote | An offer of insurance |" in glossary


# ── EARS: a copied message is not the requirement's own wording ─────────────────────

def test_modal_and_shall_inside_a_quoted_message_are_not_errors():
    # Run c4cbd381: 13 requirements stayed flagged because the message they must copy
    # says "must" or "should" — no Reviewer could fix them.
    text = ('If the name is taken, then the system shall refuse it and show '
            '"Name must be unique, and you should pick another; it shall not repeat".')
    assert check_ears("US-01-01", _requirement(pattern="unwanted", text=text)) == []


def test_modal_and_second_shall_outside_quotes_are_still_errors():
    text = ('If the name is taken, then the system must refuse it and shall show '
            '"Name is taken" and the system shall log it.')
    checks = {e["check"] for e in check_ears("US-01-01", _requirement(pattern="unwanted", text=text))}
    assert checks == {"ears.banned_modal", "ears.shall_multiple"}


# ── build order ─────────────────────────────────────────────────────────────────────

def _epic(eid: str, etype: str, depends_on: list[str], release: str = "first") -> dict:
    return {"id": eid, "name": f"Epic {eid}", "type": etype, "feature": None, "provenance": "evidenced",
            "release": release, "depends_on": depends_on, "covers": [], "slices": [f"{eid}a"]}


def _ordered_plan(**extra) -> dict:
    plan = {
        "shape": "epic-story", "product": "Acme Quoting", "personas": [], "features": [], "unassigned": [],
        "epics": [
            _epic("EPIC-01", "functional", ["EPIC-02"]),
            _epic("EPIC-02", "data", ["EPIC-04"]),
            _epic("EPIC-03", "platform", []),                  # Project setup
            _epic("EPIC-04", "platform", ["EPIC-03"]),         # Data foundation
            _epic("EPIC-05", "platform", ["EPIC-03"]),         # Delivery
            _epic("EPIC-06", "functional", ["EPIC-02"], release="later"),
            _epic("EPIC-07", "functional", ["EPIC-02"]),
        ],
        "walking_skeleton": {"flow": "Create a quote", "epics": ["EPIC-01", "EPIC-05"]},
        "definition_of_ready": ["No open question on the story."],
        "definition_of_done": ["Every scenario passes in Playwright."],
    }
    plan.update(extra)
    return plan


def _ordered_stories() -> list[dict]:
    def s(sid: str, epic: str, priority: str, points: int, deps: list[str] | None = None) -> dict:
        return _story(id=sid, epic=epic, priority=priority, points=points, dependencies=deps or [])
    return [
        s("US-01-01", "EPIC-01", "P0", 5, ["US-01-02"]), s("US-01-02", "EPIC-01", "P0", 3),
        s("US-02-01", "EPIC-02", "P0", 5), s("US-03-01", "EPIC-03", "P0", 3),
        s("US-04-01", "EPIC-04", "P0", 8), s("US-05-01", "EPIC-05", "P0", 2),
        s("US-06-01", "EPIC-06", "P2", 3), s("US-07-01", "EPIC-07", "P1", 2),
    ]


def test_build_order_puts_the_skeleton_and_everything_it_needs_first():
    build = compute_build_order(_ordered_plan(), _ordered_stories())
    info = build["epics"]
    assert {e for e, i in info.items() if i["milestone"] == 1} == {"EPIC-01", "EPIC-02", "EPIC-03", "EPIC-04", "EPIC-05"}
    assert (info["EPIC-07"]["milestone"], info["EPIC-06"]["milestone"]) == (2, 3)
    assert [info[e]["priority"] for e in ("EPIC-01", "EPIC-07", "EPIC-06")] == ["P0", "P1", "P2"]
    # Waves inside milestone 1: setup, then foundation and delivery side by side, then data, then the flow.
    assert [info[e]["wave"] for e in ("EPIC-03", "EPIC-04", "EPIC-05", "EPIC-02", "EPIC-01")] == [1, 2, 2, 3, 4]
    assert build["sequence"] == ["EPIC-03", "EPIC-04", "EPIC-05", "EPIC-02", "EPIC-01", "EPIC-07", "EPIC-06"]
    assert build["story_errors"] == [] and build["hierarchy_errors"] == []


def test_stories_are_numbered_in_build_order_and_a_story_follows_its_dependency():
    order = {sid: v["order"] for sid, v in compute_build_order(_ordered_plan(), _ordered_stories())["stories"].items()}
    assert order["US-03-01"] == 1
    assert order["US-01-02"] < order["US-01-01"]          # US-01-01 depends on US-01-02
    assert order["US-06-01"] == max(order.values())       # the later release comes last


def test_the_critical_path_is_the_heaviest_chain_of_epics():
    build = compute_build_order(_ordered_plan(), _ordered_stories())
    assert build["critical_path"] == ["EPIC-03", "EPIC-04", "EPIC-02", "EPIC-01"]


def test_graph_errors_are_reported_on_the_epics_that_carry_them():
    plan = _ordered_plan()
    plan["epics"][2]["depends_on"] = ["EPIC-01"]           # setup -> ... -> flow -> setup: a cycle
    plan["epics"][4]["depends_on"] = ["EPIC-05", "EPIC-99"]
    plan["epics"][6]["depends_on"] = ["EPIC-06"]           # first-release epic on a later one
    plan["walking_skeleton"]["epics"].append("EPIC-42")
    errors = [f"{e['id']}: {e['error']}" for e in compute_build_order(plan, _ordered_stories())["hierarchy_errors"]]
    assert "EPIC-05: depends_on names the epic itself" in errors
    assert "EPIC-05: depends_on names 'EPIC-99', which is no epic" in errors
    assert "EPIC-07: a first-release epic depends on EPIC-06, a later-release epic" in errors
    assert "walking_skeleton: names 'EPIC-42', which is no epic" in errors
    assert any(e.startswith("EPIC-01: depends_on cycle: EPIC-01 -> EPIC-02 -> EPIC-04 -> EPIC-03 -> EPIC-01")
               for e in errors)


def test_story_dependency_and_priority_errors():
    stories = _ordered_stories()
    stories[1]["dependencies"] = ["US-01-01"]              # US-01-01 <-> US-01-02
    stories[2]["dependencies"] = ["US-99-01"]
    stories[3]["dependencies"] = ["US-07-01"]              # setup needs a first-release story: built later
    stories[7]["priority"] = "P0"                          # EPIC-07 is P1
    checks = {(e["story"], e["check"]) for e in compute_build_order(_ordered_plan(), stories)["story_errors"]}
    assert checks == {("US-01-01", "dependencies.cycle"), ("US-01-02", "dependencies.cycle"),
                      ("US-02-01", "dependencies.unknown"), ("US-03-01", "dependencies.later"),
                      ("US-07-01", "priority.above_epic")}


def test_a_plan_without_a_walking_skeleton_holds_no_story_to_a_priority():
    build = compute_build_order(_ordered_plan(walking_skeleton={}), _ordered_stories())
    assert all(i["priority"] is None for i in build["epics"].values())
    assert build["story_errors"] == []


def _ordered_sandbox() -> FakeSandbox:
    sandbox = FakeSandbox()
    _write_json(sandbox, "build/backlog-plan.json", _ordered_plan())
    stories = _ordered_stories()
    _write_json(sandbox, "build/story-tasks.json", {"tasks": [
        {"id": f"{e}a", "title": e, "targets": [f"stories/{e}a.json"], "depends_on": []}
        for e in sorted({s["epic"] for s in stories})]})
    for epic in sorted({s["epic"] for s in stories}):
        mine = [dict(s, requirements=[_requirement(id=f"REQ-{s['id'][3:]}-001")],
                     gherkin=[l.replace("US-01-01", s["id"]).replace("REQ-01-001", f"REQ-{s['id'][3:]}-001")
                              .replace("@P0", f"@{s['priority']}") for l in _story()["gherkin"]])
                for s in stories if s["epic"] == epic]
        _write_json(sandbox, f"stories/{epic}a.json", {"epic": epic, "stories": mine})
    return sandbox


def test_assemble_writes_build_order_md_and_places_every_story():
    sandbox = _ordered_sandbox()
    assemble_backlog(FakeCtx(sandbox))

    md = sandbox.files["build-order.md"]
    headings = [l for l in md.splitlines() if l.startswith("## ")]
    assert headings == ["## Dependency graph", "## Story dependencies", "## Critical path",
                        "## Milestone 1 — Walking skeleton: Create a quote",
                        "## Milestone 2 — First release", "## Milestone 3 — Later release",
                        "## Definition of Ready", "## Definition of Done"]
    assert "  EPIC_03 --> EPIC_04" in md and '  EPIC_01["EPIC-01 Epic EPIC-01"]' in md
    assert "- Every scenario passes in Playwright." in md
    assert "[build-order.md](build-order.md)" in sandbox.files["backlog.md"]

    stories = {s["id"]: s for s in json.loads(sandbox.files["backlog.json"])["stories"]}
    assert (stories["US-03-01"]["order"], stories["US-03-01"]["milestone"], stories["US-03-01"]["ready"]) == (1, 1, True)
    epics = {e["id"]: e for e in json.loads(sandbox.files["backlog.json"])["backlog"]["epics"]}
    assert (epics["EPIC-07"]["priority"], epics["EPIC-07"]["milestone"]) == ("P1", 2)

    rows = {r["Issue Id"]: r for r in csv.DictReader(io.StringIO(sandbox.files["backlog.csv"]))}
    assert (rows["US-01-01"]["Milestone"], rows["US-01-01"]["Depends On"]) == ("1 Walking skeleton", "US-01-02")
    assert rows["EPIC-07"]["Priority"] == "High"


def test_a_story_with_an_open_question_is_not_ready():
    sandbox = _ordered_sandbox()
    plan_stories = json.loads(sandbox.files["stories/EPIC-03a.json"])
    plan_stories["stories"][0]["open_questions"] = ["gap-1: which CI tool?"]
    _write_json(sandbox, "stories/EPIC-03a.json", plan_stories)
    assemble_backlog(FakeCtx(sandbox))
    stories = {s["id"]: s for s in json.loads(sandbox.files["backlog.json"])["stories"]}
    assert stories["US-03-01"]["ready"] is False
    assert "Not ready: 1 of 8 stories" in sandbox.files["build-order.md"]


def test_a_story_that_needs_an_epic_built_after_its_own_is_flagged():
    stories = _ordered_stories()
    stories[3]["dependencies"] = ["EPIC-07"]               # setup (built first) needs a first-release epic
    stories[0]["dependencies"] = ["US-01-02", "EPIC-02"]   # an epic built earlier is fine
    checks = {(e["story"], e["check"]) for e in compute_build_order(_ordered_plan(), stories)["story_errors"]}
    assert checks == {("US-03-01", "dependencies.later")}


@pytest.mark.asyncio
async def test_final_assembly_below_threshold_completes_with_a_coverage_warning(monkeypatch):
    import agents.capabilities.backlog_export as export

    async def _no_pdf(sandbox):
        return "Wrote Backlog.zip."

    monkeypatch.setattr(export, "export_backlog", _no_pdf)
    sandbox = _sandbox_with_evidenced_items(total=20, covered=10)
    _write_json(sandbox, "build/review.json", {"rounds": 1, "fixed": [], "open": []})
    results: list = []
    strategy = MechanicalAssembleBacklogStrategy(spec=_Spec(), index=0, total=1, results=results)
    events = [e async for e in strategy.run(step=None, ctx=FakeCtx(sandbox))]
    types = [e["type"] for e in events]
    assert "agent_error" not in types and types[-1] == "agent_complete" and len(results) == 1
    warning = next(e["data"] for e in events if e["type"] == "validation_warning")
    assert warning["issues"][0]["message"] == (
        "Coverage warning: evidenced coverage 50% (10/20, target 85%); "
        "10 uncovered item(s) are listed in gaps.md.")


# ── dependency maps: feature and story level ────────────────────────────────────────

def _two_feature_run():
    plan = _ordered_plan(shape="feature-epic-story", features=[
        {"id": "FEAT-01", "name": "Quoting", "epics": ["EPIC-01", "EPIC-06", "EPIC-07"]},
        {"id": "FEAT-02", "name": "Platform", "epics": ["EPIC-02", "EPIC-03", "EPIC-04", "EPIC-05"]},
    ])
    stories = _ordered_stories()
    stories.append(_story(id="US-07-02", epic="EPIC-07", priority="P1", points=2,
                          dependencies=["US-01-01"], title="Send the quote"))
    return plan, stories


def _build_order(plan, stories):
    return render_build_order_md(plan, stories, compute_build_order(plan, stories), {})


def test_feature_dependencies_draw_one_edge_per_feature_pair():
    md = _build_order(*_two_feature_run())
    section = md.split("## Feature dependencies", 1)[1].split("## Dependency graph", 1)[0]
    assert 'FEAT_01["FEAT-01 Quoting"]' in section and 'FEAT_02["FEAT-02 Platform"]' in section
    # EPIC-01/06/07 (Quoting) depend on EPIC-02 (Platform): one edge, Platform → Quoting.
    assert section.count("FEAT_02 --> FEAT_01") == 1
    assert "FEAT_01 --> FEAT_02" not in section and "FEAT_02 --> FEAT_02" not in section
    # Feature, then epic, then story level.
    assert md.index("## Feature dependencies") < md.index("## Dependency graph") < md.index("## Story dependencies")


def test_story_dependencies_per_epic_with_cross_epic_stories_dashed():
    md = _build_order(*_two_feature_run())
    section = md.split("## Story dependencies", 1)[1].split("\n## ", 1)[0]
    assert "### EPIC-01" in section and "US_01_02 --> US_01_01" in section
    assert "### EPIC-07" in section and "US_01_01 --> US_07_02" in section
    assert 'US_01_01["US-01-01 (EPIC-01)"]:::external' in section
    assert "classDef external stroke-dasharray" in section
    assert "### EPIC-02" not in section  # no story dependencies, no graph


def test_an_epic_story_plan_has_no_feature_section():
    md = _build_order(_ordered_plan(), _ordered_stories())
    assert "## Feature dependencies" not in md
    assert "## Story dependencies" in md and "## Dependency graph" in md


def test_a_large_epic_is_drawn_one_slice_at_a_time():
    plan = _ordered_plan()
    stories = [_story(id=f"US-01{sl}-{n:02d}", epic="EPIC-01", priority="P0", points=1,
                      dependencies=[f"US-01{sl}-{n - 1:02d}"] if n > 1 else [])
               for sl in ("a", "b") for n in range(1, 26)]
    md = _build_order(plan, stories)
    assert "### EPIC-01 Epic EPIC-01 — slice 01a" in md
    assert "### EPIC-01 Epic EPIC-01 — slice 01b" in md


# ── big diagrams are drawn in parts (user decision 16:02) ───────────────────────────

MAX_NODES, MAX_EDGES = 15, 20
_NODE_RE = re.compile(r'^\s+(\w+)\["')
_EDGE_RE = re.compile(r"^\s+(\w+) --> (\w+)$")


def _charts(md: str) -> list[list[str]]:
    """The lines of every mermaid block in ``md``."""
    return [block.split("```", 1)[0].splitlines() for block in md.split("```mermaid")[1:]]


def _edges(md: str) -> set[tuple[str, str]]:
    return {m.groups() for chart in _charts(md) for line in chart if (m := _EDGE_RE.match(line))}


def _assert_every_chart_fits(md: str) -> None:
    """Every chart within the box and arrow limits, and in a shape the PDF prints readably:
    left to right at most 2 columns and 8 rows, or top down a chain at most 2 boxes wide."""
    for chart in _charts(md):
        nodes = list(dict.fromkeys(m.group(1) for line in chart if (m := _NODE_RE.match(line))))
        arrows = [m.groups() for line in chart if (m := _EDGE_RE.match(line))]
        assert len(nodes) <= MAX_NODES and len(arrows) <= MAX_EDGES, chart
        ranks, widest, bent = _layout(nodes, arrows)
        direction = chart[1].split()[1]
        assert (direction == "LR" and ranks <= 2 and widest <= 8) or \
               (direction == "TD" and bent <= 2 and ranks <= 7), chart


def _big_plan() -> tuple[dict, list[dict]]:
    """60 epics over three milestones; each needs up to three earlier ones, and EPIC-60
    needs 25 of them (one box with too many arrows for a chart of its own)."""
    def epic(n: int) -> dict:
        deps = [f"EPIC-{d:02d}" for d in (n - 1, n - 3, n - 7) if d >= 1] if n < 60 else \
               [f"EPIC-{d:02d}" for d in range(1, 26)]
        release = "first" if n <= 30 else "later"
        return _epic(f"EPIC-{n:02d}", "functional", deps, release=release)
    plan = _ordered_plan(epics=[epic(n) for n in range(1, 61)],
                         walking_skeleton={"flow": "Quote", "epics": ["EPIC-01", "EPIC-02"]})
    stories = [_story(id=f"US-{n:02d}-01", epic=f"EPIC-{n:02d}", priority="P1", points=1)
               for n in range(1, 61)]
    return plan, stories


def test_a_big_dependency_graph_is_drawn_in_parts_that_fit_and_lose_no_arrow():
    plan, stories = _big_plan()
    md = _build_order(plan, stories)
    section = md.split("## Dependency graph", 1)[1].split("\n## ", 1)[0]
    _assert_every_chart_fits(section)
    expected = {(d.replace("-", "_"), e["id"].replace("-", "_")) for e in plan["epics"] for d in e["depends_on"]}
    assert _edges(section) == expected
    headings = [l for l in section.splitlines() if l.startswith("### ")]
    assert len(headings) == len(set(headings)) > 3  # every part has its own heading
    assert all(h.startswith("### Milestone ") for h in headings)
    assert any("(part 1 of 4)" in h for h in headings)  # EPIC-60's 25 arrows: 8 rows a chart
    _assert_every_chart_fits(md)


def test_a_big_screens_map_is_drawn_in_parts_that_fit_and_lose_no_arrow():
    screens = [{"id": f"SCR-{n:02d}", "name": f"Screen {n}", "actions": [
        {"label": "next", "navigates_to": f"SCR-{(n % 40) + 1:02d}"},
        {"label": "hub", "navigates_to": "SCR-01"},
        {"label": "again", "navigates_to": "SCR-01"},  # a repeated arrow is drawn once
    ]} for n in range(1, 41)]
    md = render_screens_md({"screens": screens}, [])
    _assert_every_chart_fits(md)
    expected = {(f"SCR_{n:02d}", f"SCR_{(n % 40) + 1:02d}") for n in range(1, 41)} | \
               {(f"SCR_{n:02d}", "SCR_01") for n in range(1, 41)}
    assert _edges(md) == expected
    assert "### Navigation, part 1 of " in md and ":::external" in md
    assert "## SCR-40 Screen 40" in md  # the per-screen sections are unchanged


def test_a_small_graph_stays_one_chart():
    md = render_screens_md({"screens": [{"id": "SCR-a", "name": "A", "actions": [{"navigates_to": "SCR-b"}]},
                                        {"id": "SCR-b", "name": "B", "actions": []}]}, [])
    assert len(_charts(md)) == 1 and "### Navigation" not in md and "external" not in md


def test_a_node_with_too_many_arrows_is_drawn_over_several_charts():
    links = {"hub": [f"n{i}" for i in range(30)]}
    parts = diagram_parts([["hub"]], links)
    assert [len(ends) for part in parts for _, ends in part] == [8, 8, 8, 6]
    assert [o for part in parts for _, ends in part for o in ends] == links["hub"]


def test_a_chart_runs_down_the_page_for_a_chain_and_across_for_a_fan_out():
    chain = [{"id": f"SCR-{n}", "name": str(n), "actions": [{"navigates_to": f"SCR-{n + 1}"}] if n < 6 else []}
             for n in range(1, 7)]
    fan = [{"id": "SCR-0", "name": "hub", "actions": [{"navigates_to": f"SCR-{n}"} for n in range(1, 7)]}] + \
          [{"id": f"SCR-{n}", "name": str(n), "actions": []} for n in range(1, 7)]
    assert "```mermaid\nflowchart TD" in render_screens_md({"screens": chain}, [])
    assert "```mermaid\nflowchart LR" in render_screens_md({"screens": fan}, [])


def test_a_screen_no_arrow_touches_is_named_under_the_map_not_drawn():
    md = render_screens_md({"screens": [
        {"id": "SCR-a", "name": "A", "actions": [{"navigates_to": "SCR-b"}]},
        {"id": "SCR-b", "name": "B", "actions": []},
        {"id": "SCR-z", "name": "Z", "actions": []},
    ]}, [])
    assert "No screen opens these, and they open none: SCR-z Z." in md
    assert all("SCR_z" not in line for chart in _charts(md) for line in chart)
    assert "## SCR-z Z" in md  # its own section stays


def test_a_navigation_cycle_does_not_make_a_wide_map_run_down_the_page():
    # Three hubs, each opening three screens that link back: wide, and full of cycles.
    screens = []
    for h in range(3):
        kids = [f"SCR-{h}{k}" for k in range(3)]
        screens.append({"id": f"SCR-{h}", "name": f"Hub {h}", "actions": [{"navigates_to": k} for k in kids]})
        screens += [{"id": k, "name": k, "actions": [{"navigates_to": f"SCR-{h}"}]} for k in kids]
    assert "```mermaid\nflowchart LR" in render_screens_md({"screens": screens}, [])


def test_a_repeated_link_is_drawn_once():
    parts = diagram_parts([["H"]], {"H": ["a"] * 14 + ["b"] * 7})
    assert [ends for part in parts for _, ends in part] == [["a", "b"]]


def test_screens_that_open_nothing_live_in_the_first_part_that_opens_them():
    # A hub opening 40 screens that open nothing, and a screen that opens the hub.
    screens = [{"id": "SCR-hub", "name": "Hub", "actions": [{"navigates_to": f"SCR-{n:02d}"} for n in range(40)]},
               {"id": "SCR-in", "name": "In", "actions": [{"navigates_to": "SCR-hub"}]}]
    screens += [{"id": f"SCR-{n:02d}", "name": f"Leaf {n}", "actions": []} for n in range(40)]
    md = render_screens_md({"screens": screens}, [])
    _assert_every_chart_fits(md)
    charts = _charts(md)
    assert all(any(_EDGE_RE.match(line) for line in chart) for chart in charts)  # no chart without arrows
    for n in range(40):  # each leaf is a plain box exactly once, a dashed copy anywhere else
        plain = [c for c in charts for line in c if line.startswith(f'  SCR_{n:02d}["') and "external" not in line]
        assert len(plain) == 1, n
    assert _edges(md) == {("SCR_hub", f"SCR_{n:02d}") for n in range(40)} | {("SCR_in", "SCR_hub")}
    assert "SCR-hub Hub (part 1)" in md  # a hub drawn over several parts is found in its first


def test_a_repeated_screen_id_keeps_every_arrow_and_a_missing_target_says_so():
    md = render_screens_md({"screens": [
        {"id": "A", "name": "first", "actions": [{"navigates_to": "B"}]},
        {"id": "A", "name": "second", "actions": [{"navigates_to": "C"}, {"navigates_to": "GONE"}]},
        {"id": "B", "name": "B", "actions": []}, {"id": "C", "name": "C", "actions": []},
    ]}, [])
    assert {("A", "B"), ("A", "C"), ("A", "GONE")} <= _edges(md)
    assert 'GONE["GONE (no such screen)"]:::external' in md
    assert "No screen opens these" not in md


def test_a_story_part_heading_never_ends_in_an_empty_slice():
    plan = _ordered_plan()
    stories = [_story(id=f"X{n}", epic="EPIC-01", priority="P0", points=1,
                      dependencies=[f"X{n - 1}"] if n else []) for n in range(3)]
    stories += [_story(id=f"US-01a-{n:02d}", epic="EPIC-01", priority="P0", points=1,
                       dependencies=[f"US-01a-{n - 1:02d}"] if n > 1 else []) for n in range(1, 20)]
    md = _build_order(plan, stories)
    headings = [l for l in md.split("## Story dependencies", 1)[1].splitlines() if l.startswith("### ")]
    assert headings and not any(h.rstrip().endswith(("slice", "–")) or "slice  " in h for h in headings)
    _assert_every_chart_fits(md)
