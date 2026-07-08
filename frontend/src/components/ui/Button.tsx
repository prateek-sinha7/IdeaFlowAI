"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * Button — shared run-screen primitive (SC-1, D-15).
 *
 * Every value routes through the plan-01 canonical token layer (brand / ink /
 * surface / line + radius ladder) — NO raw hex. `variant` is a GENERIC
 * presentational prop (never a workflow name, SC-001).
 */
export type ButtonVariant = "primary" | "secondary";
export type ButtonSize = "sm" | "md";

// Token class strings per variant — mirrors the AGENT_ACCENT map idiom but
// keyed on tokens, not hardcoded navy.
const VARIANT_CLASS: Record<ButtonVariant, string> = {
  // brand #3C2CDA fill / white text
  primary:
    "bg-brand text-white border border-transparent hover:bg-brand-pressed disabled:opacity-50",
  // #FCFBF7 fill / #E0DDD3 border / ink text
  secondary:
    "bg-surface-card text-ink-900 border border-line-control hover:bg-surface-warm disabled:opacity-50",
};

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1",
  md: "px-3.5 py-2",
};

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={[
        // radius = 10 (button), Manrope 600, 12.5px — from the token ladder
        "inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-button)] font-sans font-semibold text-[12.5px] leading-none transition-colors disabled:cursor-not-allowed",
        SIZE_CLASS[size],
        VARIANT_CLASS[variant],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}

export default Button;
