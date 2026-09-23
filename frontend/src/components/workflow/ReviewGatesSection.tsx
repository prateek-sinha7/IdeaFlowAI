"use client";

/**
 * ReviewGatesSection — inline, expandable "Review gates" control.
 *
 * Lists every agent in the current pipeline as a checkbox. A checked agent
 * pauses the pipeline for a Human review gate after it completes (the same
 * `review_gate_*` flow `ReviewGatePanel` renders). Each agent is pre-checked
 * iff its static frontmatter declares `gate === "Human_Gate"` OR the workflow's
 * manifest declares a human-review gate on that step (`selections[id].gates`) —
 * i.e. the section opens reflecting exactly what the backend already declares.
 *
 * Wiring contract (see plan.md §5 "Gate mechanism"):
 *   - `onChange(gateAgentIds, touched)` fires whenever the selection or the
 *     touched flag changes. `gateAgentIds` is the ids of the currently-checked
 *     agents (possibly empty); `touched` is true once the user toggles anything.
 *   - The caller MUST send `gate_agent_ids` ONLY when `touched` is true (even if
 *     the array is empty — `[]` means "no gates"). When untouched it omits the
 *     field entirely, so the backend uses its static default (byte-identical to
 *     today). `onChange` must be a stable reference (wrap in `useCallback`).
 *
 * Styled to the Phase-32 token layer (brand / ink / surface / line tokens),
 * `text-[11px]` labels, token radii.
 *
 * Graceful: renders nothing when the agent list is empty.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, ShieldCheck, Check } from "lucide-react";
import type { AgentDef } from "@/types/index";
import type { SelectionsMap, StepSelection } from "./AgentsPopup";

interface ReviewGatesSectionProps {
  /** The current pipeline's agents (e.g. LIBRARY_AGENTS filtered by type). */
  agents: AgentDef[];
  /** Reports the checked agent ids + whether the user has touched the control. */
  onChange: (gateAgentIds: string[], touched: boolean) => void;
  /** Seed the initial checked ids from a saved workflow (overrides static defaults). */
  initialGateIds?: string[];
  /**
   * ISS-247 — the live per-step selections map and its writer: the SAME
   * `selections[agentId].gates` store the Advanced modal's per-agent Gate
   * combobox (`CanvasConfigRail`) reads and writes. Checking an agent here also
   * declares the `human` gate on that step, so the two controls stop reporting
   * contradictory state for one agent in one session. Absent ⇒ the checklist
   * reports through `onChange` only, exactly as before.
   */
  selections?: SelectionsMap;
  onSelectionsChange?: (next: SelectionsMap) => void;
}

/**
 * The registered gate this checklist owns — the same name `CanvasConfigRail`
 * labels "Human gate". The engine dedupes it against the per-run
 * `gate_agent_ids` selection (engine `_evaluate_gates` / WR-02), so a step may
 * carry both without arming two pauses on one gate_key.
 */
const HUMAN_GATE = "human";

/**
 * The gates that mean "this step pauses for a person" — the two ADR-0013 split
 * apart: `human` reviews a step's OWN output after it runs, `before-human`
 * reviews the previous step's output before it runs. Different gates, both human
 * review, so both render this checkbox checked. `conditional`, `approval` and
 * `security` belong to other levers and are NOT human review — reading them here
 * would re-merge exactly what ADR-0013 separated. Read-only: `withHumanGate`
 * below still writes `HUMAN_GATE` alone, so this control's ownership is unchanged.
 */
const HUMAN_REVIEW_GATES = [HUMAN_GATE, "before-human"];

/**
 * Is this step checked on load? ONLY when the workflow's own manifest declares a
 * human-review gate on it (`selections[id].gates`) — never from a static AGENT.md
 * `gate` default. FIX-323 removed those defaults deliberately ("user opts in
 * explicitly") and stripped `gate: Human_Gate` out of the prototype AGENT.md files,
 * so the old `isDefaultGated` seed is both unwanted and dead. A manifest gate is a
 * different thing: it is a choice already made and persisted, so reflecting it is
 * what FIX-323 asks for, not an exception to it.
 *
 * The manifest half is also the whole point of ISS-247's fix — a `custom-agent`
 * step has no AGENT.md and so no static `gate` field at all; `gates: [...]` is its
 * ONLY declaration, and without reading it such a step can never render checked
 * however the manifest is written.
 */
const isSeedGated = (a: AgentDef, selections?: SelectionsMap): boolean =>
  (selections?.[a.id]?.gates ?? []).some((g) => HUMAN_REVIEW_GATES.includes(g));

/** `selections` with `human` added to / removed from one step's gate list. */
function withHumanGate(
  selections: SelectionsMap,
  agentId: string,
  gated: boolean,
): SelectionsMap {
  const { gates: declared = [], ...rest } = selections[agentId] ?? {};
  // Only `human` is this control's to write — `validation`, `conditional` and
  // `before-human` belong to the levers that own them and are carried through.
  const gates = declared.filter((g) => g !== HUMAN_GATE);
  if (gated) gates.push(HUMAN_GATE);
  const step: StepSelection = gates.length > 0 ? { ...rest, gates } : rest;
  const next = { ...selections };
  // An empty step drops out of the map — the same rule AgentsPopup's
  // `handleCanvasSelection` applies, so an untouched step adds nothing.
  if (Object.keys(step).length > 0) next[agentId] = step;
  else delete next[agentId];
  return next;
}

export function ReviewGatesSection({ agents, onChange, initialGateIds, selections, onSelectionsChange }: ReviewGatesSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const [touched, setTouched] = useState(false);

  // Identity-stable key of the incoming agent set, used to (re)seed the
  // default selection when the pipeline (and thus its agents) changes.
  const agentsKey = useMemo(() => agents.map((a) => a.id).join("|"), [agents]);

  // The ids that seed as checked, and an identity-stable key of that set. Both
  // sources move: the agent list on a pipeline switch, the declared gates when
  // the workflow fetch resolves (which is AFTER mount, and after `agentsKey`
  // settles — hence the second effect below).
  const seededIds = useMemo(
    () => agents.filter((a) => isSeedGated(a, selections)).map((a) => a.id),
    [agents, selections],
  );
  const seedKey = seededIds.join("|");

  // Selected (checked) agent ids. Seeded from saved initialGateIds when provided,
  // otherwise from the gates the workflow's manifest declares — empty unless one
  // does, so nothing is pre-checked by default (FIX-323: the user opts in
  // explicitly). Re-seeds and clears `touched` on pipeline switch.
  const [checkedIds, setCheckedIds] = useState<Set<string>>(
    () => initialGateIds ? new Set(initialGateIds) : new Set(seededIds),
  );

  // Re-seed the selection to the new defaults (and clear `touched`) whenever the
  // underlying agent set changes — e.g. the user switches pipeline or customizes
  // the lineup. Keyed on the agent-id list so it fires only on real changes.
  // When initialGateIds is provided, seed from that on first run (agentsKey change).
  const initialGateIdsRef = useRef(initialGateIds);
  useEffect(() => {
    if (initialGateIdsRef.current) {
      // First change after mount with saved gates — apply them then clear the seed
      setCheckedIds(new Set(initialGateIdsRef.current));
      setTouched(true); // mark touched so the saved selection is sent on run
      initialGateIdsRef.current = undefined;
    } else {
      setCheckedIds(new Set(seededIds));
      setTouched(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentsKey]);

  // The manifest's declared gates land in `selections` AFTER the effect above has
  // already run — the workflow fetch resolves later than the agent list, and the
  // parent effect that merges them runs after this child's. Re-seed when the
  // declared set itself changes, or a step the manifest declares gated stays
  // unchecked forever. Display-only: it never sets `touched`, and a set the user
  // has already touched is left alone, so an untouched launch payload still omits
  // `gate_agent_ids` entirely (INV-3). The ref makes this a no-op on mount, where
  // the initializer above has already applied the same seed.
  const seedKeyRef = useRef(seedKey);
  useEffect(() => {
    if (seedKey === seedKeyRef.current) return;
    seedKeyRef.current = seedKey;
    if (touched || initialGateIdsRef.current) return;
    setCheckedIds(new Set(seededIds));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey]);

  // Report the current selection + touched flag upward. Runs on mount and on
  // every change; the initial (untouched) report is harmless because the caller
  // omits `gate_agent_ids` whenever `touched` is false. `onChange` is expected
  // to be stable (useCallback) so this effect does not loop.
  useEffect(() => {
    // Preserve pipeline order in the reported array (deterministic payload).
    const ordered = agents.filter((a) => checkedIds.has(a.id)).map((a) => a.id);
    onChange(ordered, touched);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkedIds, touched, agentsKey]);

  const toggle = useCallback((id: string) => {
    const gated = !checkedIds.has(id);
    setTouched(true);
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    // ISS-247 — write the same choice into the shared selections map, so the
    // Advanced modal's Gate combobox for this agent reports it too.
    onSelectionsChange?.(withHumanGate(selections ?? {}, id, gated));
  }, [checkedIds, selections, onSelectionsChange]);

  // Graceful: nothing to gate.
  if (agents.length === 0) return null;

  const gatedCount = checkedIds.size;

  return (
    <div className="w-full rounded-[var(--radius-button)] border border-line-border bg-surface-white overflow-hidden font-sans">
      {/* Header — inline expandable */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-brand-fill"
        aria-expanded={expanded}
      >
        <ShieldCheck className="h-3.5 w-3.5 text-brand flex-shrink-0" />
        <span className="text-[11px] font-semibold text-brand font-sans">Review gates</span>
        <span className="text-[11px] text-ink-400">
          {gatedCount === 0
            ? "no gates"
            : `${gatedCount} agent${gatedCount !== 1 ? "s" : ""} pause for review`}
        </span>
        <span className="ml-auto text-ink-400">
          {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
      </button>

      {/* Body — one checkbox per agent */}
      {expanded && (
        <div className="border-t border-line-divider px-3 py-2.5 space-y-1">
          <p className="text-[10px] text-ink-400 leading-relaxed mb-1.5">
            Checked agents pause the pipeline for your review after they finish.
          </p>
          {agents.map((agent) => {
            const checked = checkedIds.has(agent.id);
            return (
              <label
                key={agent.id}
                className="flex items-center gap-2.5 rounded-[var(--radius-button)] px-2 py-1.5 cursor-pointer transition-colors hover:bg-brand-fill"
              >
                <span
                  className={`flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border transition-colors ${
                    checked
                      ? "border-brand bg-brand"
                      : "border-line-control bg-surface-white"
                  }`}
                >
                  {checked && <Check className="h-3 w-3 text-white" strokeWidth={3} />}
                </span>
                <input
                  type="checkbox"
                  name={`review-gate-${agent.id}`}
                  checked={checked}
                  onChange={() => toggle(agent.id)}
                  className="sr-only"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] font-medium text-ink-900 leading-tight truncate">
                    {agent.name}
                  </span>
                  <span className="block text-[10px] text-ink-400 leading-tight truncate">
                    {agent.role}
                  </span>
                </span>

              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
