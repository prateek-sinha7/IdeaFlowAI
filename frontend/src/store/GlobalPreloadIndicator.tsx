"use client";

import { Loader2 } from "lucide-react";
import { useAppSelector } from "@/store/hooks";

/**
 * Small, non-blocking indicator for the post-sign-in background preload
 * (agents/skills/workflows — see store/listenerMiddleware.ts). Renders
 * nothing once all three have settled; never blocks the dashboard itself,
 * since none of today's dashboard content depends on this data being ready.
 */
export function GlobalPreloadIndicator() {
  const agentsStatus = useAppSelector((state) => state.agents.status);
  const skillsStatus = useAppSelector((state) => state.skills.status);
  const workflowsStatus = useAppSelector((state) => state.global.workflowsStatus);

  const isLoading =
    agentsStatus === "loading" || skillsStatus === "loading" || workflowsStatus === "loading";

  if (!isLoading) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border border-white/10 bg-black/80 px-3 py-1.5 text-[11px] text-grey/80 shadow-lg backdrop-blur-sm">
      <Loader2 className="h-3 w-3 animate-spin" />
      Loading workspace…
    </div>
  );
}
