# Phase 08 — Deferred Items (out-of-scope discoveries)

> Items discovered during execution that are OUTSIDE the current plan's scope.
> Logged (not fixed) per the executor scope-boundary rule.

## 08-05 (Wave 3)

- **`tests/agents/test_capability_resolution.py` collection error (pre-existing).**
  The module imports the deleted `install` symbol:
  `from agents.capabilities.registry import CapabilityRegistry, install`.
  `install()` was DELETED in 08-01 (INV-12 — `@register`/`discover()` is its sole
  successor; `test_install_is_deleted` enforces its absence). This stale test module
  was not updated when `install()` was removed and fails at COLLECTION time.
  - Confirmed pre-existing: the bad import is present at the 08-05 base commit
    (and earlier) — NOT introduced by 08-05.
  - Out of scope for 08-05 (F1/F3/F5 factory lift). Should be updated to use
    `discover()` (or removed if redundant with `test_registry_capabilities.py`) in a
    follow-up test-hygiene pass.

## 08 Review remediation (CR-01/WR-01..05)

PRE-EXISTING failures unrelated to the review findings or their fixes — confirmed
failing identically on the pre-fix tree (commit 9a92c0c). NOT fixed (scope
boundary: only auto-fix issues directly caused by the current task's changes).

- **`tests/unit/test_logout.py::TestJtiClaim::test_register_token_has_jti`** — fails
  `403 Forbidden` ("Self-registration is disabled"); the test assumes registration
  returns 201. An auth/config concern, unrelated to capabilities/hooks/gates/compiler.
  Pre-existing on 9a92c0c.
- **`tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack`**
  — fails `DID NOT RAISE asyncio.CancelledError`. A cancellation-path engine test
  unrelated to the review findings. Pre-existing on 9a92c0c (verified by checking out
  the pre-fix tree and re-running — same failure).
