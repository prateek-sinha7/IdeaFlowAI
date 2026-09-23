#!/usr/bin/env python3
"""Enumerate every interaction surface in the frontend, from source.

_enumerate.py lists pages, screens and `fixed inset-0` overlays. That net was too
coarse: it counted an inline rail panel as an overlay (C12) and the same component
twice (C6/C20), and it caught no dropdown, no toast, no keyboard shortcut and no
navigation edge at all.

This lists what that missed, so a gap is something we decided not to capture rather
than something we never knew about:

    python3 tests/integration/capture/_gaps.py            # summary
    python3 tests/integration/capture/_gaps.py --full     # every hit with its file

Categories:
  overlays     portals, role=dialog, aria-modal, fixed-inset layers
  dropdowns    menus/poppers that are NOT full-screen layers
  toasts       transient notifications
  navigation   every router.push/replace, <Link href>, window.open, location=
  shortcuts    global key handlers
  native       window.confirm / alert / prompt — browser dialogs a test must handle
  uploads      file inputs and drop zones
  branches     empty / error / loading render branches
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "frontend" / "src"
FULL = "--full" in sys.argv

PATTERNS = {
    "overlays": [
        (r'createPortal', "React portal"),
        (r'role="dialog"', 'role="dialog"'),
        (r'aria-modal', "aria-modal"),
        (r'fixed\s+inset-0', "fixed inset-0"),
    ],
    "dropdowns": [
        (r'role="menu"', 'role="menu"'),
        (r'role="listbox"', 'role="listbox"'),
        (r'aria-haspopup', "aria-haspopup"),
        (r'aria-expanded', "aria-expanded"),
    ],
    "toasts": [
        (r'\btoast\b', "toast"),
        (r'setToast|showToast|Toast\(', "toast state"),
    ],
    "navigation": [
        (r'router\.push\(', "router.push"),
        (r'router\.replace\(', "router.replace"),
        (r'router\.back\(', "router.back"),
        (r'<Link\s', "<Link>"),
        (r'window\.open\(', "window.open"),
        (r'window\.location\s*=|location\.href\s*=', "location assignment"),
    ],
    "shortcuts": [
        (r'addEventListener\(\s*["\']key(down|up|press)', "global key listener"),
        (r'onKeyDown|onKeyUp|onKeyPress', "key handler prop"),
        (r'\.key\s*===\s*["\']', "key comparison"),
        (r'metaKey|ctrlKey|shiftKey|altKey', "modifier key"),
    ],
    "native": [
        (r'window\.confirm\(|[^.]\bconfirm\(', "window.confirm"),
        (r'window\.alert\(|[^.]\balert\(', "window.alert"),
        (r'window\.prompt\(', "window.prompt"),
    ],
    "uploads": [
        (r'type="file"', 'input type=file'),
        (r'onDrop|onDragOver|dataTransfer', "drop zone"),
        (r'navigator\.clipboard', "clipboard"),
    ],
    "branches": [
        (r'No .{2,40} (found|yet)|Nothing here|is empty|No runs|No files', "empty state"),
        (r'Failed to|Couldn.t load|Something went wrong|error', "error state"),
        (r'isLoading|Loading|Skeleton|animate-pulse', "loading state"),
    ],
}

SKIP = re.compile(r"\.test\.|\.spec\.|__tests__|/node_modules/")

hits = defaultdict(lambda: defaultdict(list))
for f in sorted(SRC.rglob("*.ts*")):
    rel = str(f.relative_to(SRC))
    if SKIP.search(str(f)):
        continue
    try:
        lines = f.read_text().splitlines()
    except Exception:
        continue
    for cat, pats in PATTERNS.items():
        for pat, label in pats:
            for i, line in enumerate(lines, 1):
                if re.search(pat, line):
                    hits[cat][label].append((rel, i, line.strip()[:110]))

print(f"source: {SRC}")
print()
for cat, labels in hits.items():
    total = sum(len(v) for v in labels.values())
    files = {h[0] for v in labels.values() for h in v}
    print(f"── {cat}  ({total} hits across {len(files)} files)")
    for label, occ in sorted(labels.items(), key=lambda kv: -len(kv[1])):
        occ_files = sorted({o[0] for o in occ})
        print(f"   {label:22} {len(occ):4}  in {len(occ_files)} files")
        if FULL:
            for rel, i, text in occ:
                print(f"        {rel}:{i}  {text}")
        else:
            for rel in occ_files[:6]:
                print(f"        {rel}")
            if len(occ_files) > 6:
                print(f"        … {len(occ_files) - 6} more")
    print()
