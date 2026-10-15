#!/bin/sh
# QA-KB-123 analysis (3-analyzer, 2026-10-12): the exact source lines every CONFIRMED claim in ISS-1194 and its
# siblings (ISS-1207, ISS-1208, ISS-1209) rests on. Read-only. Run from the repo root:
#   sh evidence/qa-kb-123/analysis-04-source-excerpts.sh
x() { printf '\n== %s:%s-%s  (%s)\n' "$1" "$2" "$3" "$4"; sed -n "${2},${3}p" "$1" | nl -ba -v "$2" -w5 -s'  '; }
# --- the three tests that click the chip -------------------------------------------------------------------------
x tests/integration/e2e/suites/07_run_detail/test_run_detail.py 841 848 "S-07-29: unconditional chip click at 843; the skip at 848 sits behind it"
x tests/integration/e2e/suites/07_run_detail/test_run_detail.py 875 882 "S-07-30: same shape at 877 / 882"
x tests/integration/e2e/suites/15_overlays/test_overlays.py 744 751 "S-15-28: same shape at 746 / 751"
# --- the helper layer that already says an absent chip is count zero, and the one test that honours it ----------------
x tests/integration/e2e/framework/locators/run_history.py 53 76 "chip(): matches '^Prototype\\s*\\d'; chip_count(): 'an absent chip IS a count of zero'"
x tests/integration/e2e/suites/06_run_history/test_run_history.py 153 161 "S-06-05: the correct guard, inline (skip when chip_count == 0)"
x tests/integration/e2e/suites/06_run_history/test_run_history.py 184 193 "S-06-07: clicks the User Stories chip with no guard"
x tests/integration/e2e/suites/06_run_history/test_run_history.py 348 354 "S-06-13: clicks the User Stories chip with no zero check"
x tests/integration/e2e/suites/06_run_history/test_run_history.py 173 182 "S-06-06: ?type=ppt, rows == chip_count('Presentation') (0 == 0 on today's data)"
# --- why the chip is not rendered ---------------------------------------------------------------------------------
x frontend/src/components/history/RevisionFamilyView.tsx 83 104 "baseWorkflowType, KNOWN_FRAMEWORK_BASE_TYPES, filterBucketFor: v2 ids fall to custom"
x frontend/src/components/history/RevisionFamilyView.tsx 183 192 "familyRootFor"
x frontend/src/components/history/RevisionFamilyView.tsx 218 221 "root = the member whose id IS the rootRunId, else the earliest present"
x frontend/src/components/history/WorkflowHistory.tsx 227 238 "the list is fetched with limit 50 and NO type (the chip never sends type= to the backend)"
x frontend/src/components/history/WorkflowHistory.tsx 488 493 "matchesFilter: the chip filters client-side by filterBucketFor"
x frontend/src/components/history/WorkflowHistory.tsx 1193 1206 "typeGroups and typeCounts: one count per FAMILY, bucketed by the family ROOT's type"
x frontend/src/components/history/WorkflowHistory.tsx 1282 1285 "a zero-count chip returns null"
x frontend/src/lib/api.ts 1214 1223 "getWorkflows(token, {type?, limit?, offset?}); History passes only limit"
x backend/app/api/runs.py 777 792 "GET /api/runs: user-scoped, type is exact match, created_at desc"
# --- the analytics half -------------------------------------------------------------------------------------------
x backend/app/api/analytics.py 524 529 "pipeline filter: type IN (pipeline, pipeline_revision)"
x frontend/src/components/analytics/AnalyticsPage.tsx 58 70 "PIPELINE_LABELS has no v2 key; normalizeType"
x frontend/src/components/analytics/AnalyticsPage.tsx 316 322 "pipelineRows: label = PIPELINE_LABELS[normalizeType(type)] ?? normalizeType(type)"
x frontend/src/components/analytics/AnalyticsPage.tsx 412 421 "the pipeline <select> has five hard-coded options"
x frontend/src/components/analytics/AnalyticsPage.tsx 425 427 "the model <select> renders only when more than one model is listed"
x frontend/src/components/analytics/AnalyticsPage.tsx 555 570 "By Pipeline Type row: the label span comes BEFORE the figures"
x tests/integration/e2e/framework/locators/analytics.py 103 130 "runs_by_pipeline: docstring says label follows its figures; the regex pairs a count with the next label"
x tests/integration/e2e/suites/10_analytics/test_analytics.py 377 409 "ISS-289: assert pipeline_only; model filter skip; second read"
x tests/integration/e2e/suites/10_analytics/test_analytics.py 188 202 "S-10-10: only an upper bound on the sum"
# --- the preview routing (why re-basing onto plain prototype_v2 does not work) ---------------------------------------
x frontend/src/components/preview/PreviewPanel.tsx 1082 1094 "renderType: revisions of v2 map to prototype; plain prototype_v2 does not"
x frontend/src/components/preview/PreviewPanel.tsx 1633 1650 "FIRST_PARTY_RENDERERS: PrototypePreview only for renderType prototype"
x "frontend/src/app/[...view]/page.tsx" 1719 1727 "live path: the six types that fill the prototype slot"
x "frontend/src/app/[...view]/page.tsx" 3303 3310 "reopen path: the same six types"
# --- how rows get into the history, and the policy -----------------------------------------------------------------
x tests/integration/e2e/suites/25_pipeline_smoke/test_pipeline_smoke.py 1 14 "the live tier leaves a real row in the history"
x tests/integration/e2e/suites/25_pipeline_smoke/test_pipeline_smoke.py 38 41 "the prototype card: Build an interactive prototype (Fast) -> prototype.html"
x tests/integration/e2e/pytest.ini 10 27 "addopts -m 'not live' is the default (line 12); the comment block explains the split"
x backend/agents/workflows/prototype/workflow.yaml 1 8 "the v1 prototype manifest is user_launchable, not beta"
x tests/integration/screens/07-run-detail.feature.md 441 449 "S-07-29 says 'Given a completed prototype run', not 'via the chip'"
x tests/integration/screens/15-overlays.feature.md 359 366 "S-15-28 same"
