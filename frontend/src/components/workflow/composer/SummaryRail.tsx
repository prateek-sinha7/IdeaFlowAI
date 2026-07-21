"use client";

import { Save, Play } from "lucide-react";

/**
 * 41-04 — the sticky Composer Summary rail (mock: `Hexaware Composer.dc.html`
 * summary column). Shows agent + review-gate counts, the strategy, a LIVE est.
 * duration derived from the agents' `estimated_duration`, and the declared
 * capabilities. Per ND-AG the fabricated "Est. cost" row is OMITTED and the
 * PRIMARY action is Save-to-catalogue (the "Run once" button is present but
 * INERT here — its run wiring lands in 41-06). All colour/type via @theme tokens.
 */
export function SummaryRail({
  agentCount,
  gateCount,
  strategy,
  estDurationLabel,
  declaredCapabilities,
  onSaveToCatalogue,
  onRunOnce,
}: {
  agentCount: number;
  gateCount: number;
  strategy: string;
  estDurationLabel: string;
  declaredCapabilities: string[];
  onSaveToCatalogue: () => void;
  onRunOnce?: () => void;
}) {
  return (
    <div
      data-testid="composer-summary-rail"
      className="sticky top-0 rounded-2xl border border-line-control bg-surface-white px-[22px] py-5 shadow-[0_8px_30px_rgba(17,17,20,0.05)]"
    >
      <p className="mb-4 font-sans text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-300">
        Summary
      </p>

      {/* Stat tiles */}
      <div className="mb-4 grid grid-cols-2 gap-2.5">
        <div className="rounded-[11px] border border-line-faint-row bg-surface-warm p-3.5">
          <p className="font-sans text-[22px] font-bold leading-none tabular-nums text-ink-900">
            {agentCount}
          </p>
          <p className="mt-1.5 font-serif text-[10.5px] leading-none text-ink-300">
            Agents
          </p>
        </div>
        <div className="rounded-[11px] border border-line-faint-row bg-surface-warm p-3.5">
          <p className="font-sans text-[22px] font-bold leading-none tabular-nums text-ink-900">
            {gateCount}
          </p>
          <p className="mt-1.5 font-serif text-[10.5px] leading-none text-ink-300">
            Review gates
          </p>
        </div>
      </div>

      {/* Facts — strategy + est. duration. NO est. cost (ND-AG). */}
      <div className="mb-4 flex flex-col gap-2.5">
        <div className="flex items-center font-serif text-[12px] text-ink-700">
          <span className="flex-1 text-ink-400">Strategy</span>
          {strategy}
        </div>
        <div className="flex items-center font-serif text-[12px] text-ink-700">
          <span className="flex-1 text-ink-400">Est. duration</span>
          <span className="tabular-nums">{estDurationLabel}</span>
        </div>
      </div>

      {/* Declared capabilities */}
      <p className="mb-2 font-sans text-[9.5px] font-semibold uppercase tracking-[0.1em] text-ink-300">
        Declared capabilities
      </p>
      <div className="mb-[18px] flex flex-wrap gap-1.5">
        {declaredCapabilities.length > 0 ? (
          declaredCapabilities.map((d) => (
            <span
              key={d}
              className="rounded-[6px] border border-brand-border bg-brand-fill px-2.5 py-[5px] font-sans text-[10.5px] font-medium text-brand"
            >
              {d}
            </span>
          ))
        ) : (
          <span className="font-serif text-[11px] text-ink-200">None enabled</span>
        )}
      </div>

      {/* Primary action — Save to catalogue (ND-AG). */}
      <button
        type="button"
        onClick={onSaveToCatalogue}
        className="flex w-full items-center justify-center gap-2 rounded-[11px] bg-brand px-3 py-3 font-sans text-[13px] font-semibold text-surface-white transition-colors hover:bg-brand-pressed"
      >
        <Save className="h-3.5 w-3.5" />
        Save to catalogue
      </button>

      {/* Run once — present but INERT here (wired in 41-06). */}
      <button
        type="button"
        onClick={onRunOnce}
        disabled={!onRunOnce}
        title="Run wiring lands in 41-06"
        className="mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-[11px] border border-line-control bg-surface-card px-3 py-2.5 font-sans text-[12.5px] font-semibold text-ink-700 transition-colors enabled:hover:border-line-faint disabled:opacity-60"
      >
        <Play className="h-3.5 w-3.5" />
        Run once now
      </button>
    </div>
  );
}
