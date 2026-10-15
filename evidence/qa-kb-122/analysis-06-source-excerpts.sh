#!/bin/sh
# QA-KB-122 analysis (3-analyzer, 2026-10-09): the exact source lines every CONFIRMED claim in ISS-1158 and its
# siblings rests on. Read-only. Run from the repo root:  sh evidence/qa-kb-122/analysis-06-source-excerpts.sh
x() { printf '\n== %s:%s-%s  (%s)\n' "$1" "$2" "$3" "$4"; sed -n "${2},${3}p" "$1" | nl -ba -v "$2" -w5 -s'  '; }
x backend/app/api/admin.py 173 194 "CreateUserRequest: extra=forbid, no password field"
x backend/app/api/admin.py 197 205 "ResetPasswordRequest: extra=forbid, no fields at all"
x backend/app/api/admin.py 553 555 "reset-password answers {status: temporary_password_set}"
x frontend/src/app/admin/page.tsx 694 708 "create modal: no password input, button reads Send Invitation"
x frontend/src/lib/api.ts 2113 2123 "adminResetUserPassword posts an empty object"
x backend/app/core/cognito_admin.py 292 299 "invite_user signature (no way to pass a password through the API)"
x backend/app/core/cognito.py 419 423 "AdminCreateUser is asked to deliver the invitation by EMAIL"
x tests/integration/e2e/conftest.py 429 462 "disposable_user: the POST body and the returned credential"
x tests/integration/e2e/suites/24_api_contract/test_api_contract.py 335 347 "S-24-12 re-types the same body inline"
x tests/integration/e2e/suites/24_api_contract/test_api_contract.py 657 669 "S-24-25 pins the listing as hiding .uploads/ and .logs/"
x tests/integration/e2e/suites/11_admin/test_admin.py 346 353 "S-11-15 fills a password input and clicks /create/"
x tests/integration/e2e/suites/11_admin/test_admin.py 453 466 "S-11-17 posts new_password and expects requires_new_password_at_next_login"
x tests/integration/e2e/suites/11_admin/test_admin.py 492 507 "S-11-18 posts permanent=true and expects the break-glass refusal text"
x tests/integration/e2e/suites/11_admin/test_admin.py 585 592 "S-11-20 signs in as the disposable user with its password"
x tests/integration/e2e/suites/12_shell_nav/test_shell_nav.py 201 216 "S-12-11 signs in as the disposable user"
x tests/integration/e2e/suites/10_analytics/test_analytics.py 270 285 "S-10-13 signs in as the disposable user"
x tests/integration/e2e/suites/17_theme_and_tiers/test_theme_and_tiers.py 281 296 "S-17-09 signs in as the disposable user"
x tests/integration/e2e/framework/locators/home_catalog.py 48 55 "LAUNCHABLE_TITLES carries (Detailed)"
x backend/agents/workflows/ppt_v2/workflow.yaml 42 42 "the manifest label is (Depth)"
x tests/integration/e2e/framework/locators/composer.py 52 52 "AGENT_SUBTABS carries Hooks"
x frontend/src/components/workflow/composer/CanvasConfigRail.tsx 555 575 "caption is '<kind.label> · step n of m'; tabs are Overview/Skills/Data/Tools/Config"
x frontend/src/components/workflow/composer/stepKind.ts 20 20 "the plain agent kind label is AI agent"
x frontend/src/components/workflow/composer/CanvasConfigRail.dataTab.test.tsx 44 47 "the unit twin pins Data and the ABSENCE of Hooks"
x tests/integration/e2e/suites/06_run_history/test_run_history_pagination.py 186 217 "ISS-213: the assertion is shown >= extra_beyond_page_one"
x frontend/src/components/history/WorkflowHistory.tsx 1192 1206 "per-type chips are built from the loaded families only, on purpose (ISS-219 option 2)"
x tests/integration/e2e/suites/05_saved_workflows/test_iss228_launch_panel_override_binding.py 31 38 "pinned saved-workflow id + strict xfail"
x tests/integration/e2e/suites/07_run_detail/test_iss802_steps_agent_artifacts_duplicate_request.py 62 76 "counts every URL containing /api/runs/{id}/artifacts"
x frontend/src/components/preview/PreviewPanel.tsx 614 623 "the second, different artifacts read (kind=clarifications)"
echo
echo "== git: the unit-tier twin of S-24-25 was renamed and inverted in f9df3737c"
git show f9df3737c -- backend/tests/unit/test_run_sandbox_api.py | grep -n -E "^[-+].*(def test_the_reserved_subtrees|def test_every_file_is_listed|def test_a_listed_reserved|def test_the_reserved_subtrees_are_not_readable)"
echo
echo "== git: 87903ab3b states the intent of the rename"
git show --no-patch --format=%b 87903ab3b | sed -n 1,6p
