# LIVE-01 — Consolidated Live-Bedrock Evidence Record (8 Standing Deferrals)

**Requirement:** LIVE-01 (Phase 22 — Capability Surfacing and User Empowerment)
**Decision:** D-24 (22-CONTEXT.md) — defer the consolidated live-Bedrock pass to milestone-end; phase completion gates on **OFFLINE evidence** (the `defer-live-verification` project convention).
**Status:** OFFLINE evidence complete for all 10 sub-items → **phase-completion bar satisfied**. The consolidated live pass is the **milestone-end** confirmation.
**Date:** 2026-06-14

---

## Gating Rule (read first)

> **Phase completion gates on the OFFLINE evidence per item, NOT on a live Bedrock run** (D-24 / `defer-live-verification` convention).
>
> Every standing deferral below already has a **landed offline structural fix** (cited SUMMARY / commit / test). That offline evidence is what closes the phase. The **live re-confirmation** is recorded here as **DEFERRED-to-milestone-end-live-pass** — it runs once, consolidated, at milestone-end, and is **not** a blocker for marking Phase 22 complete.
>
> A row is marked **CONFIRMED-live** ONLY where a live run was genuinely performed (none in this plan — this plan does not invoke live Bedrock).

## Live-Pass Target (milestone-end)

| Field | Value |
|-------|-------|
| AWS profile | `default` |
| Account | `473293451041` |
| Model | `claude-haiku-4-5` (Haiku 4.5) |
| Entitlement | **Full** — ISS-018 does **NOT** block on the `default` profile |

**ISS-018 note:** ISS-018 is the `hexaware-srini` Bedrock entitlement loss (`ValidationException: Operation not allowed` on acct `731451715500`, an org-SCP / permission-set change — diagnosed, IT-escalation drafted). It is an **external IT escalation, out of repo scope**, and **does not block on the `default` profile** (acct `473293451041`, full entitlement). The milestone-end live pass runs entirely on `default`, so ISS-018 cannot gate it.

---

## Per-Item Evidence Table

Disposition legend:
- **CONFIRMED-live** — an actual live Bedrock run was performed (default profile, Haiku 4.5).
- **DEFERRED-to-milestone-end-live-pass** — offline structural fix landed; live re-confirm batched to the milestone-end pass (the D-24 default).

| # | Item | Offline structural evidence (landed) | Disposition | Live-pass target |
|---|------|--------------------------------------|-------------|------------------|
| 1 | **COMPACT-03** (token delta) | Deterministic offline CI gate proves task-2+ context ≤50% of full-HTML: `test_phase3_compaction.py::test_build_task2_context_is_at_least_50pct_smaller` PASSED (ratio 0.031 — 96.9% reduction on a 29,749-char fixture; 0 DB/Bedrock/key). Opt-in dual-gated live evidence harness `test_phase3_token_delta_live.py` (293 lines) SKIPS cleanly with no env. Ref: `.planning/phases/03-token-trim-measured-change-0c/03-VERIFICATION.md` (rows 3, 44, 77). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 2 | **P6 CR-02** (checkpointer fallback) | Fresh per-attempt thread_id derivation implemented + verified: `engine.py:1842` `retry_thread_id = f"{thread_id}:retry{_attempt}"` → `create_runner` at 1846 (VERIFIED). InMemory checkpointer never writes mid-stream state, so stale-checkpoint resume is **structurally unreachable offline** — only a live Postgres checkpointer + Bedrock throttle can exercise it. Ref: `.planning/phases/06-model-policy-1c/06-VERIFICATION.md` (rows 8–13, 58, 142). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 3 | **P8 OTLP** (collector export) | otel_tracing hook + span export proven OFFLINE via injected `InMemorySpanExporter` through the hook's OWN `_build_span_processor` factory (+ `_TRACER` reset): real `OtelTracingHook.handle` exports exactly 1 span with `flowin.hook/flowin.event/flowin.agent_id` attrs under scope `flowin.agents.hooks.otel_tracing`; parallel test pins OTLP-pkg-absent → console-processor degrade (ISS-010 closed by 17-02). Logging-only path fully functional now; real OTLP-collector export is the OPTIONAL upgrade path. Ref: `.planning/phases/08-.../08-VERIFICATION.md` (frontmatter reconciliation + rows 13–15, §2). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 4 | **P13 F1** (review_gate_ready on a live WS stream) | Offline boundary fully verified (gate-event composition + WS frame contract green). Live confirm = `review_gate_ready` observed on a real live WS stream from a connected browser. Ref: `.planning/phases/13-live-verification-gap-closure/13-VERIFICATION.md` (deferred frontmatter rows 14–15). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 5 | **P13 F4** (no fabricated tool-call XML preamble on live Haiku) | P15 defused the prompt trigger (shipped+pinned); offline boundary verified (preamble composition + retry/parse tests green). Live confirm = live Haiku 4.5 actually emits no fabricated tool-call XML with the no-tools preamble + handoff coder's live one-shot returns JSON. Closely related to P19 ISS-004 (engine `agent_chunk` sanitizer). Ref: `13-VERIFICATION.md` (deferred row 8). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 6 | **P13 F5** (all 15 app_builder agents role-conformant on live) | Prompt re-templating is content-only → live agent behavior is unverifiable offline; offline boundary (zero migration residue, contracts threaded, loader green) fully verified. Live confirm = full live app_builder run, all 15 agents role-conformant. Ref: `13-VERIFICATION.md` (deferred rows 11–13). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 7 | **P14 SC4** | Offline boundary verified for the Phase-14 model-policy/runtime surface (see `.planning/phases/14-.../14-VERIFICATION.md`). Live SC4 re-confirm batched to the milestone-end pass per the `defer-live-verification` convention. | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 8 | **P16 SC1** (real ValidationException → pipeline_failed) | Offline fault-injection + parity evidence sufficient to mark complete; live SC1 = real Bedrock ValidationException → run ends `pipeline_failed` with agent_error/0 agent_complete + FE degraded panel. (Note: SC1/SC2 were live-confirmed on `srini` during the 2026-06-13 campaign — see CAMPAIGN-2026-06-13; re-confirmed here as a `default`-profile milestone-end pass for completeness.) Ref: `.planning/phases/16-.../16-VERIFICATION.md` (rows 9, 40, 74, 95). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 9 | **P16 SC2** (real Stop → pipeline_cancelled on the wire) | Offline fault-injection + parity evidence sufficient; ISS-023 cooperative-cancel yields `pipeline_cancelled` once + returns. Live SC2 = real Stop → `pipeline_cancelled` frame on the wire. (Also live-confirmed on `srini` 2026-06-13; re-confirmed on `default` at milestone-end.) Ref: `16-VERIFICATION.md` (rows 9, 40, 74, 95). | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |
| 10 | **P19 ISS-004** (0 tool-XML in live `agent_chunk` stream) | 19-03 added the deterministic engine `agent_chunk` sanitizer (`_ChunkStreamSanitizer`, chunk-straddle buffer, probe-gated tool-less, SC-001 generic — no workflow/agent literal); authoritative output_chunks left RAW so the 5 characterization goldens stay byte-identical (INV-3); 4 fault-injection tests green (`tests/agents/test_chunk_sanitizer.py`). Commits 21f4d571 + 0a901b41. Live confirm = real Haiku sdlc-governance run → 0 tool-XML in live chunks. Ref: ISSUES-REGISTER ISS-004 (FIXED 19-03, live re-confirm pending); STATE.md 19-03 session note. | DEFERRED-to-milestone-end-live-pass | `default` (473293451041), `claude-haiku-4-5` |

---

## Summary of Dispositions

| Disposition | Count | Items |
|-------------|-------|-------|
| CONFIRMED-live (this plan) | 0 | — (this plan does not invoke live Bedrock; D-24 defers the live pass) |
| DEFERRED-to-milestone-end-live-pass | 10 | COMPACT-03 · P6 CR-02 · P8 OTLP · P13 F1 · P13 F4 · P13 F5 · P14 SC4 · P16 SC1 · P16 SC2 · P19 ISS-004 |

All 10 sub-items (the 8 standing deferrals) carry a **landed offline structural fix** with a cited SUMMARY / commit / test — the OFFLINE evidence that gates Phase 22 completion. The consolidated **live** re-confirmation runs once at **milestone-end** on the AWS `default` profile (acct `473293451041`) with `claude-haiku-4-5` (Haiku 4.5); **ISS-018 does not block on `default`**.

## References

- 22-SPEC.md — LIVE-01 (deferral list + acceptance; phase gates on offline evidence).
- 22-CONTEXT.md — D-24 (defer to milestone-end; `default` profile / Haiku 4.5; ISS-018 does not block on `default`).
- 22-RESEARCH.md — § Environment Availability (AWS `default` profile, Haiku 4.5) + LIVE-01 deferral row.
- .planning/ISSUES-REGISTER.md — ISS-018 (entitlement, external IT escalation), ISS-004 / ISS-010 lineage.
- Per-item phase VERIFICATION / SUMMARY docs cited inline in the table above.
- .planning/live-verification/CAMPAIGN-2026-06-13-phases16-19.md — prior live confirmations (SC1/SC2 on srini).
