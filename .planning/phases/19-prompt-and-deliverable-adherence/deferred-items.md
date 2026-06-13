# Phase 19 — Deferred / Out-of-Scope Items

## Pre-existing test failure (NOT introduced by 19-02 / ISS-005)

- **Test:** `backend/tests/agents/test_phase5_revision_validation.py::TestEventVocabularyUnchanged::test_event_types_subset_of_documented_vocabulary`
- **Symptom:** `prototype_revision` (with fix-loop) emits an UNDOCUMENTED `gate_blocked`
  event in the offline harness; the test asserts the emitted event types are a subset of
  the documented frontend vocabulary.
- **Proven pre-existing:** Fails identically with the 19-02 working changes stashed
  (`git stash` → run → still FAILED), so it is independent of the api_prefix validator /
  post_step / registry edits. The 19-02 change touches `app_builder` + the capability
  registry only; it does not touch `prototype_revision`, the `validation` gate impl, or
  the documented event vocabulary.
- **Scope:** Out of scope for 19-02 (scope boundary: only auto-fix issues directly caused
  by the current task's changes). Not fixed here. Candidate for a focused follow-up in this
  phase or a debug pass — likely an offline-DB / FK-constraint interaction causing the
  validation gate to block in the harness.
