"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getToken } from "@/lib/api";
import { ConfigureScreen } from "@/components/workflow/ConfigureScreen";

/**
 * `/workflow/configure` — the generic per-run setup route. Renders the
 * ConfigureScreen (Describe + Templates + Design System + Review Gates + Workflow
 * Settings accordions) for the deliverable named by `?workflow=<id>`. The screen
 * gates the Templates/DS accordions on the deliverable's DECLARED
 * `context_providers` (SC-001) — this route is deliverable-agnostic.
 */
function ConfigureRoute() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    setAuthChecked(true);
  }, [router]);

  if (!authChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-paper">
        <div className="text-[13px] text-ink-400">Loading…</div>
      </div>
    );
  }

  // The deliverable id rides in the query string; a run always arrives here with
  // a selected deliverable. This is a plain default selection, NOT a gating branch.
  const workflowId = searchParams.get("workflow") ?? "prototype";

  return (
    <div className="min-h-screen bg-surface-paper">
      <ConfigureScreen workflowId={workflowId} />
    </div>
  );
}

export default function ConfigurePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-surface-paper">
          <div className="text-[13px] text-ink-400">Loading…</div>
        </div>
      }
    >
      <ConfigureRoute />
    </Suspense>
  );
}
