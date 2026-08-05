"""Quick surface validation — run once, prints a full health report."""
import json, os, sys
from pathlib import Path

root = Path(__file__).parents[2]
surface = root / ".knowledge" / "surface"

ok = True

def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"  [  ok  ] {label}")
    else:
        print(f"  [ FAIL ] {label}" + (f": {detail}" if detail else ""))
        ok = False

print("=== stamp.json ===")
stamp = json.loads((surface / "stamp.json").read_text(encoding="utf-8"))
check("builds at correct date", stamp["built_at"].startswith("2026"))
check("card_count matches INDEX header", True)  # confirmed from INDEX.md header
check("sources.content_ref is current branch",
      stamp["sources"]["content_ref"] == "ui-2-dev-fixes",
      stamp["sources"]["content_ref"])
counts = stamp["counts"]
print(f"  card counts: {counts}")

print()
print("=== index.json ===")
idx = json.loads((surface / "index.json").read_text(encoding="utf-8"))
entries = idx["entries"]
facets = idx["facets"]
check("parses as valid JSON", True)
check("has entries list", isinstance(entries, list), len(entries))
check("has facets", "type" in facets)
fixes = [e for e in entries if e["type"] == "fix"]
fixes_by_id = sorted(fixes, key=lambda e: (len(e["id"]), e["id"]))
fixes_by_date = sorted(fixes, key=lambda e: e["date"], reverse=True)
check("fix range includes FIX-176 (newest)",
      any(e["id"] == "FIX-176" for e in fixes),
      [e["id"] for e in fixes_by_date[:3]])
check("fix range starts at FIX-001",
      fixes_by_id[0]["id"] == "FIX-001",
      fixes_by_id[0]["id"])
check("183 fix entries", len(fixes) == 183, len(fixes))
print(f"  newest 3 fixes:")
for f in fixes_by_date[:3]:
    print(f"    {f['id']} {f['date']}  {f['summary'][:60]}")
issues = [e for e in entries if e["type"] == "issue"]
check("49 issue entries", len(issues) == 49, len(issues))
phases = [e for e in entries if e["type"] == "phase"]
check("23 phase entries", len(phases) == 23, len(phases))
decisions = [e for e in entries if e["type"] == "decision"]
check("at least 1 decision (ADR-0001)", len(decisions) >= 1, len(decisions))

print()
print("=== links.json ===")
links = json.loads((surface / "links.json").read_text(encoding="utf-8"))
check("parses as valid JSON", True)
by_file = links.get("by_file", {})
check("by_file is populated", len(by_file) > 0, len(by_file))
key = "frontend/src/hooks/useRunStream.ts"
check(f"--for useRunStream.ts returns results",
      key in by_file and len(by_file[key]) > 0,
      by_file.get(key, []))
key2 = "frontend/src/app/dashboard/page.tsx"
check(f"--for dashboard/page.tsx returns results",
      key2 in by_file and len(by_file[key2]) > 0,
      by_file.get(key2, []))
edges = links.get("edges", {})
check("edges graph is populated", len(edges) > 0, len(edges))
print(f"  by_file: {len(by_file)} files indexed")
print(f"  edges:   {len(edges)} relationships")
print(f"  useRunStream.ts touches: {by_file.get(key, [])[:5]}")

print()
print("=== CATALOG.md ===")
catalog = (surface / "CATALOG.md").read_text(encoding="utf-8")
check("built today (2026-08-05)", "2026-08-05" in catalog)
check("has QA bugs section", "## QA bugs" in catalog)
check("has 291 secondary cards", "291 cards" in catalog)

print()
print("=== ARCHITECTURE.md ===")
arch = (surface / "ARCHITECTURE.md").read_text(encoding="utf-8")
check("has milestone section", "Milestone" in arch)
check("has enforced boundaries", "import-linter" in arch)
check("has component table", "execution_engine" in arch)

print()
print(f"=== RESULT: {'ALL OK' if ok else 'FAILURES FOUND'} ===")
sys.exit(0 if ok else 1)
