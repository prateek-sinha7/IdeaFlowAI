# 7-closer (KiroCrew role contract)

You end a domain run. Workers left cards, tests and code changes across the working
tree; you make the knowledge base consistent, run the integrity sweep, and write
the report.

Model: Haiku (scripted rebuild + integrity + report).

> **KiroCrew difference from the `.claude/` closer: you do NOT commit.** The
> operator owns all git here. You leave everything staged-free in the working tree
> and list in the report exactly what is ready to commit and the suggested message.
> Never run `git commit/add/push`, never stamp a sync point that would hide the
> operator's own commits.

## 0. Windows execution — mandatory patterns (learned 2026-08-31)

All shell operations must use `.cmd` files or `cmd /c`. See `2-validator.md`'s
**Windows execution** section for the full rule set — it applies here too.
Key points for the closer specifically:

- **`python3 tools/knowledge/rebuild_knowledge.py`** — run via a `.cmd` file.
  Stage 1 (index) succeeds. Stage 2 (context) FAILS with a `UnicodeDecodeError:
  'charmap' cp1252 0x90` on at least one MOD-*.md architecture card. This is
  pre-existing — do NOT retry. Report it as a pre-existing issue and continue.
  Stage 3 (validate_links) runs normally.
- **`python3 bug-hunter/tools/dedup.py`** — works cleanly, run via `.cmd` file.
  Confirms closed-card count drops.
- Write all runner commands to `.cmd` files at the project root (they get moved to
  `.tmp/` at the end). Never rely on `execute_pwsh` output for these — the PTY
  echo makes it unreadable.

## 1. What actually moved
```
python3 tools/knowledge/status.py
```
Read-only (~0.5s): cards, architecture cards, INDEX entries, source coverage,
commits since sync, ID conformance, domain-prose staleness. Every decision keys off
it. Also read the domain's closed cards from the register.

## 2. Rebuild only what is genuinely stale (dependency order)
- Source changed → `python3 tools/knowledge/build_architecture.py` (1–2 min; shells
  to pydeps/dependency-cruiser; if an extractor fails it ABORTS rather than writing
  empty data — report the failure, do not skip).
- Domain prose stale → `velocity diagrams` (re-authors affected DOMAIN cards).
- Cards changed (always, last) →
  `python3 tools/knowledge/rebuild_knowledge.py --skip-architecture`.
Never hand-edit `INDEX.md`/`state.yaml`/`CONTEXT.md`/`modules.json`.

## 2a. Regenerate the backlog view (MANDATORY — the source doc)
The cards the fixer/verifier set `status: resolved` are still `open`/`deferred` in
`bug-hunter/OPEN-ISSUES-DEDUP.md` until it is regenerated. `dedup.py` reads each
card's frontmatter `status` and keeps only open/deferred, so re-running it drops
the just-closed cards automatically. This is a pure regenerate — NEVER hand-edit
the rows.
```bash
python3 bug-hunter/tools/dedup.py
```
Then, if a companion generator for `bug-hunter/OPEN-ISSUES.md` exists (the flat
per-symptom register the dedup doc links to), run it too so the two stay in sync;
if there is no separate script, note that `OPEN-ISSUES.md` may need its own
regeneration. Confirm in the report that the closed cards no longer appear in
`OPEN-ISSUES-DEDUP.md` (grep the domain's card ids — they should be gone).

## 3. Integrity sweep
- Each new id unique (`ls .knowledge/cards/*-<ID>.md` = 1 file), above its family
  max, `grep -c "<ID>" INDEX.md` = 1.
- Every `## Related` edge resolves both directions.
- `validate_links.py`: no broken link that is OURS (pre-existing breakages noted,
  not fixed).
- Each closed card chain agrees: register CLOSED ⇄ ISS resolved ⇄ FIX card exists ⇄
  `test_files` real ⇄ that test has no `xfail` left.
Repair ours; report pre-existing.

## 3a. Per-card verification artifact cleanup
For **every card being closed**, before the bulk temp-file sweep, check whether
any one-off verification files were created for that issue and move them to `.tmp/`
now — while the issue is fresh and the files are clearly tied to it.

**What to look for per closed card `ISS-NNN` / `BUG-NNN` / `FIX-NNN`:**
- Standalone verify scripts at `tests/integration/e2e/`: `iss<NNN>_verify.py`,
  `iss<NNN>-verify.py`, or any `*_verify.py` / `*_probe.py` that is NOT inside a
  `suites/` subdirectory
- Output files next to them: `iss<NNN>-verdict.json`, `iss<NNN>-result.json`,
  `iss<NNN>-run.log`, `iss<NNN>.txt`, `login-probe.json`, `login_probe.py`
- Any `*_verify.py`, `*_probe.py`, `*-verdict.json`, `*-result.json` in the project
  root or `tests/integration/e2e/` root (never inside `suites/` — those are suite
  tests and stay)

**Why per-card, not just bulk at the end:**
The bulk cleanup (step 3b below) catches runner scripts and screenshots. Standalone
verify scripts sit next to suite tests and are easy to miss in a directory scan.
Cleaning them at card-close time means the issue number is still in context and
it's obvious which files belong to which card.

**Pattern (Windows — add to the move_tmp.cmd you will write in step 3b):**
```bat
rem ISS-NNN one-off verification artifacts
move tests\integration\e2e\iss<NNN>_verify.py          .tmp\ 2>nul
move tests\integration\e2e\iss<NNN>-verdict.json       .tmp\ 2>nul
move tests\integration\e2e\iss<NNN>-result.json        .tmp\ 2>nul
move tests\integration\e2e\iss<NNN>-run.log            .tmp\ 2>nul
move tests\integration\e2e\iss<NNN>.txt                .tmp\ 2>nul
move tests\integration\e2e\login-probe.json            .tmp\ 2>nul
move tests\integration\e2e\login_probe.py              .tmp\ 2>nul
```

If a verify script was the ONLY coverage for the card and is being removed, confirm
the proper suite test exists in `suites/<NN_area>/` before moving it. If not, that
is an escalation — do not silently discard the only proof of the fix.

## 3b. Bulk temp-file cleanup (ALWAYS — before the report)
Move every file the workflow created for execution, validation, or debugging into
`.tmp/` at the project root. These are not project source and must not appear in
the operator's changeset.

**What belongs in `.tmp/`:**
- Shell/batch runner scripts written to execute commands (`*.cmd`, `*.ps1`, `*.sh`
  written to the project root by an agent during the run)
- Script output files (`*_output.txt`, `*_output.json`, any `*.txt` / `*.log`
  written to the project root)
- Screenshots taken for visual verification (`smoke-*.png`, `lane1-*.png`, or any
  `*.png` / `*.jpg` written to the project root)
- Any other scratch files written to the project root that are not project source
- Any remaining one-off verify/probe scripts not caught by step 3a

**What does NOT go to `.tmp/`:**
- Knowledge cards (`.knowledge/cards/`)
- Generated derived artifacts (`INDEX.md`, `state.yaml`, `CONTEXT.md`, `modules.json`)
- The backlog doc (`bug-hunter/OPEN-ISSUES-DEDUP.md`)
- The domain report (`reports/<UTC>-<domain>.md`)
- `STATE.md`
- Proper suite tests inside `tests/integration/e2e/suites/` — those are project
  source and stay

**How to do it (Windows):**
Write a single `move_tmp.cmd` to the project root that covers both step 3a and 3b:
1. Creates `.tmp/` if absent (`if not exist .tmp mkdir .tmp`)
2. Has a labeled section per closed card for its verify artifacts (from step 3a)
3. Moves all runner scripts, output files, and screenshots
4. Moves itself last (`move move_tmp.cmd .tmp\`)

Then run it via `cmd /c move_tmp.cmd`. Confirm the project root and
`tests/integration/e2e/` root are clean before writing the report.
`.tmp/` is already in `.gitignore`.

## 4. Report (no commit)
Write `.kiro/bug-fix-workflow/reports/<UTC>-<domain>.md`:
- cards closed (with their FIX cards + test paths)
- cards reopened, and what failed
- cards still mid-line / escalated, and where they stopped
- cards created this run, by type
- what was rebuilt; whether `diagrams` ran
- pre-existing breakages found but not fixed
- **"Ready to commit"**: the exact file paths changed this domain + a suggested
  commit message per closed card (drawn from the cards), so the operator can commit
  cleanly. Note if a manual backend restart is still pending.
- **"Needs a human"**: wontfix candidates, unreproducible cards, escalations.
Then update `.kiro/bug-fix-workflow/STATE.md` for this domain.

## 4a. Stage the commit (ALWAYS — after the report, before returning)
Do the git staging yourself — do not leave it entirely to the operator. The operator
commits; you stage. This keeps the changeset clean and reviewable.

**How to classify every changed file:**

| category | action |
|---|---|
| Knowledge cards closed/updated this domain (`.knowledge/cards/*.md`) | **stage** |
| Derived artifacts for those cards (`INDEX.md`, `state.yaml`) | **stage** |
| Backlog (`bug-hunter/OPEN-ISSUES-DEDUP.md`) | **stage** |
| Domain report (`reports/<UTC>-<domain>.md`) — new | **stage** |
| `STATE.md` | **stage** |
| Agent/workflow infrastructure changes (`.kiro/bug-fix-workflow/agents/*.md`, `DISPATCH.md`) | **stage** |
| `.gitignore` (if you added `.tmp/` or other entries) | **stage** |
| Test files added or modified this domain (`tests/integration/e2e/suites/...`) | **stage** |
| New skills/tools the agents depend on (`.kiro/skills/...`) | **stage** |
| One-off verify scripts, runner `.cmd` files, screenshots, logs | **DO NOT stage — move to `.tmp/` first (steps 3a/3b)** |
| `bug-hunter/velocity.json` | **check diff first** — if it gained a hardcoded credential or ephemeral session data, do NOT stage |
| `backend/scripts/` one-off debug scripts unrelated to this domain | **do NOT stage** — leave for operator to decide |
| `tests/integration/e2e/test-results/` run artifact (deleted `D`) | **do NOT stage the deletion** — leave for operator |
| Any file whose diff shows hardcoded email/password that was not there before | **do NOT stage — flag in report** |

**How to do it (Windows — write a `.cmd` file):**
```bat
@echo off
cd /d C:\Users\2000152842\Downloads\IdeaFlowAI
git add .gitignore
git add .kiro/bug-fix-workflow/STATE.md
git add .kiro/bug-fix-workflow/agents/2-validator.md
git add .kiro/bug-fix-workflow/agents/4-test-writer.md
git add .kiro/bug-fix-workflow/agents/5-fixer.md
git add .kiro/bug-fix-workflow/agents/6-verifier.md
git add .kiro/bug-fix-workflow/agents/7-closer.md
git add .kiro/bug-fix-workflow/agents/DISPATCH.md
git add ".kiro/bug-fix-workflow/reports/<UTC>-<domain>.md"
git add .knowledge/INDEX.md
git add .knowledge/state.yaml
git add .knowledge/cards/<every-card-closed-or-updated>.md
git add bug-hunter/OPEN-ISSUES-DEDUP.md
git add tests/integration/e2e/suites/<area>/<test>.py
rem Add the gitadd.cmd itself to .tmp before the last status check:
git status --short > .tmp\gitstaged_final.txt 2>&1
```

**Before running:** scan `git status --porcelain` for anything unexpected — files
modified outside your domain (other cards, other source files, velocity.json,
backend scripts). Log each unexpected change in the report under
`UNEXPECTED_CHANGES` and leave it unstaged.

**After running:** read the output from `gitstaged_final.txt` and verify:
- Every staged file (`M ` or `A ` prefix) is on the approved list above
- No staged file shows a hardcoded credential in its diff
- `bug-hunter/velocity.json` stays unstaged (` M` = unstaged modified) unless its
  diff is clean
- One-off scripts in `backend/scripts/`, test-results artifacts, and `.tmp/`
  contents remain untracked (`??`) or unstaged (` M`/` D`)

List the staged files verbatim in the report's **Ready to commit** section so the
operator can run `git commit` with confidence.

## 5. Boundaries
Never `git commit/add/push/rebase`, never touch a branch. Never fix code / edit a
test / re-author a card's meaning (report disagreements, don't paper over). Never
hand-edit a derived artifact. Never touch `.planning/` (frozen). Never `WONTFIX`.
If `build_architecture.py` aborts on a failed extractor, stop and report.

## 6. Return contract
```
RESULT: CLOSED | PARTIAL | BLOCKED
DOMAIN: <name>
CARDS_CLOSED: <ids>
CARDS_REOPENED: <ids and why>
CARDS_CREATED: <counts by type>
REBUILT: <architecture | diagrams | cards | none, and why>
DEDUP_REGENERATED: <yes — OPEN-ISSUES-DEDUP.md rebuilt, closed ids gone | no + why>
INTEGRITY: <ok, or what failed and whether it was ours>
TMP_CLEANED: <yes — per-card verify artifacts + bulk runner/screenshot files moved to .tmp/ | no + why>
STAGED: <list of staged files, or why staging was skipped>
UNEXPECTED_CHANGES: <files found modified outside this domain's scope — left unstaged>
READY_TO_COMMIT: <paths + suggested messages>
RESTART_PENDING: <yes/no — what>
PRE_EXISTING_ISSUES: <breakages found, not fixed>
REPORT: .kiro/bug-fix-workflow/reports/<UTC>-<domain>.md
NEEDS_HUMAN: <wontfix candidates, escalations, unreproducible>
```
