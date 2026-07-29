"""Deterministic gate: is this response even well-formed?

Runs before the judge so a malformed response is never graded and structural
regressions are caught for free. Strictly structural — anything requiring
judgement about whether content is GOOD belongs in the judge rubric.
"""

from __future__ import annotations

import re
from typing import Callable

REQUIRED_CONFIG_KEYS = ("wrapper", "section_pattern", "forbidden")
# 'min_sections' is deliberately NOT required: a config may omit it and take
# the default of 1.


def validate_config(config: dict) -> None:
    """Raise ValueError if the precheck config is missing a required key."""
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ValueError(f"precheck config missing required key(s): {missing}")


def closing_tag(wrapper: str) -> str:
    """Derive `</spec>` from `<spec>`; fall back to the wrapper itself.

    Config may override via `close_wrapper` when the closing form is not
    derivable by inserting a slash (`<!doctype html>` -> `</html>`).
    """
    if wrapper.startswith("<") and wrapper.endswith(">") and not wrapper.startswith("</"):
        return "</" + wrapper[1:]
    return wrapper


def run(response: str, config: dict, *, hook: Callable | None = None) -> tuple[bool, str]:
    """Run the generic gate AND the custom hook; both must pass.

    Generic checks, first-failure-wins, all case-insensitive: the stripped
    response starts with `wrapper` and ends with its closing form; at least
    `min_sections` matches of `section_pattern`; no `forbidden` REGEX matches
    (each entry is `{pattern, reason}`, and the reason is what a failure reports).

    Returns (passed, reason). With a hook the reason is
    `"generic: ... | custom: ..."`, and the generic check is never short-circuited.
    """
    generic_passed, generic_reason = _run_generic(response, config)
    if hook is None:
        return generic_passed, generic_reason

    custom_passed, custom_reason = hook(response)
    passed = generic_passed and custom_passed
    return passed, f"generic: {generic_reason} | custom: {custom_reason}"


def _run_generic(response: str, config: dict) -> tuple[bool, str]:
    """The agent-agnostic structural gate; returns the FIRST failure's reason."""
    validate_config(config)

    wrapper_failure = _check_wrapper(response, config)
    if wrapper_failure is not None:
        return False, wrapper_failure

    section_count = len(re.findall(config["section_pattern"], response, re.MULTILINE))
    min_sections = config.get("min_sections", 1)
    if section_count < min_sections:
        return (
            False,
            f"only {section_count} section(s) matching {config['section_pattern']!r}, "
            f"need >= {min_sections}",
        )

    forbidden_failure = _check_forbidden(response, config["forbidden"])
    if forbidden_failure is not None:
        return False, forbidden_failure

    return (
        True,
        f"wrapper ok, {section_count} section(s) >= {min_sections}, no forbidden patterns",
    )


def _check_wrapper(response: str, config: dict) -> str | None:
    """Return a failure reason if the response is not bracketed by the wrapper."""
    wrapper = config["wrapper"]
    close_wrapper = config.get("close_wrapper") or closing_tag(wrapper)
    stripped = response.strip().lower()
    if stripped.startswith(wrapper.lower()) and stripped.endswith(close_wrapper.lower()):
        return None
    return (
        f"response not wrapped in {wrapper}...{close_wrapper} "
        "(preamble/postamble text present, or wrapper missing)"
    )


def _check_forbidden(response: str, forbidden: list[dict]) -> str | None:
    """Return a failure reason for the first forbidden regex that matches.

    Each entry is `{pattern, reason}`; the reason plus the text that actually
    matched is what a human reads when a run fails, so both are reported.
    """
    for entry in forbidden:
        pattern = entry["pattern"]
        match = re.search(pattern, response)
        if match is not None:
            return (
                f"forbidden pattern {pattern!r} matched {match.group(0)!r}: "
                f"{entry['reason']}"
            )
    return None
