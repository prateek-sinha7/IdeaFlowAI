# Escalated — Domain 1: warmup

No cards with status `ESCALATED` in this domain.

However, the following cards carry **operator-review notes** that require human
judgment before they can be treated as fully closed:

---

## ~~ISS-076~~ — CLOSED ✓ (won't-fix on frozen archive)

**Closed:** `.planning/TEST-REGISTER.md` is a frozen read-only archive — editing it is
prohibited by PLAN.md and the fixer role contract. The stale "123–132 green" Playwright
figure remains in the archive as historical record.

The live developer reference (`frontend/e2e/README.md`) has been updated separately to
reflect the real measured baseline (108 passed / 33 failed at `b13d5c33`).

---

## ~~ISS-095~~ — CLOSED ✓ (already-fixed)

**Closed:** all 3 `test_declared_gate_streaming.py` tests pass as of 2026-08-31
(3 passed in 43.58s). Fixed by commit `da172056` and surrounding gate-engine work.
Card's own `status` field is `resolved`; verification notes confirm ALREADY_FIXED.

---

## ~~BUG-031~~ — CLOSED ✓

**Closed:** already fixed in commit `0228bf196` (2026-08-29).
`stages: [manual]` was restored on the knowledge hook at `.pre-commit-config.yaml:185`
so `git commit` no longer fires the hook automatically.
Verified 2026-08-31 per card resolution field. No code change needed this pass.
