"use client";

import type { HTMLAttributes, ReactNode } from "react";

/**
 * Card — shared run-screen surface primitive (SC-1, D-15).
 *
 * Surface #FCFBF7, border #E6E3DB, radius = 14 (card) — all sourced from the
 * plan-01 token layer (surface / line / radius ladder), NO raw hex.
 */
export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Card({ className = "", children, ...rest }: CardProps) {
  return (
    <div
      className={[
        "bg-surface-card border border-line-border rounded-[var(--radius-card)]",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export default Card;
