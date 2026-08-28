"use client";

/**
 * ReviewGatesSection — inline, expandable "Review gates" control.
 *
 * Lists every agent in the current pipeline as a checkbox. A checked agent
 * pauses the pipeline for a Human review gate after it completes (the same
 * `review_gate_*` flow `ReviewGatePanel` renders). Each agent is pre-checked
 * iff its static frontmatter declares `gate === "Human_Gate"` — i.e. the
 * section opens reflecting exactly the backend's static default.
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

interface ReviewGatesSectionProps {
  /** The current pipeline's agents (e.g. LIBRARY_AGENTS filtered by type). */
  agents: AgentDef[];
  /** Reports the checked agent ids + whether the user has touched the control. */
  onChange: (gateAgentIds: string[], touched: boolean) => void;
  /** Seed the initial checked ids from a saved workflow (overrides static defaults). */
  initialGateIds?: string[];
}

export function ReviewGatesSection({ agents, onChange, initialGateIds }: ReviewGatesSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const [touched, setTouched] = useState(false);

  // Identity-stable key of the incoming agent set, used to (re)seed the
  // default selection when the pipeline (and thus its agents) changes.
  const agentsKey = useMemo(() => agents.map((a) => a.id).join("|"), [agents]);

  // Selected (checked) agent ids. Seeded from saved initialGateIds when provided,
  // otherwise empty — no gates pre-checked by default. The user opts in explicitly.
  // Re-seeds and clears `touched` on pipeline switch.
  const [checkedIds, setCheckedIds] = useState<Set<string>>(
    () => initialGateIds ? new Set(initialGateIds) : new Set(),
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
      setCheckedIds(new Set());
      setTouched(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentsKey]);

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
    setTouched(true);
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

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
