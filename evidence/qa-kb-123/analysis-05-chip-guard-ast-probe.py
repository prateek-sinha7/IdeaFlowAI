"""QA-KB-123 analysis (3-analyzer, 2026-10-12): the offline guard for ISS-1194, as a runnable probe.

Run from the repo root:  backend/.venv/bin/python -I evidence/qa-kb-123/analysis-05-chip-guard-ast-probe.py

Rule: in every function under tests/integration/e2e/suites that calls the run-history chip locator `.chip(`,
a `pytest.skip(` call must appear BEFORE the first `.chip(` call (by line). A chip that is not rendered (count 0,
WorkflowHistory.tsx:1284) then ends in a skip with a reason instead of a 30 s locator timeout.

Why this shape: it is green for S-06-05 (test_run_history.py:157-164, `if expected == 0: pytest.skip(...)` then
`L.chip(...)`), red for the five functions that click first, and it stays green if the fixer routes all callers
through one shared helper (the callers then contain no `.chip(` call and the helper contains the skip before it).

Reads text only: no browser, no network, no database. Output beside it as .txt.
"""
import ast
import glob
from pathlib import Path

root = Path("tests/integration/e2e/suites")
OUT = []
red = []
green = []
for f in sorted(glob.glob(str(root / "**/*.py"), recursive=True)):
    if "/.venv/" in f:
        continue
    tree = ast.parse(Path(f).read_text(encoding="utf-8"))
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)]
        chips = [c.lineno for c in calls if c.func.attr == "chip"]
        if not chips:
            continue
        skips = [c.lineno for c in calls if c.func.attr == "skip"]
        first = min(chips)
        row = f"{Path(f).relative_to(root.parent)}:{fn.lineno} {fn.name} (first .chip( at line {first})"
        (green if any(s < first for s in skips) else red).append(row)

OUT.append(f"functions calling .chip( with a pytest.skip before it (GREEN): {len(green)}")
OUT += ["   " + r for r in green]
OUT.append(f"functions calling .chip( with NO pytest.skip before it (RED): {len(red)}")
OUT += ["   " + r for r in red]
print("\n".join(OUT))
Path(__file__).with_suffix(".txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
