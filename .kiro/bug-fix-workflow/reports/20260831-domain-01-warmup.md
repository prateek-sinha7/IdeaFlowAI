# Domain 1 — warmup — Run Report
**Date:** 2026-08-31  
**Operator:** in-session (Kiro acting as orchestrator + all agent roles)  
**Branch:** current working tree (feat/conditional-gates lineage)

---

## Cards closed

| card | result | how | FIX card | test |
|------|--------|-----|----------|------|
| BUG-031 | CLOSED (pre-existing) | Already resolved in prior session (stages: [manual] restored on knowledge hook at commit 0228bf196). Verified: `.pre-commit-config.yaml:185` carries `stages: [manual]`. | none needed | none — code-path confirmed via grep |
| ISS-095 | CLOSED (ALREADY_FIXED) | All 3 tests in `tests/agents/test_declared_gate_streaming.py` PASS as of 2026-08-31 (3 passed, 43.58s). Root cause (gate rejection not cancelling pipeline, gate never firing) was fixed by commit `da172056` and gate engine work merged after 2026-08-12. ISS-091 (`status: done`) confirms the mechanism landed. Card updated: `status: resolved`, `verification.status: passed`. | none — fix already in tree | `tests/agents/test_declared_gate_streaming.py` — 3/3 green |

## Cards escalated (NEEDS_HUMAN)

| card | reason |
|------|--------|
| ISS-187 | **Product decision required.** Seven `ex_A*` QA fixtures are visible and launchable as real catalog cards to enterprise users (confirmed browser: `/create/ex_A1_loop` renders full "Provide the brief" panel with "Run workflow" button). Two valid paths: (a) `user_launchable: false` on all 7 manifests + remove from both entitlement tables — `test_entitlement_parity` stays green if both sides move together; (b) accept as demos, improve titles/descriptions. The card's own body says "product decision, not a defect with a correct answer — recorded rather than acted on." Blast radius confirmed: `backend/app/core/entitlements.py:49-55`, `frontend/src/lib/entitlements.ts:66-72`, `backend/tests/unit/test_entitlement_parity.py` (parity lock). Path (a) also has downstream consequence for ISS-173 test coverage gap (`condition_agent` naming an earlier step). |
| ISS-076 | **Frozen archive.** Card references `.planning/TEST-REGISTER.md` (stale "123–132 green" Playwright figure). `.planning/` is a frozen read-only archive per PLAN.md and the fixer role contract — no writes permitted. The stale figure cannot be corrected in place. If the document needs updating, the operator should either delete the stale section manually or close ISS-076 as `wontfix` (figures in a frozen archive are expected to go stale). |

## Cards created this run
None — no new ISS or FIX cards were needed (both resolutions were pre-existing fixes or escalations).

## Rebuild results
- **Stage 1 (index):** ✅ completed — 6 related blocks updated, 1095 cards indexed, `state.yaml` updated.
- **Stage 2 (context):** ❌ FAILED — `UnicodeDecodeError: 'charmap' codec can't decode byte 0x90` in `build_context.py` reading a MOD-*.md architecture card. **Pre-existing Windows encoding issue** — not caused by this run. `CONTEXT.md` reflects the previous state.
- **Stage 3 (validate_links):** running at time of report — see integrity note below.
- **Dedup regenerated:** ✅ `bug-hunter/OPEN-ISSUES-DEDUP.md` rebuilt — **224 open cards** (down from 226: BUG-031 and ISS-095 dropped off as resolved). `EXIT_DEDUP=0`.

## Integrity
- ISS-095 card: `status: resolved`, `verification.status: passed` ✅
- BUG-031 card: `status: resolved` (was already set before this run) ✅
- ISS-095 no longer appears in `OPEN-ISSUES-DEDUP.md` ✅
- BUG-031 no longer appears in `OPEN-ISSUES-DEDUP.md` ✅
- `build_context.py` failure is pre-existing Windows cp1252 vs UTF-8 encoding mismatch in one MOD-*.md card — not introduced by this run.

## Ready to commit
Files changed this domain run (leave for operator to review and commit):

```
.knowledge/cards/20260812-1120-ISS-095.md   # status: resolved, verification: passed
.knowledge/INDEX.md                          # 6 related blocks updated (auto-generated)
.knowledge/state.yaml                        # cards_count updated (auto-generated)
bug-hunter/OPEN-ISSUES-DEDUP.md             # ISS-095 + BUG-031 dropped off (regenerated)
.kiro/bug-fix-workflow/STATE.md             # domain 1 → DONE
.kiro/bug-fix-workflow/reports/20260831-domain-01-warmup.md  # this file
```

Suggested commit message:
```
fix(knowledge): close ISS-095 (gate streaming tests already green) + domain-1 warmup report

ISS-095: all 3 declared-gate-streaming tests now pass (da172056 + gate engine
work fixed the root cause after 2026-08-12). Card marked resolved.
BUG-031: confirmed resolved (stages:[manual] on knowledge hook at 0228bf196).
Dedup regenerated: 224 open (was 226).
ISS-187 and ISS-076 escalated to operator (product decision + frozen archive).
```

## Needs a human
1. **ISS-187** — decide: QA-only (set `user_launchable: false`, remove from both entitlement tables) or demo (keep, improve titles). The parity test enforces both sides move together.
2. **ISS-076** — decide: close as wontfix (stale figure in frozen `.planning/` archive) or manually delete the stale section.
3. **`build_context.py` encoding failure** — one MOD-*.md card has a non-UTF-8 byte (0x90 at position 7187). Find and fix the encoding in that card to restore `CONTEXT.md` regeneration on Windows.

## Restart pending
None — no `.py` or yaml/AGENT.md/env files changed by this run.

## Pre-existing issues found (not fixed)
- `build_context.py` UnicodeDecodeError on Windows (cp1252 vs UTF-8 in a MOD-*.md card). Pre-dates this run.
- ISS-076: stale figure in frozen `.planning/TEST-REGISTER.md` — unfixable under current archive rules without operator decision.
