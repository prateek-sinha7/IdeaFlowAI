---
id: BUG-R02-resume
type: bug
status: done
area: [resume, agents]
summary: >-
  review-gate approve/all-actions black-hole after a backend restart (same
  empty-roster re-arm no-op)
source: .planning/RESUME-QA-BUG-LOG.md#bug-r02
campaign: resume
severity: "severity 🔴 major"
---

### BUG-R02 — review-gate approve/all-actions black-hole after a backend restart (same empty-roster re-arm no-op)  [severity 🔴 major] [FIXED ✅]
- **Found by:** R-review-restart on 2026-07-19 · run id `0139f9de-5d89-4b1d-a4c4-2da69d73674c` (od_prototype, parked at the spec review gate; gate_key `0139f9de...:prototype-specify`; also served as BUG-R01's fresh-clarify control before it reached this gate)
- **Symptom:** `kill -9` + restart. Restore logged `restored 3 resumable run(s), auto-resumed 0 in-flight, marked 0 abandoned failed` THEN `WARNING resume_run(0139f9de-...): empty agent list — nothing to resume`. Post-restart status correctly stayed `waiting_for_user`, `review_gate_ready` sha unchanged (spec preserved), gate UI re-rendered pixel-identical (D-14g on attach). BUT `POST /api/runs/0139f9de.../gate {"action":"approve","gate_key":"...:prototype-specify"}` returned HTTP 200 `{"ok":true,"action":"approve"}` yet the run stayed `waiting_for_user` with event count frozen at 2648 and ZERO progression after 48s+. Approve black-holes exactly like the clarify answer. The gate parked AFTER the spec-writer agent completed (its `agent_complete` is durable), confirming the bail is NOT about missing durable step state -- it is purely the empty roster.
- **Expected:** after restart, all five gate actions (approve/reject/edit/redo/update_specs) over `POST /{id}/gate` work identically to a never-restarted run and drive the run downstream (Phase 49 SC-3; RESUME-17).
- **Investigation:** See "Shared root cause" above. Review-specific bail: `_rearm_gate_run` routes an open review gate to `resume_run(run_id)` (engine.py:5469). `resume_run` (7233) reads `pipeline_type = wr.type = "od_prototype"` (7265), calls `get_pipeline_agents("od_prototype")` (7298) -> `[]`, hits `if not agents:` -> logs the observed warning + `_fire_resume_cleanup` + returns (7304-7308) BEFORE `_compute_resume_offset` (7314) and the 49-02 offset-override/`gate_reentry` re-entry. So `_run_review_gate`'s `await event.wait()` (engine.py:5105) is never re-established; the approve's `event.set()` (store.py:143-144) has no listener. The re-arm reads/keys on the run's registry agent MEMBERSHIP (`get_pipeline_agents(wr.type)`), NOT the durable compiled plan -- and that lookup returns empty for the aliased type even though the spec agent already completed. Classification and coverage hole identical to BUG-R01: `test_gate_reentry_all_five_actions_post_restart` (test line 1251) and the branch-(a) re-arm tests (e.g. line 975) all use `_FIXTURE_ID="sample_wave"` with `_patched_gpa` non-empty; KAN-88 (887-909) asserts status-stays + not-driven but never asserts a post-restart `POST /gate` advances the run.
- **Fix:** design in "Shared root cause" -> Fix. Change `resume_run` (engine.py:7298) to `get_pipeline_agents(resolve_alias(pipeline_type))` (same one-line pattern; fixes the review twin AND the pre-existing branch-(b) mid-build auto-resume of od_prototype in one place). Its own gsd-quick with a RED->GREEN aliased-review restart test (all five actions) + live re-proof on od_prototype. Deferred to that task (analysis only here).

---

- **RESOLUTION (BUG-R01 + BUG-R02 FIXED — gsd-quick 260719-ghn, commit `e1866317`):** `get_pipeline_agents(resolve_alias(pipeline_type))` at engine.py:7298 (`resume_run`) + :7601 (`_replay_clarify_run`) — the raw-type roster lookup now resolves the `od_prototype`→`prototype` id-alias, so the roster is non-empty and neither driver bails. Removing the bail UNMASKED BUG-R05 (see below), fixed separately. Full live end-to-end proof (gate re-entry → approve → proceeds) in RESUME-QA-TEST-SHEET.md 'POST-FIX RE-TEST'. RED→GREEN (2 alias-roster tests), goldens 10/10, 52 resume tests, lint 4/0.
