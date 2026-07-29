"""model_graded/precheck.py — the GENERIC, agent-agnostic deterministic
pre-check.

This module has no idea any particular agent (e.g. ``prototype-specify``)
exists. Everything it checks comes from a scenario's own ``precheck:`` YAML
config (see ``clarifications.md`` Q10): a wrapper it must be bracketed by, a
minimum count of a configurable "section" pattern, and a list of forbidden
substrings. Anything a scenario needs beyond this — real parsing, not a
count/substring check — is an ADDITIONAL, narrow custom hook
(``GradedScenario.precheck_module``), run alongside this generic check, never
instead of it.
"""

from __future__ import annotations

import re

REQUIRED_CONFIG_KEYS = ("wrapper", "section_pattern", "forbidden")
# 'min_sections' is intentionally NOT in REQUIRED_CONFIG_KEYS: when a
# scenario's precheck: block omits it, scenario_discovery.py defaults it from
# the scenario-level 'min_pages' field (clarifications.md Q2) before
# run_precheck ever sees the config — by the time run_precheck runs,
# 'min_sections' is always present, but the *authoring* surface (the raw YAML
# block) is allowed to omit it in favor of the friendlier 'min_pages' name.


def validate_precheck_config(config: dict) -> None:
    """Raise ``ValueError`` if ``config`` is missing a required key.

    Called at scenario-load time (not at check time) so a scenario with a
    broken ``precheck:`` block fails loudly before any run, not silently
    mid-check.
    """
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ValueError(f"precheck config missing required key(s): {missing}")


def run_precheck(response: str, config: dict) -> tuple[bool, str]:
    """Check ``response`` against ``config`` — no model call, no agent
    knowledge, purely structural.

    ``config`` keys:
      - ``wrapper``: a string the response must both start and end with
        (after stripping whitespace, case-insensitively), with no other
        content before/after — e.g. ``"<spec>"`` checks for a response
        wrapped in ``<spec>...</spec>``.
      - ``close_wrapper`` (optional): the exact closing marker, when it
        can't be auto-derived from ``wrapper`` — e.g. a raw HTML deliverable
        opens with ``"<!doctype html>"`` and closes with ``"</html>"``,
        which don't share the simple ``<tag>``/``</tag>`` shape
        ``_closing_tag`` assumes. Defaults to ``_closing_tag(wrapper)`` when
        absent (unchanged behavior for every existing ``<tag>``-style
        scenario).
      - ``min_sections``: minimum number of lines matching ``section_pattern``.
      - ``section_pattern``: a regex (matched with ``re.MULTILINE``) counting
        "sections" — e.g. ``r"^### "`` counts markdown H3 headings.
      - ``forbidden``: substrings that must not appear anywhere in the
        response (case-insensitive).

    Returns ``(True, reason)`` if every check passes, ``(False, reason)``
    naming the FIRST failing check otherwise.
    """
    validate_precheck_config(config)

    wrapper = config["wrapper"]
    close_wrapper = config.get("close_wrapper") or _closing_tag(wrapper)
    stripped = response.strip()
    if not (
        stripped.lower().startswith(wrapper.lower())
        and stripped.lower().endswith(close_wrapper.lower())
    ):
        return (
            False,
            f"response not wrapped in {wrapper}...{close_wrapper} "
            "(preamble/postamble text present, or wrapper missing)",
        )

    pattern = re.compile(config["section_pattern"], re.MULTILINE)
    section_count = len(pattern.findall(response))
    min_sections = config.get("min_sections", 1)
    if section_count < min_sections:
        return (
            False,
            f"only {section_count} section(s) matching {config['section_pattern']!r}, "
            f"need >= {min_sections}",
        )

    lowered = response.lower()
    for forbidden in config["forbidden"]:
        if forbidden.lower() in lowered:
            return (False, f"forbidden placeholder string present: {forbidden!r}")

    return (True, f"wrapper ok, {section_count} section(s) >= {min_sections}, no forbidden strings")


def _closing_tag(wrapper: str) -> str:
    """Derive the closing tag for an opening tag like ``"<spec>"`` ->
    ``"</spec>"``. Falls back to the wrapper itself for non-tag wrappers
    (a scenario using a non-XML-style wrapper can just set ``wrapper`` to
    something whose start/end check makes sense both ways is out of scope —
    the common case here is an XML-ish tag, per prototype-specify's
    ``<spec>...</spec>`` contract).
    """
    if wrapper.startswith("<") and wrapper.endswith(">") and not wrapper.startswith("</"):
        return "</" + wrapper[1:]
    return wrapper
