# Deferred / Out-of-Scope Items — 260707-edw (image-input Wave 1)

These pre-existing branch reds are UNRELATED to the image-input change (proven
pre-existing via `git stash` on the working tree — identical pass/fail with and
without the Wave-1 diff). NOT fixed this wave (scope boundary — only auto-fix
issues directly caused by the current task's changes).

## Pre-existing branch reds (NOT caused by this wave)

- `tests/agents/test_manifest_parity.py::test_clarify_defaults_match_engine[*]`
  — 7 params fail (`app_builder`, `custom`, `dotnet_to_azure`,
  `mulesoft_to_springboot`, `ppt`, `prototype`, `user_stories`).
  `clarify.defaults must reproduce the engine _pipeline_defaults`. Stash-proof:
  identical `7 failed, 25 passed` with and without the Task-2 manifest/compiler/plan
  diff. Unrelated to `input_providers` (clarify.defaults parity drift).

- `tests/agents/test_manifest.py::test_display_name_authored_on_real_launchable_manifest[dotnet_to_azure]`
  and `::test_display_name_null_where_intentionally_unauthored[custom]`
  — 2 fail (`dotnet_to_azure is expected to be a launchable manifest`;
  `custom ... BE display_name must be ...`). Stash-proof: identical
  `2 failed, 24 passed` with and without the diff. Unrelated to `input_providers`
  (display_name / launchable-manifest catalog drift).

Note: the plan anticipated a third pre-existing red
(`test_characterization_od_ppt.py::test_od_ppt_event_snapshot`). It did NOT
reproduce in this environment — both od_ppt characterization tests pass
identically with and without the Wave-1 diff (see SUMMARY hard-gate evidence),
an even stronger INV-3 outcome. No deferral needed.
