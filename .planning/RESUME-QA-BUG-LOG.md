# Resume QA Bug Log — milestone v3.0 live-Bedrock pass (feat/ui-2)

> Companion to [RESUME-QA-TEST-SHEET](./RESUME-QA-TEST-SHEET.md). Numbering **BUG-R01+** (separate series from the SSE campaign's BUG-001..016 in [SSE-QA-BUG-LOG](./SSE-QA-BUG-LOG.md)).
>
> **Discipline (established this project):** NO bug is logged from symptoms alone. Every ❌ first gets a dedicated deep-investigation agent (max effort) that reads `.planning/IMPLEMENTATION-REGISTER.md` **fully to EOF**, root-causes with file:line evidence, checks the finding against locked decisions (POR §8, INV-1/3/12/13), and classifies pre-existing vs v3.0-introduced (re-baseline against the pre-phase commit when "pre-existing" is claimed — see the pre-phase-baseline rule). Only then is the entry written here.
>
> **Entry states:** [OPEN] → [ROOT-CAUSED] → [FIXED ✅] (fix = its own gsd-quick task with RED→GREEN + live re-proof) · [WONTFIX/BY-DESIGN] with the register citation.

## Known-open pre-existing (carried in — do NOT re-log)

- **BUG-009 (SSE log)** — od_ppt can complete with an empty deck output (LV-02 recurrence; prompt-contract, not a resume defect).
- Offline-held red suites, each proven pre-existing at phase baselines: `redo_gate_safety` 4 passed/3 failed (harness drift) · `declared_gate_streaming` 3 FK env-reds · `test_migrations` 2 stale-head asserts · `attach_replay` 1 SSE red. Each wants its own future quick task.
- **AUD-1** — audit item, not a bug (yet): the auto-resume path's terminal-status write posture. Checked live by R-A1's final-DB-status assertion; if it fails, it becomes BUG-R01 with the `resume_run`-writes-no-status analysis from Phase 50 research as the head start.

## Template

```
### BUG-Rxx — <one-line defect statement>  [severity 🔴/🟠/🟡] [OPEN]
- **Found by:** R-<row> on <date> · run id <id>
- **Symptom:** <observed, with shot/transcript refs>
- **Expected:** <sheet row's expected proof>
- **Investigation:** <agent's root cause, file:line, register cross-refs, pre-existing-vs-v3.0 classification with baseline evidence>
- **Fix:** <quick-task id + commits + live re-proof> | deferred rationale
```

---

*(no entries yet — campaign not started)*
