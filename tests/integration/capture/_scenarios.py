#!/usr/bin/env python3
"""Check that every spec scenario has a test, and every test names a real scenario.

The specs are Gherkin-in-markdown: prose tables and commentary around fenced
```gherkin blocks. Nothing executes them. A stable id carried on BOTH sides is
the entire link between a spec and the test that implements it:

    @S-01-02
    Scenario: Signing in with valid credentials lands on the dashboard

    @pytest.mark.scenario("S-01-02")
    def test_signing_in_with_valid_credentials_lands_on_the_dashboard(...):

Ids are permanent. Titles get reworded; an id never changes, which is what keeps
the link alive across edits.

    python3 tests/integration/capture/_scenarios.py            # status
    python3 tests/integration/capture/_scenarios.py --untagged # scenarios needing an id

Static, like the other gates here: regex over both sides, no imports, no pytest
run, no browser. It must stay runnable when the app cannot start.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCREENS = ROOT / "tests" / "integration" / "screens"
E2E = ROOT / "tests" / "integration" / "e2e" / "suites"

ID = r"S-\d{2}-\d{2}"

# An id tag above its Scenario line. Other tags AND comment lines may sit
# between the two — a scenario often reads
#     @S-01-07
#     @defect
#     # D-03. The banner is gated on the literal string "true"…
#     Scenario: …
# so the pattern has to step over both, or every commented scenario silently
# counts as untagged.
# Tags may also share a line — `@defect @unverified` is one line, two tags.
TAGGED = re.compile(
    rf"@({ID})((?:[ \t]*\n[ \t]*(?:@[\w-]+(?:[ \t]+@[\w-]+)*|#[^\n]*))*)"
    rf"[ \t]*\n[ \t]*Scenario(?: Outline)?:\s*(.+)"
)

# Every scenario, tagged or not, so untagged ones can be counted rather than
# silently passing by being invisible to the check above.
ANY_SCENARIO = re.compile(r"^\s*Scenario(?: Outline)?:\s*(.+)$", re.M)

MARKED = re.compile(rf'@pytest\.mark\.scenario\(\s*["\']({ID})["\']\s*\)')
LIVE_MARK = re.compile(r"@pytest\.mark\.live\b")
SKIP_MARK = re.compile(r'@pytest\.mark\.skip\(\s*reason\s*=\s*["\']([^"\']+)["\']')


def spec_scenarios():
    """id -> (file, title, tags). Duplicates are reported, not silently merged."""
    found, dupes = {}, []
    for f in sorted(SCREENS.glob("*.feature.md")):
        for m in TAGGED.finditer(f.read_text()):
            sid, tag_block, title = m.group(1), m.group(2) or "", m.group(3).strip()
            tags = set(re.findall(r"@([\w-]+)", tag_block))
            if sid in found:
                dupes.append((sid, found[sid][0], f.name))
            found[sid] = (f.name, title, tags)
    return found, dupes


def test_scenarios():
    """id -> {file, live, skip}. Marks are read so they can be cross-checked."""
    found = {}
    for f in sorted(E2E.rglob("test_*.py")):
        text = f.read_text()
        for m in MARKED.finditer(text):
            # This test's decorator block: everything from the previous `def` up
            # to the marker, which is where sibling @live / @skip would sit.
            start = max(0, text.rfind("\ndef ", 0, m.start()))
            head = text[start:m.end()]
            # The decorators may also sit AFTER the scenario marker, so include
            # the rest of the block up to this test's own `def`.
            tail_end = text.find("\ndef ", m.end())
            head += text[m.end(): tail_end if tail_end != -1 else len(text)].split("def ")[0]
            skip = SKIP_MARK.search(head)
            found[m.group(1)] = {
                "file": str(f.relative_to(E2E)),
                "live": bool(LIVE_MARK.search(head)),
                "skip": skip.group(1) if skip else None,
            }
    return found


specs, dupes = spec_scenarios()
tests = test_scenarios()

untagged = []
for f in sorted(SCREENS.glob("*.feature.md")):
    text = f.read_text()
    tagged_titles = {m.group(3).strip() for m in TAGGED.finditer(text)}
    for m in ANY_SCENARIO.finditer(text):
        if m.group(1).strip() not in tagged_titles:
            untagged.append((f.name, m.group(1).strip()))

if "--untagged" in sys.argv:
    for fname, title in untagged:
        print(f"{fname:42} {title}")
    sys.exit(1 if untagged else 0)

missing_test = sorted(set(specs) - set(tests))
unknown_id = sorted(set(tests) - set(specs))
# A scenario tagged @live whose test is not marked live runs on every default
# pass and quietly spends money. That is the one mismatch worth its own check.
live_drift = sorted(
    sid
    for sid in set(specs) & set(tests)
    if ("live" in specs[sid][2]) != tests[sid]["live"]
)


def write_ledger():
    """Regenerate docs/PROGRESS.md — what is done, what is left, per scenario.

    Generated, never hand-edited: a hand-kept checklist of 506 rows is wrong
    within a day, and a wrong one is worse than none. Refreshed by every run of
    the offline script, so it always describes the tree as it stands.
    """
    done = sum(1 for s in specs if s in tests and not tests[s]["skip"])
    skipped = sum(1 for s in specs if s in tests and tests[s]["skip"])
    todo = len(specs) - done - skipped

    out = [
        "# Implementation progress",
        "",
        "**Generated by `capture/_scenarios.py --ledger`. Do not hand-edit** — it is",
        "rewritten on every run of `scripts/run-all-offline.sh`.",
        "",
        f"| | Scenarios |",
        "|---|---:|",
        f"| Implemented and running | **{done}** |",
        f"| Implemented but skipped | **{skipped}** |",
        f"| Not yet written | **{todo}** |",
        f"| **Total** | **{len(specs)}** |",
        "",
        "`skipped` means the test exists and is linked to its spec, but cannot run",
        "yet — the reason is its `@pytest.mark.skip` text, and it is shown below.",
        "",
    ]

    by_file: dict[str, list] = {}
    for sid, (fname, title, _tags) in sorted(specs.items()):
        by_file.setdefault(fname, []).append((sid, title))

    for fname, rows in by_file.items():
        n_done = sum(1 for sid, _ in rows if sid in tests and not tests[sid]["skip"])
        n_skip = sum(1 for sid, _ in rows if sid in tests and tests[sid]["skip"])
        out += [
            f"## {fname} — {n_done}/{len(rows)}"
            + (f" ({n_skip} skipped)" if n_skip else ""),
            "",
            "| | Id | Scenario | Where |",
            "|---|---|---|---|",
        ]
        for sid, title in rows:
            t = tests.get(sid)
            if t is None:
                mark, where = "· ", "—"
            elif t["skip"]:
                mark, where = "s ", f"`{t['file']}` — {t['skip']}"
            else:
                mark, where = "ok", f"`{t['file']}`"
            out.append(f"| {mark} | `{sid}` | {title} | {where} |")
        out.append("")

    (DOCS / "PROGRESS.md").write_text("\n".join(out))
    return done, skipped, todo


DOCS = ROOT / "tests" / "integration" / "docs"

if "--ledger" in sys.argv:
    DOCS.mkdir(parents=True, exist_ok=True)
    d, s, t = write_ledger()
    print(f"docs/PROGRESS.md — {d} running, {s} skipped, {t} to write, {len(specs)} total")
    sys.exit(0)

print(f"scenarios with an id: {len(specs)}")
print(f"  implemented:        {len(specs) - len(missing_test)}")
print(f"  awaiting a test:    {len(missing_test)}")
print(f"still untagged:       {len(untagged)}")

problems = 0

if dupes:
    problems += len(dupes)
    print(f"\n── {len(dupes)} DUPLICATE id")
    for sid, a, b in dupes:
        print(f"   {sid}  {a} and {b}")

if unknown_id:
    problems += len(unknown_id)
    print(f"\n── {len(unknown_id)} test names an id no spec defines")
    for sid in unknown_id:
        print(f"   {sid}  {tests[sid]['file']}")

if live_drift:
    problems += len(live_drift)
    print(f"\n── {len(live_drift)} live/offline mismatch between spec and test")
    for sid in live_drift:
        want = "live" if "live" in specs[sid][2] else "offline"
        print(f"   {sid}  spec says {want}, test says the opposite  ({tests[sid]['file']})")

# `missing_test` is progress, not a defect, while the suite is being built: it
# counts down as tests land. Only real inconsistencies fail the gate.
sys.exit(1 if problems else 0)
