# Deferred Items — Phase 11

Out-of-scope discoveries logged during execution (NOT fixed in-plan).

## 11-03

- **`tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack` fails on clean HEAD.**
  Verified pre-existing: the failure reproduces on commit `363b7f0` (Task-1) with all
  11-03 Task-2 changes stashed, so it is NOT caused by this plan's merge dispatch. It is
  in the cancel-path subsystem (the 11-05 territory). Left untouched per the SCOPE
  BOUNDARY rule (only auto-fix issues directly caused by the current task's changes).
