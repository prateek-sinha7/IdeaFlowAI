"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getToken } from "@/lib/api";
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace("/login"); return; }
    setAuthChecked(true);
  }, [router]);

  if (!authChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-paper">
        <div className="text-[13px] text-ink-400">Loading…</div>
      </div>
    );
  }

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
