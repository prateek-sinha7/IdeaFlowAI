# Phase 22 — UI Review

**Audited:** 2026-06-15
**Baseline:** `22-UI-SPEC.md` design contract (brownfield / reuse-first, INV-12)
**Screenshots:** not captured — dev server on :3000 returns **307 (auth redirect)**, and the audited surfaces (capability palette + Advanced expander) render *inside* the `AgentsPopup` popup behind authentication. A `/` screenshot would capture only the login redirect, not the surfaces. Code-only audit (Tailwind token audit + string/state audit against the contract).
**Auditor note:** Run inline by the orchestrator after the `gsd-ui-auditor` subagent failed to spawn on three consecutive `529 Overloaded` errors. Same methodology, same baseline.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Every contract string present verbatim (locked tooltip, auto-attach, empty/loading/error); no placeholders or generic labels in new code |
| 2. Visuals | 4/4 | Clear navy-eyebrow → group → row hierarchy; icon-only controls carry `aria-label`; locked rows correctly recessed. `Boxes` header icon is off the enumerated reuse list (nit) |
| 3. Color | 4/4 | Single `#1B2A4A` accent on reserved elements only (14× in new code); zero color leakage; locked = neutral gray, error = red idiom |
| 4. Typography | 4/4 | New surfaces use only the declared micro-ramp (`text-[9px]/[10px]/[11px]`) and two weights (400/600) |
| 5. Spacing | 3/4 | Lever/row chrome matches the dense inspector scale exactly, **but** the Advanced expander caps at `max-h-[240px]` — an undeclared value vs the contract's `max-h-[200px]` |
| 6. Experience Design | 3/4 | Full loading/error/empty/populated coverage + strong a11y, **but** locked-row reason is delivered only via native `title` on a non-focusable row, and composed selections are dropped on `resume_run` (WR-02, deferred) |

**Overall: 22/24**

---

## Top 3 Priority Fixes

1. **Advanced-expander scroll cap deviates from the declared scale** — `AgentsPopup.tsx:1188` uses `max-h-[240px]`; the contract declares `max-h-[200px] overflow-y-auto pr-1` for both palette *and* expander scroll regions (UI-SPEC Spacing → Exceptions). *Impact:* a one-off arbitrary value erodes the "no new exceptions" reuse mandate. *Fix:* change to `max-h-[200px]` to match the palette and `AgentModelPicker.tsx:138`, or formally add `240px` to the declared scale if the taller region is intentional.

2. **Locked-row lock *reason* is not reliably announced to assistive tech** — the row exposes `aria-disabled="true"` + a native `title` tooltip (`AgentsPopup.tsx:933-938`), but the `<div>` is not focusable, so the reason ("…requires elevated trust… Contact your workspace admin.") may never reach a keyboard/SR user; only the visible "Engineer-only" text carries it. *Impact:* the Accessibility contract row asks for the reason "exposed via `aria-label`/`title` … so screen readers announce 'Engineer-only — not available to compose'." *Fix:* add `aria-label={\`${cap.name} — Engineer-only, not available to compose\`}` to the locked row (keep the visible pill + `title`).

3. **Composed per-step selections are silently dropped on `resume_run` (WR-02)** — a backend-restart-resumed run re-drives the bare file-compiled plan, losing the user-selected validators/gates/model/retry (documented in `deferred-items.md`). *Impact:* a launched custom workflow that survives a restart quietly reverts to defaults — a real end-to-end experience regression for the very levers this phase adds. *Fix (tracked):* persist launch-time `selections` (additive nullable column / run JSON) and re-thread through `resume_run → _execute_impl → _apply_selections`. Not a security issue (resume can only ever apply *less* privilege).

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)

Audited the new palette/expander source (`AgentsPopup.tsx:756-1360`) against the UI-SPEC **Copywriting Contract** table. Every declared string is present **verbatim**:

- Locked-row tooltip — `:936` "This capability requires elevated trust and isn't available to compose. Contact your workspace admin." ✓
- Locked-row affordance — `:958` "Engineer-only" + `Lock` icon ✓
- Auto-attach notice — `:1349` "Added required validation gate — this capability needs it." (`{gate-name}` materialized) ✓
- Empty state — `:905` "No capabilities available" / `:908` "The capability registry returned nothing. Reload, or contact support if this persists." ✓
- Loading — `:892` "Loading capabilities…" ✓
- Error — `:830` "Failed to load capabilities." / `:815` "Not authenticated." (reuses the `AgentModelPicker` idiom) ✓
- Advanced toggle — `:1212` "Advanced — {agent}" + `:1215` sub-caption "Validator · Gate · Model · Retry" ✓
- Empty expander — `:1182` "Add agents to assign per-agent levers." (mirrors the model picker copy) ✓
- Contract CTA "Save workflow" — present on the composer (`IdeaInputPage.tsx:579`); "Launch" via the existing `onRun` path (no new run button, per D-13) ✓

Generic-label scan over `756-1360`: **none** (no `Submit`/`Click here`/`Lorem`/`TODO`/`placeholder`).

Nits (not deductions): (a) the contract's **"Upgrade to use"** tier-locked variant is not implemented — correct today since all locks are engineer-only (binary `user_allowed`), but must be wired if tier-gated caps appear; (b) the `AgentsPopup` footer remains generic **"Save changes"/"Cancel"** (`:1670-1673`) — acceptable as the config-popup's local close action (both call `onClose`), not a phase-22 persist surface.

### Pillar 2: Visuals (4/4)

- Clear hierarchy: navy-iconed eyebrow (`Boxes`/`Settings2`/`Cpu` at `:863/:1210/:1640`) → title-cased group header (`:918`) → row name (semibold gray-800) + description (gray-500). Locked rows visually recede (`opacity-80`, `text-gray-400`, leading `Lock`).
- Icon-only controls are labelled: config toggle has `aria-label={\`Configuration for ${cap.name}\`}` (`:969`); the expander toggle is a real `<button>` with text.
- `security_gated` (but allowed) rows get a secondary `Lock` glyph (`:962`) distinct from the full locked treatment — a nice trust gradient.
- **Nit:** the "Capabilities" header uses the `Boxes` lucide icon (`:863`), which is *not* in the UI-SPEC's enumerated reuse list (`Lock`/`Chevron`/`Cpu`/`AlertCircle`/`Plus`/`Sliders`/`Settings2`). On-brand and from the same library, but off-inventory.
- **Nit:** the config-schema affordance (`:990-1001`) renders only field-name strings in `font-mono text-[10px]` — no type/required/help. Functional and within the contract ("renders the populated `config_schema`"), but a thin treatment.

### Pillar 3: Color (4/4)

- Accent discipline is textbook: `#1B2A4A` appears **14×** in the new code (`756-1360`), exclusively on contract-reserved elements — section eyebrow icons, `focus:border-[#1B2A4A]` on every `<select>`, hover text on toggles, the SURF-03 "Declared by this workflow" pill (`:872-873`), and the EMP-04 auto-attach pill (`:1346`).
- Locked = neutral recessed `bg-gray-50 border-gray-100 text-gray-400` — **no** navy, **no** red (contract: "locked is neutral-recessed, not an error") ✓.
- Error = `text-red-600 bg-red-50` + `AlertCircle` (reused idiom) ✓.
- Leakage scan (`blue/indigo/green/purple/amber/teal/…`): **zero** hits in the new surfaces.
- The non-navy hex cluster elsewhere in the file (`#EAF0EA`, `#5C2A4A`, `#f7f6f3`, …) is **pre-existing chrome** — the agent-avatar tint table (`:164-165`) and the dotted-grid popup background (`:1511-1512`) — not phase-22 additions.

### Pillar 4: Typography (4/4)

- New surfaces (`756-1360`) use **only** `text-[10px]` (11×), `text-[11px]` (13×), `text-[9px]` (2×) — exactly the declared micro-ramp; weights are `font-semibold` (600) and default (400) only.
- Eyebrows: `text-[10px] font-semibold uppercase tracking-widest` (`:864/:918/:1641`) — matches `AgentModelPicker.tsx:115` verbatim ✓.
- Row label `text-[11px] font-semibold` / body `text-[11px]` regular / control `text-[10px]` / sub-caption `text-[9px] text-gray-400` — all on-contract.
- The out-of-ramp sizes in the file (`text-[7px]/[8px]/[15px]/[20px]` at `:258/:1461/:1580/:1606`) are **pre-existing** AgentsPopup chrome (popup title, role badges, pipeline label) — outside the phase-22 code range.

### Pillar 5: Spacing (3/4)

- Lever/row chrome is reproduced exactly: `bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5` on every palette row and lever (`:939/:1222/:1250/:1286/:1312`) — identical to `AgentModelPicker.tsx:142` ✓.
- Dense half-steps (`gap-1.5`, `space-y-1.5`, `py-0.5`, `mb-1/mb-2`) are all from the declared exception set; `<select>` capped at `max-w-[140px]` ✓; section mounts are uniform `mx-6 mb-4 px-1` (`:1624/:1638/:1657`); header/footer rails `px-8`, body `px-6` ✓.
- Palette scroll region: `max-h-[200px] overflow-y-auto pr-1` (`:915`) — matches the contract exactly ✓.
- **Deduction:** the Advanced expander scroll region uses `max-h-[240px]` (`:1188`, 3× in file) — an **undeclared arbitrary value**. The contract's Spacing → Exceptions explicitly declares `max-h-[200px]` for "Palette/expander scroll regions." Either align to `200px` or amend the declared scale.

### Pillar 6: Experience Design (3/4)

Strong coverage:
- **State machine** parity with the proven `AgentModelPicker`: `loading → error → empty → populated` on both the palette (`:891-1009`) and the expander (`:1164-1185`), plus an explicit unauthenticated branch ("Not authenticated.").
- **Live region:** the EMP-04 auto-attach notice is `role="status"` (`:1345`) — the coupling message is announced politely ✓.
- **Keyboard/a11y:** expander toggle is a `<button>` with `aria-expanded` + `aria-controls` → the lever region id (`:1201-1202`); levers are native `<select>` with `<label htmlFor>` + `aria-label`; focus-visible via `focus:border-[#1B2A4A]`; kind groups are `role="group"` + `aria-label`.
- **Defense in depth:** the FE lock/auto-attach are advisory; the authoritative `compile(trust="user")` backstop runs at **save and launch** (22-04) — a tampered row is rejected regardless of source.

Deductions / gaps:
- **Locked-row reason a11y (see Top Fix #2):** reason is on a non-focusable `<div>` via `title` only; SR delivery is unreliable. Add an `aria-label`.
- **WR-02 (see Top Fix #3):** composed selections are dropped on `resume_run` — a documented, deferred end-to-end gap.
- **Palette ↔ expander compose disconnect (minor):** the palette is inspect-only (no per-row "add to step"); composition happens via the separate Advanced-expander dropdowns. This is the locked design (D-01 palette = visibility, D-05 expander = composition), but a user who reads a capability in the palette must re-find it in a dropdown. Worth a future affordance linking the two.
- **Group `aria-label` uses the raw `kind`** ("context_provider") rather than the title-cased label (`:917`) — SR users hear the snake_case token. Per the literal contract (`aria-label={kind}`), but title-case would read better.

---

## Minor Recommendations

4. Swap the `Boxes` Capabilities-header icon for an enumerated one (e.g. `Sliders`) if strict icon-inventory adherence is wanted (Pillar 2).
5. Enrich the config-schema affordance with type + required marker, not just field names (Pillar 2).
6. Wire the "Upgrade to use" locked-row variant before introducing any tier-gated (non-engineer-only) capability (Pillar 1).
7. Use the title-cased label for the group `aria-label` so SR output isn't snake_case (Pillar 6).
8. If the `AgentsPopup` footer ever becomes a persist surface, align "Save changes" with the "Save workflow" contract CTA (Pillar 1).

---

## Registry Safety

Skipped — `components.json` not found (shadcn not initialized for this phase, per the UI-SPEC reuse-first gate). The "capability registry" in this phase is the backend `CapabilityRegistry` (`GET /api/capabilities`), not a shadcn component registry; the registry-vetting gate does not apply.

---

## Files Audited

- `frontend/src/components/workflow/AgentsPopup.tsx` — `CapabilityPaletteSection` (`:756-1012`), `AdvancedExpander` (`:1015-1360`), mounts (`:1624-1661`), footer (`:1668-1675`) — **primary phase-22 surfaces**
- `frontend/src/components/workflow/AgentModelPicker.tsx` — reuse template + DECIDE-02 tier-filter removal (`:74-95`)
- `frontend/src/components/workflow/IdeaInputPage.tsx` — "Save workflow" CTA (`:579`), SURF-03 `declaredCapabilities` wiring (`:260,682`), selections threading
- `frontend/src/lib/api.ts` — `CapabilityEntry` type (`description`/`security_gated`/`config_schema`), `getCapabilities` fetch
- `22-UI-SPEC.md` — design contract (baseline)
- `22-CONTEXT.md` — locked decisions (D-01…D-24)
- Plan summaries 22-01 … 22-09 (intent vs. delivery)
- Context-only / no-new-visual surfaces noted but not visually scored: `WorkflowCatalog.tsx` (UXFIX-03 re-route), `PreviewPanel.tsx` (UXFIX-04 dispatch table — "no visual regression"), `DashboardLayout.tsx` (catalog-as-home re-route)
