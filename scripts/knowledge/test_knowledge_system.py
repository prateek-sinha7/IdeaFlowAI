"""
Comprehensive test suite for the .knowledge/ card store and automation system.

Tests:
  1. Card store integrity
  2. Surface file correctness
  3. ctx.py query layer (fixes, issues, phases, rules, file-based)
  4. Hook commands syntax validity
  5. Steering file compliance (no register auto-includes)
  6. Deleted-file cleanup
  7. Register sync state

Run: python scripts/knowledge/test_knowledge_system.py
Exit: 0 = all pass, 1 = failures
"""
from __future__ import annotations
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
KNOWLEDGE = ROOT / ".knowledge"
SURFACE = KNOWLEDGE / "surface"
STEERING = ROOT / ".kiro" / "steering"
HOOKS = ROOT / ".kiro" / "hooks"
SCRIPTS = ROOT / "scripts" / "knowledge"

passed = 0
failed = 0
failures: list[str] = []


def ok(label: str) -> None:
    global passed
    passed += 1
    print(f"  [  ok  ] {label}")


def fail(label: str, detail: str = "") -> None:
    global failed
    failed += 1
    msg = f"  [ FAIL ] {label}" + (f"\n           {detail}" if detail else "")
    failures.append(msg)
    print(msg)


def run_ctx(*args) -> tuple[int, str]:
    """Run ctx.py with given args, return (returncode, stdout)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "ctx.py"), *args],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    )
    return result.returncode, result.stdout.strip()


# ─── 1. Card Store Integrity ───────────────────────────────────────────────
print("\n=== 1. Card Store Integrity ===")

cards_dir = KNOWLEDGE / "cards"
card_files = list(cards_dir.glob("*.md"))
ok(f"cards directory exists ({len(card_files)} files)") if card_files else fail("no cards found")

fix_cards = [f for f in card_files if re.match(r"FIX-\d+", f.name)]
ok(f"fix cards present ({len(fix_cards)})") if len(fix_cards) >= 183 else fail(
    f"expected ≥183 fix cards, got {len(fix_cards)}")

if any(f.name == "FIX-176.md" for f in card_files):
    ok("FIX-176.md (newest fix) exists")
else:
    fail("FIX-176.md missing — store is behind register")

if any(f.name == "ADR-0001.md" for f in card_files):
    ok("ADR-0001.md (decision card) exists")
else:
    fail("ADR-0001.md missing")

iss_cards = [f for f in card_files if re.match(r"ISS-\d+", f.name)]
ok(f"issue cards: {len(iss_cards)} (expected 49)") if len(iss_cards) == 49 else fail(
    f"expected 49 issue cards, got {len(iss_cards)}")

phase_cards = [f for f in card_files if re.match(r"PHASE-\d+", f.name)]
ok(f"PHASE-NN pointer cards: {len(phase_cards)} (expected 23)") if len(phase_cards) == 23 else fail(
    f"expected 23 PHASE cards, got {len(phase_cards)}")

# ─── 2. Surface File Correctness ───────────────────────────────────────────
print("\n=== 2. Surface Files ===")

required_surface = ["INDEX.md", "RULES.md", "CATALOG.md", "ENTRY.md",
                    "ARCHITECTURE.md", "index.json", "links.json", "stamp.json"]
for fname in required_surface:
    p = SURFACE / fname
    if p.exists() and p.stat().st_size > 100:
        ok(f"{fname} exists ({p.stat().st_size:,} bytes)")
    else:
        fail(f"{fname} missing or empty")

# stamp.json correctness
stamp = json.loads((SURFACE / "stamp.json").read_text(encoding="utf-8"))
ok("stamp.json card_count=547") if stamp["card_count"] == 547 else fail(
    f"stamp card_count={stamp['card_count']}, expected 547")
ok("stamp.json content_ref=ui-2-dev-fixes") if stamp["sources"]["content_ref"] == "ui-2-dev-fixes" else fail(
    f"content_ref={stamp['sources']['content_ref']}, expected ui-2-dev-fixes")
ok("stamp.json fix count=183") if stamp["counts"]["fix"] == 183 else fail(
    f"fix count={stamp['counts']['fix']}, expected 183")

# index.json validity
idx = json.loads((SURFACE / "index.json").read_text(encoding="utf-8"))
entries = idx.get("entries", [])
fix_entries = [e for e in entries if e["type"] == "fix"]
ok(f"index.json has 183 fix entries") if len(fix_entries) == 183 else fail(
    f"index.json fix entries={len(fix_entries)}, expected 183")
ok("FIX-176 in index.json") if any(e["id"] == "FIX-176" for e in fix_entries) else fail(
    "FIX-176 missing from index.json")

# links.json validity
links = json.loads((SURFACE / "links.json").read_text(encoding="utf-8"))
by_file = links.get("by_file", {})
key = "frontend/src/hooks/useRunStream.ts"
ok(f"links.json has {len(by_file)} files indexed") if len(by_file) >= 100 else fail(
    f"links.json by_file only {len(by_file)} entries")
ok("useRunStream.ts in links.json") if key in by_file and "ADR-0001" in by_file[key] else fail(
    f"useRunStream.ts not properly indexed in links.json")

# INDEX.md content
index_md = (SURFACE / "INDEX.md").read_text(encoding="utf-8")
ok("INDEX.md has 547 cards header") if "547 cards" in index_md else fail("547 cards not in INDEX.md header")
ok("INDEX.md has FIX-176 entry") if "FIX-176" in index_md else fail("FIX-176 missing from INDEX.md")
ok("INDEX.md has ADR-0001 rule") if "ADR-0001" in index_md else fail("ADR-0001 missing from INDEX.md rules")

# ─── 3. ctx.py Query Layer ─────────────────────────────────────────────────
print("\n=== 3. ctx.py Query Layer ===")

# Fix symptom search
rc, out = run_ctx("reconnect banner")
ok("ctx.py 'reconnect banner' returns results") if out and "FIX-122" in out else fail(
    "ctx.py symptom search failed", out[:100] if out else "empty")

# Show a specific fix
rc, out = run_ctx("--show", "FIX-176")
ok("ctx.py --show FIX-176 returns card body") if "appendRunChatFrames" in out or "FIX-176" in out else fail(
    "ctx.py --show FIX-176 failed", out[:100] if out else "empty")

# Show a recent fix from the batch
rc, out = run_ctx("--show", "FIX-172")
ok("ctx.py --show FIX-172 returns card body") if "detachRun" in out or "FIX-172" in out else fail(
    "ctx.py --show FIX-172 failed", out[:100] if out else "empty")

# File-based lookup
rc, out = run_ctx("--for", "frontend/src/hooks/useRunStream.ts")
ok("ctx.py --for useRunStream.ts returns ADR-0001") if "ADR-0001" in out else fail(
    "ctx.py --for useRunStream.ts failed", out[:100] if out else "empty")

# Rules by area
rc, out = run_ctx("--rules", "sse")
ok("ctx.py --rules sse returns ADR-0001") if "ADR-0001" in out else fail(
    "ctx.py --rules sse failed", out[:100] if out else "empty")

# Phase lookup
rc, out = run_ctx("--type", "phase", "prototype manifest")
ok("ctx.py --type phase finds PHASE-07") if "PHASE-07" in out or "prototype" in out.lower() else fail(
    "ctx.py phase lookup failed", out[:100] if out else "empty")

# Issue lookup
rc, out = run_ctx("--type", "issue", "review gate")
ok("ctx.py --type issue finds review gate issues") if out and "ISS-" in out else fail(
    "ctx.py issue lookup failed", out[:100] if out else "empty")

# Bug lookup
rc, out = run_ctx("--type", "bug", "resume")
ok("ctx.py --type bug finds resume bugs") if "BUG-R" in out or "resume" in out.lower() else fail(
    "ctx.py bug lookup failed", out[:100] if out else "empty")

# Dashboard file — high-frequency file
rc, out = run_ctx("--for", "frontend/src/app/dashboard/page.tsx")
ok("ctx.py --for dashboard/page.tsx returns cards") if out else fail(
    "ctx.py --for dashboard/page.tsx returned nothing")

# ─── 4. Hook Command Validity ──────────────────────────────────────────────
print("\n=== 4. Hook Files ===")

expected_hooks = {
    "sync-fix-cards.kiro.hook": {
        "event": "fileEdited",
        "pattern": ".planning/FIX-REGISTER.md",
        "cmd_contains": "extract.py fixes",
    },
    "sync-issue-phase-cards.kiro.hook": {
        "event": "fileEdited",
        "pattern": ".planning/ISSUES-REGISTER.md",
        "cmd_contains": "extract.py issues",
    },
    "knowledge-freshness-check.kiro.hook": {
        "event": "agentStop",
        "cmd_contains": "check.py",
    },
}

for fname, spec in expected_hooks.items():
    path = HOOKS / fname
    if not path.exists():
        fail(f"{fname} missing")
        continue
    hook = json.loads(path.read_text(encoding="utf-8"))
    ok(f"{fname} parses as valid JSON")
    ok(f"{fname} enabled=true") if hook.get("enabled") else fail(f"{fname} not enabled")
    ok(f"{fname} event={spec['event']}") if hook["when"]["type"] == spec["event"] else fail(
        f"{fname} wrong event: {hook['when']['type']}")
    cmd = hook["then"]["command"]
    ok(f"{fname} command contains '{spec['cmd_contains']}'") if spec["cmd_contains"] in cmd else fail(
        f"{fname} command missing '{spec['cmd_contains']}'", cmd[:80])
    ok(f"{fname} has PYTHONIOENCODING=utf-8") if "PYTHONIOENCODING=utf-8" in cmd else fail(
        f"{fname} missing encoding fix", cmd[:80])
    if "pattern" in spec:
        patterns = hook["when"].get("patterns", [])
        ok(f"{fname} targets {spec['pattern']}") if spec["pattern"] in patterns else fail(
            f"{fname} wrong patterns: {patterns}")

# ─── 5. Steering File Compliance ───────────────────────────────────────────
print("\n=== 5. Steering File Compliance ===")

forbidden_patterns = [
    "#[[file:.planning/IMPLEMENTATION-REGISTER.md]]",
    "#[[file:.planning/ISSUES-REGISTER.md]]",
    "#[[file:.planning/FIX-REGISTER.md]]",
    "@.planning/IMPLEMENTATION-REGISTER.md",
    "fix-archives/",
]

velocity_files = [
    STEERING / "velocity-ai-analyze.md",
    STEERING / "velocity-ai-fix.md",
]

for vfile in velocity_files:
    content = vfile.read_text(encoding="utf-8")
    fname = vfile.name
    for pattern in forbidden_patterns:
        if pattern in content:
            fail(f"{fname} still contains forbidden: {pattern}")
        else:
            ok(f"{fname} no forbidden '{pattern[:40]}'")

# velocity-ai-analyze must use ctx.py
analyze = (STEERING / "velocity-ai-analyze.md").read_text(encoding="utf-8")
ok("velocity-ai-analyze.md references ctx.py") if "ctx.py" in analyze else fail(
    "velocity-ai-analyze.md missing ctx.py reference")
ok("velocity-ai-analyze.md loads ARCHITECTURE.md") if "ARCHITECTURE.md" in analyze else fail(
    "velocity-ai-analyze.md missing ARCHITECTURE.md load")
ok("velocity-ai-analyze.md loads INDEX.md") if "INDEX.md" in analyze else fail(
    "velocity-ai-analyze.md missing INDEX.md load")

# velocity-ai-fix must use ctx.py and extract.py
fix_file = (STEERING / "velocity-ai-fix.md").read_text(encoding="utf-8")
ok("velocity-ai-fix.md references ctx.py") if "ctx.py" in fix_file else fail(
    "velocity-ai-fix.md missing ctx.py reference")
ok("velocity-ai-fix.md Step 9 uses extract.py") if "extract.py fixes" in fix_file else fail(
    "velocity-ai-fix.md Step 9 missing extract.py instruction")
ok("velocity-ai-fix.md Step 9 uses build_index.py") if "build_index.py" in fix_file else fail(
    "velocity-ai-fix.md Step 9 missing build_index.py instruction")

# invariants.md must transclude .knowledge/INVARIANTS.md
inv = (STEERING / "invariants.md").read_text(encoding="utf-8")
ok("invariants.md transclude .knowledge/INVARIANTS.md") if "#[[file:.knowledge/INVARIANTS.md]]" in inv else fail(
    "invariants.md missing #[[file:.knowledge/INVARIANTS.md]] transclusion")

# project-index.md must reference ctx.py
proj = (STEERING / "project-index.md").read_text(encoding="utf-8")
ok("project-index.md references ctx.py") if "ctx.py" in proj else fail(
    "project-index.md missing ctx.py reference")
ok("project-index.md references ARCHITECTURE.md") if "ARCHITECTURE.md" in proj else fail(
    "project-index.md missing ARCHITECTURE.md")

# ─── 6. Deleted Files Cleanup ──────────────────────────────────────────────
print("\n=== 6. Deleted Files (should NOT exist) ===")

should_not_exist = [
    ROOT / ".planning" / "fix-register-index.md",
    ROOT / ".planning" / "fix-archives",
    STEERING / "IMPLEMENTATION-REGISTER.md",
    STEERING / "ai-saas-platform-rules.md",
    STEERING / "phases",
    ROOT / ".kiro" / "steering" / "phases" / "phases-01-12-foundation.md",
]

for path in should_not_exist:
    if path.exists():
        fail(f"should be deleted but still exists: {path.relative_to(ROOT)}")
    else:
        ok(f"correctly absent: {path.relative_to(ROOT)}")

# ─── 7. Register Sync State ────────────────────────────────────────────────
print("\n=== 7. Register Sync State ===")

result = subprocess.run(
    [sys.executable, str(SCRIPTS / "check.py")],
    capture_output=True, text=True, encoding="utf-8", cwd=ROOT
)
output = result.stdout + result.stderr

ok("check.py runs without crash") if result.returncode in (0, 1) else fail(
    "check.py crashed", output[-200:])
ok("cards vs registers: all entries extracted") if "cards vs registers (all entries extracted" in output else fail(
    "registers not fully extracted", [l for l in output.splitlines() if "registers" in l])
ok("index vs cards: fresh") if "index vs cards (fresh" in output else fail(
    "index is stale")
ok("coverage: 1064/1064") if "1064/1064" in output else fail(
    "coverage check failed", [l for l in output.splitlines() if "coverage" in l])

known_warns = ["cards vs code", "links (1 point", "usable, but see warnings"]
unexpected = [l for l in output.splitlines()
              if "warn" in l.lower() and not any(kw in l for kw in known_warns)]
ok("no unexpected warnings") if not unexpected else fail(
    "unexpected warnings found", str(unexpected))

# ─── Final Report ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  PASSED: {passed}   FAILED: {failed}")
if failures:
    print("\nFailed checks:")
    for f in failures:
        print(f)
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
