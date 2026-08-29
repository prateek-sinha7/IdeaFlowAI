# Hunt state

## RUN — full line, stage=all (8th launch 2026-08-28 20:26 CEST) — COMPLETE

RUN         started 2026-08-28 20:26 CEST · closed 2026-08-29 03:03 UTC ·
              status **COMPLETE** — every one of the 92 register bugs reached a terminal
              status this run: 79 CLOSED, 7 ESCALATED, 4 DUPLICATE, 2 UNREPRODUCIBLE.
REGISTER    92 bugs, 0 remaining in a working phase (no Open/CONFIRMED/ANALYZED/TESTED/FIXED
              rows left — everything is CLOSED or a terminal non-CLOSED disposition).
REPORT      bug-hunter/reports/20260829-030330-all.md — full per-bug index, the 7 ESCALATED
              decisions a human needs to make, the 4 DUPLICATEs, 2 UNREPRODUCIBLE, 3 bugs that
              REOPENED once mid-run and were re-fixed/re-verified CLOSED, and the WONTFIX
              mirror (bug-hunter/wontfix-candidates.md — its one entry is now stale/superseded,
              the bug it describes was actually fixed, see the report's WONTFIX section).
CONSISTENCY tools/knowledge/validate_links.py: 12,121/12,123 links resolve. The 2 broken are
              both pre-existing (ISS-217→BUG-20260827-232305-root, ISS-328→ISS-341) and not
              introduced by this run. Register vs. card Status spot-checked across all 7
              ESCALATED bugs — no drift found (root cards genuinely resolved+passed; the bug
              stays escalated only because a documented sibling card is still open).
NEXT        Human review of the 7 ESCALATED decisions in the report (each names 2 concrete
              options). No further autonomous work queued — the register has nothing left to
              validate/analyze/test/fix/verify. A fresh hunt pass would need new bug reports or
              a wider surface sweep to have anything to work on.

### What this run did (8th launch through close)

Picked up from the 7th launch's pause (~20 Open bugs, 1 fixed-pending-verify) and ran the
full validate→analyze→test→fix→verify assembly line to completion. Roughly 60+ card-minting
agents ran concurrently across the run; card-ID allocation races were frequent (a dozen+
self-detected collisions, all repaired in place — see "Card-ID concurrency" below) but no
card content was lost. Backend AWS/Bedrock credentials, which were broken at the start of the
7th launch, were valid throughout this run, so live-pipeline surfaces (real agent runs, the
`/stream` view, live gates) were testable for the first time this hunt.

Highlights, not exhaustive — see the report for the full per-bug index:
- Every remaining CONFIRMED/ANALYZED bug from the 7th launch's backlog was carried through
  test→fix→verify to CLOSED, except the 13 that landed on a terminal non-CLOSED status.
- Several root-cause corrections happened mid-run: an analyzer would re-derive a root cause
  that contradicted an earlier validator/analyzer's card (e.g. ISS-232 correcting ISS-... on
  the library-skills cold-mount race; ISS-363 correcting ISS-258's route-editor mechanism;
  ISS-374 correcting ISS-253's file attribution). Corrections are recorded on the corrected
  card, not silently overwritten.
- Three bugs reopened once during verify (see report) and were successfully re-fixed.
- Two fixers ESCALATED rather than build an unrequested backend persistence surface the
  4-test-writer's shipped test implicitly demanded (the two `library-agents-id` "fake save"
  bugs) — flagged as a product decision, not guessed at.

### Card-ID concurrency (worth fixing before the next large parallel wave)

Recurred constantly this run: two+ concurrent agents both read the card-store max, both
compute the same next id, both write — one silently overwrites (rare, self-detected via a
re-check) or both self-detect via `ls` and renumber. Every instance this run was caught and
repaired without data loss, but it cost real time across dozens of phase results. Worth adding
a locking/reservation step (e.g. an atomic mkdir-based lock on the id, or a central allocator)
before the next run that dispatches this many parallel card-minting agents at once.

Tree: /Users/bilala/Developer/Projects/VELOCITY-AI (branch feat/bug-hunter) — servers confirmed
      watching this checkout throughout.

---

Started: 2026-08-27 UTC · scaled to full registry 2026-08-27 22:20 UTC
CLEAN_STREAK_REQUIRED = 2
PAGE_REGISTRY = 55 pages (p33 /runs/<diverted> RESTORED 03:13 — 15 diverted runs exist, hidden behind the /runs 50-row cap; p56 is a state of p34, not a page)
Scheduling: BREADTH-FIRST — r1 across all pages, then r2, etc.
Dispatch mode: SERIALIZED — one worker at a time (all agents share one Playwright MCP Chrome)

| # | page | route | slug | round | active_worker | bugs | clean | blocked | status | last_probe_focus |
|---|---|---|---|---|---|---|---|---|---|---|
| p01 | Login | `/login` | login | 2 | — | 1 | 1 | 0 | READY | r2 password reveal, keyboard, long inputs; r2 clean: 5 candidates deduped, open-redirect safe |
| p02 | Login (expired banner) | `/login?expired=true` | login-expired-true | 2 | — | 2 | 0 | 0 | READY | r2 returnTo after expiry + banner lifecycle; r2 BUG-...-101500 expiry drops destination, redirect param unused |
| p03 | Login (expired=1, no banner) | `/login?expired=1` | login-expired-1 | 2 | — | 1 | 0 | 0 | READY | r2 toast container + extreme viewports; r2 BUG-...-041815 login error not announced |
| p04 | Register redirect stub | `/register` | register | 2 | — | 1 | 1 | 0 | READY | r2 stub redirect + traversal on sub-paths; r2 clean: traversal is class-4 fallback, no new surface |
| p05 | Root branch | `/` | root | 2 | — | 1 | 1 | 0 | READY | r2 stacked bounces + back after signin via /; r2 clean: all 3 token states correct, class-1 dup only |
| p06 | Dashboard | `/dashboard` | dashboard | 2 | — | 1 | 1 | 0 | READY | r2 launch panels + recent runs + keyboard; r2 clean: cards are buttons, routes verified |
| p07 | Create (dashboard alias) | `/create` | create | 2 | — | 2 | 0 | 0 | READY | r2 composer/advanced modal from /create; r2 BUG-...-051530 seeded manifest fails save 422 |
| p08 | PPT wizard | `/create/ppt` | create-ppt | 2 | — | 2 | 0 | 0 | READY | r2 other templates + save flows; r2 BUG-...-052800 save-as-my-version discards brief+template |
| p09 | Prototype wizard | `/create/prototype` | create-prototype | 2 | — | 2 | 0 | 0 | READY | r2 advanced modal + upload flows; r2 BUG-...-053300 raw errno on url import; save-discard confirmed shared |
| p10 | Create app panel | `/create/app` | create-app | 2 | — | 2 | 0 | 0 | READY | r2 attach file + save-as-version + workflow tab; r2 BUG-...-053745 silent text-attachment truncation |
| p11 | User-stories panel | `/create/user-stories` | create-user-stories | 2 | — | 2 | 0 | 0 | READY | r2 skills/hooks tabs + agent add/remove; r2 BUG-...-054500 add-agent default tab always empty |
| p12 | Fixture launch panel | `/create/ex_A2_branch` | create-ex-a2-branch | 2 | — | 2 | 0 | 0 | READY | r2 sibling fixtures + prompt-user toggle; r2 BUG-...-055300 human gate invisible in UI |
| p13 | Workflow create ppt redirect | `/workflow/create?mode=ppt` | workflow-create-ppt | 2 | — | 1 | 1 | 0 | READY | r2 case sensitivity + signed-out round trip; r2 clean: no client-nav asymmetry here |
| p14 | Workflow create prototype redirect | `/workflow/create?mode=prototype` | workflow-create-prototype | 2 | — | 2 | 0 | 0 | READY | r2 remaining leads: case + signed-out; r2 BUG-...-060000 mode param path traversal to /admin |
| p15 | Saved workflows | `/workflows` | workflows | 2 | — | 2 | 0 | 0 | READY | r2 delete dialog naming + new/run buttons; r2 BUG-...-052400 delete dialog names nothing |
| p16 | Empty composer | `/workflows/new` | workflows-new | 2 | — | 2 | 0 | 0 | READY | r2 save flows + sub-agent nesting; r2 BUG-...-060700 empty-name save silent no-op |
| p17 | Workflow detail | `/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` | workflows-id | 2 | — | 1 | 1 | 0 | READY | r2 traversal + edit affordance; r2 clean: traversal reaches no privilege boundary |
| p18 | Workflow edit composer | `/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/edit` | workflows-id-edit | 2 | — | 1 | 1 | 0 | READY | r2 skills/hooks fidelity + concurrent edit; r2 clean: model override persists, picker populated |
| p19 | Built-in canvas | `/workflows/ppt/canvas` | workflows-ppt-canvas | 2 | — | 2 | 0 | 0 | READY | r2 immutability via navigate-away + simple view; r2 BUG-...-073350 canvas vs simple deliverable mismatch |
| p20 | Saved workflow launch panel | `/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/run` | workflows-id-run | 2 | — | 2 | 0 | 0 | READY | r2 cold-load race on saved override; r2 BUG-...-073900 override loses fetch race, generic wizard |
| p21 | Legacy builder | `/workflow` | workflow | 2 | — | 2 | 0 | 0 | READY | r2 signed-out auth gate on orphan builder; r2 BUG-...-074900 stale attachment marker |
| p22 | Run history | `/runs` | runs | 2 | — | 2 | 0 | 0 | READY | r2 run card nav + actions menu; r2 BUG-...-051900 header token count wrong |
| p23 | Run detail Preview | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e` | runs-id | 2 | — | 2 | 0 | 0 | READY | r2 chat composer + download/share; r2 BUG-...-095700 chat timestamps recompute on reload |
| p24 | Run Steps | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps` | runs-id-steps | 2 | — | 2 | 0 | 0 | READY | r2 row expansion + back/forward; r2 BUG-...-080047 [object Object] in tool-call summary |
| p25 | Agent step detail | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps/<agentId — resolve from Steps>` | runs-id-steps-agent | 2 | — | 1 | 1 | 0 | READY | r2 in-app nav to step detail + cross-run ids; r2 clean: no in-app agent URL exists; no traversal surface |
| p26 | Run Files | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files` | runs-id-files | 2 | — | 2 | 0 | 0 | READY | r2 empty-state + per-row preview; r2 BUG-...-082706 size labels use char count not bytes |
| p27 | Run Workspace | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/workspace` | runs-id-workspace | 2 | — | 1 | 1 | 0 | READY | r2 D-02 routing consequences + tree; r2 clean: D-02 resolved, sizes correct here |
| p28 | Run Audit | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/audit` | runs-id-audit | 2 | — | 2 | 0 | 0 | READY | r2 filters/empty state/refetch; r2 BUG-...-audit-export-r2 export loses category+severity |
| p29 | Full-bleed preview | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/preview/full` | runs-id-preview-full | 2 | — | 2 | 0 | 0 | READY | r2 keyboard slides + viewport + missing run; r2 BUG-...-084621 fullscreen btn offscreen at 375px |
| p30 | Run stream view | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/stream` | runs-id-stream | 2 | — | 2 | 0 | 0 | READY | r2 live run now possible with valid creds; r2 BUG-...-085047 download disabled on live-completed run |
| p31 | Failed run detail | `/runs/a85e46a6-0485-4447-9c4f-ce572a1b4f23` | runs-failed | 2 | — | 2 | 0 | 0 | READY | r2 reopen-from-failed-step + per-agent errors; r2 BUG-...-085400 steps panel frozen at 'Run failed' during live resume |
| p32 | Cancelled run detail | `/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3` | runs-cancelled | 2 | — | 2 | 0 | 0 | READY | r2 version picker + share/download on cancelled; r2 BUG-...-085830 status stuck cancelled after real failure |
| p33 | Diverted run detail | `/runs/940ca699-b21b-4666-8e44-3370a08a4561` | runs-diverted | 2 | — | 2 | 0 | 0 | READY | r2 successor link + files/workspace/audit tabs; r2 BUG-...-090219 workspace false claim on diverted |
| p34 | Run pinned to version | `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/versions/1` | runs-id-versions | 2 | — | 2 | 0 | 0 | READY | r2 download/share carry pinned version; r2 BUG-...-090732 tab click drops pinned version, serves v1 |
| p35 | Library Agents | `/library` | library | 2 | — | 2 | 0 | 0 | READY | r2 pills/agents tab/drawer mapping; r2 BUG-...-050115 direct URL bypasses disabled-agent gating |
| p36 | Library Skills | `/library?tab=skills` | library-skills | 2 | — | 2 | 0 | 0 | READY | r2 card-to-drawer mapping at 186 scale; r2 BUG-...-091300 skill detail renders wrong content (regression?) |
| p37 | Library Hooks | `/library?tab=hooks` | library-hooks | 2 | — | 2 | 0 | 0 | READY | r1 keyboard-inaccessible cards (BUG-...-025521) + r2 copy-no-feedback (BUG-...-025500); r1 ran 42m, my STALLED call was wrong |
| p38 | Agent drawer | `/library/agents/<first card>` | library-agents-id | 2 | — | 2 | 0 | 0 | READY | r2 verify detail-route regression scope + composer cross-check; r2 BUG-...-092630 skills Add false success, no persist |
| p39 | Skill drawer | `/library/skills/<first card>` | library-skills-id | 2 | — | 2 | 0 | 0 | READY | r2 confirm regression + composer cross-surface; r2 BUG-...-093400 raw markdown in composer skill modal; both prior skill-detail bugs now stale |
| p40 | Hook drawer | `/library/hooks/post-design-quality` | library-hooks-id | 2 | — | 2 | 0 | 0 | READY | r2 hook preview markdown + close-state; r2 BUG-...-093757 close resets list filters |
| p41 | Settings Profile | `/settings/profile` | settings-profile | 2 | — | 2 | 0 | 0 | READY | r2 tabs/keyboard/readonly email; r2 BUG-...-050900 confirm field missing reveal toggle |
| p42 | Settings AI model | `/settings/ai-model` | settings-ai-model | 2 | — | 2 | 0 | 0 | READY | r2 rapid changes + mid-save nav; r2 BUG-...-094120 lost-update race, 200 reports wrong value |
| p43 | Settings Usage | `/settings/usage` | settings-usage | 2 | — | 2 | 0 | 0 | READY | r2 deliverable pills + pro tier + dead controls; r2 BUG-...-094937 direct-URL tier bypass to locked wizard |
| p44 | Settings Constitution | `/settings/constitution` | settings-constitution | 2 | — | 2 | 0 | 0 | READY | r2 unsaved-nav + does it reach agents; r2 BUG-...-095800 Clear deletes instantly, no confirm; constitution DOES reach agents |
| p45 | Settings Security | `/settings/security` | settings-security | 2 | — | 1 | 1 | 0 | READY | r2 keyboard nav + destructive-action patterns; r2 clean: static page, keyboard + cross-tier checked |
| p46 | Settings redirect | `/settings` | settings | 2 | — | 1 | 0 | 0 | READY | r2 tier-specific settings gating; r2 BUG-...-042311 client-nav 404s instead of redirect |
| p47 | Analytics | `/analytics` | analytics | 2 | — | 2 | 0 | 0 | READY | r2 model filter + daily chart + empty combos; r2 BUG-...-102900 tooltip raw integers; chart data correct |
| p48 | Admin | `/admin` | admin | 2 | — | 2 | 0 | 0 | READY | r2 sort, plan chip, duplicate email — NO grant; r2 BUG-...-103434 duplicate-email 409 swallowed silently |
| p49 | Handoff settings (secrets) | `/handoff/settings` | handoff-settings | 2 | — | 2 | 0 | 0 | READY | r2 api key list at scale + revoke + copy; r2 BUG-...-103900 whitespace key name never trimmed |
| p50 | Handoff not found | `/handoff/nope-not-real` | handoff-invalid | 2 | — | 1 | 0 | 0 | READY | r2 real expired/consumed token path; r2 BUG-...-042900 network error shown as not-found |
| p51 | 404 screen | `/this-route-does-not-exist` | not-found | 2 | — | 0 | 2 | 0 | CONVERGED | r2 FOUC race on 404; r2 clean: FOUC ruled out, storage write traced app-wide |
| p52 | Missing run | `/runs/00000000-0000-0000-0000-000000000000` | runs-nonexistent | 2 | — | 0 | 2 | 0 | CONVERGED | r2 SPA-nav stale content on dead run link; r2 clean: SPA nav, races, auth-loss all clean |
| p53 | Missing workflow | `/workflows/00000000-0000-0000-0000-000000000000` | workflows-nonexistent | 2 | — | 2 | 0 | 0 | READY | r2 dead-link canvas: run-once + other bad-id subroutes; r2 BUG-...-104200 dead-link Run once fires unshown 9-agent pipeline |
| p54 | Preview quota error | `/preview-fullscreen?error=quota` | preview-fullscreen-quota | 2 | — | 1 | 1 | 0 | READY | r2 ready-state controls + error param variants; r2 clean: opener safe-by-construction, quota branch genuinely reachable |
| p55 | Preview no payload | `/preview-fullscreen` | preview-fullscreen | 2 | — | 2 | 0 | 0 | READY | r2 real payload + download zip + resize persistence; r2 BUG-...-105300 markdown heading parsed as phantom file |

## Orchestrator recovery playbook (standing approval to continue unattended)

Check both servers answer before each dispatch (`:3000/dashboard`, `:8000/docs`). Rules:

| Symptom | Action |
|---|---|
| Worker returns BLOCKED, transient cause | Relaunch same page, same round+1. Two consecutive identical blockers -> mark BLOCKED, keep every other lane moving. |
| Worker returns malformed / no `RESULT:` line | Do NOT count as clean. Relaunch with a sharper prompt. |
| Worker silent > 45 min | **Do NOT trust transcript mtime — it does not update during long tool calls.** A worker has run 42m with a frozen mtime while fully alive. Never relaunch on idle alone: the only reliable signals are the task-completion notification and an explicit failure status. If truly worried, SendMessage the worker and wait; relaunch ONLY after a failed/errored notification. |
| `ledger.lock/` present with no active worker | Stale. Verify no worker is live, then `rmdir` it and note it in the report. |
| Frontend or backend not answering | Wait 60s, retest up to 5 times. Still down -> stop dispatching, record a dependency failure, do not fabricate results. |
| Playwright/Chrome wedged (navigate never returns) | Treat the page as BLOCKED-transient, relaunch once; a fresh worker gets a fresh browser context. |
| Session left signed out | Harmless: the brief tells every worker to sign in when no token is present. |
| Ledger append lost / evidence dir missing for a filed bug | Re-verify with grep; if truly missing, relaunch that page and note the loss. |

Never mark a page CONVERGED on anything but two explicit `RESULT: NO_NEW_BUG` returns.
Never stop the hunt because bugs are plentiful, or because a lane is slow.

---

## Live run notes — volatile, moved out of the worker brief 2026-08-28

Time-bound facts that were living in the standing brief. They are true as recorded and
will go stale; the brief has to stay durable, so they belong here.

## AWS/Bedrock credentials are now valid (updated 2026-08-28 ~08:05 UTC)
Earlier workers hit `AccessDeniedException` from Bedrock and correctly attributed it to the
environment rather than filing it. **That is fixed.** Agent replies and real pipeline execution
now work, which unlocks surfaces that were previously untestable:

- live-run states (a run actually progressing through agents, not just seeded terminal runs)
- the `/runs/<id>/stream` view against a genuinely live run
- live gate/clarification prompts and the human-gate fixtures (`ex_A4_*`)
- chat follow-ups on a run that can really respond

**Rules for launching a real run:**
- Only when your assignment genuinely needs a live run, and **at most ONE per invocation**.
- Say so explicitly in COVERAGE, with the run id you created.
- Prefer the cheapest workflow that exercises the behaviour; do not launch long pipelines to
  test a UI detail that a seeded run already demonstrates.
- Never cancel or delete another lane's seeded fixtures (`b9feac1c…` completed,
  `d6e425b6…` failed, `a8dfa959…` cancelled, `940ca699…` diverted).
- A run you launch is yours: it is fine to leave it completed, but do not abandon a run mid-gate
  waiting on human input — either answer the gate or cancel the run you started.

If you see a model/provider error now, it is a REAL finding, not environment noise — but verify
it twice and record the exact error before filing.

## Two ledger entries are STALE — pending human reconciliation
Verified 2026-08-28 09:34 UTC: the skill-detail route now works correctly for every id class
tested (hyphenated and no-hyphen, direct URL and card click, content matching the API). The
~08:30 UTC dev-server restart appears to have cleared it. These two entries were accurate when
observed but do NOT currently reproduce:

- `BUG-20260828-030430-library-skills-id` (Medium) — no-hyphen skill ids render the catalog
- `BUG-20260828-091300-library-skills-r2` (High) — all skill ids render wrong content

**Do not re-file either, and do not "confirm" them as still-broken without fresh evidence.**
A human will reconcile them. If you DO see the skill-detail route misbehave again, that is
new and important information — record the exact id, entry path and time.

---

# Accumulated hunt knowledge

Built up across rounds, not standing instruction — which is why it lives in state rather
than in an agent definition. Every hunter AND `2-validator` should read the bug classes
before filing or confirming anything.

## Emerging bug CLASSES — check before filing
Some defects recur across routes with one underlying cause. If your candidate matches a class
below, it is very likely a DUPLICATE: keep hunting instead of filing, unless yours is
independently actionable for a reason you can state in one sentence.

1. **Blank/unhydrated page after a history navigation.** Back (or Back-then-Forward) leaves a
   route permanently blank with no console error and healthy 200s; only a manual reload
   recovers. Already filed twice: on `/` (after a corrupt-token bounce) and on
   `/create/prototype` (Back→Forward). A third route showing the same shape is a duplicate.
2. **Unscoped browser-storage cache leaking across accounts.** Already filed for
   `sessionStorage['vlc_home_recents_v1']` (the catalog's "Jump back in"). Another key with the
   same unscoped-cache shape is the same root cause unless the leaked data is materially
   different in kind.
3. **Escape does not dismiss an overlay.** Already filed twice: the `/dashboard` catalog
   Inspect modal, and the `/workflows` card actions menu. It is also known on the Advanced
   workflow modal (D-22). The app-wide pattern is established — a THIRD route showing it is a
   duplicate, not a find. Only file it again if the overlay traps the user with no other exit
   (no close button, no outside-click dismissal), which makes it materially worse.
4. **An unknown/404 route silently renders the Dashboard while the URL stays put.** Already
   filed twice: `/register/<anything>` for an authenticated user, and `/workflows/<bad-id>/run`
   after a client-side 404. Both are the catch-all falling back to the dashboard instead of the
   404 screen. A third route with this shape is a DUPLICATE.
5. **A validation/requirement error that will not clear once satisfied.** Already filed twice:
   the settings password-mismatch error, and the `/create/ppt` unsatisfiable "Pick a design
   system" pill. A third instance needs a genuinely different mechanism to count.


## Resolved instances (use these, do not go hunting for ids)
- completed run `b9feac1c-ec21-4531-8ba7-bb391786993e`
- failed run `a85e46a6-0485-4447-9c4f-ce572a1b4f23`  (was d6e425b6…, which a resume test
  legitimately flipped to `cancelled` on 2026-08-28 08:54 UTC — do NOT use the old id for a
  failed-state test; 11 genuinely failed runs remain)
- cancelled run `a8dfa959-e233-4ddf-87ce-d9a942cefde3`
- saved workflow `656ca387-e69c-474d-b7ff-5fd9eb017cc0` ("My prototype")
- nonexistent uuid `00000000-0000-0000-0000-000000000000`
- API token: `curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json'
  -d '{"email":"qa-admin@flowinqa.com","password":"flowin-e2e-pass"}'` → `access_token`.
  Use the API only to inspect state, never as a substitute for driving the UI.


## Live lead — unsanitized params that build navigation targets
`/workflow/create?mode=../admin` escapes the `/create` namespace and lands on the live admin
console (filed, High). The `mode` value is interpolated into a route path with no sanitisation.

**If your page takes a param, id, slug or tab value that ends up in a URL path, test traversal**:
`../`, `%2e%2e%2f`, `..%2f`, and deeper forms (`../../settings`). Candidates include
`/create/<type>`, `/library/<kind>/<id>`, `/runs/<id>/<tab>`, `/workflows/<id>/<sub>`,
`/handoff/<token>`, and any `?tab=` / `?mode=` / `?category=` param.
A traversal that reaches a DIFFERENT route than the one filed is likely the SAME root cause —
report the reach and treat it as a duplicate unless it crosses a privilege boundary the filed
one does not. Never use a traversal to perform a destructive or privileged ACTION; observing
where it lands is enough.
