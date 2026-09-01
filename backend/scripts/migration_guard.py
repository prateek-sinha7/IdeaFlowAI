"""Guard against retroactive edits to already-released Alembic revisions.

THE FAILURE MODE THIS EXISTS TO CATCH
-------------------------------------
Alembic records **only a revision ID** in the ``alembic_version`` table — never
a hash of what that revision contained. So when a database is stamped at head
``0037`` and a developer edits the body of revision ``0032``:

* ``alembic upgrade head`` reads ``0037``, concludes there is nothing to do, and
  exits 0. Revision ``0032`` is **never executed**. The edit does not reach that
  database, and no error is reported anywhere.
* A database created *after* the edit (a fresh dev box, a new environment, CI)
  runs the NEW ``0032`` and gets the new schema.

The two databases now disagree permanently, and nothing in Alembic, in
``alembic upgrade``, or in an ``alembic check`` against a fresh database can see
it — every one of those derives the schema by running the edited file, so they
all agree with each other and disagree only with production.

Note carefully that making the DDL idempotent does not help here. Idempotency
protects code that runs; this code never runs.

The project has already paid for this once: revision 0028 exists solely to
repair the 0024/0025 drift, and its docstring records that dropping the objects
in its ``downgrade`` would reintroduce the drift "because 0024/0025 are already
stamped and will never re-run".

HOW THE GUARD WORKS
-------------------
``alembic/versions.lock`` pins a fingerprint for every revision that has been
released. ``--verify`` recomputes the fingerprints and fails on any mismatch.

The fingerprint is taken over the revision's **executable logic**, not its bytes:
the source is parsed to an AST, docstrings are stripped, and the tree is
re-unparsed to canonical form before hashing. Reformatting, comment edits,
docstring improvements and line-ending changes therefore do NOT trip the guard —
only a change to what the migration actually does.

RELEASE BOUNDARY
----------------
A revision is "released" once it lands on ``dev``, because pushing to ``dev``
triggers ``deploy.yml``, which applies migrations on container start. From that
moment the revision is stamped in a real database and can never be re-run.
That is why the lock is updated on merge, not on deploy.

WHEN THE GUARD FIRES, THE FIX IS A FORWARD REVISION
---------------------------------------------------
Editing a released migration cannot repair a database that already ran it. The
correct response is a new revision at the tip that brings existing databases
into line — guarded with the helpers in ``migration_helpers.py`` so it no-ops on
databases that are already correct. Revision 0028 is the worked example.

USAGE
-----
    cd backend

    # CI / pre-merge: fail on retro-edits, duplicate IDs, or multiple heads
    uv run python scripts/migration_guard.py --verify

    # After ADDING a new revision: record its fingerprint
    uv run python scripts/migration_guard.py --update

    # Deliberately re-freeze an intentionally rewritten revision (rare; requires
    # a reason, which is recorded in the lock file for the next reviewer)
    uv run python scripts/migration_guard.py --update --allow-modified \
        --reason "0032 never deployed beyond a local branch"

Exit codes: 0 = clean, 1 = a guard failed, 2 = usage/environment error.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_VERSIONS_DIR = _BACKEND_DIR / "alembic" / "versions"
_LOCK_PATH = _BACKEND_DIR / "alembic" / "versions.lock"

_LOCK_FORMAT_VERSION = 1

# ``revision = "0032"`` / ``revision: str = '0032'`` — tolerant of both quote
# styles and of an annotated assignment, which script.py.mako may emit.
_REVISION_RE = re.compile(
    r"^revision(?:\s*:\s*str)?\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE
)


class GuardError(RuntimeError):
    """A guard condition failed. Message is operator-facing."""


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """Remove docstring expressions from every module/class/function scope.

    Docstrings are documentation, not behaviour. Excluding them means a
    reviewer can clarify a historical migration's docstring — often exactly what
    you want to do after an incident — without the guard treating it as a
    behavioural change and without needing an ``--allow-modified`` override.
    """
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            # A function whose only statement was a docstring still needs a body.
            node.body = body[1:] if len(body) > 1 else [ast.Pass()]
    return tree


def logic_fingerprint(source: str) -> str:
    """Return a sha256 over the canonicalised, docstring-free logic of ``source``.

    ``ast.unparse`` normalises formatting, quoting, whitespace, line endings and
    comments, so the digest reflects executable semantics only. A file that
    cannot be parsed is a hard error — an unparseable migration would crash the
    entrypoint anyway, so failing here is strictly earlier and cheaper.
    """
    tree = ast.parse(source)
    canonical = ast.unparse(_strip_docstrings(tree))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _revision_id(source: str, path: Path) -> str:
    match = _REVISION_RE.search(source)
    if not match:
        raise GuardError(
            f'{path.name}: no top-level `revision = "..."` assignment found. '
            "Every Alembic revision file must declare one."
        )
    return match.group(1)


def scan_versions() -> dict[str, dict[str, str]]:
    """Fingerprint every revision file, keyed by revision ID.

    Raises on duplicate revision IDs. That check matters independently: when two
    branches claim the same ID, Alembic keeps one file, silently drops the other
    from the graph, and the chain reports multiple heads — the exact collision
    this project hit twice (0031 -> re-homed to 0036, 0032 -> re-homed to 0037).
    """
    if not _VERSIONS_DIR.is_dir():
        raise GuardError(f"versions directory not found: {_VERSIONS_DIR}")

    found: dict[str, dict[str, str]] = {}
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        source = path.read_text(encoding="utf-8")
        rev = _revision_id(source, path)
        if rev in found:
            raise GuardError(
                f"duplicate revision ID {rev!r}: {found[rev]['file']} and "
                f"{path.name} both declare it. Alembic will silently drop one "
                "from the graph and report multiple heads. Re-home the newer "
                "one to the tip — the ID already recorded in deployed "
                "alembic_version rows keeps its number."
            )
        found[rev] = {"file": path.name, "logic_sha256": logic_fingerprint(source)}
    return found


# ---------------------------------------------------------------------------
# Lock file I/O
# ---------------------------------------------------------------------------


def load_lock() -> dict[str, dict[str, str]]:
    """Return the pinned revisions from the lock file, or an empty mapping."""
    if not _LOCK_PATH.exists():
        return {}
    data = json.loads(_LOCK_PATH.read_text(encoding="utf-8"))
    if data.get("lock_format_version") != _LOCK_FORMAT_VERSION:
        raise GuardError(
            f"{_LOCK_PATH.name}: unsupported lock_format_version "
            f"{data.get('lock_format_version')!r} (expected {_LOCK_FORMAT_VERSION})"
        )
    revisions = data.get("revisions", {})
    if not isinstance(revisions, dict):
        raise GuardError(f"{_LOCK_PATH.name}: 'revisions' must be an object")
    return revisions


def write_lock(revisions: dict[str, dict[str, str]], note: str | None) -> None:
    """Write the lock file, sorted by revision ID for a reviewable diff."""
    payload = {
        "lock_format_version": _LOCK_FORMAT_VERSION,
        "_comment": (
            "Fingerprints of released Alembic revisions. A mismatch means an "
            "already-applied migration was edited, which can never reach a "
            "database that is already stamped past it. Regenerate ONLY when "
            "adding a new revision: python scripts/migration_guard.py --update"
        ),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revisions": dict(sorted(revisions.items())),
    }
    if note:
        payload["last_override_reason"] = note
    _LOCK_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _format_drift(
    modified: list[tuple[str, dict[str, str]]], removed: list[str]
) -> str:
    lines: list[str] = []
    if modified:
        lines.append(
            "The following RELEASED migrations were modified. Alembic records only "
            "revision IDs, so these edits will NEVER be applied to any database "
            "already stamped at or past them:"
        )
        for rev, entry in modified:
            lines.append(f"    - {rev}  ({entry['file']})")
        lines.append("")
        lines.append(
            "Fix: revert the edit and add a NEW revision at the tip that brings "
            "existing databases into line, guarded with migration_helpers so it "
            "no-ops where already correct (revision 0028 is the worked example)."
        )
    if removed:
        if lines:
            lines.append("")
        lines.append(
            "The following released migrations have DISAPPEARED. Deleting a "
            "stamped revision breaks `alembic upgrade` on every database that "
            "recorded it ('Can't locate revision'):"
        )
        for rev in removed:
            lines.append(f"    - {rev}")
    return "\n".join(lines)


def cmd_verify() -> int:
    """Fail when a released revision was edited or removed, or IDs collide."""
    current = scan_versions()
    pinned = load_lock()

    if not pinned:
        print(
            "migration_guard: no lock file yet. Create the baseline with:\n"
            "    uv run python scripts/migration_guard.py --update",
            file=sys.stderr,
        )
        return 1

    modified = [
        (rev, entry)
        for rev, entry in sorted(current.items())
        if rev in pinned and entry["logic_sha256"] != pinned[rev]["logic_sha256"]
    ]
    removed = sorted(set(pinned) - set(current))
    added = sorted(set(current) - set(pinned))

    if modified or removed:
        print(_format_drift(modified, removed), file=sys.stderr)
        return 1

    if added:
        # New revisions are expected and fine — but the lock must be updated in
        # the same commit, or the next PR inherits an un-pinned migration and
        # the guard silently stops covering it.
        print(
            "migration_guard: new revisions are not pinned yet: "
            f"{', '.join(added)}\n"
            "Run `uv run python scripts/migration_guard.py --update` and commit "
            "alembic/versions.lock alongside the migration.",
            file=sys.stderr,
        )
        return 1

    print(f"migration_guard: OK — {len(current)} revisions match versions.lock")
    return 0


def cmd_update(allow_modified: bool, reason: str | None) -> int:
    """Re-pin fingerprints. Refuses to overwrite a changed release without a reason."""
    current = scan_versions()
    pinned = load_lock()

    modified = [
        rev
        for rev, entry in sorted(current.items())
        if rev in pinned and entry["logic_sha256"] != pinned[rev]["logic_sha256"]
    ]
    if modified and not allow_modified:
        print(
            "migration_guard: refusing to re-pin modified released revisions: "
            f"{', '.join(modified)}\n"
            "--update is for ADDING revisions. If a rewrite is genuinely correct "
            "(e.g. the revision never left a local branch), re-run with "
            '--allow-modified --reason "<why>".',
            file=sys.stderr,
        )
        return 1
    if modified and not reason:
        print(
            "migration_guard: --allow-modified requires --reason, so the next "
            "reviewer can see why a released migration was re-pinned.",
            file=sys.stderr,
        )
        return 2

    write_lock(current, reason if modified else None)
    added = sorted(set(current) - set(pinned))
    print(
        f"migration_guard: wrote {_LOCK_PATH.relative_to(_BACKEND_DIR)} "
        f"({len(current)} revisions"
        + (f", added {', '.join(added)}" if added else "")
        + (f", re-pinned {', '.join(modified)}" if modified else "")
        + ")"
    )
    return 0


def cmd_check_heads() -> int:
    """Assert the chain has exactly one head.

    Two heads make ``alembic upgrade head`` fail outright with "Multiple head
    revisions are present", which crash-loops the container because
    ``docker-entrypoint.sh`` runs it under ``set -eu``. This has happened twice.
    Imported lazily so ``--verify`` stays usable without app config loaded.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    # A dummy URL keeps env.py off settings.DATABASE_URL: reading the script
    # directory needs no database, and requiring one would make this unusable
    # as a pre-merge check.
    cfg.set_main_option("sqlalchemy.url", "sqlite://")

    heads = list(ScriptDirectory.from_config(cfg).get_heads())
    if len(heads) != 1:
        print(
            f"migration_guard: expected exactly ONE head, found {len(heads)}: "
            f"{heads}\n"
            "`alembic upgrade head` fails with 'Multiple head revisions are "
            "present', and the backend entrypoint runs it under `set -eu`, so "
            "the container will crash-loop. Re-home the newer revision onto the "
            "other head, or add a merge revision.",
            file=sys.stderr,
        )
        return 1
    print(f"migration_guard: OK — single head {heads[0]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migration_guard",
        description="Detect retroactive edits to released Alembic revisions.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--verify",
        action="store_true",
        help="fail if a released revision was edited/removed or IDs collide",
    )
    group.add_argument(
        "--update", action="store_true", help="re-pin fingerprints into versions.lock"
    )
    group.add_argument(
        "--check-heads", action="store_true", help="assert exactly one alembic head"
    )
    parser.add_argument(
        "--allow-modified",
        action="store_true",
        help="with --update: permit re-pinning an already-released revision",
    )
    parser.add_argument(
        "--reason", help="with --allow-modified: why the rewrite is safe"
    )
    args = parser.parse_args(argv)

    try:
        if args.verify:
            return cmd_verify() or cmd_check_heads()
        if args.update:
            return cmd_update(args.allow_modified, args.reason)
        return cmd_check_heads()
    except GuardError as exc:
        print(f"migration_guard: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
