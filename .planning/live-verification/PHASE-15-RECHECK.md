# Phase-15 Live Re-Check — 2026-06-13

Real AWS Bedrock Haiku 4.5 (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`), profile
`hexaware-srini`, region eu-central-1 · stock backend (restarted post-15-01 so the
edited AGENT.md bodies loaded fresh) · Postgres 16 (alembic 0020) · FE-exact WS driver
(`/tmp/flowin-live-pass15.py`, reusing the 2026-06-12 pass-2 driver). Phase pointer:
Phase 15 (live-pass-prompt-contract-closure), plan 15-03, per D-05.
Cost actually incurred: **$0.092** (run $0.082 + revision $0.010; budget ~$0.10 held).
Frames: `/tmp/flowin-live-evidence/phase15-od_ppt[-revision]-frames.jsonl`.

## LV-02 (SC1)

**Disposition: CLOSED (live)**

- od_ppt run `8c060c35-d9cb-40ab-9226-16861349be60` (130.7s, 244,250 tok): resolved
  `final_output` = **18,661 chars**, first line `<!DOCTYPE html>`, 5 `<section class="slide …">`
  elements (3 bare + cover + cta variants) — the DECK, not QA narration (the 2026-06-12
  failure shape was a 1,350-char QA report winning over the 21,394-char deck).
- Validator stream shape matches the 15-01 contract: ~1,046 chars of QA commentary, then
  exactly **ONE** `<artifact>` block containing the complete `<!DOCTYPE` deck, nothing after
  (`<artifact` count = 1). Commentary-before-artifact is expected and allowed; first-match
  unwrap still resolves the deck. (Minor adherence note: commentary ran longer than the
  contract's "at most two short sentences" — non-load-bearing, resolution unaffected.)
- FE-exact `od_ppt_output` revision `4a027d51-5abc-414c-8a90-daf65243e1ac` (32.7s):
  returned a **revised deck** (18,697 chars, `<!DOCTYPE` first, same 5 slides) — the
  requested title change applied in `<title>`, `<h1>`, and footer span; otherwise
  byte-identical to the parent; `cmp` differs (revision actually revised). The FR-014
  chain therefore fed the DECK (not narration) into the revision pipeline.
- Saved artifacts: `artifacts/phase15-od-ppt-final.html`, `artifacts/phase15-od-ppt-revision.html`.
- Offline evidence (15-02 gate, cited either way): LV-02 composition test
  (`test_od_ppt_deck_resolution_with_contract_shaped_validator`) green through REAL
  engine + REAL PptResolver; all contract pins green (11 nodes); 5 characterization
  goldens byte-identical (99 passed / 7 skipped, 35.58s; lint-imports clean) — see
  `15-02-SUMMARY.md` "Phase Gate Evidence".

## F4-residual (SC2)

**Disposition: NEXT-LIVE-PASS**

- Next-pass check (named): zero `<function_calls>` / `<invoke>` / `write_todos` preamble
  lines in the three sdlc-governance live streams (app / dotnet / mulesoft pipelines) —
  regex `<function_calls|<invoke\b|write_todos|<antml` over chunks + finals, expected 0
  (2026-06-12 baseline: 10 fabricated elements in app-sdlc-governance's preamble, lines 2–36).
- Not chased this session: requires live app_builder / migration pipeline runs (cost fence
  per 15-03 plan). Ride-along data point only: this session's od_ppt run + revision scanned
  0 tool-XML hits in chunks and finals (sdlc-governance agents not in these pipelines).
- Shipped mitigation: 15-01 anti-fabrication contracts in all three bodies, pinned by
  15-02 `test_sdlc_governance_anti_fabrication_contract` (3 parametrized nodes, green).

## F5-residual (SC3)

**Disposition: NEXT-LIVE-PASS**

- Next-pass check (named): `/api/v1` occurrence count in app-infra-generator's live
  app_builder output consistent with api-design / devops (2026-06-12 baseline: infra 0×
  in 3,083 lines vs api-design 58× / devops 50×; expect infra ≥ healthcheck + nginx +
  smoke-curl occurrences, i.e. clearly non-zero).
- Not chased this session: same app_builder cost fence.
- Shipped mitigation: 15-01 top-of-body `API PATH CONTRACT` (8 literal `/api/v1`
  occurrences), pinned by 15-02 `test_infra_generator_api_v1_contract` (green).

## Linkage

| Finding | REPORT-2026-06-12.md section | Prompt half | Pin half | Live status |
|---------|------------------------------|-------------|----------|-------------|
| LV-02 | "LV-02 (major, product) — od_ppt deliverable takes the validator's narration" | 15-01 Task 1 (od-ppt-validator deck re-emission contract) | 15-02 contract pins + composition test | CLOSED (live, this record) |
| F4-residual | "F5 re-audit … Residual 3 (F4 residual)" | 15-01 Task 2 (sdlc-governance anti-fabrication contracts) | 15-02 anti-fabrication pins | NEXT-LIVE-PASS |
| F5-residual | "F5 re-audit … Residual 2" | 15-01 Task 3 (app-infra-generator API PATH CONTRACT) | 15-02 /api/v1 pins | NEXT-LIVE-PASS |
