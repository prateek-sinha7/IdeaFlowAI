# Phase 32 — Run-Screen Redesign [A4] · UI Review (6-pillar visual audit)

**Audited:** 2026-07-08
**Baseline:** evidence 11 §B (canonical shared-surface spec) + POR D-15. This is the reskin phase — audited AGAINST the locked §B tokens/status-model, not a pixel diff (DS mock HTML is not in-repo).
**Method:** Offline — code read + `git grep` over the Phase 32 delta (`7d5a467d..HEAD`). No dev server; anything needing live render is flagged `human-verify`.
**Verdict:** **FLAG** (18/24) — token layer + new primitives + chat/Steps/Audit/WaveTree are faithfully tokenized; but the **Preview + ReviewGate + layout shells were never migrated off the retired navy `#1B2A4A`**, which breaks the one-blue mandate on in-scope surfaces. Not a BLOCK (nothing breaks task completion; a11y region intact), but the reskin is **not complete** until the navy leak is closed.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Terminology aligned (Thinking→Steps, "Audit" panel, canonical status labels); `Badge` renders raw free-string status when `label` omitted (LW). |
| 2. Visuals | 3/4 | Clean primitive hierarchy, but a second brand (navy `#1B2A4A` + `to-violet-600` gradient) competes with brand purple on the Preview/Gate surfaces. |
| 3. Color | 2/4 | Token layer + primitives + chat/Steps/Audit/WaveTree are pure-token; **13× hardcoded `#1B2A4A` + 2× `#f5f5f0` + 77 retired `gray-/blue-` utilities** leak in Preview/ReviewGate/DashboardLayout. One-blue violated. |
| 4. Typography | 4/4 | Manrope + Heebo swapped in; SF-Mono code token; retired Inter/Fraunces/JetBrains fully gone; primitives use `font-sans` 12.5px per DS §B4. |
| 5. Spacing/Radius | 3/4 | Radius ladder resolved (button=10, card=14) and consumed via `--radius-*`; off-ladder `rounded-md/rounded-xl` persists in the un-migrated Preview/Gate. |
| 6. Experience Design | 3/4 | Terminal states rendered, `role=log`+`aria-live=polite` preserved, empty/filter/export states present; LW-03 cancelled-color split (red vs amber) is a live status-semantics regression. |

**Overall: 18/24**

---

## Top Findings (ranked by severity)

### 1. BLOCKER — Retired navy `#1B2A4A` never migrated to brand tokens (Color / one-blue)
The reskin's core value is token fidelity to §B2 (`--brand #3C2CDA`). Three **in-scope** changed files still hardcode the old navy and retired neutrals instead of consuming tokens:
- `frontend/src/components/preview/ReviewGatePanel.tsx` — **7×** `#1B2A4A` (gate icon gradient `from-[#1B2A4A] to-violet-600` :339; approve button `bg-[#1B2A4A]` :436; reject button border/text :453; textarea focus ring :414) + retired `gray-*` neutrals.
- `frontend/src/components/preview/PreviewPanel.tsx` — **2×** `#1B2A4A` on the export controls (`bg-[#1B2A4A] … hover:bg-[#2a3d5e]` :1075, :1084).
- `frontend/src/components/layout/DashboardLayout.tsx` — **4×** `#1B2A4A` (progress-dots/ping :199/203/236/247) + **2× `#f5f5f0`** page background (:1357, :1585) where §B2 mandates `--surface-paper #F0EEE7`.
- Across Preview + ReviewGate: **77** occurrences of retired `bg-/text-/border-gray-*` and `blue-*` utilities.

Impact: on the Preview tab and the inline Steps review-gate (the exact surfaces this phase reskinned), the user sees a navy/violet brand competing with the canonical `#3C2CDA` used everywhere else in the run screen. This is the D-15 "adopt the mock's visual language" mandate half-applied. `ReviewGatePanel` is squarely in scope — it was de-literalized for SC-001 in plan 32-08 but its palette was left untouched.
**Fix:** Replace `#1B2A4A`→`bg-brand`/`text-brand`/`hover:bg-brand-pressed`, drop the `to-violet-600` gradient, `#f5f5f0`→`bg-surface-paper`, and swap `gray-*`→`ink-*`/`line-*` tokens. Prefer routing the gate/export buttons through the new `Button` primitive.

### 2. WARNING — LW-03 confirmed: cancelled renders red in WaveTree, amber in Badge (Experience / status correctness)
`frontend/src/components/workflow/WaveTreePanel.tsx:38` routes `cancel*` → `"failed"` bucket → `text-status-failed` (red, :55), documented as IN-05 "cancelled is terminal." But `frontend/src/components/ui/Badge.tsx:27-28` maps `cancelled` → `text-status-amber` per §B3. A single cancelled run therefore reads **amber in the lane/status badge and red in the wave tree** — a direct violation of §B3's one-status-palette rule (cancelled = amber `#9A6B1E`, agent-level label "Skipped"). Scope: confined to these two components; both are token-consuming (no hex), so this is a mapping decision, not a leak.
**Fix (canonical):** give `cancelled` its own amber branch in `WaveTreePanel.statusKind` + `STATUS_STYLE` so it matches Badge/§B3. If the red is a deliberate product-semantics choice ("cancelled wave = terminal failure"), it must be ratified as a §C human decision and the annotation is insufficient on its own.

### 3. WARNING — `Badge` label-free fallback renders raw free-string status (Copywriting)
`frontend/src/components/ui/Badge.tsx:62` — `{label ?? status}`. The color ramp is normalized (`normalizeStatus`) but the visible text is not, so `status="completed"` with no `label` shows "COMPLETED" while painted on the `done` ramp. Cosmetic; contradicts §B3's canonical labels.
**Fix:** render a display-name map keyed on the normalized key, e.g. `label ?? DISPLAY[key]`.

### 4. WARNING — off-ladder radii persist on un-migrated surfaces (Spacing/Radius)
Preview/ReviewGate still use Tailwind `rounded-md`/`rounded-xl` rather than the resolved `--radius-button (10)` / `--radius-card (14)` ladder that the new primitives consume. Cleared automatically if finding #1 routes these through `Button`/`Card`.

---

## Pillar Detail

### Pillar 1 — Copywriting (3/4)
- Verified: tab relabel Thinking→Steps (`Tabs`/tab-host, plan 32-07); Audit panel named "Audit" per §7; status labels flow through §B3 keys. No generic "Submit/OK" leakage found in the reskinned components.
- Gap: Badge raw-status fallback (finding #3). No empty/error copy regressions found in `AuditTab` (has empty + filtered states) or `WaveTreePanel` (`ordered.length === 0` empty branch, :92).

### Pillar 2 — Visuals (3/4)
- Focal hierarchy is clean in the tokenized components; primitives give consistent chip/button/card weights.
- Deduction: the navy+violet gradient on the gate icon (`ReviewGatePanel.tsx:339`) and navy export buttons introduce a second accent that fights the brand focal color. human-verify the composed run screen for the two-brand effect once a server is up.

### Pillar 3 — Color (2/4)
- Strong: `globals.css` `@theme`/`:root` is a verbatim §B2/§B3/§B4 port (brand one-chroma, warm ink, status ramp, severity ladder, resolved radius). `Button/Card/Pill/Tabs/Badge`, `RunChatLane`, `AuditTab`, `AgentThinkingTab`, `PrototypePipelineView`, `WaveTreePanel` = **zero hex**, all `bg-brand`/`text-status-*`/`var(--status-*)`.
- Status-color correctness verified: running = blue (`Badge.running`→`text-status-running #3C2CDA`; `RunChatLane` primary `bg-brand`), NOT amber — the mock's Handoff amber-running bug is absent. "Queued/Not run" = neutral grey (`status-queued #9A9B92`), NOT amber — the Failed-mock amber "Not run" bug is absent.
- BLOCKER: navy `#1B2A4A` / `#f5f5f0` / retired `gray-*`/`blue-*` leak (finding #1). Note: `globals.css` `.markdown-content` also carries off-palette cool greys (`#374151`, `#111827`, `#6b7280`, `#f9fafb`, `#1e293b`) — pre-existing, inside the token file, lower priority but should fold into the ink ramp.

### Pillar 4 — Typography (4/4)
- `app/layout.tsx` loads `Manrope` + `Heebo` (`--font-manrope`/`--font-heebo`), bound to `--font-sans`/`--font-serif`; `--font-mono` = `'SF Mono', ui-monospace, Menlo, monospace` per §B2. No Inter/Fraunces/JetBrains anywhere in the delta. Primitives standardize on `font-sans`, 12.5px buttons/tabs, 8.5px badges per §B4/§6.7.

### Pillar 5 — Spacing/Radius (3/4)
- Radius ladder resolved and consumed via `rounded-[var(--radius-button)]` (10) / `--radius-card` (14) / `--radius-tag` (5) / `--radius-pill` (999). Deduction for off-ladder `rounded-md/xl` on the un-migrated Preview/Gate (finding #4).

### Pillar 6 — Experience Design (3/4)
- a11y verified: `ChatPanel.tsx:207-208` retains `role="log"` + `aria-live="polite"`; `RunChatLane` delegates to it and its test (`RunChatLane.test.tsx:47-51`) guards the attribute. Streaming region preserved.
- Terminal states (cancelled/failed/degraded) render off generic pipeline markers (plan 32-06). Audit tab has counters, severity filters, empty/filtered states, and client-side CSV/JSON export.
- Deduction: LW-03 cancelled red/amber split (finding #2). human-verify: focus-ring visibility and contrast of `text-status-*` chips on their `-fill` backgrounds need a live render to confirm WCAG AA; the token values match §B3 which the mocks used, so low risk.

---

## Files Audited
- `frontend/src/styles/globals.css` (token layer)
- `frontend/src/components/ui/{Button,Card,Pill,Tabs,Badge}.tsx` (primitives)
- `frontend/src/app/layout.tsx` (font swap)
- `frontend/src/components/chat/RunChatLane.tsx` + `ChatPanel.tsx` (aria-live)
- `frontend/src/components/preview/{PreviewPanel,ReviewGatePanel}.tsx`
- `frontend/src/components/results/{AuditTab,AgentThinkingTab,PrototypePipelineView}.tsx`
- `frontend/src/components/workflow/WaveTreePanel.tsx`
- `frontend/src/components/layout/DashboardLayout.tsx`
- Baseline: `.planning/v2.0-evidence/11-cross-mock-reconciliation.md` §B; POR D-15.

_Screenshots: not captured (offline audit, no dev server)._
