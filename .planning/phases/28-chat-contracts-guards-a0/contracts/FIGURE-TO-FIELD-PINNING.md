# Figure-to-Field Pinning

**Phase 28 (A0) UI-SPEC input — satisfies POR SC-2 (every displayed figure pinned to a real backend field).**
**Authority:** evidence `07-synthesized-contracts.md` §3 (seed list) + `01-run-ui-teardown.md` §7 (data contract), COMPLETED here by reading the engine emit sites in `backend/agents/execution_engine/engine.py`, `.../fanout.py`, `.../capabilities/strategies/wave_scheduler.py`, and `backend/app/api/runs.py`. The mock is a visual reference only; unconfirmed figures are marked **UNVERIFIED** so Phase 32 chases them rather than wiring a synthesized number (mock-fiction regression, evidence 01 §9).

> Field names below are VERIFIED-in-code against the emit sites (line anchors as-of 2026-07-07 on branch `feat/ui-2`; re-grep before wiring, KAN insertions shift lines).

---

## 1. Pinned figures (verified in code)

| Run-screen figure (mock) | Producing event | Exact field(s) | Emit site | Status |
|---|---|---|---|---|
| Per-agent **duration** (`"97s"`, `dur`) | `agent_complete` | `duration` (seconds, `round(duration,2)`) | `engine.py:3473` | VERIFIED |
| Per-agent **tokens** (`"30.1k tok"`, `tok`) | `agent_complete` | `input_tokens`, `output_tokens`, `total_tokens` | `engine.py:3475–3476` | VERIFIED |
| Per-agent **cache split** | `agent_complete` | `cache_read_tokens`, `cache_write_tokens` | `engine.py:3479–3480` | VERIFIED (stripped from goldens by `_VOLATILE_STRIP_KEYS`, live on the wire) |
| Per-agent **output size** | `agent_complete` | `output_length` (chars) | `engine.py:3474` | VERIFIED |
| Agent **index / total** ("agent 4 of 5") | `agent_complete` | `index`, `total` | `engine.py:3474` | VERIFIED |
| Run **total tokens** (`"14.8M"`) + input/output split | `pipeline_complete` | `total_input_tokens`, `total_output_tokens`, `total_tokens` | `engine.py:2322–2324` | VERIFIED |
| Run **total cache split** | `pipeline_complete` | `total_cache_read_tokens`, `total_cache_write_tokens` | `engine.py:2327–2328` | VERIFIED (golden-stripped) |
| Run **duration** (`"24m 6s"`) | `pipeline_complete` | `total_duration` (seconds) | `engine.py:2316` | VERIFIED |
| Run **agents done / total** (`"5 / 5 agents"`) | `pipeline_complete` | `agents_completed`, `agents_total` | `engine.py:2317–2318` | VERIFIED |
| **Estimated cost** (est. spend) | `pipeline_complete` | `estimated_cost_usd` (via shared `estimate_cost_usd()`, cache-discounted: prices uncached input = `total_input − cache_read − cache_write`, plus cache tiers) | `engine.py:2334–2341` | VERIFIED |
| **Model id** | `pipeline_complete` | `model_id` | `engine.py:2342` | VERIFIED (golden-stripped) |
| **Deliverable** name + mimetype | `pipeline_complete` | `deliverable_filename`, `deliverable_mimetype` | `engine.py:2320–2321` | VERIFIED (golden-stripped) |
| **Degraded** flag + failed agents | `pipeline_complete` (conditional) | `status="degraded"`, `agents_failed[]` | `engine.py:2389–2390` | VERIFIED (present only when partially failed) |
| **Version numbers** (v1 / v2, version timeline) | `/family` aggregation | `revision_index` (1-based chronological, ordered `created_at ASC, id ASC`) | `runs.py:920, 1000–1011` | VERIFIED |
| Construction **checklist count** | `task_progress` | `completed_count`, `completed_tasks[]` | `engine.py:3113–3114` | VERIFIED (caps at N-1 during the final fix-loop — KAN-99; see derivation contract §3) |
| **Wave** progress (wave i, task_ids) | `wave_started` / `wave_completed` / `wave_failed` | `wave_index`, `step`, `task_ids` | `wave_scheduler.py:269, 293, 299` | VERIFIED |
| **Sub-agent / worker** rows | `subagent_spawned` / `subagent_result` | `worker`, `agent`, `isolation`, `depth` (+ stamped `wave_index`, `step`) | `fanout.py:508–510, 514`; stamp `wave_scheduler.py:283–287` | VERIFIED |

---

## 2. `agent_input.context_sources` — the "Context received" rail (in-code verification)

**Requirement (POR SC-2):** verify that `agent_input.context_sources` carries a **name + size** per source, and pin the exact sub-field names.

**Emit site:** `agent_input` event, `engine.py:2771–2778`; `context_sources` is built by `_build_context_sources(spec, ordered_agents, ectx)` at `engine.py:5116–5143`. Each source entry is a dict with these EXACT sub-fields (verified in code):

| Sub-field | Type | Meaning |
|---|---|---|
| `type` | str | `"summary"` (text output) or `"artifact"` (typed artifact) |
| `agent_id` | str | the upstream (producing) agent id |
| `agent_name` | str | the upstream agent's display name |
| `summary_length` | int | character length of the summarized/consumed output |
| `full_output_length` | int | character length of the full upstream output |

**VERDICT — name+size sub-fields:**
- **NAME → VERIFIED** as `agent_name` (fallback `agent_id`). There is NO literal `name` key; the display name lives in `agent_name`.
- **SIZE → VERIFIED** as `full_output_length` (and `summary_length`) — a **character count**, not bytes. There is NO literal `size` key.

**Important semantic caveat (do not mis-wire):** `context_sources` describes **upstream AGENT outputs** consumed into this agent's prompt (routed by `produces`/`consumes` via `_filter_consumed_outputs`), NOT uploaded files. The mock's "Context received" rail renders file-like rows with `{name, meta}` where `meta` is a size + a **cache/reduction %** (e.g. `'36.4k · -12%'`, `'151.6k · -70%'`, mock `Run:805/842`). The size maps to `full_output_length`/`summary_length`, but:
- **The cache / reduction −% sub-field is UNVERIFIED in `context_sources`.** No cache-% or compaction-ratio key exists on the `context_sources` entries. Per evidence 07 §3 + evidence 03 §5, the cache −% must come from **separate P26 cache telemetry** (the per-agent `cache_read_tokens` / `cache_write_tokens` on `agent_complete`, `total_cache_*` on `pipeline_complete`) and compaction ratios (the `html_skeleton` compaction capability) — NOT from `context_sources`. Phase 32 must compute the −% from cache telemetry, not read it off the rail source.
- The mock renders these as uploaded-file rows; the real source is inter-agent output handoffs. Phase 32 should relabel accordingly (or additionally surface real uploaded context once UPLD-01/03 land — currently no `POST /runs/{id}/files` persistence exists; evidence 03 §4 CORRECTIONS).

**Golden note:** `context_sources` is listed in `_VOLATILE_STRIP_KEYS` (`tests/agents/characterization/_normalize.py:101–170`) — it is stripped from the canonical multiset so the 5 goldens stay byte/event-identical, but it IS present on the live wire (verified above).

---

## 3. Figures marked UNVERIFIED (Phase 32 must chase)

| Figure | Reason UNVERIFIED |
|---|---|
| Context-source **cache / reduction −%** (`-12%`, `-70%`) | Not a `context_sources` sub-field. Must be derived from P26 cache telemetry (`cache_read_tokens`/`cache_write_tokens`) + compaction ratios (`html_skeleton`); the exact per-source attribution of a −% to an individual context row is NOT emitted — Phase 32 must define the computation. (Evidence 01 §11 flags these as illustrative strings in the mock.) |
| Uploaded-file context rows (name + byte size) | No persistence surface exists (`POST /runs/{id}/files` absent, `context_provider:uploaded_files` absent — evidence 03 §4/§8 CORRECTIONS). The rail today can only show inter-agent output sources, not user uploads. |
| Per-agent live token/elapsed during streaming (Live `"…tok · live"`) | Live/streaming interim counts accrue from `agent_chunk` usage events; the pinned settled values are on `agent_complete`. The interim display value is a client-side running sum, not a single emitted field. |

---

## 4. Rule for Phase 32

Wire only VERIFIED figures directly. For any UNVERIFIED figure, either compute it from the pinned telemetry fields (documenting the derivation) or omit it — never synthesize. This prevents the mock-fiction regressions evidence 01 §9 warns about.
