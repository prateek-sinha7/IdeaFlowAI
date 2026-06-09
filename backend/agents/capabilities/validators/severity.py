"""agents/capabilities/validators/severity.py — the single severity mapping (VALID-03).

THE canonical, single-source mapping of the internal P0–P3 severities to the
UI-facing CRITICAL/HIGH/MEDIUM/LOW labels (VALID-03 / D-04 / Q24). The whole
phase shares this ONE function:

  * the 08-02 ``validation`` gate imports it (eliminating the forward reference
    to 08-04) — so it MUST be import-clean: pure stdlib, NO ``@register`` /
    ``discover()`` side-effect, importable at any time including before the
    validator impls land;
  * 08-04's ``Validator`` impls IMPORT it (they MUST NOT recreate it);
  * the API / frontend severity labels derive from it.

There is exactly ONE definition of ``map_severity`` in the tree — do not add a
second mapping anywhere (VALID-03 single-source rule).
"""

from __future__ import annotations

# The single internal-severity -> UI-label mapping (P0 most severe). Internal
# severities are the engineer-facing P0–P3 ladder; the labels are what the UI /
# API surface. Keep this dict the SOLE source — every consumer imports the
# function below, never re-derives the mapping.
_SEVERITY_LABELS: dict[str, str] = {
    "P0": "CRITICAL",
    "P1": "HIGH",
    "P2": "MEDIUM",
    "P3": "LOW",
}


def map_severity(internal: str) -> str:
    """Map an internal P0–P3 severity to its UI label (VALID-03 single source).

    ``P0 -> CRITICAL``, ``P1 -> HIGH``, ``P2 -> MEDIUM``, ``P3 -> LOW``.

    Raises:
        ValueError: for any input outside ``P0``–``P3`` — one deterministic
            behavior, NAMING the bad value (no silent default, no second mapping).
    """
    try:
        return _SEVERITY_LABELS[internal]
    except KeyError:
        raise ValueError(
            f"unknown internal severity {internal!r} — expected one of "
            f"{sorted(_SEVERITY_LABELS)}"
        ) from None
