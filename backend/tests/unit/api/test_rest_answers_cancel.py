"""Status-set source guards (INV-12) — one definition, imported, never copied.

Two AST scans of ``backend/{agents,app,scripts}`` asserting that the NON-terminal and
TERMINAL run-status sets are each defined EXACTLY ONCE, in
``agents/execution_engine/engine.py``. Both sets had a history of being copy-pasted:
the non-terminal tuple was duplicated into a second module and cited by five different
``file:line`` values in one week, every one wrong within days; the terminal set was
independently spelled out in at least three places before API-001 (task.md R-05).

Pure static analysis — no store, no HTTP, no fixtures, so these need nothing but the
repository on disk. They previously shared a file with the answers/cancel ENDPOINT
tests, whose ISS-089 durability assertions need a real store; those now live in
``tests/integration/api/test_rest_answers_cancel_api.py``.

NOTE the scanner resolves ``backend/`` via ``Path(__file__).parents[3]``, so this file
must stay exactly three directories below it (``tests/unit/api/``).
"""

from __future__ import annotations


def test_the_non_terminal_status_set_has_exactly_one_definition():
    """Source guard (INV-12). This tuple was copied into a second module and cited by five
    different ``file:line`` values in one week, every one of them wrong within days. One
    definition, imported — a copy is how the drift keeps happening."""
    import ast
    import pathlib

    from agents.execution_engine.engine import NON_TERMINAL_RUN_STATUSES

    expected = {
        "running",
        "planning",
        "clarifying",
        "waiting_for_user",
        "generating",
        "analyzing",
        "revising",
    }
    assert set(NON_TERMINAL_RUN_STATUSES) == expected

    backend = pathlib.Path(__file__).resolve().parents[3]
    definitions: list[str] = []
    for package in ("agents", "app", "scripts"):
        for path in sorted((backend / package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                value = getattr(node, "value", None)
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                    continue
                items = value.elts
                if not items or not all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str)
                    for e in items
                ):
                    continue
                if {e.value for e in items} == expected:
                    # `.as_posix()` — a relative path's default str() uses `\`
                    # separators on Windows, which never matches the forward-slash
                    # module-path assertion below (a portability gap, not a real
                    # multiple-definition finding).
                    rel = path.relative_to(backend).as_posix()
                    definitions.append(f"{rel}:{node.lineno}")

    assert (
        len(definitions) == 1
    ), f"the non-terminal status set is defined {len(definitions)} times: {definitions}"
    assert definitions[0].startswith("agents/execution_engine/engine.py:"), definitions


def _find_literal_set_definitions(expected: set[str]) -> list[str]:
    """AST-scan ``backend/{agents,app,scripts}`` for a top-level assignment whose
    literal tuple/list/set of string constants equals ``expected`` exactly.
    Shared by both status-set source guards below (INV-12 — one scanner, not two)."""
    import ast
    import pathlib

    backend = pathlib.Path(__file__).resolve().parents[3]
    definitions: list[str] = []
    for package in ("agents", "app", "scripts"):
        for path in sorted((backend / package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                value = getattr(node, "value", None)
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                    continue
                items = value.elts
                if not items or not all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str)
                    for e in items
                ):
                    continue
                if {e.value for e in items} == expected:
                    rel = path.relative_to(backend).as_posix()
                    definitions.append(f"{rel}:{node.lineno}")
    return definitions


def test_the_terminal_status_set_has_exactly_one_definition():
    """API-001 (task.md R-05) source guard (INV-12) — the terminal-set counterpart
    of ``test_the_non_terminal_status_set_has_exactly_one_definition`` above.

    Before API-001, "terminal" was independently spelled out as the SAME
    ``{"cancelled", "failed", "degraded"}``/``{"completed","degraded","failed",
    "cancelled"}`` literal in at least THREE places (``_review_gate_run_is_terminal``,
    the ``/resume`` endpoint's inverse resumable-set, and ``chat_router.py``'s
    ``TERMINAL_STATUSES``) — none of which the ORIGINAL guard above could catch,
    because it only scans for a copy of the NON-terminal set's specific 7 values.
    This is the missing counterpart: it fails loudly if this 4-value set is ever
    copy-pasted again instead of imported from ``TERMINAL_RUN_STATUSES``.
    """
    from agents.execution_engine.engine import TERMINAL_RUN_STATUSES

    expected = {"completed", "cancelled", "failed", "degraded", "diverted"}
    assert set(TERMINAL_RUN_STATUSES) == expected

    definitions = _find_literal_set_definitions(expected)

    assert (
        len(definitions) == 1
    ), f"the terminal status set is defined {len(definitions)} times: {definitions}"
    assert definitions[0].startswith("agents/execution_engine/engine.py:"), definitions
