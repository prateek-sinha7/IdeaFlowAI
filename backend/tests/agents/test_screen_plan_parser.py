"""Unit tests for agents/capabilities/task_parsers/screen_plan.py."""

from __future__ import annotations

import asyncio

import pytest

from agents.capabilities.registry import discover, CapabilityRegistry
from agents.capabilities.screen_inventory import (
    COMPONENT_CLASSES,
    Inventory,
    parse_inventory,
)
from agents.capabilities.strategies.wave_scheduler import build_waves
from agents.capabilities.task_parsers.screen_plan import (
    ScreenPlanParser,
    build_tasks,
    render_body,
)
from agents.workflows.plan import Task


class TestRegistryScreenPlanParser:
    """Test that screen_plan parser is registered."""

    def test_parser_registered(self):
        discover()
        registry = CapabilityRegistry()
        parser = registry.resolve("task_parser", "screen_plan")
        assert hasattr(parser, "name")
        assert parser.name == "screen_plan"


class TestScreenPlanParserParse:
    """Test the parse() method (from text only)."""

    def test_parse_returns_list_of_tasks(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home", "title": "Home"}]}'
        tasks = parser.parse(text)
        assert isinstance(tasks, list)
        assert len(tasks) >= 1

    def test_parse_creates_task_per_screen(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home"}, {"id": "about"}]}'
        tasks = parser.parse(text)
        assert len(tasks) == 2

    def test_parse_task_id_format(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "search"}]}'
        tasks = parser.parse(text)
        assert tasks[0].id == "screen-search"

    def test_parse_task_targets_parts_html(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home"}]}'
        tasks = parser.parse(text)
        assert tasks[0].targets == ["parts/home.html"]

    def test_parse_task_no_dependencies(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home"}]}'
        tasks = parser.parse(text)
        assert tasks[0].depends_on == []

    def test_parse_task_conflict_keys_equal_targets(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home"}]}'
        tasks = parser.parse(text)
        assert tasks[0].conflict_keys == tasks[0].targets

    def test_parse_task_done_when_includes_section_selector(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "dashboard"}]}'
        tasks = parser.parse(text)
        assert any("section.screen#dashboard" in d for d in tasks[0].done_when)

    def test_parse_task_done_when_includes_attribute_strings(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home", "transitions": [{"label": "Go", "to": "about"}]}]}'
        tasks = parser.parse(text)
        # Should have section selector + attribute strings
        assert len(tasks[0].done_when) >= 2

    def test_parse_invalid_inventory_raises_value_error(self):
        parser = ScreenPlanParser()
        with pytest.raises(ValueError, match="screen_plan"):
            parser.parse('{"screens": []}')


class TestScreenPlanParserPreferringTarget:
    """Test the parse_preferring_target() method."""

    def test_parse_preferring_target_with_no_sandbox_uses_reply(self):
        parser = ScreenPlanParser()
        reply = '{"screens": [{"id": "home"}]}'
        tasks = parser.parse_preferring_target(reply, sandbox=None)
        assert len(tasks) == 1

    def test_parse_preferring_target_prefers_file_over_reply(self):
        parser = ScreenPlanParser()

        # Fake sandbox with read() method
        class FakeSandbox:
            def read(self, path):
                if path == "build/screens.json":
                    return '{"screens": [{"id": "file-screen"}]}'
                return None

        sandbox = FakeSandbox()
        reply = '{"screens": [{"id": "reply-screen"}]}'
        tasks = parser.parse_preferring_target(reply, sandbox=sandbox)

        # Should use file, not reply
        assert tasks[0].id == "screen-file-screen"

    def test_parse_preferring_target_falls_back_to_reply_if_file_missing(self):
        parser = ScreenPlanParser()

        class FakeSandbox:
            def read(self, path):
                return None  # All reads return None

        sandbox = FakeSandbox()
        reply = '{"screens": [{"id": "reply-screen"}]}'
        tasks = parser.parse_preferring_target(reply, sandbox=sandbox)

        # Should fall back to reply
        assert tasks[0].id == "screen-reply-screen"

    def test_parse_preferring_target_inlines_spec_md(self):
        parser = ScreenPlanParser()

        class FakeSandbox:
            def read(self, path):
                if path == "build/screens.json":
                    return '{"screens": [{"id": "home", "title": "Home"}]}'
                if path == "spec.md":
                    return "### home — Home Screen\n\nThis is the home screen."
                return None

        sandbox = FakeSandbox()
        tasks = parser.parse_preferring_target("", sandbox=sandbox)

        # The spec section should appear in the task body
        assert "### home" in tasks[0].body

    def test_parse_preferring_target_inlines_req_lines(self):
        parser = ScreenPlanParser()

        class FakeSandbox:
            def read(self, path):
                if path == "build/screens.json":
                    return '{"screens": [{"id": "home", "reqs": ["REQ-001"]}]}'
                if path == "spec.md":
                    return "REQ-001 | some requirement | screens: home"
                return None

        sandbox = FakeSandbox()
        tasks = parser.parse_preferring_target("", sandbox=sandbox)

        # The REQ line should appear in the task body
        assert "REQ-001" in tasks[0].body

    def test_parse_preferring_target_raises_when_nothing_to_parse(self):
        parser = ScreenPlanParser()

        class FakeSandbox:
            def read(self, path):
                return None

        sandbox = FakeSandbox()
        with pytest.raises(ValueError, match="screen_plan"):
            parser.parse_preferring_target("", sandbox=sandbox)


class TestRenderBody:
    """Test the render_body() function."""

    def test_render_body_contains_write_instruction(self):
        screen = parse_inventory('{"screens": [{"id": "home"}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        body = render_body(screen, inv, "")
        assert "Write: parts/home.html" in body

    def test_render_body_contains_screen_id_and_kind(self):
        screen = parse_inventory('{"screens": [{"id": "home"}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        body = render_body(screen, inv, "")
        assert "id: home" in body
        assert "kind: page" in body

    def test_render_body_contains_attribute_strings_in_backticks(self):
        screen = parse_inventory('{"screens": [{"id": "home", "transitions": [{"label": "Go", "to": "about"}]}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "home"}, {"id": "about"}]}')
        body = render_body(screen, inv, "")
        # Attribute string should appear in backticks
        assert 'data-goto="about"' in body

    def test_render_body_page_includes_page_header_rule(self):
        screen = parse_inventory('{"screens": [{"id": "home"}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        body = render_body(screen, inv, "")
        assert "page-header" in body

    def test_render_body_dialog_includes_dialog_rule(self):
        screen = parse_inventory('{"screens": [{"id": "modal", "kind": "dialog"}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "modal", "kind": "dialog"}]}')
        body = render_body(screen, inv, "")
        assert "DIALOG" in body
        assert "no close button" in body

    def test_render_body_contains_component_classes(self):
        screen = parse_inventory('{"screens": [{"id": "home"}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        body = render_body(screen, inv, "")
        # Should mention that classes come from the fixed list
        for cls in ["page-header", "form", "btn"]:
            assert cls in body

    def test_render_body_spec_section_inline(self):
        screen = parse_inventory('{"screens": [{"id": "home"}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        spec = "### home — Home Screen\n\nBuild a home screen."
        body = render_body(screen, inv, spec)
        assert "### home" in body

    def test_render_body_missing_spec_section_noted(self):
        screen = parse_inventory('{"screens": [{"id": "home"}]}').screens[0]
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        body = render_body(screen, inv, "")
        # Should say spec.md has no section
        assert "spec.md has no" in body or "has no" in body


class TestBuildTasks:
    """Test the build_tasks() function."""

    def test_build_tasks_inventory_and_spec(self):
        inv = parse_inventory('{"screens": [{"id": "home"}, {"id": "about"}]}')
        tasks = build_tasks(inv, "")
        assert len(tasks) == 2
        assert all(isinstance(t, Task) for t in tasks)

    def test_build_tasks_without_spec(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        tasks = build_tasks(inv)  # spec defaults to ""
        assert len(tasks) == 1

    def test_build_tasks_ids_sequential(self):
        inv = parse_inventory('{"screens": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]}')
        tasks = build_tasks(inv, "")
        assert tasks[0].id == "screen-s1"
        assert tasks[1].id == "screen-s2"
        assert tasks[2].id == "screen-s3"


class TestScreenPlanInWaves:
    """Test that screen plan tasks land in ONE wave."""

    def test_all_screens_in_one_wave(self):
        inv = parse_inventory(
            '{"screens": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]}'
        )
        tasks = build_tasks(inv, "")
        waves = build_waves(tasks)
        # All tasks should be in one wave (no dependencies)
        assert len(waves) == 1
        assert len(waves[0]) == 3


class TestScreenPlanTaskTitleFormat:
    """Test task title generation."""

    def test_task_title_format(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "dashboard", "title": "Dashboard"}]}'
        tasks = parser.parse(text)
        assert "Dashboard" in tasks[0].title
        assert "page" in tasks[0].title or "dialog" in tasks[0].title


class TestScreenPlanDoneWhenFormat:
    """Test done_when list generation."""

    def test_done_when_section_check(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "profile"}]}'
        tasks = parser.parse(text)
        done = tasks[0].done_when
        # First item should be the section selector
        assert any("section.screen#profile" in d for d in done)

    def test_done_when_includes_all_transition_attrs(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home", "transitions": [{"label": "To A", "to": "a"}, {"label": "To B", "to": "b"}]}]}'
        tasks = parser.parse(text)
        done = tasks[0].done_when
        # Should include both transitions (as attribute strings)
        assert len(done) >= 3  # section + 2 transitions


class TestScreenPlanDialogHandling:
    """Test special handling for dialog screens."""

    def test_dialog_screen_in_tasks(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "confirm", "kind": "dialog"}]}'
        tasks = parser.parse(text)
        assert len(tasks) == 1
        # Task should still follow the same structure
        assert "screen-confirm" in tasks[0].id

    def test_dialog_auto_close_in_done_when(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "modal", "kind": "dialog"}]}'
        tasks = parser.parse(text)
        done = tasks[0].done_when
        # Auto-added close transition should be in done_when
        assert any("data-closes" in d for d in done)


class TestScreenPlanReqsHandling:
    """Test requirement annotation in task body."""

    def test_reqs_in_inventory_shown_in_task(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home", "reqs": ["REQ-001", "REQ-002"]}]}'
        tasks = parser.parse(text)
        body = tasks[0].body
        assert "REQ-001" in body
        assert "REQ-002" in body

    def test_no_reqs_shown_as_see_spec(self):
        parser = ScreenPlanParser()
        text = '{"screens": [{"id": "home"}]}'
        tasks = parser.parse(text)
        body = tasks[0].body
        # Should say to see SPEC when no reqs
        assert "see SPEC" in body or "SPEC" in body


# ── v4: field count in the brief, stricter done-when, flow backstop on disk ────────
class _Sandbox:
    def __init__(self, files):
        self.files = dict(files)

    def read(self, p):
        return self.files.get(p)

    def write(self, p, c):
        self.files[p] = c


_SPEC_V4 = """## Flows
### Flow 1
1. `home` — user clicks Go → lands on `detail`

## Screens
### home — Home
- Fields:
  | Field | Control | Required | Example | Options |
  |---|---|---|---|---|
  | Name | text | no | Coronado | |
  | Type | dropdown | no | Corp | |
  | State | text | no | TX | |

### detail — Detail
"""


def test_v4_brief_carries_field_count_and_state_and_attribute_rules():
    inv = parse_inventory('{"screens": [{"id": "home", "title": "Home"}, {"id": "detail", "title": "Detail"}]}')
    body = render_body(inv.by_id()["home"], inv, _SPEC_V4)
    assert "at least 3 form controls" in body and "the SPEC lists 3 fields" in body
    assert "every element with class `state` is named by a `data-show`" in body
    assert "no element carries two of data-goto" in body
    body_detail = render_body(inv.by_id()["detail"], inv, _SPEC_V4)
    assert "form controls" not in body_detail  # no Fields block, no count line


def test_v4_parse_preferring_target_applies_the_flow_backstop_and_writes_it_back():
    sb = _Sandbox({
        "build/screens.json": '{"screens": [{"id": "home", "title": "Home"}, {"id": "detail", "title": "Detail"}]}',
        "spec.md": _SPEC_V4,
    })
    tasks = ScreenPlanParser().parse_preferring_target("", sandbox=sb, target="build/screens.json")
    home = next(t for t in tasks if t.id == "screen-home")
    assert 'data-goto="detail"' in home.body and 'data-goto="detail"' in home.done_when
    import json as _json
    written = _json.loads(sb.files["build/screens.json"])
    assert written["screens"][0]["transitions"] == [{"label": "Go", "attr": "data-goto", "to": "detail"}]
    assert written["notes"] and written["notes"][0].startswith("flow backstop")


def test_v4_write_back_keeps_extra_keys_on_existing_transitions():
    sb = _Sandbox({
        "build/screens.json": '{"screens": [{"id": "home", "title": "Home", "transitions": [{"label": "Help", "attr": "data-goto", "to": "detail", "source": "REQ-001"}]}, {"id": "detail", "title": "Detail"}, {"id": "other", "title": "Other"}]}',
        "spec.md": "## Flows\n### F\n1. `home` — user clicks Next → lands on `other`\n\n## Screens\n### home — Home\n### detail — Detail\n### other — Other\n",
    })
    ScreenPlanParser().parse_preferring_target("", sandbox=sb, target="build/screens.json")
    import json as _json
    tr = _json.loads(sb.files["build/screens.json"])["screens"][0]["transitions"]
    assert tr[0] == {"label": "Help", "attr": "data-goto", "to": "detail", "source": "REQ-001"}
    assert tr[1] == {"label": "Next", "attr": "data-goto", "to": "other"}
