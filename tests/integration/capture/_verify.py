#!/usr/bin/env python3
"""Consistency check across the integration-test docs.

Run after any capture sweep, before committing:

    python3 tests/integration/capture/_verify.py

Catches the four ways these docs rot:

  1. a Screenshots line pointing at a folder that no longer exists
     (this fired for real after sweep 3 renamed every shot)
  2. a defect id referenced in a spec but never defined in DEFECTS-OBSERVED.md
  3. a page listed in PAGES.md with no screenshot or no fingerprint
  4. a screenshot on disk that no document mentions

Exits non-zero if anything is wrong, so it can gate a commit.
"""
import re
import sys
from pathlib import Path

D = Path(__file__).resolve().parent.parent
SHOTS = D / "screenshots"

# Ids that look like this file's defect scheme but are not. Keep this list
# short and justified — it is an escape hatch, not a filing cabinet.
NOT_OUR_DEFECT_IDS = {
    "D-20",  # UXFIX-03 / D-20 is an external design-doc reference in 02-home-catalog
}

problems = []

# 1. Screenshot folders named in specs resolve.
for f in sorted((D / "screens").glob("*.feature.md")):
    m = re.search(r"^\*\*Screenshots:\*\*.*$", f.read_text(), re.M)
    if not m:
        problems.append(f"{f.name}: no Screenshots line")
        continue
    for folder in sorted(set(re.findall(r"`(\d\d-[a-z-]+)/", m.group(0)))):
        if not (SHOTS / folder).is_dir():
            problems.append(f"{f.name}: names missing folder {folder}")

# 2. Referenced defect ids are defined.
dtext = (D / "DEFECTS-OBSERVED.md").read_text()
defined = set(re.findall(r"^## (D-\d+)", dtext, re.M)) | set(re.findall(r"\| (C-\d+)", dtext))
referenced = set()
for f in list((D / "screens").glob("*.md")) + [D / "PAGES.md", D / "MANIFEST.md", D / "README.md"]:
    referenced |= set(re.findall(r"\b(D-\d+|C-\d+)\b", f.read_text()))
undefined = referenced - defined - NOT_OUR_DEFECT_IDS
if undefined:
    problems.append(f"referenced but not defined in DEFECTS-OBSERVED.md: {sorted(undefined)}")

# 3. Every page in PAGES.md has evidence.
pages = (D / "PAGES.md").read_text()
page_ids = sorted(set(re.findall(r"\| (p\d\d) \|", pages)))
FINGERPRINT_EXEMPT = {"p56"}  # a state of p34, recorded inside p34's fingerprint
for pid in page_ids:
    if not list(SHOTS.glob(f"*/{pid}-*.png")):
        problems.append(f"{pid}: listed in PAGES.md with no screenshot")
    if pid not in FINGERPRINT_EXEMPT and not list((D / "capture").glob(f"{pid}-*.json")):
        problems.append(f"{pid}: listed in PAGES.md with no fingerprint")

# 4. No orphan screenshots.
alldocs = "\n".join(f.read_text() for f in D.rglob("*.md"))
for png in sorted(SHOTS.rglob("*.png")):
    if png.stem.split("-")[0] not in alldocs and png.stem not in alldocs:
        problems.append(f"orphan screenshot, referenced by no doc: {png.relative_to(SHOTS)}")

print(f"pages listed:  {len(page_ids)}")
print(f"screenshots:   {len(list(SHOTS.rglob('*.png')))}")
print(f"fingerprints:  {len(list((D / 'capture').glob('*.json')))}")
print(f"defects:       {len(defined)} defined")
print()
if problems:
    print(f"PROBLEMS ({len(problems)}):")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("PROBLEMS: none")
