"""T7 — the ``users.is_admin`` / ``users.tier`` columns must not drive decisions.

Cognito groups are the sole authority for role and tier. The DB columns are a
non-authoritative PROJECTION of them (Decision 3): a console-added admin, or a
tier change that landed in the pool but not the row, makes the column disagree
with what the pool will actually let the person do. Reading the column to decide
something is therefore an authorization bug that no functional test will catch,
because the column is usually right.

So this scans for reads and requires each one to be declared display-only.

WHY THIS IS AN AST SCAN AND NOT A REGEX OVER LINES
--------------------------------------------------
The previous version matched ``\\buser\\.(is_admin|tier)\\b`` line by line and
keyed its allow-list on ``path:line-number``. Three consequences, all of which
were live:

* ``\\buser\\.`` never matches ``current_user.is_admin`` -- ``_`` is a word
  character, so there is no boundary before ``user``. ``current_user`` is the
  name the entire API layer binds the caller to, so the highest-risk reads in
  the codebase were invisible to the guard.
* Line numbers drift. Editing anything ABOVE a hit silently invalidates its
  allow-list entry, and the test then fails pointing at approved code -- which
  trains people to re-pin the numbers rather than read the finding.
* Docstrings and comments matched, so prose describing the rule was recorded as
  a violation of it, and half the allow-list existed to excuse documentation.

Parsing instead fixes all three at once: ``ast`` cannot see inside a string, an
``ast.Store`` context distinguishes an ORM WRITE (``user.tier = new_tier`` --
keeping the projection in sync, which is required, not a violation) from a READ,
and keying on the enclosing function survives edits elsewhere in the file.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: The projected columns. Reading either to decide something is the bug.
_PROJECTION_ATTRS = {"is_admin", "tier"}

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_APP_DIR = _BACKEND_DIR / "app"
_ALLOWLIST_PATH = Path(__file__).parent / "projection_read_allowlist.txt"


def _is_user_binding(name: str) -> bool:
    """True for names that hold a ``User`` ORM row.

    Covers ``user`` and every ``*_user`` binding (``current_user``,
    ``target_user``, ``admin_user``). The old regex caught only the bare name and
    therefore missed ``current_user`` entirely.
    """
    return name == "user" or name.endswith("_user")


def _findings(source: str) -> list[tuple[str, str, int]]:
    """Every projection-column READ, as ``(enclosing_scope, attr, lineno)``.

    Writes are excluded deliberately: ``user.is_admin = is_admin`` in
    ``cognito_admin.change_role`` is the projection being UPDATED to match the
    pool. That is the mechanism that keeps the column honest, not a use of it.
    """
    tree = ast.parse(source)
    out: list[tuple[str, str, int]] = []

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, f"{scope}.{child.name}" if scope else child.name)
                continue
            if (
                isinstance(child, ast.Attribute)
                and child.attr in _PROJECTION_ATTRS
                and isinstance(child.ctx, ast.Load)
                and isinstance(child.value, ast.Name)
                and _is_user_binding(child.value.id)
            ):
                out.append((scope or "<module>", child.attr, child.lineno))
            visit(child, scope)

    visit(tree, "")
    return out


def _load_allowlist() -> dict[str, str]:
    """Parse ``path::scope::attr  # reason`` entries into signature -> reason.

    A reason is mandatory. An allow-list of bare signatures decays into a list of
    things nobody remembers approving, which is how the column ends up back in a
    decision path with a rubber stamp already attached.
    """
    if not _ALLOWLIST_PATH.exists():
        return {}

    entries: dict[str, str] = {}
    # utf-8-sig, not utf-8: this repo is edited on Windows, where several editors
    # and `Set-Content -Encoding utf8` prepend a BOM. Read as plain utf-8 the BOM
    # becomes part of the first signature and the file fails to parse with a
    # baffling message about an entry nobody can see.
    for raw in _ALLOWLIST_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        signature, _, reason = line.partition("#")
        signature = signature.strip()
        reason = reason.strip()
        if not signature:
            continue
        if not reason:
            pytest.fail(
                f"{_ALLOWLIST_PATH.name}: entry {signature!r} has no reason. "
                "Every exemption must say why the read is display-only."
            )
        entries[signature] = reason
    return entries


def test_no_projection_reads_in_decision_context():
    """Every ``user.is_admin`` / ``user.tier`` read must be declared display-only."""
    allowed = _load_allowlist()
    found: dict[str, tuple[str, int]] = {}

    for path in sorted(_APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relpath = path.relative_to(_BACKEND_DIR).as_posix()
        # Unreadable or unparseable application source is a hard failure, not a
        # silently skipped file. The previous version wrapped the whole read in
        # `except Exception: pass`, so a syntax error anywhere made that file
        # exempt from the guard without a word.
        source = path.read_text(encoding="utf-8", errors="strict")
        try:
            hits = _findings(source)
        except SyntaxError as exc:
            pytest.fail(f"{relpath}: could not parse ({exc})")

        for scope, attr, lineno in hits:
            found[f"{relpath}::{scope}::{attr}"] = (relpath, lineno)

    violations = sorted(set(found) - set(allowed))
    if violations:
        msg = [
            "Projection reads found in code that is not declared display-only.",
            "",
            "`users.is_admin` / `users.tier` are a non-authoritative projection of",
            "Cognito groups. Use effective_is_admin() / effective_tier() for any",
            "decision. If the read only shapes a response, add it below with a reason.",
            "",
        ]
        for signature in violations:
            relpath, lineno = found[signature]
            msg.append(f"  {signature}   ({relpath}:{lineno})")
        msg += [
            "",
            f"Allow-list format ({_ALLOWLIST_PATH.name}):",
            "  app/api/admin.py::_to_response::tier  # response field, not a decision",
        ]
        raise AssertionError("\n".join(msg))


def test_allowlist_has_no_stale_entries():
    """An exemption that no longer matches real code must be removed.

    Kept separate from the scan so the two failures stay legible: one says "new
    read needs review", this one says "this approval is dead". Left unchecked,
    stale entries accumulate and can silently pre-approve a future read that
    happens to land in the same function.
    """
    allowed = _load_allowlist()
    live: set[str] = set()

    for path in sorted(_APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relpath = path.relative_to(_BACKEND_DIR).as_posix()
        for scope, attr, _lineno in _findings(
            path.read_text(encoding="utf-8", errors="strict")
        ):
            live.add(f"{relpath}::{scope}::{attr}")

    stale = sorted(set(allowed) - live)
    assert not stale, (
        "These allow-list entries no longer match any projection read and should "
        "be deleted:\n" + "\n".join(f"  {s}" for s in stale)
    )
