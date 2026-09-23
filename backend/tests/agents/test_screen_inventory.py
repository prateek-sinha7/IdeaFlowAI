"""Unit tests for agents/capabilities/screen_inventory.py."""

from __future__ import annotations

import pytest

from agents.capabilities.screen_inventory import (
    COMPONENT_CLASSES,
    Inventory,
    InventoryError,
    Screen,
    Transition,
    attribute_string,
    parse_inventory,
    slug,
)


class TestSlug:
    """Test the slug() function."""

    def test_slug_lowercases_and_hyphenates(self):
        assert slug("Account Transactions") == "account-transactions"

    def test_slug_handles_special_chars(self):
        assert slug("Hello & World!") == "hello-world"

    def test_slug_strips_leading_trailing_whitespace(self):
        assert slug("  spaces  ") == "spaces"

    def test_slug_empty_or_whitespace_defaults_to_screen(self):
        assert slug("") == "screen"
        assert slug("   ") == "screen"

    def test_slug_multiple_consecutive_hyphens_reduced(self):
        assert slug("a___b") == "a-b"


class TestAttributeString:
    """Test the attribute_string() function."""

    def test_data_opens_with_dialog_prefix(self):
        t = Transition(label="Open", attr="data-opens", to="dialog-settings")
        assert attribute_string(t) == 'data-opens="dialog-settings"'

    def test_data_opens_adds_prefix_if_missing(self):
        t = Transition(label="Open", attr="data-opens", to="settings")
        assert attribute_string(t) == 'data-opens="dialog-settings"'

    def test_data_opens_no_double_prefix(self):
        t = Transition(label="Open", attr="data-opens", to="dialog-settings")
        assert attribute_string(t) == 'data-opens="dialog-settings"'

    def test_data_closes_with_dialog_prefix(self):
        t = Transition(label="Close", attr="data-closes", to="settings")
        assert attribute_string(t) == 'data-closes="dialog-settings"'

    def test_data_goto_verbatim(self):
        t = Transition(label="Go", attr="data-goto", to="home")
        assert attribute_string(t) == 'data-goto="home"'

    def test_data_tab_verbatim(self):
        t = Transition(label="Tab", attr="data-tab", to="panel-a")
        assert attribute_string(t) == 'data-tab="panel-a"'

    def test_data_submit_verbatim(self):
        t = Transition(label="Submit", attr="data-submit", to="checkout")
        assert attribute_string(t) == 'data-submit="checkout"'


class TestParseInventoryErrors:
    """Test error conditions in parse_inventory()."""

    def test_empty_text_raises_error(self):
        with pytest.raises(InventoryError, match="empty"):
            parse_inventory("")

    def test_whitespace_only_raises_error(self):
        with pytest.raises(InventoryError, match="empty"):
            parse_inventory("   \n\n  ")

    def test_invalid_json_raises_error_with_line_column(self):
        with pytest.raises(InventoryError, match="not valid JSON"):
            parse_inventory("{invalid json}")

    def test_json_no_screens_list_raises_error(self):
        with pytest.raises(InventoryError, match="no 'screens' list"):
            parse_inventory('{"title": "App"}')

    def test_json_empty_screens_list_raises_error(self):
        with pytest.raises(InventoryError, match="empty"):
            parse_inventory('{"screens": []}')

    def test_screen_missing_id_raises_error(self):
        with pytest.raises(InventoryError, match="no 'id'"):
            parse_inventory('{"screens": [{"title": "Home"}]}')

    def test_duplicate_screen_id_raises_error(self):
        with pytest.raises(InventoryError, match="duplicate screen id"):
            parse_inventory(
                '{"screens": [{"id": "home", "title": "Home"}, {"id": "home", "title": "Home 2"}]}'
            )


class TestParseInventoryDefaults:
    """Test defaults and normalization in parse_inventory()."""

    def test_top_level_array_wrapped(self):
        inv = parse_inventory('[{"id": "home", "title": "Home"}]')
        assert len(inv.screens) == 1
        assert any("top-level array wrapped" in n for n in inv.notes)

    def test_missing_title_defaults_from_id(self):
        inv = parse_inventory('{"screens": [{"id": "search-page"}]}')
        assert inv.screens[0].title == "Search Page"
        assert any("title defaulted" in n for n in inv.notes)

    def test_kind_overlay_becomes_dialog(self):
        inv = parse_inventory('{"screens": [{"id": "popup", "kind": "overlay"}]}')
        assert inv.screens[0].kind == "dialog"

    def test_kind_modal_becomes_dialog(self):
        inv = parse_inventory('{"screens": [{"id": "modal-x", "kind": "modal"}]}')
        assert inv.screens[0].kind == "dialog"

    def test_kind_unknown_defaults_by_id_suffix(self):
        inv = parse_inventory(
            '{"screens": [{"id": "settings-dialog", "kind": "unknown-kind"}]}'
        )
        assert inv.screens[0].kind == "dialog"
        assert any("unknown kind" in n for n in inv.notes)

    def test_kind_unknown_no_suffix_defaults_to_page(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "kind": "unknown"}]}'
        )
        assert inv.screens[0].kind == "page"

    def test_screen_id_normalised_and_noted(self):
        inv = parse_inventory('{"screens": [{"id": "Home Page"}]}')
        assert inv.screens[0].id == "home-page"
        assert any("normalised" in n for n in inv.notes)

    def test_entry_missing_defaults_to_first_page(self):
        inv = parse_inventory(
            '{"screens": [{"id": "s1", "kind": "dialog"}, {"id": "s2", "kind": "page"}]}'
        )
        assert inv.entry == "s2"

    def test_entry_unknown_defaults_to_first_page(self):
        inv = parse_inventory(
            '{"screens": [{"id": "s1", "kind": "page"}], "entry": "unknown"}'
        )
        assert inv.entry == "s1"
        assert any("not a screen" in n for n in inv.notes)

    def test_entry_is_first_screen_if_no_pages(self):
        inv = parse_inventory('{"screens": [{"id": "d1", "kind": "dialog"}]}')
        assert inv.entry == "d1"


class TestParseInventoryTransitions:
    """Test transition parsing and inference in parse_inventory()."""

    def test_transition_attr_inferred_for_dialog_target(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home"}, {"id": "settings", "kind": "dialog", "transitions": [{"to": "settings"}]}]}'
        )
        settings = inv.screens[1]
        assert len(settings.transitions) >= 1
        assert any(t.to == "settings" and t.attr == "data-opens" for t in settings.transitions)

    def test_transition_attr_inferred_for_self_reference_as_tab(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "transitions": [{"to": "home"}]}]}'
        )
        assert inv.screens[0].transitions[0].attr == "data-tab"

    def test_transition_attr_inferred_for_page_nav_as_goto(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home"}, {"id": "about", "transitions": [{"to": "home"}]}]}'
        )
        assert inv.screens[1].transitions[0].attr == "data-goto"

    def test_transition_data_goto_to_dialog_changed_to_opens(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home"}, {"id": "settings", "kind": "dialog", "transitions": [{"attr": "data-goto", "to": "settings"}]}]}'
        )
        settings = inv.screens[1]
        assert any(t.attr == "data-opens" for t in settings.transitions)
        assert any("changed to data-opens" in n for n in inv.notes)

    def test_transition_dialog_auto_close_added(self):
        inv = parse_inventory(
            '{"screens": [{"id": "modal", "kind": "dialog"}]}'
        )
        modal = inv.screens[0]
        assert any(t.attr == "data-closes" for t in modal.transitions)
        assert any("close transition" in n for n in inv.notes)

    def test_transition_target_unknown_to_page_noted(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "transitions": [{"to": "unknown"}]}]}'
        )
        assert any("unknown screen" in n for n in inv.notes)

    def test_transition_target_unknown_to_dialog_noted(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "kind": "dialog", "transitions": [{"attr": "data-closes", "to": "unknown"}]}]}'
        )
        assert any("not a dialog" in n for n in inv.notes)

    def test_transition_label_defaulted_from_target(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "transitions": [{"to": "about"}]}]}'
        )
        assert inv.screens[0].transitions[0].label == "About"

    def test_transition_with_explicit_label(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "transitions": [{"label": "Go Home", "to": "home"}]}]}'
        )
        assert inv.screens[0].transitions[0].label == "Go Home"

    def test_transition_missing_to_dropped(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "transitions": [{"label": "Bad"}]}]}'
        )
        assert len(inv.screens[0].transitions) == 0
        assert any("no 'to'" in n for n in inv.notes)

    def test_transition_data_tab_slugs_target(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home-page", "transitions": [{"to": "Home Page"}]}]}'
        )
        # "Home Page" slugs to "home-page", which equals the screen id, so it's a tab
        assert inv.screens[0].transitions[0].attr == "data-tab"
        assert inv.screens[0].transitions[0].to == "home-page"


class TestParseInventoryById:
    """Test the by_id() method."""

    def test_by_id_returns_dict_keyed_by_screen_id(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home"}, {"id": "about"}]}'
        )
        by_id = inv.by_id()
        assert "home" in by_id
        assert "about" in by_id
        assert by_id["home"].id == "home"


class TestParseInventoryPages:
    """Test the pages and dialogs properties."""

    def test_pages_returns_non_dialog_screens(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "kind": "page"}, {"id": "modal", "kind": "dialog"}]}'
        )
        pages = inv.pages
        assert len(pages) == 1
        assert pages[0].id == "home"

    def test_dialogs_returns_dialog_screens(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home"}, {"id": "modal", "kind": "dialog"}]}'
        )
        dialogs = inv.dialogs
        assert len(dialogs) == 1
        assert dialogs[0].id == "modal"


class TestScreenDialogIdProperty:
    """Test the dialog_id property."""

    def test_dialog_id_prefixed(self):
        screen = Screen(id="settings", title="Settings", kind="dialog")
        assert screen.dialog_id == "dialog-settings"

    def test_is_dialog_property(self):
        page = Screen(id="home", title="Home", kind="page")
        dialog = Screen(id="settings", title="Settings", kind="dialog")
        assert not page.is_dialog
        assert dialog.is_dialog


class TestParseInventoryComplexCase:
    """Test a complex inventory with mixed screens, transitions, etc."""

    def test_complete_workflow(self):
        text = """{
            "title": "Inland Marine Quote System",
            "entry": "search",
            "screens": [
                {"id": "search", "title": "Search Quotes", "kind": "page", "nav": "Quote",
                 "transitions": [{"label": "View Details", "to": "details"}]},
                {"id": "details", "title": "Quote Details", "kind": "page",
                 "transitions": [{"label": "Back", "to": "search"}]},
                {"id": "confirm", "title": "Confirm", "kind": "dialog",
                 "transitions": []}
            ]
        }"""
        inv = parse_inventory(text)
        assert inv.title == "Inland Marine Quote System"
        assert inv.entry == "search"
        assert len(inv.screens) == 3
        assert inv.screens[0].nav == "Quote"
        assert inv.screens[2].kind == "dialog"
        # Check auto-close was added to dialog
        assert any(t.attr == "data-closes" for t in inv.screens[2].transitions)


class TestFencedJson:
    """Test parsing JSON within markdown code fences."""

    def test_json_in_triple_backticks(self):
        text = """```json
{"screens": [{"id": "home", "title": "Home"}]}
```"""
        inv = parse_inventory(text)
        assert len(inv.screens) == 1
        assert inv.screens[0].id == "home"

    def test_json_in_backticks_without_lang(self):
        text = """```
{"screens": [{"id": "home", "title": "Home"}]}
```"""
        inv = parse_inventory(text)
        assert len(inv.screens) == 1

    def test_raw_json_without_fence(self):
        text = '{"screens": [{"id": "home"}]}'
        inv = parse_inventory(text)
        assert len(inv.screens) == 1


class TestComponentClasses:
    """Test that COMPONENT_CLASSES is well-formed."""

    def test_component_classes_is_tuple_of_strings(self):
        assert isinstance(COMPONENT_CLASSES, tuple)
        assert all(isinstance(c, str) for c in COMPONENT_CLASSES)

    def test_component_classes_contains_expected_entries(self):
        expected = [
            "page-header",
            "page-title",
            "form",
            "btn",
            "table",
            "tabs",
        ]
        for exp in expected:
            assert exp in COMPONENT_CLASSES

    def test_component_classes_no_duplicates(self):
        assert len(COMPONENT_CLASSES) == len(set(COMPONENT_CLASSES))


class TestParseInventoryNotesAccumulate:
    """Test that notes accumulate correctly."""

    def test_multiple_notes_recorded(self):
        inv = parse_inventory(
            '{"screens": [{"id": "Page Name"}, {"id": "modal-dialog", "kind": "unknown"}]}'
        )
        assert len(inv.notes) >= 2
        assert any("normalised" in n for n in inv.notes)
        assert any("unknown kind" in n for n in inv.notes)


# ── spec helpers + flow backstop (prototype v4) ───────────────────────────────────
from agents.capabilities.screen_inventory import (  # noqa: E402
    apply_flow_backstop,
    flow_moves,
    spec_fields,
    spec_section,
)

_SPEC = """## Flows
### Flow 1 — Quote
1. `search` — user clicks Search → results appear on same screen
2. `search` — user clicks account name → lands on `account`
3. `account` — user clicks the folder icon → lands on `edit-dialog`
4. `edit-dialog` — user clicks Save → returns to `account`
5. `account` — underwriter verifies fields and clicks Policy Info → lands on `policy`

## Screens
### search — Search
- Fields:
  | Field | Control | Required | Example | Options |
  |---|---|---|---|---|
  | Account # | text | no | 2243114 | |
  | Status | dropdown | no | Any | Any, Active |
- Actions:
  | Control | What it does | Navigates to | Evidence |
  |---|---|---|---|
  | Search | runs the search | stays | [p.2] |

### account — Account
- Fields:
  - Name [text: Coronado]
  - Type [dropdown: Corporation]
  - State [text: TX]
- Actions: none

### policy — Policy
### edit-dialog — Edit
"""


def test_spec_fields_reads_a_table_and_skips_header_and_rule_rows():
    assert spec_fields(spec_section(_SPEC, "search")) == ["Account #", "Status"]


def test_spec_fields_reads_indented_bullets():
    assert spec_fields(spec_section(_SPEC, "account")) == ["Name", "Type", "State"]


def test_spec_fields_is_empty_without_a_fields_block():
    assert spec_fields(spec_section(_SPEC, "policy")) == []
    assert spec_fields("") == []


def test_flow_moves_names_both_ends_and_a_label_when_the_line_has_one():
    moves = flow_moves(_SPEC)
    assert ("search", "account", "") in moves or ("search", "account", "account name") in moves
    assert ("account", "edit-dialog", "") in moves or any(m[:2] == ("account", "edit-dialog") for m in moves)
    assert any(m[:2] == ("account", "policy") and m[2] == "Policy Info" for m in moves)
    assert not any(m[0] == m[1] for m in moves)


def test_apply_flow_backstop_adds_missing_moves_and_leaves_existing_and_dialog_sources():
    inv = parse_inventory(
        '{"entry": "search", "screens": ['
        '{"id": "search", "title": "Search", "transitions": [{"label": "Account", "attr": "data-goto", "to": "account"}]},'
        '{"id": "account", "title": "Account"},'
        '{"id": "policy", "title": "Policy"},'
        '{"id": "edit-dialog", "title": "Edit", "kind": "dialog"}]}'
    )
    notes = apply_flow_backstop(inv, _SPEC)
    by = inv.by_id()
    assert [t.to for t in by["search"].transitions] == ["account"]  # existing, not duplicated
    added = {(t.attr, t.to): t.label for t in by["account"].transitions}
    assert added[("data-opens", "edit-dialog")]  # page → dialog becomes data-opens
    assert added[("data-goto", "policy")] == "Policy Info"  # label taken from the flow line
    assert all(t.attr == "data-closes" for t in by["edit-dialog"].transitions)  # dialog source untouched
    assert len(notes) == 2 and all(n.startswith("flow backstop: added") for n in notes)
    assert notes == inv.notes[-2:]


def test_flow_moves_accepts_bold_ids_as_the_analyst_writes_them():
    spec = """## Flows
### Flow 1
1. **search** — User clicks Search → lands on **search** (results state)
2. **search** (results) — User clicks Trans folder icon → lands on **account-transactions**
3. **policy-info** — User fills fields, clicks States → lands on **im-states**

## Screens
### search — Search
"""
    moves = flow_moves(spec)
    assert ("search", "account-transactions") in [(a, b) for a, b, _ in moves]
    assert ("policy-info", "im-states") in [(a, b) for a, b, _ in moves]
    assert not any(a == b for a, b, _ in moves)


def test_spec_fields_walks_sub_sectioned_tables_until_the_next_bullet():
    sec = """### uis-form — UIS
- Route: /uis-form
- Fields:

**Basic Information Section:**

| Field | Control | Required | Example or default | Options |
|---|---|---|---|---|
| Insured Name | Text | No | Coronado | — |
| Agent | Text | Yes | AMWINS | — |

**General Policy Information Section:**

| Field | Control | Required | Example or default | Options |
|---|---|---|---|---|
| Reporting | Dropdown | Yes | No | No; Yes |
- Actions:
  | Control | What it does | Navigates to | Evidence |
  |---|---|---|---|
  | Save | saves | stays | [p.7] |
"""
    assert spec_fields(sec) == ["Insured Name", "Agent", "Reporting"]


def test_flow_moves_reads_each_screens_actions_table_destination_column():
    spec = """## Flows
### Flow 1
1. The user searches, then opens the account.

## Screens
### account-search — Account Search

- **Fields:**

| Field | Control | Required | Example or default | Options |
|-------|---------|----------|--------------------|---------|
| Account # | Text | No | 182067033019 | — |

- **Actions:**

| Control | What it does | Navigates to | Evidence |
|---------|-------------|--------------|----------|
| Search button | Submits search | stays | [quote p.02] |
| Folder icon (Trans column) | Opens account transactions | account-transactions | [quote p.02] |
| Tasks tab | [not evidenced] | — | [not evidenced] |
| Clone icon | Opens the clone dialog | `transaction-type` | [quote p.03] |

### account-transactions — Account Transactions

- **Actions:**

| Control | What it does | Navigates to | Evidence |
|---------|-------------|--------------|----------|
| Back | Returns to search | **account-search** | [quote p.03] |
| Refresh | Reloads | account-transactions | [quote p.03] |

## Missing
"""
    moves = flow_moves(spec)
    assert ("account-search", "account-transactions", "Folder icon (Trans column)") in moves
    assert ("account-search", "transaction-type", "Clone icon") in moves
    assert ("account-transactions", "account-search", "Back") in moves
    assert not any(a == b for a, b, _ in moves), "a row that stays on its screen is not a move"
    assert not any(b in ("stays", "—") for _, b, _ in moves)
    assert not any(a == "account-search" and b == "182067033019" for a, b, _ in moves), "Fields rows are not actions"
