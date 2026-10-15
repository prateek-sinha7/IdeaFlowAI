"""QA-KB-122 analysis (3-analyzer, 2026-10-09): the e2e catalog title lists vs the manifests.

Run from the repo root:  backend/.venv/bin/python -I evidence/qa-kb-122/analysis-04-catalog-title-drift.py

home_catalog.py says LAUNCHABLE_TITLES is "Derived from `user_launchable: true AND is_beta: false` in the
workflow manifests" and COMING_SOON_TITLES is `user_launchable: true` but `is_beta: true`. This re-derives both
sets from backend/agents/workflows/*/workflow.yaml (display_name, user_launchable, is_beta) and diffs them with
the literals. Pure file reads, no network, no database.
"""
import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def lits(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise SystemExit(f"{name} not found in {path}")


loc = ROOT / "tests/integration/e2e/framework/locators/home_catalog.py"
pinned_launchable = lits(loc, "LAUNCHABLE_TITLES")
pinned_soon = lits(loc, "COMING_SOON_TITLES")

launchable, soon, hidden = {}, {}, {}
for wf in sorted((ROOT / "backend/agents/workflows").glob("*/workflow.yaml")):
    m = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
    name = m.get("display_name") or m.get("name") or wf.parent.name
    ul, beta = bool(m.get("user_launchable", False)), bool(m.get("is_beta", False))
    if ul and not beta:
        launchable[name] = wf.parent.name
    elif ul and beta:
        soon[name] = wf.parent.name
    else:
        hidden[name] = wf.parent.name

say(f"manifests: {len(launchable)} launchable, {len(soon)} coming-soon (beta), {len(hidden)} not user-launchable")
say()
say("LAUNCHABLE_TITLES pinned in home_catalog.py but NOT a launchable manifest label today:")
for t in pinned_launchable:
    if t not in launchable:
        near = [n for n in launchable if n.split(" (")[0] == t.split(" (")[0]]
        say(f"   {t!r}   (same stem now served as: {near})")
say()
say("launchable manifest labels NOT in LAUNCHABLE_TITLES (the list claims to be 'the full launchable set'):")
for n, wid in launchable.items():
    if n not in pinned_launchable:
        say(f"   {n!r}  [{wid}]")
say()
say("COMING_SOON_TITLES pinned but not a beta+launchable manifest label today:")
for t in pinned_soon:
    if t not in soon:
        say(f"   {t!r}  -> in launchable: {t in launchable}; hidden: {t in hidden}")
Path(__file__).with_suffix(".txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
