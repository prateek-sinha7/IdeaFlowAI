# Deferred Items — quick task 260703-d4v

## Pre-existing (out of scope) — NOT caused by this change

### `test_characterization_od_ppt.py::test_od_ppt_event_snapshot` fails at base HEAD

- **Discovered during:** Task 2 offline gate run (5 characterization goldens).
- **Symptom:** od_ppt normalized event stream diverges from the committed golden at
  index 3 (`agent_input` / `context_message` for `od-ppt-brief-analyst`).
- **Proven pre-existing:** Reverted `backend/app/api/prototype_templates.py` to its
  parent version (`max_length=8000`, i.e. before this task's change) and the same
  golden failed IDENTICALLY. This task only touches `RunRequest.brief` (an API
  request-body model on `POST /api/prototype/run`); the od_ppt golden drives the
  engine via `ndjson_adapter` and never constructs `RunRequest`, so it is impossible
  for this change to affect that stream.
- **INV-3 status:** UNAFFECTED by this change. The other 4 goldens
  (prototype, od_prototype, prototype_revision, app_builder) pass byte/event-identical
  with NO snapshot update.
- **Disposition:** Out of scope for 260703-d4v. Left for a dedicated investigation.
  Do NOT regenerate the golden here — the divergence is in the od_ppt context-message
  content, not related to the brief cap.
