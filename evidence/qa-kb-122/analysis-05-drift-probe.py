"""QA-KB-122 analysis (3-analyzer, 2026-10-09): offline drift probe over the live e2e tier.

Run from the repo root:  backend/.venv/bin/python -I evidence/qa-kb-122/analysis-05-drift-probe.py

Pure file reads (ast + regex): no network, no database, no browser. Each section is one drift guard a
4-test-writer could turn into a unit test under backend/tests/unit/ (the pattern of
backend/tests/unit/services/test_entitlement_parity.py: parse the other tree as text). Every section is
RED today; the expected count after the fix is 0.
"""
import ast
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E2E = ROOT / "tests/integration/e2e"
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def rel(p):
    return str(Path(p).relative_to(ROOT))


# ---------------------------------------------------------------- G1: POST body keys vs CreateUserRequest
admin_tree = ast.parse((ROOT / "backend/app/api/admin.py").read_text(encoding="utf-8"))
fields = None
for node in admin_tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "CreateUserRequest":
        fields = {s.target.id for s in node.body if isinstance(s, ast.AnnAssign)}
say(f"G1  CreateUserRequest fields (backend/app/api/admin.py, extra=forbid): {sorted(fields)}")
bad = []
for f in (E2E / "conftest.py", E2E / "suites/24_api_contract/test_api_contract.py"):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for d in ast.walk(tree):
        if isinstance(d, ast.Dict):
            keys = {k.value for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if {"email", "tier", "is_admin"} <= keys:  # the create-user body
                extra = sorted(keys - fields)
                if extra:
                    bad.append((rel(f), d.lineno, extra))
for r in bad:
    say(f"      RED  {r[0]}:{r[1]} sends {r[2]} -> 422 extra_forbidden")
say(f"      sites: {len(bad)} (expected 0 after the fix)")
say()

# ---------------------------------------------------------------- G2: rail sub-tabs vs CanvasConfigRail.tsx
comp = ast.parse((E2E / "framework/locators/composer.py").read_text(encoding="utf-8"))
pinned = next(ast.literal_eval(n.value) for n in comp.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "AGENT_SUBTABS")
tsx = (ROOT / "frontend/src/components/workflow/composer/CanvasConfigRail.tsx").read_text(encoding="utf-8")
block = tsx[tsx.index('{ id: "overview"'): tsx.index('{ id: "config"') + 60]
live = re.findall(r'label:\s*"([^"]+)"', block)
say(f"G2  AGENT_SUBTABS pinned (composer.py:52): {pinned}")
say(f"      tabs rendered by CanvasConfigRail.tsx:     {live}")
say(f"      RED  pinned but not rendered: {sorted(set(pinned) - set(live))}; rendered but not pinned: {sorted(set(live) - set(pinned))}")
src = (E2E / "suites/04_composer_canvas/test_composer_canvas.py").read_text(encoding="utf-8").splitlines()
for i, ln in enumerate(src, 1):
    if "step 1 of" in ln and "re.compile" in ln:
        say(f"      RED  test_composer_canvas.py:{i}: {ln.strip()}   (caption is '<kind.label> · step n of m', kind.label='AI agent', stepKind.ts:20)")
say()

# ---------------------------------------------------------------- G4: strict xfail markers vs the ISS card status
say("G4  strict-xfail markers (suites/**) and the status of the ISS card each one cites")
XPASSED = {"ISS-796": "XPASS 04_composer_canvas.log:474", "ISS-923": "XPASS 05_saved_workflows.log:100", "ISS-1033": "XPASS 05_saved_workflows.log:102",
           "ISS-213": "XPASS 06_run_history.log:114", "ISS-190": "XPASS 12_shell_nav.log:184"}
rows = []
for f in sorted(glob.glob(str(E2E / "suites/**/*.py"), recursive=True)):
    for i, ln in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
        m = re.search(r'xfail\(reason="(ISS-\d+)[^"]*"[^)]*strict=True', ln)
        if m:
            card = glob.glob(str(ROOT / f".knowledge/cards/*-{m.group(1)}.md"))
            st = re.search(r"^status:\s*(\S+)", Path(card[0]).read_text(encoding="utf-8"), re.M).group(1) if card else "?"
            rows.append((m.group(1), st, rel(f), i))
for iss, st, f, i in rows:
    tag = XPASSED.get(iss, "still XFAIL in the 2026-10-09 run" if iss not in ("ISS-1157",) else "added later for QA-KB-116")
    say(f"      {iss:9s} card={st:11s} {f}:{i}   [{tag}]")
say(f"      markers: {len(rows)}; the five that XPASSed (strict -> failure): {sorted(XPASSED)}")
say()

# ---------------------------------------------------------------- G5: pinned UUID literals
say("G5  UUID literals pinned in tests/integration/e2e (the all-zero 404-probe id excluded)")
pat = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
n = 0
for f in sorted(glob.glob(str(E2E / "**/*.py"), recursive=True)):
    if "__pycache__" in f:
        continue
    for i, ln in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
        for u in pat.findall(ln):
            if u != "00000000-0000-0000-0000-000000000000" and not ln.lstrip().startswith(("#", '"""')) and "=" in ln.split(u)[0]:
                say(f"      RED  {rel(f)}:{i}  {ln.strip()[:100]}")
                n += 1
say(f"      assignments pinning an id: {n} (expected 0 after the fix)")
say()

# ---------------------------------------------------------------- G6: create-user dialog locators vs admin/page.tsx
page = (ROOT / "frontend/src/app/admin/page.tsx").read_text(encoding="utf-8").splitlines()
start = next(i for i, ln in enumerate(page) if "Create user modal" in ln)
end = next(i for i, ln in enumerate(page) if "Delete confirm modal" in ln)
modal = "\n".join(page[start:end])
say(f"G6  admin/page.tsx create modal (lines {start+1}-{end}): has type=\"password\" input: {'type=\"password\"' in modal}; submit label 'Send Invitation': {'Send Invitation' in modal}; 'Create User' button text: {bool(re.search(r'>\\s*Create User\\s*<', modal))}")
for f in sorted(glob.glob(str(E2E / "suites/11_admin/*.py"))):
    for i, ln in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
        if 'input[type="password"]' in ln and "fill" in ln or re.search(r'name="Create User"|name=re\.compile\(r"create"', ln) or "password_field = page.locator" in ln:
            say(f"      RED  {rel(f)}:{i}  {ln.strip()[:110]}")
Path(__file__).with_suffix(".txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
