# Deferred / out-of-scope items — Phase 33

Discovered during 33-05 execution. These are PRE-EXISTING failures on the clean
baseline (commit 9a81a0b3), NOT caused by 33-05 changes, and outside 33-05 scope
(SCOPE BOUNDARY — only auto-fix issues directly caused by the current task).

## Pre-existing manifest test failures (baseline 9a81a0b3)

`cd backend && python3.11 -m pytest tests/agents -k manifest` fails identically
BEFORE and AFTER 33-05 (74 passed on both; 33-05 introduces zero new failures):

- `test_manifest.py::test_display_name_authored_on_real_launchable_manifest[dotnet_to_azure]`
- `test_manifest.py::test_display_name_null_where_intentionally_unauthored[custom]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[app_builder]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[custom]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[dotnet_to_azure]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[mulesoft_to_springboot]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[ppt]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[prototype]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[user_stories]`

These are workflow.yaml data-drift vs test-expectation mismatches (launchable/display_name
metadata + clarify-defaults parity), unrelated to the `chat:` field. Left untouched.
