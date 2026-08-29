"use client";

/**
 * UpgradePlanModal — the app's single plan-management affordance (ISS-291).
 *
 * Both entry points open THIS component rather than each growing its own logic:
 * the Usage & Limits "Manage plan" button (`AccountSettings.tsx`), which had no
 * `onClick` at all, and the header account menu's basic-tier "Upgrade" link
 * (`AppHeader.tsx`), which only navigated the user to that same inert button
 * (ISS-397).
 *
 * There is no billing/tier-change backend to call — `UPGRADE_PATH` names the
 * next tier, it does not action a change — so the modal states the current plan,
 * what the next one unlocks, and hands the request to a workspace admin.
 *
 * Shell cloned from the delete-confirm modal in `SavedWorkflowsPage.tsx:410-443`
 * (backdrop + scale-in + role/aria wiring); portalled to <body> like
 * `WorkflowPickerModal.tsx:213` so `AppHeader`'s `z-40` stacking context cannot
 * trap it.
 */

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { CreditCard } from "lucide-react";
import { TIER_LABELS, TIER_PIPELINES, UPGRADE_PATH } from "@/lib/entitlements";
import type { Tier } from "@/lib/entitlements";

interface UpgradePlanModalProps {
  /** The account's real tier, as loaded by the surface that opens this modal. */
  tier: Tier;
  onClose: () => void;
}

// Base deliverables (revision variants excluded, same rule as the Usage & Limits
// deliverable-access grid) that `next` adds over `current`.
function unlockedCount(current: Tier, next: Tier): number {
  return Array.from(TIER_PIPELINES[next]).filter(
    p => !p.endsWith("_revision") && !TIER_PIPELINES[current].has(p),
  ).length;
}

export function UpgradePlanModal({ tier, onClose }: UpgradePlanModalProps) {
  const next = UPGRADE_PATH[tier];
  const unlocks = next ? unlockedCount(tier, next) : 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[var(--scrim)] backdrop-blur-sm p-4"
      onClick={onClose}
      role="presentation"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.15 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="upgrade-plan-title"
        onClick={(e) => e.stopPropagation()}
        className="bg-surface-white rounded-2xl border border-line-border shadow-[var(--elevation-modal)] p-6 max-w-[360px] w-full"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-surface-warm flex items-center justify-center">
            <CreditCard className="h-5 w-5 text-ink-600" />
          </div>
          <div>
            <h3 id="upgrade-plan-title" className="text-[13px] font-semibold text-ink-900">
              {next ? "Upgrade your plan" : "Manage plan"}
            </h3>
            <p className="text-[11px] text-ink-400">You are on the {TIER_LABELS[tier]} plan</p>
          </div>
        </div>

        <p className="text-[12px] text-ink-500 leading-relaxed mb-5">
          {next ? (
            <>
              The <span className="font-semibold text-ink-800">{TIER_LABELS[next]}</span> plan unlocks{" "}
              {unlocks} more deliverable {unlocks === 1 ? "type" : "types"}. Plan changes are made by
              your workspace administrator — contact them to move this account to {TIER_LABELS[next]}.
            </>
          ) : (
            <>
              {TIER_LABELS[tier]} is the highest plan — every deliverable type is already available to
              you. Contact your workspace administrator to change this plan.
            </>
          )}
        </p>

        <button
          onClick={onClose}
          autoFocus
          className="w-full rounded-xl border border-line-border px-4 py-2.5 text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors"
        >
          Close
        </button>
      </motion.div>
    </div>,
    document.body,
  );
}
