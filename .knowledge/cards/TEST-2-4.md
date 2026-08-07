---
id: TEST-2-4
type: test
status: done
area: [workflow, agents, artifacts]
summary: >-
  2.4 SC-001 — prototype-as-manifest parity proof (THE CORE VALUE) (register part 07)
source: .planning/TEST-REGISTER.md#2-4-sc-001-prototype-as-manifest-parity-proof-th
covers: [BE-PARITY-01, BE-PARITY-02, BE-PARITY-03, BE-PARITY-04, BE-PARITY-05, BE-PARITY-06]
---

### 2.4 SC-001 — prototype-as-manifest parity proof (THE CORE VALUE)  (register part 07)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-PARITY-01 | **A brand-new non-prototype `task_loop` workflow runs from manifest + AGENT.md, ZERO engine edits** (git-containment check: no proof artifact under `execution_engine/`; manifest uses only registered caps) | `pytest tests/agents/test_sc001_nonprototype_task_loop.py` (3) | 🟢 **PROVEN** |
| BE-PARITY-02 | Same proven for fan-out (`sample_fanout`) | `pytest tests/agents/test_sc001_fanout.py` (3) | 🟢 |
| BE-PARITY-03 | **5 goldens byte-identical** (prototype/prototype_revision/od_prototype/od_ppt/app_builder) — deliverable bytes == committed golden | `pytest tests/agents/test_characterization_*.py -k byte_snapshot` (5) | 🟢 char-locked |
| BE-PARITY-04 | **5 goldens semantic-event-parity** — normalized event stream == golden; fails on dropped/reordered event or lost key | `…-k event_snapshot` (5) | 🟢 char-locked |
| BE-PARITY-05 | Kernel knows no workflow by name (INV-1): banned-pattern grep == 0, CI hard-fail; `agents/prototype/` package DELETED | `pytest tests/agents/test_banned_patterns.py` (11); `ls agents/prototype` → absent | 🟢 CI-gated |
| BE-PARITY-06 | 9 capability families live behind ports off the compiled manifest (strategies/resolvers/providers/parser/compaction) | `pytest tests/agents/test_routing_parity.py test_strategies.py` | 🟢 |
