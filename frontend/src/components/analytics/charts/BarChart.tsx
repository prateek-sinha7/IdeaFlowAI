"use client";

/**
 * BarChart — reusable, token-styled flex/SVG bar-chart primitive (Phase 38, SC-1).
 *
 * Extracted verbatim-geometry from the inline BarChart in AnalyticsPage.tsx
 * (flex items-end bars, motion.div height animation, per-bar hover tooltip).
 * The original hardcoded navy bar colour is replaced by the Phase-32 one-chroma
 * brand token `var(--brand)`; a datum may opt into a run-status colour
 * (`--status-*`) ONLY when the caller flags it (`status`).
 *
 * Generic presentation primitive (SC-001/INV-1): data-prop driven, NO
 * workflow-name branch. Carries role="img" + aria-label (T-38-A11Y) so the
 * whole chart is a single readable text alternative for assistive tech; the
 * per-bar tooltips are decorative supplements.
 */

import { motion } from "motion/react";

/** When a datum IS a run-status, colour that bar from the status ramp. */
type StatusDatum = "running" | "done" | "failed" | "amber" | "queued";

const STATUS_FILL: Record<StatusDatum, string> = {
  running: "var(--status-running)",
  done: "var(--status-done)",
  failed: "var(--status-failed)",
  amber: "var(--status-amber)",
  queued: "var(--status-queued)",
};

export interface BarDatum {
  label: string;
  value: number;
  /** Optional secondary count used when no primary value is present. */
  runs?: number;
  /** Flag this bar as a run-status datum → status-ramp colour. */
  status?: StatusDatum;
  /** Optional per-bar tooltip; falls back to a composed label:value string. */
  tip?: string;
}

export interface BarChartProps {
  data: BarDatum[];
  /** Screen-reader text alternative summarising the series (T-38-A11Y). */
  ariaLabel: string;
  /** Base bar chroma; defaults to the one-chroma brand token. */
  chroma?: string;
}

export function BarChart({ data, ariaLabel, chroma = "var(--brand)" }: BarChartProps) {
  if (!data.length) return null;

  const hasValues = data.some((d) => d.value > 0);
  const display = hasValues ? data : data.map((d) => ({ ...d, value: d.runs ?? 0 }));
  const max = Math.max(...display.map((d) => d.value), 1);
  // Mock-fidelity peak (Phase 40): the analytics daily-activity chart shows ONE
  // dark brand "peak" bar (the series max) among lighter lavender bars — see
  // shots-shell/target/analytics__shell.png. First max index wins; only for
  // non-status series (status bars keep their status-ramp colour + opacity).
  const peakIdx = display.reduce(
    (best, d, i, arr) => (d.value > arr[best].value ? i : best),
    0,
  );

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className="flex items-end gap-[3px] h-32 w-full"
    >
      {display.map((d, i) => {
        const pct = (d.value / max) * 100;
        const fill = d.status ? STATUS_FILL[d.status] : chroma;
        // Non-status bars: the peak renders as the solid dark brand fill, the
        // rest as a uniform lighter lavender (opacity ramp collapsed to a flat
        // tint so exactly one dark peak reads against lavender, per the mock).
        const isPeak = !d.status && d.value > 0 && i === peakIdx;
        const barOpacity = d.status
          ? d.value > 0 ? 0.75 + (i / display.length) * 0.25 : 0.12
          : isPeak
          ? 1
          : d.value > 0
          ? 0.34
          : 0.12;
        const tip =
          d.tip ??
          (hasValues
            ? `${d.label}: ${d.value}`
            : `${d.label}: ${d.value} run${d.value !== 1 ? "s" : ""}`);
        return (
          <div
            key={i}
            className="flex-1 flex flex-col justify-end group relative h-full"
          >
            <motion.div
              data-testid="bar-chart-bar"
              initial={{ height: 0 }}
              animate={{ height: `${Math.max(pct, d.value > 0 ? 6 : 0)}%` }}
              transition={{ duration: 0.5, delay: i * 0.02, ease: "easeOut" }}
              className="w-full rounded-t-[3px] cursor-pointer"
              style={{
                background: fill,
                opacity: barOpacity,
              }}
            />
            <div className="absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2 bg-surface-near-black text-white text-[9px] px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20 shadow-lg">
              {tip}
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-[var(--surface-near-black)]" />
            </div>
          </div>
        );
      })}
    </div>
  );
}
