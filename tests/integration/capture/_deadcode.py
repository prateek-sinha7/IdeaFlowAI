#!/usr/bin/env python3
"""Which component files does no other source file import?

A file whose *exported symbols* are referenced nowhere is unmountable — no route can
reach it. This matters for the spec suite because such a file is not a coverage gap
to close, it is code to delete, and writing scenarios for it wastes phase-2 effort.

Match on every exported symbol, NOT on the filename. RevisionFamilyView.tsx exports
`FamilyGroupCard` and `VersionTimeline` and is very much alive; a filename-only check
calls it dead and is wrong. That mistake was made once during sweep 6 and caught
before it reached a spec — hence this tool.

    python3 tests/integration/capture/_deadcode.py
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "frontend" / "src"
IS_TEST = re.compile(r"\.test\.|\.spec\.|__tests__")

EXPORT = re.compile(
    r"^export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function|const|class|type|interface)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
EXPORT_LIST = re.compile(r"^export\s*\{([^}]*)\}", re.M)

COMMENT = re.compile(r"/\*[\s\S]*?\*/|//[^\n]*")


def strip_comments(t):
    """A name that appears only in a comment is not an import.

    Half this codebase's components are name-dropped in explanatory comments —
    AgentModelPicker is discussed in four files that do not use it, and one unit
    test exists purely to assert it is NOT mounted. Matching comments marks such a
    file live and hides real dead code.
    """
    return COMMENT.sub(" ", t)


files = [f for f in SRC.rglob("*.ts*") if not IS_TEST.search(str(f))]
tests = [f for f in SRC.rglob("*.ts*") if IS_TEST.search(str(f))]
src_text = {f: strip_comments(f.read_text()) for f in files}
raw_text = {f: f.read_text() for f in files}
test_text = "\n".join(f.read_text() for f in tests)


def exports(text):
    names = set(EXPORT.findall(text))
    for grp in EXPORT_LIST.findall(text):
        for part in grp.split(","):
            part = part.strip().split(" as ")[-1].strip()
            if part:
                names.add(part)
    return {n for n in names if n[:1].isupper()}


dead, live = [], 0
for f in files:
    if f.suffix != ".tsx" or f.stem in ("page", "layout", "route", "error", "not-found", "global-error"):
        continue
    names = exports(raw_text[f]) or {f.stem}
    used = False
    for g, t in src_text.items():
        if g == f:
            continue
        if any(re.search(rf"\b{re.escape(n)}\b", t) for n in names):
            used = True
            break
    if used:
        live += 1
        continue
    in_tests = any(re.search(rf"\b{re.escape(n)}\b", test_text) for n in names)
    dead.append((f.relative_to(SRC), len(raw_text[f].splitlines()), sorted(names)[:4], in_tests))

print(f"component files scanned: {live + len(dead)}")
print(f"imported by no other source file: {len(dead)}")
print()
for rel, loc, names, in_tests in sorted(dead, key=lambda x: -x[1]):
    flag = "has unit tests" if in_tests else "no tests either"
    print(f"  {loc:5} loc  {str(rel):52} exports {', '.join(names)}   [{flag}]")
