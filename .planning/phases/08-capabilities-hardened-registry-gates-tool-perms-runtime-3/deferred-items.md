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
