"""Unit tests for ``app.agents.workflow_builder.script_policy``.

The expected tables are restated here from design section 3.4.4 and do not read
the module's own constants, so a change to a row or a refusal text fails a test.
The module is pure data, so nothing here touches the disk.

Requirements: 35.1 to 35.3, 35.5 to 35.12.
"""

from __future__ import annotations

import pytest

from app.agents.workflow_builder.script_policy import (
    BUILDER_SKILL_ID,
    EXPORTS_DIR,
    HELP_OPTIONS,
    POLICY,
    SLOT_REFUSALS,
    OptionSpec,
    PathSlotKind,
    ScriptRule,
    allowed_script_names,
    get_rule,
    unknown_script_message,
)

_SCRIPTS = (
    "catalog_lookup.py",
    "export_manifest.py",
    "refresh_catalog.py",
    "schema_sync.py",
    "selftest.py",
    "validate_manifest.py",
)

# subcommand -> (options with takes_value, (min, max)) for catalog_lookup.py.
_CATALOG_SUBCOMMANDS: dict[str, tuple[dict[str, bool], tuple[int, int | None]]] = {
    "overview": ({"--trust": True}, (0, 0)),
    "models": ({"--eu": False}, (0, 0)),
    "icons": ({}, (0, 0)),
    "kind": ({"--trust": True}, (1, 1)),
    "agents": ({"--all": False}, (0, 0)),
    "agent": ({}, (1, 1)),
    "skills": ({}, (0, None)),
    "workflows": ({}, (0, 0)),
    "mcp": ({}, (0, 0)),
    "trust": ({}, (1, 1)),
    "field": ({"--full": False}, (0, 1)),
    "search": ({}, (1, None)),
    "example": ({}, (0, 2)),
}

_OWN_FILES = "always reads the skill's own catalog and schema"
_CI_CATALOG = "The catalog is refreshed in CI. Use catalog_lookup.py to read it."
_SCHEMA_FIXED = "The schema never changes at run time. Use --check."
_SELFTEST_CI = "CI runs the compiler self-test"

# (script, refused option, text every refusal for that option must contain)
_REFUSALS: list[tuple[str, str, str]] = [
    ("catalog_lookup.py", "--catalog", _OWN_FILES),
    ("catalog_lookup.py", "--schema", _OWN_FILES),
    ("validate_manifest.py", "--catalog", _OWN_FILES),
    ("validate_manifest.py", "--schema", _OWN_FILES),
    ("selftest.py", "--compiler", _SELFTEST_CI),
    ("selftest.py", "--catalog", _OWN_FILES),
    *[
        ("refresh_catalog.py", option, _CI_CATALOG)
        for option in (
            "--source",
            "--api",
            "--render",
            "--token",
            "--out-json",
            "--out-md",
            "--schema",
            "--no-schema",
        )
    ],
    ("schema_sync.py", "--catalog", _SCHEMA_FIXED),
    ("schema_sync.py", "--schema", _SCHEMA_FIXED),
]


def _rule(script: str) -> ScriptRule:
    rule = get_rule(BUILDER_SKILL_ID, script)
    assert rule is not None
    return rule


def _option_table(rule: ScriptRule) -> dict[str, OptionSpec]:
    return dict(rule.options)


def test_policy_keys_the_builder_skill_to_exactly_the_six_scripts_when_loaded() -> None:
    assert set(POLICY) == {BUILDER_SKILL_ID}
    assert tuple(sorted(POLICY[BUILDER_SKILL_ID])) == _SCRIPTS


@pytest.mark.parametrize("script", _SCRIPTS)
def test_policy_rule_names_its_own_script_when_looked_up_by_file_name(
    script: str,
) -> None:
    assert _rule(script).script == script


def test_get_rule_returns_none_when_the_script_is_not_in_the_table() -> None:
    assert get_rule(BUILDER_SKILL_ID, "rm_rf.py") is None


def test_get_rule_returns_none_when_the_skill_id_is_unknown() -> None:
    assert get_rule("some-other-skill", "selftest.py") is None


def test_allowed_script_names_returns_the_sorted_names_when_skill_is_known() -> None:
    assert allowed_script_names(BUILDER_SKILL_ID) == _SCRIPTS


def test_allowed_script_names_returns_empty_when_skill_id_is_unknown() -> None:
    assert allowed_script_names("some-other-skill") == ()


def test_unknown_script_message_lists_every_allowed_script_when_called() -> None:
    message = unknown_script_message(BUILDER_SKILL_ID)

    assert message == f"Only these scripts can run: {', '.join(_SCRIPTS)}."


def test_help_options_are_the_short_and_long_pair_when_read() -> None:
    assert frozenset({"-h", "--help"}) == HELP_OPTIONS


# --- catalog_lookup.py ----------------------------------------------------------


def test_catalog_lookup_has_exactly_the_documented_subcommands_when_loaded() -> None:
    rule = _rule("catalog_lookup.py")

    assert rule.subcommands is not None
    assert set(rule.subcommands) == set(_CATALOG_SUBCOMMANDS)
    assert set(rule.subcommand_arity) == set(_CATALOG_SUBCOMMANDS)


@pytest.mark.parametrize("subcommand", sorted(_CATALOG_SUBCOMMANDS))
def test_catalog_lookup_subcommand_row_matches_the_table_when_loaded(
    subcommand: str,
) -> None:
    rule = _rule("catalog_lookup.py")
    expected_options, expected_arity = _CATALOG_SUBCOMMANDS[subcommand]

    assert rule.subcommands is not None
    options = rule.subcommands[subcommand]
    assert {name: spec.takes_value for name, spec in options.items()} == (
        expected_options
    )
    assert all(spec.slot is None for spec in options.values())
    assert rule.subcommand_arity[subcommand] == expected_arity


def test_catalog_lookup_takes_no_top_level_options_or_positionals_when_loaded() -> None:
    rule = _rule("catalog_lookup.py")

    assert not rule.options
    assert rule.positional_slots == ()
    assert rule.intercept is None


# --- validate_manifest.py -------------------------------------------------------


def test_validate_manifest_options_match_the_table_when_loaded() -> None:
    options = _option_table(_rule("validate_manifest.py"))

    assert {name: spec.takes_value for name, spec in options.items()} == {
        "--trust": True,
        "--summary": False,
        "--json": False,
        "--strict": False,
        "--quiet-info": False,
        "--compiler": True,
    }


def test_validate_manifest_reads_the_manifest_from_the_sandbox_when_loaded() -> None:
    assert _rule("validate_manifest.py").positional_slots == (
        PathSlotKind.SANDBOX_READ,
    )


def test_validate_manifest_discards_the_compiler_directory_when_loaded() -> None:
    rule = _rule("validate_manifest.py")

    assert rule.options["--compiler"].slot is PathSlotKind.IGNORED
    assert rule.intercept == "compiler_dry_run"


# --- selftest.py ----------------------------------------------------------------


def test_selftest_takes_no_options_or_arguments_when_loaded() -> None:
    rule = _rule("selftest.py")

    assert not rule.options
    assert rule.positional_slots == ()
    assert rule.subcommands is None


# --- refresh_catalog.py and schema_sync.py --------------------------------------


@pytest.mark.parametrize(
    ("script", "reason"),
    [("refresh_catalog.py", _CI_CATALOG), ("schema_sync.py", _SCHEMA_FIXED)],
)
def test_check_only_script_accepts_only_check_and_requires_it_when_loaded(
    script: str, reason: str
) -> None:
    rule = _rule(script)

    assert {name: spec.takes_value for name, spec in rule.options.items()} == {
        "--check": False
    }
    assert rule.required_any == frozenset({"--check"})
    assert reason in rule.required_reason


# --- export_manifest.py ---------------------------------------------------------


def test_export_manifest_options_match_the_table_when_loaded() -> None:
    options = _option_table(_rule("export_manifest.py"))

    assert {name: (spec.takes_value, spec.slot) for name, spec in options.items()} == {
        "--yaml": (True, PathSlotKind.EXPORT_WRITE),
        "--save-payload": (True, PathSlotKind.EXPORT_WRITE),
        "--run-payload": (True, PathSlotKind.EXPORT_WRITE),
        "--message": (True, None),
        "--name": (True, None),
    }


def test_export_manifest_requires_exactly_one_output_option_when_loaded() -> None:
    rule = _rule("export_manifest.py")

    assert rule.exactly_one_of == frozenset(
        {"--yaml", "--save-payload", "--run-payload"}
    )
    assert rule.positional_slots == (PathSlotKind.SANDBOX_READ,)
    assert "exactly one output option" in rule.required_reason
    assert EXPORTS_DIR in rule.required_reason


def test_exports_dir_is_the_sandbox_exports_folder_when_read() -> None:
    assert EXPORTS_DIR == "/exports/"


# --- refusal texts --------------------------------------------------------------


@pytest.mark.parametrize(("script", "option", "expected"), _REFUSALS)
def test_refusal_for_returns_the_reason_and_alternative_when_option_is_refused(
    script: str, option: str, expected: str
) -> None:
    reason = _rule(script).refusal_for(option)

    assert reason is not None
    assert expected in reason


def test_refused_options_match_the_table_exactly_when_loaded() -> None:
    expected: dict[str, set[str]] = {}
    for script, option, _ in _REFUSALS:
        expected.setdefault(script, set()).add(option)

    for script in _SCRIPTS:
        assert set(_rule(script).refused) == expected.get(script, set())


@pytest.mark.parametrize("script", ["export_manifest.py", "selftest.py"])
def test_refusal_for_returns_none_when_option_is_not_refused(script: str) -> None:
    assert _rule(script).refusal_for("--not-a-real-option") is None


def test_refresh_catalog_gives_one_answer_when_a_path_option_or_no_check_is_used() -> (
    None
):
    rule = _rule("refresh_catalog.py")

    assert rule.required_reason == rule.refusal_for("--source")


def test_selftest_refusal_points_at_the_platform_check_when_compiler_is_used() -> None:
    reason = _rule("selftest.py").refusal_for("--compiler")

    assert reason is not None
    assert "validate_manifest.py <manifest> --compiler" in reason


@pytest.mark.parametrize(
    "script", ["catalog_lookup.py", "validate_manifest.py", "selftest.py"]
)
def test_own_file_refusal_names_the_allowed_call_when_catalog_is_refused(
    script: str,
) -> None:
    reason = _rule(script).refusal_for("--catalog")

    assert reason is not None
    assert "Run it without --catalog or --schema." in reason


def test_every_refusal_text_is_a_complete_sentence_when_loaded() -> None:
    for script in _SCRIPTS:
        for option, reason in _rule(script).refused.items():
            assert reason.strip(), f"{script} {option} has an empty refusal"
            assert reason.rstrip().endswith("."), f"{script} {option} is not a sentence"


# --- slot refusals --------------------------------------------------------------


def test_slot_refusals_cover_every_path_slot_that_can_fail_when_loaded() -> None:
    assert set(SLOT_REFUSALS) == {
        PathSlotKind.SANDBOX_READ,
        PathSlotKind.EXPORT_WRITE,
        PathSlotKind.SCRIPT,
    }


def test_slot_refusal_for_exports_names_the_exports_folder_when_read() -> None:
    assert SLOT_REFUSALS[PathSlotKind.EXPORT_WRITE] == (
        "Write exports under /exports/. The canvas saves and runs the workflow."
    )


def test_slot_refusal_for_manifest_names_the_workflows_folder_when_read() -> None:
    text = SLOT_REFUSALS[PathSlotKind.SANDBOX_READ]

    assert "/workflows/my.workflow.json" in text
    assert "skill's own files cannot be used as input" in text


def test_slot_refusal_for_script_names_the_scripts_folder_when_read() -> None:
    assert SLOT_REFUSALS[PathSlotKind.SCRIPT] == (
        "Run a script from the skill's scripts folder, for example "
        "/skills/velocity-workflow-creator/scripts/catalog_lookup.py."
    )


def test_policy_tables_are_read_only_when_a_caller_tries_to_change_them() -> None:
    rule = _rule("selftest.py")

    with pytest.raises(TypeError):
        POLICY[BUILDER_SKILL_ID]["evil.py"] = rule  # type: ignore[index]
    with pytest.raises(TypeError):
        rule.refused["--x"] = "no"  # type: ignore[index]
