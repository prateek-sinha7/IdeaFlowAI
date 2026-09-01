# Domain 7 — frontend·library — Run Report

**UTC timestamp:** 2026-09-01T19:00:00Z  
**Domain:** frontend·library  
**Cards in scope:** 11  
**Batches:** B1 (LibraryPage.tsx, 10 cards) + B2 (ISS-605 test, 1 card)

---

## Cards Closed (7)

| card | disposition | FIX card | test path |
|---|---|---|---|
| ISS-330 | FIXED — FetchErrorState + failed branches in all 3 grids | FIX-456 | LibraryPage.test.tsx (9 green) |
| ISS-336 | FIXED — useMemo wrapping in useHooksCatalog.ts | FIX-457 | LibraryPage.test.tsx (9 green) |
| ISS-605 | FIXED — data-testid + scoped assertion, it.fails removed | FIX-458 | LibraryPage.skillMarkdown.test.tsx (1 green) |
| ISS-318 | ALREADY_FIXED — FIX-383 already dropped onSkillsChange | (FIX-383) | LibraryPage.test.tsx (pre-existing green) |
| ISS-335 | ALREADY_FIXED — EmptyGridState already uses filteredAgents.length===0 | (FIX-342) | LibraryPage.test.tsx (pre-existing green) |
| ISS-441 | ALREADY_FIXED — FIX-383 already fixed the hooks tab readOnly gate | (FIX-383) | pre-existing green |
| ISS-591 | ALREADY_FIXED — FIX-403 already routed SkillDetailModal through SkillMarkdown | (FIX-403) | pre-existing green |

### BUG cards confirmed already closed
- **BUG-095** — already ESCALATED/FIXED by FIX-383 (onSkillsChange removed). Status unchanged (escalated), no new code change needed.

---

## Cards Escalated (3)

| card | reason |
|---|---|
| BUG-073 | Already ESCALATED by prior fixer (2026-08-29). Fix needs either: (a) gate Config-tab levers read-only in AgentsPopup.tsx (domain 12), or (b) new backend endpoint for per-agent overrides. Product decision still open. No code changed. |
| ISS-392 | Remains OPEN — root cause analysis of BUG-073. Same escalation: fix belongs in AgentsPopup.tsx (domain 12 primary file). No code changed here. |
| ISS-378 | Fix belongs in `AgentsPopup.tsx` (domain 12 primary fix site — `ConfigLeversFlat` missing Tools row). Editing it here would violate the cross-domain collision rule. Scheduled for domain 12. |

---

## Files Touched

| file | change |
|---|---|
| `frontend/src/components/library/LibraryPage.tsx` | Added `FetchErrorState` component; added `=== "failed"` branch in all 3 grid renders (agents/skills/hooks); added `data-testid="skill-formatted-content"` to formatted section div |
| `frontend/src/hooks/useHooksCatalog.ts` | Wrapped `reduxHooks.map()` in `useMemo([reduxHooks])`; added `useMemo` import |
| `frontend/src/components/library/LibraryPage.skillMarkdown.test.tsx` | Removed `it.fails` marker; scoped both assertions to `[data-testid="skill-formatted-content"]` container |

---

## FIX Cards Written

- `FIX-456` — ISS-330: FetchErrorState + failed branches (LibraryPage.tsx)
- `FIX-457` — ISS-336: useMemo for hooks array (useHooksCatalog.ts)  
- `FIX-458` — ISS-605: scoped test assertion + data-testid (LibraryPage.tsx + test)

---

## Verification

| check | result |
|---|---|
| `tsc --noEmit` | TSC_EXIT=0 — zero errors |
| `vitest run LibraryPage.skillMarkdown.test.tsx LibraryPage.test.tsx` | VITEST_EXIT=0 — 10/10 tests passed |
| knowledge rebuild stage 1 (index) | SUCCESS — INDEX.md updated, 1141 cards indexed |
| knowledge rebuild stage 2 (context) | FAILED — pre-existing UnicodeDecodeError cp1252 0x90 in MOD-*.md card (documented in DISPATCH.md — CONTEXT.md stays stale) |
| validate_links | 9 broken links in MOD-backend.md (all point to .venv312 package paths) — pre-existing, not ours |
| dedup regenerated | YES — DEDUP_EXIT=0; 171 open → 150 units (closed cards dropped to ✅ Closed section) |

---

## What Needs a Human

- **BUG-073 / ISS-392 / ISS-378**: All three require editing `AgentsPopup.tsx` (domain 12). The operator must decide whether domain 12's run should include the Config-tab read-only gate for BUG-073/ISS-392 (a product decision: gate vs. new backend endpoint).
- **ISS-318 e2e test** (`tests/integration/e2e/suites/08_library/test_iss318_agent_skills_add_persists.py`): Still 2 XFAIL after FIX-383 — the test asserts the persistence path (new endpoint), not the read-only fix. Needs a human call on which remedy is the product answer before the test can be updated.

---

## Ready to Commit

**Commit 1 — production fixes:**
```
fix(library): add error state for failed API fetches and memoize hooks catalog

ISS-330: FetchErrorState component + agentsStatus/skillsStatus/hooksStatus === "failed"
branches added to all three grids in LibraryPage.tsx so a failed fetch shows
a distinct message instead of a blank grid.

ISS-336: useHooksCatalog now wraps the hooks array in useMemo([reduxHooks]),
matching useSkillsCatalog's pattern so HOOKS.find() in the cold-mount effect
gets stable array references.
```
Files: `frontend/src/components/library/LibraryPage.tsx`, `frontend/src/hooks/useHooksCatalog.ts`

**Commit 2 — test fix:**
```
test(library): scope ISS-605 assertion to formatted-content section; remove it.fails

FIX-458: Added data-testid="skill-formatted-content" to the SkillDetailModal
formatted section. LibraryPage.skillMarkdown.test.tsx assertion 2 now queries
within that container only (not the whole dialog), so the deliberate raw
SKILL.md <pre> block no longer makes it unsatisfiable. it.fails removed since
FIX-403 already landed the real markdown fix.
```
Files: `frontend/src/components/library/LibraryPage.tsx` (same as commit 1, can combine), `frontend/src/components/library/LibraryPage.skillMarkdown.test.tsx`

**Commit 3 — knowledge cards:**
```
knowledge: Domain 7 frontend·library — 7 closed, 3 escalated

FIX-456, FIX-457, FIX-458 written. ISS-330, ISS-335, ISS-336, ISS-318, ISS-441,
ISS-591, ISS-605 → resolved. OPEN-ISSUES-DEDUP.md regenerated (171→150 units).
```
Files: `.knowledge/cards/20260901-1900-FIX-456.md`, `FIX-457.md`, `FIX-458.md`, updated ISS cards, `INDEX.md`, `state.yaml`, `bug-hunter/OPEN-ISSUES-DEDUP.md`, `STATE.md`, this report.

---

## Pre-existing Issues (not fixed here)

- `build_context.py` UnicodeDecodeError cp1252 0x90 — MOD-*.md card has non-UTF-8 byte at ~position 7187. Documented pre-existing.
- `validate_links.py` 9 broken links — all in `MOD-backend.md` → `.venv312` package paths. Pre-existing.
