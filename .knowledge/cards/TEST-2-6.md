---
id: TEST-2-6
type: test
status: done
area: [workflow, agents]
summary: >-
  2.6 Security gates & tool permissions (register part 08/10)
source: .planning/TEST-REGISTER.md#2-6-security-gates-tool-permissions-register-par
covers: [BE-GATE-01, BE-GATE-02, BE-GATE-03, BE-GATE-04, BE-GATE-05]
---

### 2.6 Security gates & tool permissions  (register part 08/10)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-GATE-01 | `exec`/`network`/`secrets`/`spawn_subagents` default **OFF**; `intersect_permissions` AND-mask can only LOWER | `pytest tests/agents/test_tool_permissions.py` | 🟢 |
| BE-GATE-02 | exec needs `gates:[security,approval]` or compile-error (D-01); `security` gate network/secrets **BLOCK** (byte-identical deny); exec PASS only behind security+approval+workspace allow-list | `pytest tests/agents/test_gates.py test_compiler_trust.py` | 🟢 |
| BE-GATE-03 | `human`/`approval` gates delegate to the **one** durable HITL → `review_gate_*` events byte-identical; first-exec approval memory run-scoped & durable | `pytest tests/agents/test_gates.py test_declared_gate_streaming.py` | 🟢 → drives UI TS-N |
| BE-GATE-04 | `validation` gate: CRITICAL→`block`+`gate_blocked`, residual→`validation_warning`+pass | `pytest tests/agents/test_gates.py` | 🟢 → drives UI TS-J/TS-N |
| BE-GATE-05 | INV-13 banned-pattern gate: no 2nd `create_deep_agent`, no local deepagents shadow, deepagents `task` tool excluded | `pytest tests/agents/test_banned_patterns.py` | 🟢 |
