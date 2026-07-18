# Deferred items — quick-260718-rf7 (CWF-002)

Out-of-scope discoveries during execution (NOT fixed — logged per executor scope rule).

## Pre-existing test failure (unrelated to CWF-002)

- **Test:** `tests/agents/test_model_pricing.py::test_websocket_cost_site_uses_shared_function`
- **Failure:** `FileNotFoundError: app/api/websocket.py` — the test reads `backend/app/api/websocket.py`, which was DELETED in the Phase 44 SSE transport cutover (WS→SSE). The test's pinned path is stale.
- **Not caused by this task:** CWF-002 only touched `app/api/run_commands.py`, `app/api/runs.py`, `agents/execution_engine/engine.py`, and `tests/unit/test_rest_run_launch.py`. Failure reproduces independently of these edits (the file simply does not exist on `feat/ui-2`).
- **Suggested fix (separate task):** repoint the test at the SSE launch driver cost site (`app/api/run_commands.py`) or remove the WS-specific assertion, mirroring the SSE-cutover test reconciliation done for the rest of the suite.
