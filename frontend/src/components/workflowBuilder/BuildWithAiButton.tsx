"use client";

/**
 * BuildWithAiButton: the entry control of the AI Workflow Builder on the Saved
 * Workflows page, next to "New workflow" (Req 1.1, 1.4). It matches the Composer
 * header's AI button: the same brand tint, icon, size and focus ring, so the
 * entry looks the same wherever it appears. A native button, so it is keyboard
 * operable with a visible focus ring (Req 14.1). The `ref` prop is forwarded to
 * the button (React 19 passes `ref` as a prop).
 */

import { Sparkles } from "lucide-react";
import type { Ref } from "react";

export interface BuildWithAiButtonProps {
  onClick: () => void;
  ref?: Ref<HTMLButtonElement>;
  disabled?: boolean;
  label?: string;
}

export function BuildWithAiButton({
  onClick,
  ref,
  disabled = false,
  label = "Build with AI",
}: BuildWithAiButtonProps) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-[10px] border border-brand/30 bg-brand/[0.06] px-3.5 py-2.5 font-sans text-[12.5px] font-semibold text-brand transition-colors hover:border-brand hover:bg-brand/10 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
      {label}
    </button>
  );
}

export default BuildWithAiButton;
