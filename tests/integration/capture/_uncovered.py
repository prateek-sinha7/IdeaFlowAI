#!/usr/bin/env python3
"""Which frontend components are mentioned in NO spec and NO capture?

The blunt completeness check. A component named nowhere in tests/integration is one
nobody decided about — it is not a judgement that it needs coverage, only that its
absence was never deliberate.

    python3 tests/integration/capture/_uncovered.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"
DOCS = ROOT / "tests" / "integration"

SKIP = re.compile(r"\.test\.|\.spec\.|__tests__")

# Everything the specs, manifests and fingerprints say, as one blob.
corpus = []
for f in list(DOCS.rglob("*.md")) + list(DOCS.rglob("*.json")):
    try:
        corpus.append(f.read_text())
    except Exception:
        pass
corpus = "\n".join(corpus)

components, uncovered = [], []
for f in sorted(SRC.rglob("*.tsx")):
    if SKIP.search(str(f)):
        continue
    rel = f.relative_to(SRC)
    name = f.stem
    if name in ("page", "layout", "route"):
        # named by their route, not their filename
        name = str(rel.parent)
    components.append((str(rel), name))
    if name not in corpus and str(rel) not in corpus:
        uncovered.append((str(rel), name, len(f.read_text().splitlines())))

print(f"components scanned: {len(components)}")
print(f"mentioned nowhere in tests/integration: {len(uncovered)}")
print()
for rel, name, loc in sorted(uncovered, key=lambda x: -x[2]):
    print(f"  {loc:5} loc   {rel}")
