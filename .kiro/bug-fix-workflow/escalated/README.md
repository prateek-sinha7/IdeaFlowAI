# Escalated Tasks — Master Index

All items below were flagged `ESCALATED` (or require operator/human approval before
they can proceed) during the domain bug-fix runs. They are grouped by the type of
decision needed so a human reviewer can triage them efficiently.

**Total escalated items: 29 → 11 open** (18 closed)
- 8 require a product / architecture decision before code can move
- 8 stale / not-reproducible → all **8 closed ✓**
- 4 cross-domain coordination → **1 closed ✓** (ISS-263 superseded), 3 remaining
- 4 test rewrites → all **4 closed ✓**
- 2 require operator approval → all **2 closed ✓**

### Closed ✓
| card | closed reason |
|---|---|
| ISS-119 | Routing tests already reconciled upstream; no red defect |
| ISS-133 | Stale duplicate of ISS-125 / FIX-421 (already shipped) |
| ISS-094 | Already fixed upstream in engine.py |
| ISS-096 | od-ppt-validator path doesn't exist; test passes 14/14 |
| ISS-130 | Hazard closed upstream by KRN-005 scratch_lock |
| ISS-156 | Mismatch not present on this branch; all named tests green |
| BUG-031 | `stages: [manual]` restored in commit `0228bf196` (2026-08-29); already live |
| ISS-095 | All 3 gate-streaming tests pass as of 2026-08-31; fixed by commit `da172056` |
| ISS-076 | Won't-fix on frozen `.planning/` archive; live `frontend/e2e/README.md` baseline updated |
| ISS-132 | Option A: `invocation_gated=False` added at `task_loop.py` run_agent call site |
| ADR-0002 | Option 3: `pipeline_type` is permanent on-wire/on-disk name; vocabulary gate converted to skip |
| ISS-161 | Already fixed by Phase 33/43 Concierge wiring (`chat_router.py:215`) |
| ISS-422 | Truncated badge in `ChatAttachments.tsx`; `_build_attached_files_block` reads `entry["truncated"]` |
| ISS-632 | Removed `[:2]` from harnesses; count assertions use `len(specs)` |
| ISS-634 | `_drive_single_agent` uses `compiled_override` to bypass ADR-0008 |
| ISS-638 | 6 stale assertions fixed across 5 test files; 0 production changes |
| ISS-630 | Autouse fixture stubs `build_model`; stale `analyzer_solution`/`+1`/`revision_analyzer_complete` assertions removed |
| ISS-263 | Superseded by ISS-381 — premise was inferred and refuted; actual defect is the 422 roster rejection |

---

## Quick-reference table

| card(s) | domain file | decision type | one-line description |
|---|---|---|---|
| ISS-076, ISS-095 | ~~01-warmup.md~~ | ~~🔒 Operator approval~~ | **CLOSED ✓** — ISS-095 already-fixed (da172056); ISS-076 won't-fix on frozen archive; e2e/README.md baseline updated |
| BUG-031 | ~~01-warmup.md~~ | ~~🔒 Operator approval~~ | **CLOSED ✓** — `stages: [manual]` already restored in commit `0228bf196` (2026-08-29) |
| ISS-112 | [06-frontend-components.md](06-frontend-components.md) | 🏗 Backend design | No FE attachment-ref data source — define backend API shape first |
| ISS-434 | [06-frontend-components.md](06-frontend-components.md) | 🏗 Backend design | `PipelineRunState.deliverableMimetype` missing — coordinate BE+FE |
| ISS-189 | [12-frontend-workflow.md](12-frontend-workflow.md) | 🔀 Cross-domain coord | ISS-228 family (saved workflow discards override) — clarify scope |
| ISS-197 | [12-frontend-workflow.md](12-frontend-workflow.md) | 🔀 Cross-domain coord | ISS-228 family — same as ISS-189 |
| ISS-362 | [12-frontend-workflow.md](12-frontend-workflow.md) | 🎯 Product decision | ReviewGatesSection zero-interaction model (ISS-306 class) |
| ISS-377 | [12-frontend-workflow.md](12-frontend-workflow.md) | 🎯 Product decision | Manifest vs. user-selections gate exclusivity — must align with ISS-419 |
| ISS-134 | [14-backend-api.md](14-backend-api.md) | 🏗 Architecture | Cancel-liveness: process-local dict breaks ECS multi-container |
| ISS-419 | [14-backend-api.md](14-backend-api.md) | 🎯 Product decision | Gate seeding reverses FIX-377 / ADR-0013 — 3 options on card |
| ISS-119 | ~~14-backend-api.md~~ | ~~✅ Close decision~~ | **CLOSED ✓** — routing tests already reconciled upstream |
| ISS-133 | ~~14-backend-api.md~~ | ~~✅ Close decision~~ | **CLOSED ✓** — stale duplicate of ISS-125/FIX-421 |
| ~~ISS-161~~ ✓ | ~~14-backend-api.md~~ | ~~👁 Human review~~ | **CLOSED ✓** — already fixed by Phase 33/43 Concierge wiring (`chat_router.py:215`) |
| ISS-398 | [14-backend-api.md](14-backend-api.md) | 👁 Human review | Sibling of ISS-292 — confirm fix shape and approve |
| ~~ISS-422~~ ✓ | ~~14-backend-api.md~~ | ~~👁 Human review~~ | **CLOSED ✓** — truncated badge in `ChatAttachments.tsx`; `_build_attached_files_block` reads `entry["truncated"]` |
| ~~ISS-180, ISS-181, ISS-263, ISS-381~~ | [14-backend-api.md](14-backend-api.md) | 🔀 Cross-domain coord | ISS-263 **CLOSED ✓** (superseded by ISS-381); ISS-180/181/381 — `user_workflows.py` cluster, 3 remaining |
| ISS-105 | [14-backend-api.md](14-backend-api.md) | 🏗 Architecture | SSE uvicorn cancel + shutdown race — review fix approach before landing |
| ISS-096 | ~~15-backend-other.md~~ | ~~✅ Close decision~~ | **CLOSED ✓** — od-ppt-validator path mismatch; test green 14/14 |
| ISS-130 | ~~15-backend-other.md~~ | ~~✅ Close decision~~ | **CLOSED ✓** — hazard fixed upstream by KRN-005 |
| ~~ISS-132~~ ✓ | ~~15-backend-other.md~~ | ~~🎯 Product decision~~ | **CLOSED ✓** — Option A implemented: `invocation_gated=False` in `task_loop.py` |
| ISS-156 | ~~15-backend-other.md~~ | ~~✅ Close decision~~ | **CLOSED ✓** — mismatch not present on this branch |
| ~~ISS-630~~ ✓ | ~~15-backend-other.md~~ | ~~🧪 Test rewrite needed~~ | **CLOSED ✓** — autouse fixture stubs `build_model`; stale `analyzer_solution`/`+1`/`revision_analyzer_complete` assertions removed |
| ~~ISS-632~~ ✓ | ~~15-backend-other.md~~ | ~~🧪 Test rewrite needed~~ | **CLOSED ✓** — removed `[:2]`; count assertions use `len(specs)` |
| ~~ISS-634~~ ✓ | ~~15-backend-other.md~~ | ~~🧪 Test rewrite needed~~ | **CLOSED ✓** — `_drive_single_agent` uses `compiled_override` to bypass ADR-0008 |
| ~~ISS-638~~ ✓ | ~~15-backend-other.md~~ | ~~🎯 Product decision~~ | **CLOSED ✓** — 6 stale assertions fixed across 5 test files; 0 production changes |
| ~~ADR-0002~~ ✓ | ~~15-backend-other.md~~ | ~~🎯 Product decision~~ | **CLOSED ✓** — Option 3: `pipeline_type` is permanent on-wire/on-disk name; gate converted to skip |
| ISS-094 | ~~15-backend-other.md~~ | ~~✅ Close decision~~ | **CLOSED ✓** — already fixed upstream in engine.py |

---

## Decision types — legend

| icon | type | what it means |
|---|---|---|
| 🔒 | Operator approval | A human must review and sign off before the fixer can commit |
| 🎯 | Product decision | A product owner must choose between defined options — no "right answer" without a decision |
| 🏗 | Architecture / backend design | A design or infrastructure choice must be made before code can move |
| 🔀 | Cross-domain coordination | Fix spans multiple domain boundaries — needs sequencing / ownership assignment |
| 👁 | Human card review | Card is a stub or has unclear scope — a human needs to read and clarify it |
| ✅ | Close decision | Evidence strongly suggests the card should be closed (already fixed, not reproducible, or stale duplicate) — human confirms |
| 🧪 | Test rewrite needed | No production defect; test harness must be rewritten — needs an owner assigned |

---

## Suggested triage order

### 1 — ~~Easy closes~~ — ALL DONE ✓

~~These are very likely safe to close with a quick human confirmation:~~

- ~~**ISS-119**~~ ✓ routing tests already reconciled upstream
- ~~**ISS-133**~~ ✓ stale duplicate of ISS-125 (already shipped)
- ~~**ISS-094**~~ ✓ already fixed upstream
- ~~**ISS-096**~~ ✓ od-ppt-validator path doesn't exist, test passing
- ~~**ISS-130**~~ ✓ hazard already closed by KRN-005
- ~~**ISS-156**~~ ✓ mismatch not reproducible on current branch

### 2 — Linked product decisions (must decide together)

These three cards are intertwined — deciding one unlocks the others:

- **ISS-419** (domain 14) + **ISS-377** (domain 12) + **ISS-362** (domain 12)
  All hinge on the same question: what is the intended gate-seeding and
  exclusivity model when `user_allowed=False` gates appear in a manifest?
  Read the 3 options on the ISS-419 card, choose one, then ISS-377 and
  ISS-362 follow.

- **ISS-132** — N sequential per-task gates: choose one of the 3 fix shapes
  on the card and assign an owner.

- **ADR-0002** — `pipeline_type` rename go/no-go: either schedule it as a
  coordinated breaking release or formally defer it. Nothing else is blocked
  by this, but the card should not remain open indefinitely.

### 3 — Architecture decisions (need design before coding)

- **ISS-134** — cancel-liveness shared-signal store for ECS
- **ISS-105** — SSE uvicorn cancel/shutdown race fix approach
- **ISS-112** + **ISS-434** — define `attachmentRef` and `deliverableMimetype`
  backend API shape, then unblock the FE fixes

### 4 — Cross-domain / coordination

- **ISS-180, ISS-181, ISS-263, ISS-381** — read the four cards, map cross-file
  deps, sequence the fixes
- **ISS-189 + ISS-197** — clarify ISS-228 family scope across LaunchWizard /
  domain boundaries
- **ISS-398 + ISS-422** — human reviews the sibling fix shapes and approves

### 5 — Test rewrites (assign to 4-test-writer)

Once ADR-0008 is confirmed intentional:

- **ISS-630** — rewrite integration tests to match post-refactor contract
- **ISS-632** — drop `[:2]` slice, derive counts from full roster
- **ISS-634** — use `execute(compiled_override=…)` seam instead of `[:2]`
- **ISS-638** — four per-row stale assertion updates (after owner decisions above)

### 6 — Operator approvals (need a commit review)

- **BUG-031** — review `.pre-commit-config.yaml` change
- **ISS-076 / ISS-095** — confirm freeze or allow docs-only update pass

---

## Domain coverage

| domain file | escalated cards |
|---|---|
| [01-warmup.md](01-warmup.md) | ISS-076, ISS-095 *(operator-review)*, BUG-031 *(operator-review)* |
| 02-frontend-settings.md | — none — |
| 03-frontend-lib.md | — none — |
| 04-tests-integration.md | — none — |
| 05-frontend-preview.md | — none — |
| [06-frontend-components.md](06-frontend-components.md) | ISS-112, ISS-434 |
| 07-frontend-library.md | — none — |
| 08-frontend-routes.md | — none — |
| 09-frontend-history.md | — none — |
| 10-frontend-composer.md | — none — |
| 11-frontend-hooks.md | — none — |
| [12-frontend-workflow.md](12-frontend-workflow.md) | ISS-189, ISS-197, ISS-362, ISS-377 |
| 13-frontend-layout.md | — none — |
| [14-backend-api.md](14-backend-api.md) | ISS-134, ISS-419, ISS-119, ISS-133, ISS-161, ISS-398, ISS-422, ISS-180, ISS-181, ISS-263, ISS-381, ISS-105 |
| [15-backend-other.md](15-backend-other.md) | ISS-096, ISS-130, ISS-132, ISS-156, ISS-630, ISS-632, ISS-634, ISS-638, ADR-0002, ISS-094 |
