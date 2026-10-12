# Baseline: 022-prototype-v2-revisions

Test counts taken before any spec 022 code change, one file at a time. T07 re-runs the same files and compares.

## Backend

Taken 2026-09-30 17:30–17:37 CEST on `feat/user-stories-v2` @ `419261a90`, backend unedited. Command per file:
`.venv/bin/python -m pytest -q -p no:cacheprovider -rfE <file>` from `backend/`.

The frontend's `entitlements.ts` edit (spec 022 T05, frontend rows) was already in the working tree, which is why `test_entitlement_parity.py` shows 3 failures: the UI offered the three new pipeline names before the backend tiers did. The backend T05 rows are expected to clear them.

### Spec 022 T02 list

The T02 path `backend/tests/unit/test_revision_intelligence.py` does not exist; the file is `backend/tests/integration/agents/test_revision_intelligence.py` (row 1).

| # | file | passed | failed | errors | skipped | xfailed | xpassed |
|---|---|---|---|---|---|---|---|
| 1 | tests/integration/agents/test_revision_intelligence.py | 19 | 0 | 0 | 0 | 0 | 0 |
| 2 | tests/agents/test_b8_custom_revision_registered.py | 2 | 0 | 0 | 0 | 0 | 0 |
| 3 | tests/agents/test_ppt_revision_writes_deliverable.py | 4 | 0 | 0 | 0 | 0 | 0 |
| 4 | tests/agents/test_revision_ordinal_v3.py | 6 | 2 | 0 | 0 | 0 | 0 |
| 5 | tests/agents/test_revision_routes_v3.py | 0 | 12 | 0 | 0 | 0 | 0 |
| 6 | tests/contract/agents/test_characterization_prototype_feature_revision.py | 4 | 0 | 0 | 0 | 0 | 0 |
| 7 | tests/contract/agents/test_characterization_prototype_large_revision.py | 2 | 0 | 0 | 0 | 0 | 0 |
| 8 | tests/contract/agents/test_characterization_prototype_revision.py | 2 | 0 | 0 | 0 | 0 | 0 |
| 9 | tests/integration/agents/test_phase5_revision_validation_db.py | 8 | 0 | 0 | 0 | 0 | 0 |
| 10 | tests/integration/agents/test_revision_analyzer_integration.py | 20 | 0 | 0 | 0 | 0 | 0 |
| 11 | tests/integration/agents/test_run_revision_fe_contract.py | 2 | 0 | 0 | 0 | 0 | 0 |
| 12 | tests/integration/api/test_rest_revisions_api.py | 24 | 1 | 0 | 0 | 0 | 0 |
| 13 | tests/unit/agents/test_gate_revision_discriminator.py | 6 | 0 | 0 | 0 | 0 | 0 |
| 14 | tests/unit/agents/test_revision_gating.py | 6 | 1 | 0 | 0 | 0 | 0 |
| 15 | tests/unit/agents/test_spec_revision_context.py | 4 | 0 | 0 | 0 | 0 | 0 |
| 16 | tests/unit/agents/test_spec_revision_cycles.py | 7 | 0 | 0 | 0 | 0 | 0 |
| 17 | tests/unit/app/test_revision_analyzer.py | 19 | 1 | 0 | 0 | 0 | 0 |
| 18 | tests/unit/app/test_revision_file_editing.py | 6 | 0 | 0 | 0 | 0 | 0 |
| 19 | tests/unit/agents/workflows/test_manifest_coverage.py | 34 | 0 | 0 | 0 | 3 | 0 |
| 20 | tests/unit/services/test_entitlement_parity.py | 53 | 3 | 0 | 44 | 0 | 0 |
| 21 | tests/agents/test_backlog_assemble.py | 52 | 0 | 0 | 0 | 0 | 0 |
| 22 | tests/agents/test_mechanical_assemble_backlog.py | 8 | 0 | 0 | 0 | 0 | 0 |

### Extended list (files the backend rows touch)

| # | file | passed | failed | errors | skipped | xfailed | xpassed |
|---|---|---|---|---|---|---|---|
| 23 | tests/unit/agents/workflows/test_manifest_parity.py | 64 | 4 | 0 | 0 | 0 | 0 |
| 24 | tests/unit/agents/workflows/test_manifest.py | 39 | 0 | 0 | 0 | 0 | 0 |
| 25 | tests/unit/agents/test_phase6_frontend_consistency.py | 17 | 0 | 0 | 0 | 0 | 0 |
| 26 | tests/unit/agents/test_registry.py | 27 | 0 | 0 | 0 | 1 | 0 |
| 27 | tests/unit/agents/test_registry_helpers.py | 27 | 0 | 0 | 0 | 0 | 0 |
| 28 | tests/unit/agents/test_registry_discovery.py | 10 | 0 | 0 | 0 | 0 | 0 |
| 29 | tests/unit/api/test_concierge_proposal_channels.py | 12 | 0 | 0 | 0 | 0 | 0 |
| 30 | tests/unit/services/test_entitlement_authority.py | 4 | 0 | 0 | 0 | 0 | 0 |
| 31 | tests/unit/api/test_workflows_api.py | 4 | 0 | 46 | 0 | 0 | 0 |
| 32 | tests/integration/agents/test_pipeline_workflows.py | 50 | 0 | 0 | 57 | 0 | 0 |
| 33 | tests/unit/agents/execution_engine/test_compiler.py | 35 | 0 | 0 | 0 | 0 | 0 |
| 34 | tests/unit/app/test_run_pipeline_validation.py | 50 | 0 | 0 | 0 | 0 | 0 |
| 35 | tests/integration/api/test_entitlement_authority_api.py | 3 | 0 | 0 | 0 | 0 | 0 |
| 36 | tests/integration/api/test_rest_run_launch_api.py | 20 | 5 | 0 | 0 | 0 | 0 |

### Failures already present before spec 022

| file | failing tests | reason pytest printed |
|---|---|---|
| test_revision_ordinal_v3.py | `test_three_completed_revisions_tag_v1_v2_v3`, `test_two_sibling_revisions_tag_v1_v2_v3_not_v1_v2_v2` | NOT NULL constraint failed: users.cognito_sub |
| test_revision_routes_v3.py | all 12 | `'password_hash' is an invalid keyword argument for User` |
| test_rest_revisions_api.py | `test_driver_happy_path_persists_output_columns` | the JSON object must be str, bytes or bytearray, not NoneType |
| test_revision_gating.py | `test_declared_revision_with_parent_seeds_after_assert_owns` | XPASS(strict) — ISS-633 unfixed |
| test_revision_analyzer.py | `TestAgentMdSmoke::test_analyzer_agent_md_frontmatter_max_tokens` | assert 32768 == 4096 |
| test_entitlement_parity.py | `test_same_pipelines_per_tier[enterprise/hexaware/pro]` | UI offers, backend refuses: backlog_revision, prototype_v2_feature_revision, prototype_v2_revision (frontend T05 landed first). **Enterprise also fails on `sample_subagents_parallel`, independently of spec 022:** the backend entitles it and `frontend/src/lib/entitlements.ts` never listed it (HEAD has only the comment "reference fan-out fixture — kept in parity with the backend map"). Left as is by decision: adding it would offer that sample pipeline to enterprise users. So after spec 022 enterprise is expected to stay red for this one reason only; hexaware and pro go green. |
| test_manifest_parity.py | `test_planner_run_everywhere[backlog]`, `[prototype_v2]`, `test_clarify_defaults_match_engine[backlog]`, `[prototype_v2]` | planner/clarify pins do not cover the two file-manifest workflows |
| test_workflows_api.py | 46 errors | `UnitIsolationError: Unit test opened a real database connection` at setup (first recorded here as "workflow compilation errors"; corrected 2026-10-01 from the re-run log) |
| test_rest_run_launch_api.py | `test_driver_persists_full_agent_history_like_ws`, `test_owned_source_links_the_child`, `test_foreign_source_drops_the_link_but_still_launches`, `test_unknown_source_drops_the_link_but_still_launches`, `test_driver_persists_model_id_and_prices_non_circular` | the JSON object must be str, bytes or bytearray, not NoneType |

### Re-run after spec 022 (2026-10-01)

Same command, one file at a time, with every backend row of spec 022 in the working tree (revision 6 included). 30 of the 36 files gave exactly their baseline counts. The other 6 changed only by the cases the 3 new manifests add:

| # | file | baseline | re-run | why |
|---|---|---|---|---|
| 19 | test_manifest_coverage.py | 34 passed, 3 xfailed | 37 passed, 3 xfailed | 3 new manifests; pin 36 → 39 |
| 20 | test_entitlement_parity.py | 53 passed, 3 failed, 44 skipped | 63 passed, 1 failed, 42 skipped | hexaware and pro now green; enterprise fails only on `sample_subagents_parallel`, as expected above |
| 23 | test_manifest_parity.py | 64 passed, 4 failed | 70 passed, 4 failed | 6 new cases (3 ids × 2 tests); the same 4 failures |
| 27 | test_registry_helpers.py | 27 passed | 30 passed | the composed-revision allow-list test |
| 31 | test_workflows_api.py | 4 passed, 46 errors | 4 passed, 49 errors | 3 new `test_list_step_count_matches_compiled_plan[...]` cases, same `UnitIsolationError` |
| 32 | test_pipeline_workflows.py | 50 passed, 57 skipped | 54 passed, 62 skipped | 9 new cases: 4 pass, 5 skip on "has no agents" / "has <2 agents" (registry roster, not the compiled plan; decision D1) |

No new failure. New files:

| file | result |
|---|---|
| tests/unit/test_v2_revision_routing.py | 47 passed |
| tests/unit/test_backlog_revision.py | 16 passed |
| tests/unit/test_revision_workspace_mode.py | 6 passed |
| tests/unit/app/test_binary_deliverable.py | 6 passed |
