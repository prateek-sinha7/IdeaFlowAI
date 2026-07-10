"use client";

/**
 * DonutChart — reusable, token-styled SVG donut primitive (Phase 38, SC-1).
 *
 * Extracted verbatim-geometry from the inline donut in AnalyticsPage.tsx
 * (cx=44 cy=44 r=36, strokeDasharray = 2*PI*36, motion.circle sweep,
 * transform="rotate(-90 44 44)"). The original hardcoded grey track and navy
 * sweep are replaced by Phase-32 @theme tokens: the sweep is `var(--brand)`
 * (one-chroma base) by default, or a run-status colour (`--status-done` /
 * `--status-failed`) ONLY when the caller flags the datum as a run-status
 * (`status`). The track is a neutral token (`--status-queued-fill`).
 *
 * Generic presentation primitive (SC-001/INV-1): data-prop driven, NO
 * workflow-name branch. Carries role="img" + aria-label (T-38-A11Y) so the
 * SVG is a single readable text alternative for assistive tech.
 */

import { motion } from "motion/react";

const R = 36;
const CIRCUMFERENCE = 2 * Math.PI * R;

/** When a datum IS a run-status, colour the sweep from the status ramp. */
type StatusDatum = "done" | "failed";

const STATUS_STROKE: Record<StatusDatum, string> = {
  done: "var(--status-done)",
  failed: "var(--status-failed)",
};

export interface DonutChartProps {
  /** Filled fraction of the ring, 0–100. */
  percent: number;
  /** Screen-reader text alternative summarising the datum (T-38-A11Y). */
  ariaLabel: string;
  /** Base sweep chroma; defaults to the one-chroma brand token. */
  chroma?: string;
  /** Flag the sweep as a run-status datum → status-ramp colour. */
  status?: StatusDatum;
  /** Optional centre label (e.g. "87%"); rendered over the ring. */
  children?: React.ReactNode;
}

export function DonutChart({
  percent,
  ariaLabel,
  chroma = "var(--brand)",
  status,
  children,
}: DonutChartProps) {
  const pct = Math.max(0, Math.min(100, percent));
  const stroke = status ? STATUS_STROKE[status] : chroma;

  return (
    <div className="relative">
      <svg
        width="88"
        height="88"
        viewBox="0 0 88 88"
        role="img"
        aria-label={ariaLabel}
      >
        <circle
          cx="44"
          cy="44"
          r={R}
          fill="none"
          stroke="var(--status-queued-fill)"
          strokeWidth="10"
        />
        <motion.circle
          cx="44"
          cy="44"
          r={R}
          fill="none"
          stroke={stroke}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${CIRCUMFERENCE}`}
          initial={{ strokeDashoffset: CIRCUMFERENCE }}
          animate={{ strokeDashoffset: CIRCUMFERENCE * (1 - pct / 100) }}
          transition={{ duration: 1, ease: "easeOut" }}
          transform="rotate(-90 44 44)"
        />
      </svg>
      {children != null && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          {children}
        </div>
      )}
    </div>
  );
}
