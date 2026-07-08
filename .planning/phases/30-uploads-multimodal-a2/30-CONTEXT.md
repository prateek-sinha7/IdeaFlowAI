# Phase 30: Uploads & Multimodal [A2] - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR + evidence.

<domain>
## Phase Boundary — SCOPE-TRIMMED (image spine already landed)

The run-entry IMAGE spine already shipped pre-milestone (IMAGE-INPUT-PLAN waves `edw`/`frv`/`gvq`): `backend/agents/capabilities/input_providers/run_images.py`, the prototype `input_providers: [run_images]` opt-in, `prototype-specify` `injects:[images]`, WS ingress + validation caps + vision guard, FE picker/preview, 7 tests. VERIFIED present. So Phase 30's REMAINING scope is the file/document half + the residues:

1. **UPLD-01** — `POST /api/runs/{id}/files` (multipart, two-layer owner check → 404) persisting bytes under the run's `RunSandbox`.
2. **UPLD-03** — document text-extraction (reuse `/api/files/extract-text` internals) into STICKY context AND raw bytes into the sandbox for agent `read_file`; a new `context_provider:uploaded_files` capability (register + `_KNOWN` + `discover()` lockstep + drift-guard bump); sticky-context proof: the uploaded context is present in EVERY subsequent `agent_input`.
3. **UPLD-02 residue** — the PER-TURN image carrier: images attached to a chat turn ride the Phase-29 `POST /api/runs/{id}/messages` path into the NEXT dispatch's `HumanMessage` content blocks (Phase 29 built the chat_message path — reuse it; do NOT rebuild).
4. **UPLD-04 residue** — client-side image resize before upload.
5. **ND-10 (LOCK-E)** — image persistence for replay/reopen is DEFERRED: render an honest "image not kept" placeholder on reopen; do NOT build durable image storage.

Authoritative inputs (READ — do not re-derive): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §2 (D-07 — the image path is PAYLOAD-TRANSIENT: images ride the message → `ectx.run_images` → base64 blocks, they NEVER touch the sandbox/DB/run_events; the "Images → RunSandbox" wording was corrected — only DOCUMENTS go to the sandbox), §3 (⭐ DECISION LOCK — LOCK-E defers image-persistence, LOCK-C no checkpoints). Evidence: `03-backend-chat-surface-map.md` §4 (the ONE upload surface today = `POST /api/files/extract-text`, no persistence) + §8 (gap analysis) + its CORRECTIONS addendum (image spine now landed), `12-coverage-and-backend-map.md` (Part 2 Category-A/B). Phase-29 chat path: `backend/app/api/run_commands.py` / `chat_router.py` (the `POST /api/runs/{id}/messages` + narrator surface to reuse for per-turn images).

**Register note:** the image-input cluster (waves edw/frv/gvq) is NOT yet in `IMPLEMENTATION-REGISTER.md` — add its entry as part of this phase (memory: register-first discipline).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3; do NOT re-open)

- Documents → sandbox + sticky context (UPLD-01/03). Images → payload-transient (already built); per-turn images reuse the Phase-29 message path (UPLD-02). Client resize (UPLD-04). Image-persistence DEFERRED → "image not kept" placeholder on reopen (ND-10 / LOCK-E).
- New capability `context_provider:uploaded_files` — kernel-pure port impl (or app-side if heavy-dep), self-registered, surfaced generically; the compiler records it, `_compose_context_message` composes it, gated per-agent by `injects:`. SC-001: keyed on the declared capability, never a workflow name.
- Ownership: `POST /api/runs/{id}/files` two-layer owner check (WorkflowRun.user_id == principal, then ScopedStore) → 404 on miss (P13/P25 IDOR precedent, `user_id` not the nullable `owner_id`). Size/type caps + mime allow-list on the upload (mirror the image-ingress caps).

INVARIANTS: SC-001/INV-1, INV-3 (5 goldens byte/event-identical — uploads dormant on golden runs), INV-13, import-linter 4/0, additive migrations only (Q3 — likely none; sandbox + run_events cover it), owner+workspace on anything persisted.
</decisions>

<code_context>
## Existing Code Insights (from evidence 03/12)

`backend/app/api/file_extract.py` (`POST /api/files/extract-text` — PDF/DOCX/PPTX→text, no persistence, the internals to reuse); `backend/app/agents/sandbox.py` (`RunSandbox` under `RUNS_ROOT`, traversal-proof, the deepagents `FilesystemBackend` root — where uploaded docs land for `read_file`); `backend/agents/capabilities/input_providers/run_images.py` + `context_providers/*` (the provider pattern to clone for `uploaded_files`); `backend/agents/capabilities/registry.py` (`@register` + `_KNOWN` + `discover()` lockstep + the drift-guard count); `backend/app/api/run_commands.py`/`chat_router.py` (Phase-29 `POST /api/runs/{id}/messages` — thread per-turn images here). Offline verify: targeted suites + `/opt/homebrew/bin/lint-imports`, `python3.11`; full pytest HANGS — never run it.
</code_context>

<specifics>
## Specific Ideas

Deliverables: `POST /api/runs/{id}/files` (owner-scoped, capped) → RunSandbox; a `context_provider:uploaded_files` capability making uploaded doc text sticky in every subsequent `agent_input`; the per-turn image carrier wired onto the Phase-29 message path → next dispatch content blocks; client-side image resize in the FE attach UI; the "image not kept" reopen placeholder (ND-10); and the IMPLEMENTATION-REGISTER entry for the already-landed image-input cluster. Additive; goldens byte-identical.
</specifics>

<deferred>
## Deferred Ideas

Image persistence for reopen/replay (ND-10/LOCK-E — placeholder only). Team-sharing/resume-from-failed/prompt-override deferred (LOCK-E). Durable non-text binary handling beyond sandbox placement.

## Execution-viability note (autonomous run)
The upload endpoint, `uploaded_files` provider, sticky-context proof, and per-turn carrier are additive backend + FE, offline-testable (targeted suites + shape tests, mirroring the image-input tests). Any live-Bedrock multimodal confirmation is deferred to the milestone-end live pass (Phase 34). If a check needs a live server/SSO, mark it live-deferred — do not hang, do not fabricate.
