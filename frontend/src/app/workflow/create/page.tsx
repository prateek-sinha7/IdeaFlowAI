"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LaunchWizard } from "@/components/workflow/LaunchWizard";
import type { LaunchMode } from "@/lib/launchDraft";

/**
 * `/workflow/create` — the ONE unified deliverable-launch route (plan 37-07).
 * Replaces the retired `/workflow/prototype/templates` + `/workflow/ppt/templates`
 * pages. The deliverable family rides in `?mode=prototype|ppt` — a GENERIC route
 * param, NEVER a per-workflow branch (SC-001) — and the in-page Web/Deck toggle
 * switches it live.
 */
function CreateRoute() {
  const searchParams = useSearchParams();
  // Auth is owned by LaunchWizard (it also picks up the chain hand-off), so the
  // wrapper only resolves the deliverable family from the route param. IN-07: the
  // duplicate getToken/redirect + loading gate here was a redundant second gate.
  // Default to prototype; only the two deliverable families are valid modes.
  const mode: LaunchMode = searchParams.get("mode") === "ppt" ? "ppt" : "prototype";
  return <LaunchWizard initialMode={mode} />;
}

export default function CreatePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-surface-paper">
          <div className="text-[13px] text-ink-400">Loading…</div>
        </div>
      }
    >
      <CreateRoute />
    </Suspense>
  );
}
