---
id: TEST-26
type: test
status: done
area: [sse, workflow, agents]
summary: >-
  TS-K — Wave / Subagent tree (WaveTreePanel) — fan-out & wave visualization
source: .planning/TEST-REGISTER.md#ts-k-wave-subagent-tree-wavetreepanel-fan-out-wa
covers: [BE-FAN, BE-WAVE, TS-K-01, TS-K-02, TS-K-03, TS-K-04, TS-K-05, TS-K-06, TS-K-07]
---

### TS-K — Wave / Subagent tree (WaveTreePanel) — fan-out & wave visualization

Mounted bottom-left in a **fold-fix container** (`flex-shrink-0 max-h-[40%]`). Heading `Wave / Subagent Tree` (CSS-uppercased). This is the UI for BE-FAN-* / BE-WAVE-*.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-K-01 | **Fold-above-the-fold (ISS-019)** | open execution at 1440×950 | heading `Wave / Subagent Tree` visible **without page scroll** (heading y≈884, bottom ≤950); page has no overflow (`bodyScrollH==viewportH`) | ✅ (V1: y=884) |
| TS-K-02 | Empty state | no fan-out running | `No waves running.` (exact, trailing period) in a gray pill | ✅ |
| TS-K-03 | Wave groups | run a fan-out/wave workflow (`sample_fanout`/`sample_wave`/custom) | one card per wave `Wave {index}` (`Wave 0`, `Wave 1`…) sorted asc; comma-joined task ids; wave status badge | ✅ (V2/S10: 3 workers) |
| TS-K-04 | Worker leaves | during fan-out | ≥2 distinct worker leaves nested under a wave (`pl-4 border-l`), each `worker.agent` + status badge | ✅ |
| TS-K-05 | Status buckets | through wave lifecycle | badge color by substring: running→blue (`Loader2 spin`), completed→emerald (`CheckCircle2`), **failed/cancel→red** (`XCircle`), else pending→gray; text = raw status | 🔴 |
| TS-K-06 | Populated scroll | many waves | list scrolls within `max-h-[260px]`/`max-h-[40%]`, panel stays in the fold | 🔴 |
| TS-K-07 | Reconnect dedup | reload mid-fanout | replayed `subagent_*`/`wave_*` frames don't duplicate leaves (idempotent by `event_id`) — see TS-S | 🟡 |
