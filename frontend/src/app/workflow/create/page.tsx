"use client";

import { Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { LaunchWizard } from "@/components/workflow/LaunchWizard";
import { routes } from "@/lib/routes";
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
  const router = useRouter();
  // Auth is owned by LaunchWizard (it also picks up the chain hand-off), so the
  // wrapper only resolves the deliverable family from the route param. IN-07: the
  // duplicate getToken/redirect + loading gate here was a redundant second gate.
  const raw = searchParams.get("mode");

  // ISS-376: when proxy.ts's redirect does not run (cached response, CDN layer,
  // matcher miss), CreateRoute() received no canonicalization fallback of its own
  // and silently rendered the prototype wizard under an unresolved URL. An explicit
  // redirect here closes the gap: any `raw` that is not a known mode gets
  // canonicalized to `?mode=prototype` so the URL and content agree.
  const isKnownMode = raw === "prototype" || raw === "ppt" || raw === "ppt_v2";
  const mode: LaunchMode =
    raw === "ppt" || raw === "ppt_v2" ? raw : "prototype";

  useEffect(() => {
    // Redirect unknown/null/empty mode values to the canonical prototype URL so
    // the address bar and rendered content are always consistent.
    if (raw !== null && !isKnownMode) {
      router.replace(`${routes.create()}?mode=prototype`);
    }
  }, [raw, isKnownMode, router]);

  // While the redirect is in flight, render nothing — same pattern as the
  // mounted/auth gate in [...view]/page.tsx.
  if (raw !== null && !isKnownMode) {
    return null;
  }

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
