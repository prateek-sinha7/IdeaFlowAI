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
#
# ``SKIPPED`` is the render-skip SENTINEL (quick-260701-bob / VALIDATOR-SKIPPED): it
# is NOT part of the P0–P3 blocking ladder — it only ever lands on the audit ROW
# (via record_validation_result) so a render skip is RECORDED, never swallowed into
# "no issues". It is never returned as a blocking Issue and the gate never maps it,
# so the P0–P3 ordering used elsewhere (``_worst_label`` / block-critical) is intact.
_SEVERITY_LABELS: dict[str, str] = {
    "P0": "CRITICAL",
    "P1": "HIGH",
    "P2": "MEDIUM",
    "P3": "LOW",
    "SKIPPED": "SKIPPED",
}


def map_severity(internal: str) -> str:
    """Map an internal severity to its UI label (VALID-03 single source).

    ``P0 -> CRITICAL``, ``P1 -> HIGH``, ``P2 -> MEDIUM``, ``P3 -> LOW`` — plus the
    render-skip sentinel ``SKIPPED -> SKIPPED`` (audit-row-only; never a blocking
    Issue, so the P0–P3 blocking ladder is unchanged).

    Raises:
        ValueError: for any input outside ``P0``–``P3``/``SKIPPED`` — one
            deterministic behavior, NAMING the bad value (no silent default, no
            second mapping).
    """
    try:
        return _SEVERITY_LABELS[internal]
    except KeyError:
        raise ValueError(
            f"unknown internal severity {internal!r} — expected one of "
            f"{sorted(_SEVERITY_LABELS)}"
        ) from None


def render_coverage_status(rres: object, require_render: bool) -> str:
    """The SINGLE render-coverage policy decision (quick-260701-bob / RENDER-SEAM).

    The one function every render consumer routes through — html_render, the engine's
    ``_select_issues_to_fix`` and ``_run_validation_fix_loop`` — so "did the render
    actually run, and if not does it fail closed?" has exactly ONE home:

      * ``"ok"``              — the render ran (``rres.available`` is True): use its
                                console/page/nav/coverage findings normally.
      * ``"skipped_blocked"`` — the render did NOT run AND ``require_render`` is True:
                                fail CLOSED (html_render emits a P0 → the existing
                                ValidationGate block-critical policy → GATE_BLOCK).
      * ``"skipped_allowed"`` — the render did NOT run AND ``require_render`` is False:
                                pass, but a distinct ``validator_skipped`` audit row is
                                recorded so the skip is never silently dropped.

    Pure/stdlib (import-clean): kernel-pure so the gate, the app validators and the
    engine can all import it without a kernel→app edge (import-linter 4/0).
    """
    if getattr(rres, "available", False):
        return "ok"
    return "skipped_blocked" if require_render else "skipped_allowed"
