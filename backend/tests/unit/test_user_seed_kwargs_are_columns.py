"""ISS-904 - no test may seed a User with a column the Cognito-only model dropped.

Pure AST scan (no I/O). Red while test_iss401_reset_password_message.py still
builds User(auth_provider=..., password_hash=...); green once it is retired.
"""

import ast
import pathlib

import pytest

from app.models.user import User

TESTS_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.issue("ISS-904")
def test_user_seeds_only_use_real_columns():
    cols = {c.key for c in User.__table__.columns} | {
        a.key for a in User.__mapper__.attrs
    }
    bad = []
    for path in TESTS_ROOT.rglob("*.py"):
        if path == pathlib.Path(__file__).resolve():
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "User"
            ):
                for kw in node.keywords:
                    if kw.arg and kw.arg not in cols:
                        bad.append(
                            f"{path.relative_to(TESTS_ROOT)}:{node.lineno} {kw.arg}"
                        )
    assert not bad, f"User(...) seeded with non-column kwargs: {bad}"
