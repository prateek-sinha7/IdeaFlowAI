# Deferred items — quick-260720-ec4

## Pre-existing test failures (out of scope, NOT introduced by this plan)

Verified on the PRISTINE tree (pristine `engine.py`/`kernel_services.py` source AND pristine `test_gates.py`): `tests/agents/test_gates.py` → **3 failed, 38 passed**. These fail independently of this plan's changes — test-harness stub drift, not production regressions:

- `test_raising_hitl_gate_blocks_and_stops_gate_evaluation` — `AttributeError: '_Ctx' object has no attribute 'gate_agent_ids'`
- `test_engine_sentinel_carries_human_gate_edit_detail` — `AttributeError: '_Ctx' object has no attribute 'gate_agent_ids'`
- `test_apply_declared_gate_edit_rewrites_upstream_artifact_and_result` — `AttributeError: '_Ectx' object has no attribute 'artifacts'`

These are `_Ctx`/`_Ectx` local test-stub classes missing attributes the engine now reads. Fix = update the stubs in those test bodies to carry `gate_agent_ids` and an `artifacts` graph. Not touched here (scope boundary — this plan does not modify those tests).
</content>
