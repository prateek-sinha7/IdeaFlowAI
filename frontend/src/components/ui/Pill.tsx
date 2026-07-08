"use client";

import type { HTMLAttributes, ReactNode } from "react";

/**
 * Pill — shared run-screen chip primitive (SC-1, D-15).
 *
 * radius = 999 (pill), border #E0DDD3, white surface — all from the plan-01
 * token layer (radius ladder / line / surface), NO raw hex.
 */
export interface PillProps extends HTMLAttributes<HTMLSpanElement> {
  children: ReactNode;
}

export function Pill({ className = "", children, ...rest }: PillProps) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 bg-surface-white text-ink-700 border border-line-control rounded-[var(--radius-pill)] px-2.5 py-0.5 font-sans text-[11px] leading-none",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </span>
  );
}

export default Pill;
