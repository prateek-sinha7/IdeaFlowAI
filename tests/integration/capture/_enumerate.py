#!/usr/bin/env python3
"""Enumerate every UI surface from the frontend source, so the capture list is
derived rather than discovered. Prints four sections:

  ROUTES    - routes.ts builders + parseViewPath screens
  OVERLAYS  - modals, dialogs, drawers, popups, sheets (fixed-inset / role=dialog)
  TABS      - tab strips and their testids
  STATES    - empty / error / loading / skeleton branches

Run from the repo root.
"""
import os
import re
import subprocess

FE = "frontend/src"


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------- ROUTES
section("ROUTES — builders in routes.ts")
src = open(f"{FE}/lib/routes.ts", encoding="utf-8").read()
builders = re.findall(r"^\s{2}(\w+):\s*\(([^)]*)\)[^=]*=>", src, re.M)
for name, args in builders:
    print(f"  routes.{name}({args.strip()})")
print(f"  -- {len(builders)} builders")

screens = re.findall(r"\{\s*screen:\s*'([a-z-]+)'", src)
print(f"\n  ParsedView screens ({len(set(screens))}): {', '.join(sorted(set(screens)))}")


# -------------------------------------------------------------- OVERLAYS
section("OVERLAYS — modal / dialog / drawer / popup components")
# Components whose name says overlay, or that render a fixed full-screen layer.
names = sh(
    f"grep -rlE 'fixed inset-0|role=\"dialog\"' {FE} --include=*.tsx | sort"
).split()
for f in names:
    base = os.path.basename(f)
    hits = sh(f"grep -cE 'fixed inset-0|role=\"dialog\"' '{f}'").strip()
    # what opens it: look for a state flag
    flags = set(re.findall(r"(?:const|,)\s*\[?(show[A-Z]\w+|is[A-Z]\w*Open|\w*Modal\w*)\b",
                           open(f, encoding="utf-8").read()))
    flags = sorted(x for x in flags if len(x) < 32)[:5]
    print(f"  {f.replace(FE + '/', ''):<62} layers={hits:<3} {', '.join(flags)}")
print(f"  -- {len(names)} files render an overlay layer")


# ------------------------------------------------------------------ TABS
section("TABS — tab strips and their testids")
out = sh(f"grep -rhoE 'data-testid=\"tab-[a-z0-9-]+\"' {FE} --include=*.tsx | sort -u")
ids = [x.split('"')[1] for x in out.split()]
print(f"  testids ({len(ids)}): {', '.join(ids)}")
files = sh(f"grep -rlE 'role=\"tab\"' {FE} --include=*.tsx | sort").split()
print(f"\n  files with role=tab ({len(files)}):")
for f in files:
    print(f"    {f.replace(FE + '/', '')}")


# ---------------------------------------------------------------- STATES
section("STATES — empty / error / loading branches")
for label, pat in [
    ("empty",    r"No [a-z]+ yet|nothing here|empty|Nothing to"),
    ("error",    r"went wrong|failed to|Error loading|couldn't"),
    ("loading",  r"Skeleton|isLoading|status === \"loading\"|Loading"),
]:
    files = sh(f"grep -rlE '{pat}' {FE} --include=*.tsx | sort").split()
    print(f"\n  {label} ({len(files)} files):")
    for f in files[:24]:
        print(f"    {f.replace(FE + '/', '')}")
    if len(files) > 24:
        print(f"    ... and {len(files) - 24} more")
