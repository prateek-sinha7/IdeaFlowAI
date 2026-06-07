"""MAN-05 structure test — pipeline_type consumed only by the id-alias resolver
for routing; the surviving behavioral branches match an explicit allow-list.

This test reads ``agents/execution_engine/engine.py`` source and enforces the
D-09 routing-vs-behavioral split for Phase 4 (1A):

  * The ONLY routing consumption of ``pipeline_type`` this phase adds is the
    run-entry id-alias resolver (``resolve_alias`` / ``compile_for_run``) — a
    function call, NOT a behavioral branch.
  * Every surviving BEHAVIORAL branch that keys off ``pipeline_type`` or
    ``spec.id == "<literal>"`` is one of the explicit Phase-7-scoped survivors
    enumerated in RESEARCH §D-09. The set collected from source must EXACTLY
    equal the allow-list — so the test FAILS if a NEW behavioral routing branch
    is introduced (MAN-05 violation) OR a survivor is deleted/refactored before
    its Phase-7 home exists.

The allow-list is matched on the normalized predicate TEXT (not line numbers) so
it survives line drift but pins the exact branch conditions.
"""

from __future__ import annotations

import re
from pathlib import Path

_ENGINE = (
    Path(__file__).resolve().parents[2]
    / "agents"
    / "execution_engine"
    / "engine.py"
)

# ── The explicit Phase-7-scoped survivor allow-list (D-09) ──────────────────
# 8 behavioral `pipeline_type` branches + 3 `spec.id == "prototype-build"`
# behavioral branches. Each entry is the normalized predicate text (whitespace
# collapsed, leading `if `/`elif ` and trailing `:` stripped where applicable).
# These are the branches that REMAIN until Phase 7 extracts them into
# capabilities. NONE may be deleted in 1A; NO new one may be added.
_ALLOWED_BEHAVIORAL_BRANCHES: frozenset[str] = frozenset(
    {
        # ── pipeline_type behavioral branches (8) ──────────────────────────
        # _resolve_final_output deliverable-by-class (L2/L9)
        'pipeline_type == "prototype_revision"',  # :425 (in _resolve_final_output)
        "pipeline_type in _PROTOTYPE_PIPELINE_TYPES",  # :442 (in _resolve_final_output)
        # revision seeding / baseline (L4/L8)
        # NOTE: same predicate text as the resolver branch above; the seeding
        # block (:620) and the deliverable block (:425) share the literal. It is
        # a single allow-listed predicate — counted once in the set.
        # PPT carousel sanitize (L3) — run-level and per-agent
        "pipeline_type in _PPT_PIPELINE_TYPES and final_output",  # :1118
        "pipeline_type in _PPT_PIPELINE_TYPES and output",  # :1484
        # L10 HTML read-back — pinned by the migration ledger
        'pipeline_type in ("od_prototype", "prototype")',  # :1470
        # persistence guard (skip custom-workflow persist)
        'pipeline_type in PIPELINE_AGENTS and pipeline_type != "custom"',  # :2228
        # ── spec.id behavioral branches (prototype-build dispatch, L7 + L12) ─
        'getattr(spec, "id", None) == "prototype-build"',  # :984 (L7 dispatch)
        'spec.id == "prototype-build" and task_num_str not in ("", "1")',  # :2542 (L12 sizing)
        'spec.id == "prototype-build"',  # :2625 (L12 injection)
    }
)

# Recognises a behavioral routing branch: an `if`/`elif` condition (or a boolean
# assignment) that keys off pipeline_type or a literal spec.id dispatch.
_BEHAVIORAL_RE = re.compile(
    r"(?:^|\W)pipeline_type\s*(?:==|\bin\b)"
    r'|(?:getattr\(spec,\s*"id"[^)]*\)|spec\.id)\s*==\s*"[^"]+"'
)


def _strip_comment(line: str) -> str:
    """Drop a trailing `#` comment, ignoring `#` inside string literals (simple)."""
    out = []
    in_str: str | None = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _normalize_predicate(line: str) -> str:
    """Reduce a source line to its normalized predicate text.

    Strips line-leading whitespace, a leading `if `/`elif `/assignment LHS, the
    trailing `:` and any wrapping parens of a compound condition, and collapses
    internal whitespace — so the allow-list pins the condition, not formatting.
    """
    code = _strip_comment(line).strip()
    # Strip an `if `/`elif `/`while ` prefix and a trailing colon.
    code = re.sub(r"^(if|elif|while)\s+", "", code)
    code = code.rstrip(":").strip()
    # Strip a boolean-assignment LHS like `is_build_task_2_plus = (`.
    m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*\((.*)\)$", code)
    if m:
        code = m.group(1).strip()
    # Collapse internal runs of whitespace.
    code = re.sub(r"\s+", " ", code)
    return code


def _collect_behavioral_branches() -> set[str]:
    """Collect the normalized predicate text of every behavioral branch in source."""
    found: set[str] = set()
    for raw in _ENGINE.read_text(encoding="utf-8").splitlines():
        code = _strip_comment(raw)
        if not _BEHAVIORAL_RE.search(code):
            continue
        # Only consider actual condition/assignment lines (not bare references in
        # f-strings / log payloads, which the comment strip + the `==`/`in` token
        # plus an `if`/`elif`/assignment shape already largely exclude).
        stripped = code.strip()
        if not (
            stripped.startswith(("if ", "elif ", "while "))
            or re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*\(", stripped)
        ):
            continue
        found.add(_normalize_predicate(raw))
    return found


def test_behavioral_branches_match_allow_list_exactly() -> None:
    """The surviving pipeline_type/spec.id behavioral branches == the allow-list.

    Fails if a NEW behavioral routing branch was introduced (MAN-05 violation) or
    a Phase-7-scoped survivor was deleted/refactored.
    """
    found = _collect_behavioral_branches()

    unexpected = found - _ALLOWED_BEHAVIORAL_BRANCHES
    assert not unexpected, (
        "NEW / unrecognised behavioral pipeline_type or spec.id branch(es) found "
        f"in engine.py (MAN-05 violation): {sorted(unexpected)}"
    )

    missing = _ALLOWED_BEHAVIORAL_BRANCHES - found
    assert not missing, (
        "Phase-7-scoped survivor behavioral branch(es) missing from engine.py — "
        f"do NOT delete/refactor them in 1A: {sorted(missing)}"
    )


def test_routing_consumption_is_the_id_alias_resolver_only() -> None:
    """The only NON-behavioral pipeline_type consumption added this phase is the
    run-entry id-alias resolver (routing), not a behavioral branch.

    `resolve_alias(pipeline_type)` and `compile_for_run(pipeline_type)` are the
    routing seam: function calls that map the label to a manifest id and source
    the compiled plan. They are NOT behavioral branches (no `if pipeline_type`),
    so they do not appear in the allow-list above.
    """
    src = _ENGINE.read_text(encoding="utf-8")
    assert "resolve_alias(pipeline_type)" in src
    assert "compile_for_run(pipeline_type)" in src

    # The resolver call must NOT be a behavioral branch (it is routing).
    found = _collect_behavioral_branches()
    assert not any("resolve_alias" in p or "compile_for_run" in p for p in found)


def test_no_legacy_pipeline_type_dispatch_fallback() -> None:
    """No legacy pipeline_type dispatch fallback remains (INV-12).

    The engine must NOT source its agent list from a pipeline_type-keyed dispatch
    branch as a fallback to the compiled plan. The agent sequence comes from
    `compiled.steps`; the only `get_pipeline_agents` reference in the engine, if
    any, is the 1A drift-assertion comparison — never a dispatch fallback that
    selects which agents to run by pipeline_type.
    """
    src = _ENGINE.read_text(encoding="utf-8")
    # The compiled plan is the agent-sequence source.
    assert "compile_for_run(pipeline_type)" in src
    # The planner-skip + clarify-defaults sources are the compiled plan, not the
    # removed hardcoded dict / prototype-pipeline computation.
    assert 'compiled.planner == "skip"' in src
    assert "compiled.clarify.defaults" in src
    # The removed legacy routing SOURCES must be gone from executable code.
    assert "_pipeline_defaults" not in _executable_source(src)
    assert "SKIP_PLANNER_FOR_PROTOTYPE and is_prototype_pipeline" not in _executable_source(src)


def _executable_source(src: str) -> str:
    """Return source with `#`-comment lines removed (docstrings/comments may
    legitimately MENTION the removed legacy names in explanatory prose)."""
    lines = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(_strip_comment(line))
    return "\n".join(lines)
