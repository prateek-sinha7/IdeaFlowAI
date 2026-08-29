"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Play,
  Loader2,
  GitBranch,
  Settings as SettingsIcon,
  RotateCcw,
} from "lucide-react";

import { getToken } from "@/lib/api";
import { ENV } from "@/lib/env";
import { useHandoffSocket } from "@/hooks/useHandoffSocket";
import type { StreamMessage } from "@/types/index";
import {
  getHandoff,
  startHandoff,
  type HandoffSessionView,
} from "@/lib/api-handoff";

import { HandoffAgentPanel } from "./HandoffAgentPanel";
import { HandoffPreviewPanel } from "./HandoffPreviewPanel";
import { IntegrationsCard } from "./IntegrationsCard";
import { useHandoffPipelineState } from "./useHandoffPipelineState";
import type { HandoffAgentId, HandoffStreamMessage } from "./types";

/**
 * Top-level handoff workflow view.
 *
 *   ┌─ Top bar (back / status / mode)
 *   │
 *   ├──────────────┬──────────────────────────────────────────────────┐
 *   │ Left panel   │ Right panel                                       │
 *   │ Agent cards  │ Tabs: Diff | Tests | Compliance                  │
 *   │ Phase log    │ Body: streaming diff / report views               │
 *   │              │ PR strip when done                                │
 *   └──────────────┴──────────────────────────────────────────────────┘
 *
 * Same shape as the existing pptx / user-stories workflows so the user
 * does not see "something new" beyond the content. Lives entirely
 * inside ``components/handoff/`` and only imports from shared helpers
 * (``getToken``, ``useHandoffSocket``, lucide, motion) — no modifications
 * to existing workflow code.
 */
export function HandoffWorkflow({ token: handoffToken }: { token: string }) {
  const router = useRouter();

  const [authToken, setAuthToken] = useState<string | null>(null);
  const [session, setSession] = useState<HandoffSessionView | null>(null);
  const [loading, setLoading] = useState(true);
  // ISS-301 — a load failure has to remember whether an HTTP response was
  // ever received: "offline" and "this token does not exist" are different
  // answers and must not render the same way.
  const [loadError, setLoadError] = useState<{
    message: string;
    offline: boolean;
  } | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { state, handleMessage, setPipelineStatus } = useHandoffPipelineState();
  const [selectedAgent, setSelectedAgent] = useState<HandoffAgentId | null>(null);

  // Auth gate
  useEffect(() => {
    const t = getToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    setAuthToken(t);
  }, [router]);

  // Initial fetch — and re-fetch when pipeline finishes for refresh safety.
  const fetchSession = useCallback(async () => {
    if (!authToken || !handoffToken) return;
    setLoading(true);
    setLoadError(null);
    try {
      const sess = await getHandoff(authToken, handoffToken);
      setSession(sess);
      // Hydrate completed-state from persisted pipeline_output.
      const out = (sess.pipeline_output ?? {}) as Record<string, unknown>;
      if (sess.status === "completed" || sess.status === "failed") {
        // Coding agent: replay so the Diff tab fills in on refresh / late
        // navigation. Without this, a user who comes back to a finished
        // handoff sees an empty Diff tab even though the PR has the changes.
        if (out.coding_summary && typeof out.coding_summary === "object") {
          const cs = out.coding_summary as Record<string, unknown>;
          handleMessage({
            type: "agent_complete",
            data: {
              agent_id: "coding_agent",
              summary: (cs.summary as string) ?? "",
              rationale: (cs.rationale as string) ?? "",
              edit_count: (cs.edit_count as number) ?? 0,
              edits: cs.edits,
              tests_added: cs.tests_added,
              follow_ups: cs.follow_ups,
            },
          });
        }
        // Apply-edits results: the live pipeline emits these via phase_end;
        // on hydration we synthesise the same envelope so the APPLIED /
        // REJECTED status pills render correctly.
        if (Array.isArray(out.edit_results)) {
          handleMessage({
            type: "phase_end",
            section: "apply_edits",
            data: { results: out.edit_results as unknown as Record<string, unknown> },
          });
        }
        if (typeof out.pr_url === "string" && typeof out.pr_number === "number") {
          // Synthesise a pr_created event so the preview shows the PR strip.
          handleMessage({
            type: "pr_created",
            data: { url: out.pr_url, number: out.pr_number },
          });
        }
        if (out.test_report) {
          handleMessage({
            type: "agent_complete",
            data: { agent_id: "test_agent", report: out.test_report },
          });
        }
        if (out.compliance_report) {
          handleMessage({
            type: "agent_complete",
            data: { agent_id: "compliance_agent", report: out.compliance_report },
          });
        }
        handleMessage({
          type: "pipeline_complete",
          data: {
            resolved_mode: out.resolved_mode,
            branch_name: out.branch_name,
            pr_url: out.pr_url,
            pr_number: out.pr_number,
          },
        });
        setPipelineStatus(sess.status === "completed" ? "completed" : "failed");
      } else {
        setPipelineStatus(sess.status);
      }
    } catch (err) {
      // ISS-301 — no HTTP response behind the failure means it says nothing
      // about whether this token exists: api-handoff's authedJson labels that
      // ApiError(status 0), and a raw fetch rejection is a bare TypeError.
      const offline =
        err instanceof TypeError ||
        (err as { status?: number } | null)?.status === 0;
      setLoadError({
        message: err instanceof Error ? err.message : "Failed to load handoff",
        offline,
      });
    } finally {
      setLoading(false);
    }
  }, [authToken, handoffToken, handleMessage, setPipelineStatus]);

  useEffect(() => {
    if (authToken && handoffToken) void fetchSession();
  }, [authToken, handoffToken, fetchSession]);

  // Live WS — only when we're actively running.
  const wsUrl = useMemo(() => {
    if (!handoffToken) return undefined;
    return ENV.API_URL.replace(/^http/, "ws") + `/ws/handoff/${encodeURIComponent(handoffToken)}`;
  }, [handoffToken]);

  // The handoff socket hook delivers ``StreamMessage`` whose ``data``
  // type is a union for the existing workflow / chat surfaces; the handoff
  // reducer only reads via ``as Record<string, unknown>``, so we re-shape
  // at the boundary to satisfy structural typing without touching the
  // global enum.
  const wsBridge = useCallback(
    (msg: StreamMessage) => {
      const widened: HandoffStreamMessage = {
        type: msg.type as string,
        chunk: msg.chunk,
        section: msg.section,
        data: (msg.data ?? undefined) as Record<string, unknown> | undefined,
      };
      handleMessage(widened);
    },
    [handleMessage]
  );

  const wsActive = session?.status === "running" && !state.done;
  useHandoffSocket({
    url: wsUrl,
    token: wsActive ? authToken : null,
    onMessage: wsBridge,
  });

  // Re-fetch session once the pipeline signals done so we pick up persisted state.
  const reFetchedRef = useRef(false);
  useEffect(() => {
    if (state.done && !reFetchedRef.current && authToken && handoffToken) {
      reFetchedRef.current = true;
      void fetchSession();
    }
  }, [state.done, authToken, handoffToken, fetchSession]);

  const handleStart = useCallback(async () => {
    if (!authToken || !handoffToken) return;
    setStarting(true);
    setStartError(null);
    try {
      await startHandoff(authToken, handoffToken);
      await fetchSession();
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Failed to start pipeline");
    } finally {
      setStarting(false);
    }
  }, [authToken, handoffToken, fetchSession]);

  // ---- Loading / error skeletons ----
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Loader2 className="h-5 w-5 animate-spin text-gray-500" />
      </div>
    );
  }
  // ISS-411 — key the full-page state off `!session` alone. A failed REFRESH of
  // an already-loaded session left `loadError` set while `session` was still
  // valid, and the OR discarded the whole running/completed view.
  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md text-center">
          <h1 className="text-[15px] font-semibold text-gray-900 mb-1">
            {loadError?.offline
              ? "Couldn't reach VelocityAI"
              : "Handoff not found"}
          </h1>
          <p className="text-[12px] text-gray-500 mb-4">
            {loadError?.offline
              ? "The request never reached the server, so this handoff may still be fine. Check your connection and try again."
              : loadError?.message ??
                "This handoff token doesn't exist, has expired, or belongs to a different account."}
          </p>
          <div className="flex items-center justify-center gap-3">
            {loadError?.offline && (
              <button
                onClick={() => void fetchSession()}
                className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 text-white px-3 py-1.5 text-[11px] font-medium hover:bg-blue-700"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Retry
              </button>
            )}
            <Link href="/dashboard" className="text-[12px] text-blue-700 hover:underline">
              Back to dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const canStart = session.status === "pending" || session.status === "failed";
  // Ensure expires_at is treated as UTC — backend returns naive ISO strings without Z
  const expiresAtUtc = session.expires_at.endsWith("Z") ? session.expires_at : session.expires_at + "Z";
  const expired =
    session.status === "expired" || new Date(expiresAtUtc) < new Date();

  // Onboarding state: need PAT before we can run.
  const showOnboarding = !session.has_github_pat && canStart && !expired;

  // ---- Render ----
  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-5 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center h-8 w-8 rounded-lg hover:bg-gray-100"
          >
            <ArrowLeft className="h-4 w-4 text-gray-500" />
          </Link>
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">
              Handoff workflow · {session.source_client ?? "unknown"} · {session.mode}
              {session.resolved_mode ? ` → ${session.resolved_mode}` : ""}
            </div>
            <div className="text-[13px] font-semibold text-gray-900 truncate">
              {session.task_description}
            </div>
            <div className="text-[10px] text-gray-500 inline-flex items-center gap-1 truncate mt-0.5">
              <GitBranch className="h-3 w-3" />
              {session.repo_url}
              {session.source_branch ? ` · ${session.source_branch}` : ""}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            href="/handoff/settings"
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-[11px] text-gray-700 hover:bg-gray-50"
          >
            <SettingsIcon className="h-3.5 w-3.5" />
            Integrations
          </Link>
          {canStart && session.has_github_pat && !expired && (
            <button
              onClick={handleStart}
              disabled={starting}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 text-white px-3 py-1.5 text-[11px] font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {starting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : session.status === "failed" ? (
                <RotateCcw className="h-3.5 w-3.5" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {starting
                ? "Starting..."
                : session.status === "failed"
                ? "Retry pipeline"
                : "Start pipeline"}
            </button>
          )}
        </div>
      </header>

      {/* Body */}
      <main className="flex-1 min-h-0 flex">
        {showOnboarding ? (
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-2xl mx-auto px-6 py-8">
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 mb-5">
                <h2 className="text-[14px] font-semibold text-amber-900 mb-1">
                  One more step before this can run
                </h2>
                <p className="text-[12px] text-amber-900">
                  VelocityAI needs a GitHub PAT (with{" "}
                  <code className="px-1 rounded bg-amber-100">repo</code> scope) to
                  clone {session.repo_url} and open the pull request. Add one below —
                  it&apos;s saved encrypted and never returned by any API.
                </p>
              </div>
              <IntegrationsCard />
              <p className="text-[11px] text-gray-500 mt-4">
                After saving, the <strong>Start pipeline</strong> button in the top
                bar will activate.
              </p>
            </div>
          </div>
        ) : expired ? (
          <div className="flex-1 flex items-center justify-center text-center px-6">
            <div className="max-w-md">
              <h2 className="text-[14px] font-semibold text-gray-900 mb-2">
                This handoff has expired
              </h2>
              <p className="text-[12px] text-gray-500 mb-4">
                Handoff URLs are good for one hour. Re-run{" "}
                <code className="px-1 rounded bg-gray-100">/flowin-handoff</code>{" "}
                from your IDE to mint a new one.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="w-[320px] flex-shrink-0">
              <HandoffAgentPanel
                state={state}
                selectedAgentId={selectedAgent}
                onSelectAgent={setSelectedAgent}
              />
            </div>
            <div className="flex-1 min-w-0">
              <HandoffPreviewPanel
                state={state}
                selectedAgentId={selectedAgent}
                onSelectAgent={setSelectedAgent}
              />
            </div>
          </>
        )}
      </main>

      {/* ISS-411 — refresh failure over an already-loaded session: a notice,
          not a replacement for the view it failed to refresh. */}
      {loadError && (
        <div className="absolute bottom-16 right-4 max-w-md rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-800 shadow">
          {loadError.offline
            ? "Couldn't reach VelocityAI to refresh this handoff — what's shown may be out of date."
            : loadError.message}
        </div>
      )}

      {/* Start error toast */}
      {startError && (
        <div className="absolute bottom-4 right-4 max-w-md rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-[11px] text-red-700 shadow">
          {startError}
        </div>
      )}
    </div>
  );
}
