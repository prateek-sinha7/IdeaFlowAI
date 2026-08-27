#!/usr/bin/env python3
"""Extract the backend API contract from source, and check it against the specs.

The UI specs assert what a user sees. This asserts the shape underneath: if an
endpoint's method, path, auth requirement or response model changes, the diff of
this tool's output says so.

    python3 tests/integration/capture/_api.py            # inventory + coverage
    python3 tests/integration/capture/_api.py --json     # machine-readable
    python3 tests/integration/capture/_api.py --missing  # only what no spec names

An endpoint counts as covered when its FULL path (with `{param}` normalised) appears
in a spec — not merely a shared path segment like `users`, which is the weak check
that made the API look covered when it was not.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BE = ROOT / "backend" / "app"
DOCS = ROOT / "tests" / "integration"

# Decorator + handler name only. The signature is read separately by balancing
# parens: `([^)]*)` stops at the first `)`, which `Depends(get_db)` supplies on
# line one — that truncation reported 30 endpoints as public when they are not.
ROUTE = re.compile(
    r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']((?:[^()]|\([^()]*\))*)\)'
    r'(?:\s*\n\s*@[^\n]*)*'
    r'\s*\n(?:async\s+)?def\s+(\w+)\s*\(',
    re.M,
)


def signature_at(text, open_paren_idx):
    """Return the full parameter list starting at the handler's `(`."""
    depth, i = 0, open_paren_idx
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1:i]
        i += 1
    return ""
PREFIX = re.compile(r'APIRouter\(\s*(?:[^)]*?)prefix\s*=\s*["\']([^"\']+)')
INCLUDE = re.compile(r'include_router\(\s*([\w.]+)[^)]*?prefix\s*=\s*["\']([^"\']+)')

# Router variable -> mount prefix, from main.py
mounts = {}
main = BE / "main.py"
if main.exists():
    for m in INCLUDE.finditer(main.read_text()):
        mounts[m.group(1).split(".")[-1]] = m.group(2)


def auth_of(sig):
    """Classify an endpoint's auth requirement from its dependency signature.

    Match on the substring `get_current_user`, NOT on an exact name: the codebase
    uses get_current_user, get_current_user_with_payload and get_current_active_user
    interchangeably. An earlier version matched exact names and reported
    /api/auth/change-password and every MFA endpoint as PUBLIC — a mislabelled auth
    requirement in a contract spec is worse than no spec at all.
    """
    if re.search(r"get_current_admin|require_admin|admin_user", sig):
        return "admin"
    if re.search(r"get_current_user|current_user|get_current_active", sig):
        return "user"
    return "public"


endpoints = []
for f in sorted(BE.rglob("*.py")):
    if "test" in f.name:
        continue
    text = f.read_text()
    pm = PREFIX.search(text)
    own = pm.group(1) if pm else ""
    stem = f.stem
    mount = mounts.get(stem, "")
    for m in ROUTE.finditer(text):
        method, path, opts, fn = m.groups()
        sig = signature_at(text, m.end() - 1)
        full = (mount + own + path) or "/"
        full = re.sub(r"//+", "/", full)
        status = re.search(r"status_code\s*=\s*(?:status\.)?(\w+)", opts)
        model = re.search(r"response_model\s*=\s*([\w\[\]| .]+?)\s*(?:,|$)", opts)
        endpoints.append({
            "method": method.upper(),
            "path": full,
            "handler": fn,
            "file": str(f.relative_to(ROOT)),
            "auth": auth_of(sig),
            "status_code": status.group(1) if status else None,
            "response_model": model.group(1).strip() if model else None,
        })

endpoints.sort(key=lambda e: (e["path"], e["method"]))

if "--json" in sys.argv:
    print(json.dumps(endpoints, indent=2))
    sys.exit(0)

# Exclude the snapshot this tool itself writes. It lists every endpoint by full
# path, so including it makes the coverage check pass tautologically — 108/108
# proving only that the generator ran. Coverage must mean "a SPEC names it".
corpus = "\n".join(
    f.read_text()
    for f in list(DOCS.rglob("*.md")) + list(DOCS.rglob("*.json"))
    if f.name != "API-CONTRACT.json"
)


def covered(ep):
    p = re.sub(r"\{[^}]+\}", "{}", ep["path"])
    variants = {ep["path"], p, p.replace("{}", "{id}")}
    return any(v in corpus for v in variants)


missing = [e for e in endpoints if not covered(e)]

if "--missing" in sys.argv:
    for e in missing:
        print(f"{e['method']:6} {e['path']}")
    sys.exit(1 if missing else 0)

by_auth = {}
for e in endpoints:
    by_auth[e["auth"]] = by_auth.get(e["auth"], 0) + 1

print(f"endpoints: {len(endpoints)}")
for a in ("public", "user", "admin"):
    print(f"  {a:7} {by_auth.get(a, 0)}")
print(f"\nnamed in a spec by FULL path: {len(endpoints) - len(missing)} / {len(endpoints)}")
if missing:
    print(f"\n── {len(missing)} not named")
    for e in missing:
        print(f"   {e['method']:6} {e['path']:52} {e['auth']:6} {e['file']}")
sys.exit(1 if missing else 0)
