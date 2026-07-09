# Deferred / Out-of-Scope Items — 260707-gvq (image-input Wave 3)

## Out-of-Scope Pre-existing Reds (NOT fixed — SCOPE BOUNDARY)

Proven pre-existing via `git stash` (identical failures on clean HEAD with the gvq
data-only edits removed — same 5 failed / 6 passed). Unrelated to `input_providers` /
`images`: `test_factory_injects.py` uses synthetic `_Spec` dataclasses, never the real
`prototype-specify` spec my edit touched.

- `tests/unit/test_factory_injects.py::test_full_injection_order`
- `tests/unit/test_factory_injects.py::test_full_system_prompt_role_last`
- `tests/unit/test_factory_injects.py::test_brief_analyst_no_craft`
- `tests/unit/test_factory_injects.py::test_template_missing_raises`
- `tests/unit/test_factory_injects.py::test_no_od_context_raises_for_template`

(Composition/`CRITICAL OUTPUT RULES` + `TemplateMissingError` drift in the factory
injection path — a standing branch red, out of scope for this data-only opt-in.)

- `tests/agents/test_manifest.py::test_display_name_authored_on_real_launchable_manifest[dotnet_to_azure]`
- `tests/agents/test_manifest.py::test_display_name_null_where_intentionally_unauthored[custom]`

(The 2 plan-anticipated display_name/launchable catalog reds — stay identically red.)

## DEFERRED live-verification item

- **LIVE Bedrock proof** — the `prototype-specify` spec-writer actually receives/reads the
  attached diagram — **+ the middleware/checkpointer image-payload gate** (IMAGE-INPUT
  §12 F2/F3, retry/replay amplification). DEFERRED to a user-driven run; the orchestrator
  produces the runbook. No live Bedrock run attempted in this offline wave
  (defer-live-verification-to-milestone-end convention, T-gvq-03 accept-deferred).
