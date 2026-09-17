"""T8 — the Cognito client boundary, and the audit trail that depends on it.

``core/cognito_admin.py`` owns every Cognito Admin* SEQUENCE. That is not
layering for its own sake: the ordering invariants (revoke-before-mutate,
disable-before-delete, idempotent ``UserNotFoundException``) and the audit event
for each mutation live there and ONLY there. A module that reaches past it to the
boto3 client gets none of them, silently — the operation still succeeds, so no
functional test notices, and the only evidence is a missing audit row nobody is
looking for.

Three things are pinned here, because they fail independently:

1. Nothing outside the allowed foundational modules touches the Cognito client.
2. Every state-mutating public function in ``cognito_admin`` emits an audit event.
3. ``api/admin.py`` imports no raw provider SDK at all — it must speak the
   lifecycle layer's typed errors, not botocore's.

WHY AST AND NOT LINE REGEX
--------------------------
The previous version matched three regexes against raw lines. It missed
``import app.core.cognito``, ``from app.core import cognito as c``, and any
``from app.core.cognito import (`` spanning two lines — all of which are the same
violation. It also wrapped every file read in ``except Exception: pass``, so an
unparseable module became exempt without a word. Parsing the import graph instead
makes the check exhaustive over import FORMS rather than over spellings someone
thought to enumerate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_APP_DIR = _BACKEND_DIR / "app"

#: The module that wraps boto3. Importing it means talking to Cognito directly.
_CLIENT_MODULE = "app.core.cognito"

#: Foundational modules permitted to hold the client directly, each with the
#: reason it cannot go through the lifecycle layer.
_ALLOWED: dict[str, str] = {
    "app/core/cognito.py": "the adapter itself — this IS the boto3 wrapper",
    "app/core/cognito_admin.py": "the lifecycle layer that orchestrates the adapter",
    "app/core/provisioning.py": "JIT provisioning runs on the token path, before any admin sequence exists",
    "app/core/identity.py": "credential resolution / token verification — no user lifecycle involved",
    "app/api/auth.py": "self-service token + MFA endpoints act on the CALLER's access token, which the Admin* layer has no concept of",
    # Named individually rather than exempting app/scripts/** wholesale: a
    # directory wildcard would hand a free pass to any future file dropped there,
    # including one that turns out to be request-path logic.
    "app/scripts/reconcile_cognito_users.py": "out-of-band operator tool; reconciles pool state against the DB with no route layer or request in play",
    "app/scripts/retry_cognito_deletions.py": "out-of-band operator tool; drains the deferred AdminDeleteUser queue that delete_user already audited",
}

#: Public functions that change state and must therefore be auditable.
_MUTATING_PUBLIC_FUNCTIONS = {
    "invite_user",
    "change_tier",
    "change_role",
    "disable_user",
    "enable_user",
    "reset_password",
    "delete_user",
}

#: Public functions deliberately WITHOUT an audit event, and why. Kept explicit
#: so "no event" is a recorded decision rather than an oversight nobody notices.
_NON_MUTATING_PUBLIC_FUNCTIONS: dict[str, str] = {
    "is_last_admin": "pure read predicate — changes nothing, so there is nothing to audit",
    "generate_temporary_password": "pure generator; auditing it would put logging next to a credential",
    "try_delete_pool_user": "deferred-retry half of delete_user, which already emitted USER_DELETED — a second event would double-count",
}


def _iter_app_modules():
    """Yield ``(relpath, ast.Module)`` for every application source file."""
    for path in sorted(_APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relpath = path.relative_to(_BACKEND_DIR).as_posix()
        # A read or parse failure is a hard error. The previous version swallowed
        # both, which quietly exempted the file from the boundary check.
        source = path.read_text(encoding="utf-8", errors="strict")
        try:
            yield relpath, ast.parse(source)
        except SyntaxError as exc:
            pytest.fail(f"{relpath}: could not parse ({exc})")


def _imported_modules(tree: ast.Module) -> set[str]:
    """Every module this file imports, as dotted names, across all import forms.

    Covers ``import a.b``, ``import a.b as c``, ``from a.b import x`` and
    ``from a import b`` — the last one being how ``cognito`` is usually pulled in
    and the one a naive ``from X import`` regex gets wrong.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — not how this codebase refers to app.*
                continue
            module = node.module or ""
            found.add(module)
            for alias in node.names:
                # `from app.core import cognito` -> app.core.cognito
                found.add(f"{module}.{alias.name}")
    return found


def _creates_cognito_boto_client(tree: ast.Module) -> bool:
    """True if this file calls ``boto3.client("cognito-idp")`` itself."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "client"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value == "cognito-idp":
                return True
    return False


def test_cognito_client_is_confined_to_the_lifecycle_layer():
    """No module outside the allow-list may import the adapter or build a client."""
    violations: list[str] = []

    for relpath, tree in _iter_app_modules():
        if relpath in _ALLOWED:
            continue

        if _CLIENT_MODULE in _imported_modules(tree):
            violations.append(f"{relpath}: imports {_CLIENT_MODULE}")
        if _creates_cognito_boto_client(tree):
            violations.append(f'{relpath}: calls boto3.client("cognito-idp")')

    assert not violations, (
        "Direct Cognito client access outside the lifecycle layer:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n\nThese bypass cognito_admin's ordering invariants AND its audit "
        "events. Route through app.core.cognito_admin, or add the module to "
        "_ALLOWED with the reason it cannot.\n\nCurrently allowed:\n"
        + "\n".join(f"  {k}  # {v}" for k, v in sorted(_ALLOWED.items()))
    )


def test_admin_api_imports_no_raw_provider_sdk():
    """``api/admin.py`` must speak typed lifecycle errors, not botocore's.

    It previously imported ``botocore.exceptions.ClientError`` to catch a raw
    error leaking out of ``is_last_admin``. That coupling is what made the leak
    invisible: the route layer looked like it handled the failure, while a
    ``ClientError`` from any OTHER call in the same block would fall through
    ``_raise_for`` untranslated and surface as a 500.
    """
    tree = ast.parse(
        (_APP_DIR / "api" / "admin.py").read_text(encoding="utf-8", errors="strict")
    )
    imported = _imported_modules(tree)
    leaked = sorted(
        m for m in imported if m.split(".")[0] in {"boto3", "botocore"}
    )

    assert not leaked, (
        "app/api/admin.py imports the raw AWS SDK: "
        + ", ".join(leaked)
        + ".\nCatch cognito_admin's ProviderUnavailableError instead — the "
        "lifecycle layer's job is to translate provider failures so the route "
        "layer only chooses a status code."
    )


def test_every_mutating_cognito_admin_function_emits_an_audit_event():
    """Each state-changing public function must contain an ``auth_events.emit`` call.

    Structural rather than behavioural on purpose: the behavioural tests in
    ``tests/unit/test_cognito_admin_lifecycle.py`` cover what each function does,
    but a mutation that silently stops auditing still passes all of them. The
    audit row is the only durable record of who changed whose privileges, so its
    ABSENCE needs its own failing test.
    """
    tree = ast.parse(
        (_APP_DIR / "core" / "cognito_admin.py").read_text(
            encoding="utf-8", errors="strict"
        )
    )

    emits: dict[str, bool] = {}
    public_functions: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        public_functions.add(node.name)
        emits[node.name] = any(
            isinstance(sub, ast.Attribute) and sub.attr == "emit"
            for sub in ast.walk(node)
        )

    missing = sorted(
        name for name in _MUTATING_PUBLIC_FUNCTIONS if not emits.get(name)
    )
    assert not missing, (
        "These state-mutating public functions emit no audit event: "
        + ", ".join(missing)
        + ".\nEvery privilege or lifecycle change must leave an auth_events "
        "record — it is the only trace of who did what to whom."
    )

    # The two lists together must account for every public function, so a NEW
    # public function cannot be added without deciding which side it is on.
    classified = _MUTATING_PUBLIC_FUNCTIONS | set(_NON_MUTATING_PUBLIC_FUNCTIONS)
    unclassified = sorted(public_functions - classified)
    assert not unclassified, (
        "New public function(s) in cognito_admin.py are unclassified: "
        + ", ".join(unclassified)
        + ".\nAdd each to _MUTATING_PUBLIC_FUNCTIONS (and emit an audit event) "
        "or to _NON_MUTATING_PUBLIC_FUNCTIONS with the reason it needs none."
    )

    # And a function declared non-mutating must not quietly start auditing —
    # that would mean it began changing state and the classification went stale.
    surprising = sorted(
        name for name in _NON_MUTATING_PUBLIC_FUNCTIONS if emits.get(name)
    )
    assert not surprising, (
        "Declared non-mutating, but now emits an audit event: "
        + ", ".join(surprising)
        + ".\nIf it changed state, move it to _MUTATING_PUBLIC_FUNCTIONS."
    )
