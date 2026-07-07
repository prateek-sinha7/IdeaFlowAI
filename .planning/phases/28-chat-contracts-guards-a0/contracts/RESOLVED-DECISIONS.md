# Resolved-Decisions Record — LOCK-A..G + ND-1..ND-13

**Phase 28 (A0) decision record — the single citable authority for the milestone's locked scope.**
**Authority:** POR §3 ⭐ AUTONOMOUS-RUN DECISION LOCK (user approved "go with all recommendations", 2026-07-07) in `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`, with the ND-13 cosmetic defaults pinned against evidence `11-cross-mock-reconciliation.md` §B/§C.

> **These are DECIDED.** Phase 28 only FORMALIZES them — it does NOT re-derive or re-open ANY decision (mode: yolo / skip_discuss, POR §3). Every ND below is either RESOLVED or DEFERRED with its lock source. Later phases CITE this record instead of re-litigating ND-1..ND-13. No decision here may be re-opened without an explicit human override at the POR level.

---

## 1. The AUTONOMOUS-RUN DECISION LOCK — LOCK-A..G

| Lock | Substance |
|---|---|
| **LOCK-A (proceed)** | v1.0 stays `verifying`; v2.0 EXECUTION proceeds now. The live-Bedrock close-out folds into Phase 34 / is marked live-deferred where SSO is interactive. |
| **LOCK-B (transport — ADDITIVE-ONLY, overrides D-13 deletion timing)** | The unattended Phase 29 is **ADDITIVE-ONLY**: build the SSE stream + REST commands **ALONGSIDE** `/ws/chat`, behind a transport flag. **Do NOT delete the WS run-handlers, do NOT arm the deletion ratchets, do NOT touch `useWebSocket.ts`.** WS deletion + the INV-12 exit gate become a SEPARATE supervised follow-up after the human validates the cutover live. Wire-parity characterization is still built and must pass (SSE ≡ WS frames). |
| **LOCK-C (no human checkpoints)** | `mode: yolo` + `skip_discuss: true`; the run auto-proceeds through routine gates. plan-check / code-review / verify / security stay ON and may still park on a genuine blocker. |
| **LOCK-D (cost)** | Full power (Opus + max effort) on substantive agents; the 11 checker agents stay on Sonnet (quality-profile default). Accepted high overnight cost. |
| **LOCK-E (build-vs-defer)** | **DEFER** (do NOT build this milestone): workflow **team-sharing** (ND-12 / evidence 08), **resume-from-failed-step** (ND-4), per-agent **prompt-override persistence** (ND-7), **image-persistence-on-reopen** (ND-10 → render an "image not retained" placeholder). **Pre-launch chat (ND-1):** client-side only, kept until launch (no draft rows). **Concierge (ND-2): always-on.** |
| **LOCK-F (naming/look)** | Run output = **"Deliverable"** (ND-13.6); DS picker shows the **real ~14 count**, no catalog expansion (ND-8); deliverable-type names = the P22 `display_name`s (Interactive Prototype / User Stories / Presentation / App Builder / Custom, ND-13.7); the 5 cosmetic cross-mock conflicts take the reconciliation defaults (running=blue, "Not run"=grey, nav=purple-underline, avatar=rounded-square, radius buttons 10 / cards 14 — ND-13.1–5). Per-type agent roster = the real manifests (mechanical, D-15 rule iii). |
| **LOCK-G (honest limits)** | Live-Bedrock phases finish offline + mark "live check pending"; phases run **sequentially** (worktrees broken here); a genuine blocker **parks** the run rather than guessing. |

---

## 2. ND-1..ND-13 disposition table

One row per ND. **Decision** is RESOLVED (decided + in scope this milestone), RESOLVED-deferred (decided now, executed post-milestone), or DEFERRED (out of this milestone per a lock). **Disposition source** cites the POR / lock authority.

| ND | Topic | Decision | Disposition source |
|---|---|---|---|
| **ND-1** | Pre-launch chat persistence | **RESOLVED** — v1 client-side transcript only (folds into brief + optional `chat_history` artifact at launch); NO draft run rows this milestone. `draft` rows deferred to Phase 37 (two consumers: composer chat + Configure "Save draft"). | LOCK-E ("pre-launch chat client-side only, kept until launch, no draft rows") |
| **ND-2** | Concierge rollout | **RESOLVED** — Concierge **always-on** (default-on lane + router); behind a per-run toggle initially; **Haiku** default model. | LOCK-E ("Concierge: always-on") |
| **ND-3** | Legacy free-chat retirement (`user_message` / `ChatRunner` / 7-agent `chat` pipeline / `Sidebar`) | **RESOLVED-deferred** — record the deprecation decision now; **execute post-milestone** (INV-12 eventually demands one chat subsystem). | POR §2 ND-3 + INV-12 (single chat subsystem) |
| **ND-4** | Resume-from-failed-step (mock's "Reopen & fix") | **DEFERRED** — real new backend scope (engine has crash-resume, not user-triggered failed-run resume). "Edit brief & run again" ships (relaunch exists). Milestone B / v-next. | LOCK-E (resume-from-failed-step deferred) |
| **ND-5** | Share button | **DEFERRED** — mock-only; not built. | POR §2 ND-5 (deferred, mock-only) |
| **ND-6** | Audit export | **RESOLVED (partial)** — CSV/JSON client-side **in scope** (Phase 32); compliance-**PDF deferred**. | POR §2 ND-6 |
| **ND-7** | Per-agent system-prompt override persistence (shell Agent drawer) | **DEFERRED** — touches AGENT.md territory; needs its own record before Phase 37; not built this milestone. | LOCK-E (prompt-override persistence deferred) |
| **ND-8** | Design-system catalog scale | **RESOLVED** — DS picker uses the **real ~14 count** (mock's "150 systems" is fiction); NO catalog expansion. Product decision on real catalog size/sourcing deferred to before Phase 37. | LOCK-F (DS real ~14 count, no expansion) |
| **ND-9** | Steering-state across resume | **RESOLVED (design-in-Phase-29)** — pending steering notes / chat-session state across `resume_run` addressed in **Phase 29's design** (same additive-column remedy class as P22's WR-02). | POR §2 ND-9 (address in Phase 29 design) |
| **ND-10** | Image persistence for replay/reopen | **DEFERRED** — run-entry images stay payload-transient (reopen / `resume_run` / restart lose them); render an explicit **"image not retained" placeholder**. Interacts with ND-9. | LOCK-E (image-persistence deferred → placeholder) |
| **ND-11** | Unify the consume-once injection seams + thread-id policy | **RESOLVED (Phase-29 first design task)** — whether `steering_notes` subsumes the `redo_directive` / `spec_revision_context` family, plus thread-id policy reconciliation (Redo forks `:redo{N}`; KAN-101 sub-pipeline reuses BASE threads), is Phase 29's **first design task**. | POR §3 Wave 2 ("resolves ND-11 as its first design task") |
| **ND-12** | Sibling-screen scope (second teardown lock) | **RESOLVED (scoped)** — Login/Register → **Phase 35** reskin-only; Admin → **Phase 35** reskin (Status/Last-active columns + email-invite deferred); identity traps (SSO/SCIM, password-reset, email-invitations, suspension) **DROPPED**; Composer + Wizard → **Phase 37**; **Handoff DEFERRED post-v2.0** (its `useWebSocket.ts` survives, ratchets carve it out). Team-sharing deferred per LOCK-E. | POR §2 ND-12 (locked 2026-07-07) + LOCK-E |
| **ND-13** | Seven cross-mock design conflicts (evidence 11 §C) | **RESOLVED (defaults) / 2 product picks taken** — (1) nav = **purple-underline**; (2) radius = **buttons 10 / cards 14**; (3) Handoff amber `running` = **bug → make blue**; (4) `cancelled` label by scope (run "Cancelled" / agent "Skipped") = **keep, intentional**; (5) avatar = **rounded-square** (align DS); (6) run-output name = **"Deliverable"** (product pick taken); (7) deliverable-type names = the P22 `display_name`s + **real per-type agent roster** (real manifests, product-pick taken). | LOCK-F + evidence 11 §B/§C reconciliation defaults |

---

## 3. Additive-only + always-on summary (the load-bearing invariants)

- **Transport is ADDITIVE-ONLY** (LOCK-B): SSE + REST are built **alongside** `/ws/chat` behind a flag; no WS deletion, no ratchets, `useWebSocket.ts` untouched this milestone.
- **Concierge always-on** (ND-2 / LOCK-E), Haiku default.
- **LOCK-E deferrals** (out of this milestone): team-sharing, resume-from-failed-step, per-agent prompt-override persistence, image-persistence-on-reopen (placeholder instead). Pre-launch chat is client-side only.
- **Output name is "Deliverable"** (LOCK-F / ND-13.6); DS real ~14 count (ND-8); P22 `display_name` type names (ND-13.7).

Every disposition above is DECIDED. This record is the single artifact later phases cite; re-opening any ND requires an explicit POR-level human override.
