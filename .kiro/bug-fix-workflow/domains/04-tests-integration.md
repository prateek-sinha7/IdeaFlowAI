# Domain 4 — tests·integration

5 cards, 2 batches. These are TEST-side defects (stale/wrong assertions), not app
bugs — the fixer edits the TEST, which is allowed here ONLY because each card says
the test is what's wrong. Low blast radius.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | tests·integration (ISS-625, ISS-627) | ISS-625, ISS-627 | C (stale-test) | validate→fix(test)→verify | haiku |
| B2 | 2 | `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py` | ISS-623, ISS-626, ISS-628 | C (stale-test) | validate→fix(test)→verify | haiku |

Notes:
- All five are the "chips count families vs headline counts runs" / lost-agent
  fixture-drift class recorded around ISS-618. The fix is aligning the assertion
  with current (correct) app behaviour — NOT changing the app.
- If validate finds the APP is actually wrong (not the test), STOP and escalate —
  that flips it from a test fix to a real bug and it belongs in run-history/composer.
- ISS-627 spans five test files (08_library, 09_settings, 15_overlays); ISS-628
  spans four. These are 3+-file edits but test-only — keep haiku, but the verifier
  (sonnet) must confirm no baseline regression across all named suites.

Collision note: B2's file also appears in ISS-626/628. Owned here. Domain 9
(run-history) and domain 10 (composer) must not touch these test files.
Status: NOT STARTED.
