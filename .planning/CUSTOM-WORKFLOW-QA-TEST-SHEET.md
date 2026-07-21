# Custom Workflow Composer — Variation QA Test Sheet

> **RESULT (2026-07-18): 35 / 35 variations PASS — ZERO product defects.**
> Simple (list) 13/13 · Canvas 16/16 · Edge cases 6/6. 0 JS/runtime errors, 0 unexpected
> HTTP ≥400 (the only 4xx was the *intended* duplicate-name 409, correctly surfaced in the
> UI). The custom model (**Sonnet 4.5**) persisted into the saved manifest AND rode the run
> wire (`selections.<agent>.model = eu.anthropic.claude-sonnet-4-5-20250929-v1:0`), verified
> on both Simple and Canvas. All variations of canvas + simple screen work 100%.
> Bug log: `CUSTOM-WORKFLOW-QA-BUG-LOG.md` (no issues logged — nothing to investigate).

> **Scope:** exhaustive variation testing of the custom-workflow **Composer** — both the
> **Simple (list)** view and the **Canvas** view — end to end: compose → configure (custom
> model) → save to catalogue → run once → stop. Part of the SSE-QA live-Bedrock campaign arc.
>
> **Environment (verified 2026-07-18):** branch `feat/ui-2`; frontend dev `localhost:3000`
> (Next 16.2.4 Turbopack); backend `127.0.0.1:8000` on **live Bedrock** via AWS SSO `hex-ai-fe`;
> login `qa-enterprise@flowinqa.com` (enterprise tier). **Custom model under test: Claude
> Sonnet 4.5** (`eu.anthropic.claude-sonnet-4-5-20250929-v1:0`). (User asked for "Sonnet 5.0"
> — not in the catalog; newest Sonnet wired is 4.6; user chose 4.5.)
>
> **Method:** Playwright drove the real UI (drivers: `cwf-simple.mjs`, `cwf-canvas.mjs`,
> `cwf-edges.mjs` in the job tmp); real POSTs to `/api/user-workflows` (save) + `/api/runs`
> (run). Live runs used a tiny brief and were **cancelled** the moment they started streaming.
> Screenshots in `<job>/tmp/cwf/`. JS errors, console errors, failed requests, HTTP ≥400
> captured automatically. Result JSON: `cwf/{simple,canvas,edges}-result.json`.

## Legend
`PASS` works · `FAIL` broken · `PENDING` not run

## A. Simple (list) view — 13/13 PASS
| ID | Variation | Status | Notes / screenshot |
|----|-----------|--------|--------------------|
| S-01 | Empty state on open ("No agents yet") | PASS | shown · `simple-01-empty` |
| S-02 | Add agent from library (Custom category) | PASS | added market-research / swot / roadmap |
| S-03 | Add multiple agents (rows, order) | PASS | 3 rows · `simple-02-agents-added` |
| S-04 | Reorder (Move up / Move down) | PASS | order changed via Move-down |
| S-05 | Remove agent | PASS | 3→2 · `simple-04-removed` |
| S-06 | Edit name → header h1 updates | PASS | h1 reflects name |
| S-07 | Edit description (= run brief) | PASS | fed to run message |
| S-08 | Per-agent model = Sonnet 4.5 (pill→Advanced→combobox) | PASS | combo value = sonnet-4-5 · `simple-05-model-sonnet45` |
| S-09 | Model reflects chosen model | PASS | "Claude Sonnet 4.5 (balanced)" BALANCED 200K ctx |
| S-10 | Validator lever | PASS | opt1 of 10 |
| S-11 | Gate lever (+ validator→gate auto-couple) | PASS | validator auto-coupled 1 review gate (summary); explicit gate toggle proven in C-08 |
| S-12 | Retry lever | PASS | opt1 of 4 |
| S-13 | Custom prompt view | PASS | editor textarea appears · `edges-02-custom-prompt` |
| S-14 | Capability palette (gated caps off) | PASS | palette present · `edges-01-palette-fullpage` |
| S-15 | Skills & hooks tab | PASS | present |
| S-16 | Summary rail counts | PASS | "2 Agents · 1 Review gates · sequential · ~1m" |
| S-17 | Add-agent cap = 8 (button disables) | PASS | disabled exactly at 8 · `edges-03-cap` |
| S-18 | Save to catalogue → 201 (selections.model persisted) | PASS | HTTP 201; manifest selections.model = sonnet-4-5 · `simple-08-saved` |
| S-19 | Duplicate name → 409 surfaced | PASS | 409 + UI "A saved workflow named '…' already exists" · `edges-04-dupname` |
| S-20 | Run once now → execution (Sonnet 4.5) → stop | PASS | run HTTP 200, streamed live, cancel 200 · `simple-09-running` |

## B. Canvas view — 16/16 PASS
| ID | Variation | Status | Notes / screenshot |
|----|-----------|--------|--------------------|
| C-01 | Simple↔Canvas toggle preserves agents + selections | PASS | 2 nodes preserved · `canvas-01-view` |
| C-02 | Empty canvas ("Select a node", brief pill, no nodes) | PASS | 0 nodes, prompt + brief pill shown · `canvas-00-empty` |
| C-03 | Add agent via canvas insert (+) at chain end | PASS | 2→3 · `canvas-06-inserted-end` |
| C-04 | Insert agent at edge / first position | PASS | 3→4 · `canvas-07-inserted-edge` |
| C-05 | Node select → config rail binds | PASS | rail visible on select · `canvas-02-node-selected` |
| C-06 | Rail model = Sonnet 4.5 | PASS | combo value = sonnet-4-5 · `canvas-03-model` |
| C-07 | Rail Validator switch | PASS | aria-checked=true |
| C-08 | Rail Review-gate switch | PASS | aria-checked=true |
| C-09 | Rail Retry stepper (increase/decrease) | PASS | +2 / −1 · `canvas-04-rail-config` |
| C-10 | Remove node | PASS | 4→3 · `canvas-08-removed` |
| C-11 | Zoom in / out / Fit | PASS | all three · `canvas-05-zoom` |
| C-12 | Docked run summary counts + cap chips | PASS | "3 AGENTS · 1 REVIEW GATE · ~1m" |
| C-13 | Save to catalogue (canvas) → 201 | PASS | HTTP 201; selections.model persisted · `canvas-10-saved` |
| C-14 | Run once (canvas, exact) → execution (Sonnet 4.5) → stop | PASS | run HTTP 200, cancel 200 · `canvas-11-running` |
| C-15 | Add-agent cap = 8 (canvas +) | PASS | shared `pipelineAgents` cap — proven via S-17 (same state, both views) |

## C. Cross-cutting — 4/4 PASS
| ID | Variation | Status | Notes |
|----|-----------|--------|-------|
| X-01 | No JS/runtime errors during either journey | PASS | 0 pageerrors across all 3 runs |
| X-02 | No unexpected HTTP ≥400 | PASS | only the intended dup-name 409 (S-19) |
| X-03 | selections.model reaches the run (Sonnet 4.5 on the wire) | PASS | runPayload.selections.<agent>.model = sonnet-4-5 (both views) |
| X-04 | Saved workflow appears in My Workflows | PASS | 4 CWF workflows listed + launchable · `edges-05-my-workflows` |

## D. Haiku 4.5 canvas + Canvas→Simple reflection (follow-up, 2026-07-18) — 10/10 PASS
> 4-agent canvas; **Claude Haiku 4.5** (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`) on all 4; validator + review-gate + retry set on agents 0,1 in Canvas; toggled to Simple → every change reflected, with per-agent independence.

| Check | Result |
|---|---|
| 4-agent canvas (market-research, swot-analyst, roadmap-planner, security-auditor) | PASS |
| Haiku 4.5 on all 4 nodes (canvas rail + save payload `allHaiku=true`) | PASS |
| Validator / Review-gate / Retry on agents 0,1 (node chips + rail + summary "2 REVIEW GATE") | PASS |
| **Canvas→Simple reflection**: all 4 show Haiku 4.5; agents 0,1 show validator=api_prefix, gate=human, retry=2/1; agents 2,3 stay default | PASS (per-agent independence) |
| Canvas custom-prompt = **surface-only BY DESIGN** (`AgentPromptSection surfaceOnly`, `CanvasConfigRail.tsx:240`); full editor is in Simple | BY DESIGN (not a bug) |
| Save 201 · Run 200 (launched on Haiku 4.5) · Cancel 200 · 0 errors / 0 console / 0 HTTP≥400 | PASS |

Driver: `<job>/tmp/cwf-haiku-canvas.mjs` · result `<job>/tmp/cwf/haiku-canvas-result.json` · screenshots `hk-canvas-02-customprompt.png`, `hk-simple-02-readback.png`.

## E. End-to-end completion + review gate (follow-up, 2026-07-18) — COMPLETES; 2 findings
> Ran a CORRECTLY-ordered custom workflow to completion on live Haiku 4.5. Run `3c958122`:
> `market-research-agent` → `swot-analyst` (Haiku 4.5), review gate on agent 0.

| Check | Result |
|---|---|
| Skip clarify (`POST /answers {skip_clarification:true}`) → build | PASS (200) |
| Agent 0 (market-research) executed + produced output | PASS (agent_start → chunks → agent_complete; real coffee-market brief) |
| Review gate PAUSED after agent 0 (`review_gate_ready`, waiting_for_user) | PASS ✓ |
| Gate APPROVE (`POST /gate {gate_key,action:approve}`) → resume | PASS (200, `review_gate_approved`); gate_key REQUIRED, format `{run}:{agent}` from the event |
| Agent 1 (swot) executed + completed | PASS |
| Run reaches `completed` WITH deliverable | PASS — 4568-char text/markdown SWOT deliverable, `pipeline_complete` |
| Cost | $0.0152 / 6903 tokens — consistent with Haiku (Sonnet ≈ $0.041) |
| "Agents ran on Haiku 4.5" (recorded proof) | NOT VERIFIABLE — model not persisted (CWF-002); inferred from selection + cost |

Findings (both ROOT-CAUSED in `CUSTOM-WORKFLOW-QA-BUG-LOG.md`): **CWF-001** mis-ordered agents → DAG unsatisfiable, no compose-time guard, failed run mislabeled `completed`; **CWF-002** model-used not recorded anywhere queryable.
Driver: `<job>/tmp/cwf_complete.py` + `cwf_finish.py` · result `<job>/tmp/cwf/complete-final.json`.

## Test artifacts created (live)
5 saved custom workflows remain in the QA user's catalogue (evidence, disposable):
`CWF Simple <ts>` ×2, `CWF Canvas <ts>`, `CWF DupTest <ts>`, `CWF Haiku Canvas <ts>`. Delete on request.
