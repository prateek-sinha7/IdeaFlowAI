---
id: BUG-R01-resume
type: bug
status: done
area: [resume, agents]
summary: >-
  clarify answer black-holes after a backend restart (re-arm never re-creates the
  awaiting coroutine)
source: .planning/RESUME-QA-BUG-LOG.md#bug-r01
campaign: resume
severity: "severity 🔴 major"
---

### BUG-R01 — clarify answer black-holes after a backend restart (re-arm never re-creates the awaiting coroutine)  [severity 🔴 major] [FIXED ✅]
- **Found by:** R-clarify-restart on 2026-07-19 · run id `75979e2c-c02a-480a-8610-051f6b9ff785` (od_prototype, parked at the 5-question clarify questionnaire)
- **Symptom:** `kill -9` + bare-uvicorn restart. Restore logged `restored 2 resumable run(s), auto-resumed 0, marked 0 abandoned failed` (status correctly stayed `waiting_for_user`) AND `WARNING _replay_clarify_run(75979e2c-...): empty agent list — nothing to replay`. Questions replayed byte-identical (durable `questionnaire_ready`, event count 6->6, zero model re-gen). Then `POST /api/runs/75979e2c-.../answers` with 5 valid responses returned HTTP 200 `{"ok":true,"count":5}` (answers STORED) but the run stayed `waiting_for_user` indefinitely (0 new events after 40s+, no submission log activity). Discriminating control: a FRESH never-crashed od_prototype clarify run (`0139f9de-...`) submitted the identical payload shape and immediately proceeded (`waiting_for_user`->`generating`, events 6->187 in ~5s). The ONLY difference is the restart.
- **Expected:** after restart, a clarify answer over `POST /{id}/answers` proceeds into the normal planner->agents dispatch exactly as a never-restarted run (Phase 49 SC-4/SC-5; RESUME-17).
- **Investigation:** See "Shared root cause" above. Clarify-specific bail: `_replay_clarify_run` (engine.py:7556) reads `pipeline_type = wr.type = "od_prototype"` (7584), calls `get_pipeline_agents("od_prototype")` (7601) which returns `[]` (id-alias, no own AGENT.md -- verified `len 0` offline; register line 254), hits `if not agents:` -> logs the observed warning + `_fire_resume_cleanup` + returns (7608-7613) BEFORE `_drive_resumed_stream` (7682). So `_execute_impl` is never re-driven with `_clarify_replay` and `ClarifyEngine.run`'s `await event.wait()` (clarify_engine.py:299) is never re-established; the answer's `event.set()` (store.py:80-81) has no listener. Classification: v3.0 / Phase 49 regression (the fail->re-arm flip turned KAN-88's honest WR-05 failure into a silent black hole for od_prototype). Coverage hole: `test_clarify_parked_run_replays_durable_questions_and_proceeds` (test line 2827) passes only because `_ResumeHarness._patched_gpa` (244-245) returns fixture specs for `_FIXTURE_ID="sample_wave"`; no test seeds the aliased `od_prototype` against the real `get_pipeline_agents`.
- **Fix:** design in "Shared root cause" -> Fix. Change `_replay_clarify_run` (engine.py:7601) to `get_pipeline_agents(resolve_alias(pipeline_type))`. Its own gsd-quick with a RED->GREEN aliased-clarify restart test + live re-proof on od_prototype. Deferred to that task (analysis only here).
