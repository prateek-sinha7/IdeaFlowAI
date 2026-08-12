---
id: 260812-wir
status: complete
date: 2026-08-12
commits: e3c38594, 2b25d3d0, f5df7c85
---

# Summary — quick-260812-wir

All three shipped. Detail lives in the registers (this file is a pointer, per convention):
`FIX-REGISTER.md` FIX-244/245/246 · `FIX-TEST-REGISTER.md` TEST-028/029 ·
`IMPLEMENTATION-REGISTER.md` quick-260812-wir · `ISSUES-REGISTER.md` ISS-123/124/126 closed,
ISS-121 symptom corrected, ISS-135..141 filed.

Three things worth carrying forward:

- **ISS-124 was filed `minor` and was not.** With no durable `pipeline_cancelled` row,
  `_reconcile_terminal_status` took its D2 fail-safe and recorded the owner's Stop as
  **failed** (`assert 'failed' == 'cancelled'`).
- **ISS-126's filed locus was wrong.** A terminal run never opens an SSE stream, so both
  previously-rejected backend options addressed a path the symptom does not traverse.
- **Green unit tests were not verification.** Two of the three FE pieces were found only in
  a real browser: a wholesale legacy→store overwrite (ISS-138) and `laneClarifyOpen`, the one
  lane branch not gated on `isRunning`.

Live A/B, no money spent: `808612bf` (corrupted) → "Cancelled", no Stop; `1ea6d262`
(clean control) unchanged.
