"use client";

/**
 * 41-04 — the sticky Composer Summary rail (mock: `Hexaware Composer.dc.html`
 * summary column). Shows agent + review-gate counts, the strategy, and a LIVE
 * est. duration derived from the agents' `estimated_duration`. Per ND-AG the
 * fabricated "Est. cost" row is OMITTED. Save/Run
 * moved to the shared ComposerPage header (one pair of actions for the whole
 * composer instead of a second copy down here) — this rail is now read-only
 * context. All colour/type via @theme tokens.
 */
export function SummaryRail({
  agentCount,
  gateCount,
  strategy,
  estDurationLabel,
}: {
  agentCount: number;
  gateCount: number;
  strategy: string;
  estDurationLabel: string;
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
    </div>
  );
}
