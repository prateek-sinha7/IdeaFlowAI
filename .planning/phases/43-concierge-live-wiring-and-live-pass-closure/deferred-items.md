
## 43-04 out-of-scope discovery (2026-07-15)
- `tests/unit/test_run_pipeline_validation.py` — 12 pre-existing failures (registry
  agent allow-list / custom-pool drift, e.g. `app-*` / `od-ppt-*` agents leaking into
  the custom utility pool). NOT caused by 43-04: the test references none of the
  routed code (0 matches for cached_invoke/usage_sink/SmartPlanner/ClarifyEngine/
  classify_task/ComplianceAgent), and 43-04 touched no registry/loader/run-validation
  file. Scope boundary — logged, not fixed.
