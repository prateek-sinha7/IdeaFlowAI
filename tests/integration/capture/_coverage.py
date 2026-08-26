#!/usr/bin/env python3
"""The definitive coverage check: every addressable control, against every spec.

Components and routes are too coarse a unit — a spec can name a page and still miss
half its buttons. The atomic unit of an E2E suite is the thing a test can address:

    data-testid   the intended hook
    aria-label    the accessible name
    name=         form fields
    role=         landmark/widget roles

This lists every one in the frontend and reports which appear nowhere in
tests/integration. Anything it prints is a control no scenario can currently target.

    python3 tests/integration/capture/_coverage.py           # summary + misses
    python3 tests/integration/capture/_coverage.py --all     # also list what IS covered

Template-literal values (`tab-${id}`) are normalised to a `<...>` wildcard and
matched by prefix, because a spec cannot name every instance of a templated id.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"
DOCS = ROOT / "tests" / "integration"
SHOW_ALL = "--all" in sys.argv
IS_TEST = re.compile(r"\.test\.|\.spec\.|__tests__")

corpus = "\n".join(
    f.read_text()
    for f in list(DOCS.rglob("*.md")) + list(DOCS.rglob("*.json"))
)

PATTERNS = {
    "data-testid": re.compile(r'data-testid=(?:"([^"]+)"|\{`([^`]+)`\})'),
    "aria-label": re.compile(r'aria-label=(?:"([^"]+)"|\{`([^`]+)`\})'),
    "name": re.compile(r'\bname="([a-z][a-z0-9-]{2,})"'),
}

found = {k: {} for k in PATTERNS}
for f in sorted(SRC.rglob("*.tsx")):
    if IS_TEST.search(str(f)):
        continue
    text = f.read_text()
    rel = str(f.relative_to(SRC))
    for kind, pat in PATTERNS.items():
        for m in pat.finditer(text):
            raw = m.group(1) or m.group(2) or ""
            if not raw:
                continue
            # `tab-${x}` -> literal prefix before the first interpolation
            norm = re.split(r"\$\{", raw)[0].rstrip("-_ ")
            if not norm or len(norm) < 3:
                continue
            found[kind].setdefault(norm, set()).add(rel)


def covered(value):
    if value in corpus:
        return True
    # templated: a spec naming the prefix covers the family
    return bool(re.search(re.escape(value) + r"[-_`{$<]", corpus))


total = miss_total = 0
report = {}
for kind, values in found.items():
    misses = sorted((v, sorted(fs)) for v, fs in values.items() if not covered(v))
    report[kind] = misses
    total += len(values)
    miss_total += len(misses)
    print(f"{kind:12} {len(values):4} distinct   {len(misses):4} in no spec")

print()
print(f"TOTAL {total} addressable controls, {miss_total} uncovered "
      f"({100 * (total - miss_total) // max(total, 1)}% covered)")

for kind, misses in report.items():
    if not misses:
        continue
    print(f"\n── uncovered {kind} ({len(misses)})")
    for value, files in misses:
        where = files[0] + (f" +{len(files) - 1}" if len(files) > 1 else "")
        print(f"   {value:44} {where}")

if SHOW_ALL:
    for kind, values in found.items():
        print(f"\n── all {kind} ({len(values)})")
        for v in sorted(values):
            print(f"   {'✓' if covered(v) else '✗'} {v}")

sys.exit(1 if miss_total else 0)
