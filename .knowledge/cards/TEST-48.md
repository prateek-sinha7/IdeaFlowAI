---
id: TEST-48
type: test
status: done
summary: >-
  G4 — Wire tests into CI
source: .planning/TEST-REGISTER.md#g4-wire-tests-into-ci
---

### G4 — Wire tests into CI

Today CI runs only `backend:characterization` (7 files) + `backend:test` (`tests/unit`) + `backend:lint` (`lint-imports`/`ruff`/`vulture`) + `frontend:lint`/`frontend:typecheck`. **FE vitest (109 tests) and the new Playwright suite are NOT gated.** Add `frontend:test` (vitest, with the 7 known-fails quarantined/fixed) and `e2e:mocked` (Playwright mocked-WS) as MR gates; run `e2e:live` nightly.
