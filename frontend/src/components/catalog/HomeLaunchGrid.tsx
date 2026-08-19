"use client";

/**
 * HomeLaunchGrid — the data-driven Home landing (Plan 20-02 / WF-DB-01).
 *
 * Workflows are sourced from the Redux store's global.workflows (populated
 * once per sign-in by store/listenerMiddleware.ts's fetchWorkflows — see
 * store/slices/globalSlice.ts) rather than an internal fetch. The store
 * persists across client-side navigation for the session, giving the same
 * "instant on revisit" behavior the old sessionStorage cache provided,
 * without a second, independently-cached copy of the same data.
 *
 * Recent runs still use their own fetch + sessionStorage cache below — that
 * data isn't part of the app-wide preload.
 *
 * SC-001 / ND-D: every row + recent comes from live endpoints (never fabricated).
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Lock, AlertCircle, Plus, Info, X, Construction } from "lucide-react";
import { getWorkflowIcon } from "@/lib/workflowIcons";
import type { WorkflowType } from "@/types/index";
import type { WorkflowRun } from "@/types/index";
import { WorkflowDialog } from "@/components/workflow/WorkflowDialog";
import type { Tier } from "@/lib/entitlements";
import { canRunPipeline, TIER_LABELS, getUpgradeTier } from "@/lib/entitlements";
import { baseWorkflowType } from "@/lib/workflowChaining";
import { useWorkflowLabels } from "@/hooks/useWorkflowMetadata";
import { selectWorkflowWizardPath } from "@/store/slices/globalSlice";
import type { UserWorkflowSummary, AnalyticsSummary } from "@/lib/api";
import { getAnalyticsSummary, getToken } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";
import type { WorkflowSummary } from "@/store/api/workflows";

// ─── sessionStorage cache helpers ───────────────────────────────────────────
const CACHE_KEY_RECENTS   = "vlc_home_recents_v1";

function readCache<T>(key: string): T[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T[]) : [];
  } catch {
    return [];
  }
}

function writeCache<T>(key: string, data: T[]): void {
  if (typeof window === "undefined") return;
  try { sessionStorage.setItem(key, JSON.stringify(data)); } catch { /* quota exceeded — ignore */ }
}

// ─── Props ───────────────────────────────────────────────────────────────────

interface HomeLaunchGridProps {
  onSelectFeature: (type: WorkflowType) => void;
  /** kept for API compatibility with SavedWorkflowsPage profile dropdown */
  onLaunchSaved?: (saved: UserWorkflowSummary) => void;
  userTier?: Tier;
  /** controlled-optional brief from DashboardLayout */
  brief?: string;
  onBriefChange?: (value: string) => void;
  onBuild?: () => void;
  onOpenRun?: (run: WorkflowRun) => void;
  /** pre-fetched from page.tsx — used to skip internal fetch when already loaded */
  recentRuns?: WorkflowRun[];
}

const RECENTS_LIMIT = 6;

const STATUS_TONE: Record<string, { label: string; dot: string; text: string }> = {
  completed: { label: "Done",      dot: "bg-status-done",    text: "text-status-done"    },
  running:   { label: "Running",   dot: "bg-status-running", text: "text-status-running" },
  revising:  { label: "Revising",  dot: "bg-status-running", text: "text-status-running" },
  failed:    { label: "Failed",    dot: "bg-status-failed",  text: "text-status-failed"  },
  degraded:  { label: "Degraded",  dot: "bg-status-failed",  text: "text-status-failed"  },
  cancelled: { label: "Cancelled", dot: "bg-ink-300",        text: "text-ink-400"        },
};

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return `${Math.round(days / 7)}w ago`;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function HomeLaunchGrid({
  onSelectFeature,
  userTier = "basic",
  brief,
  onBriefChange,
  onBuild,
  onOpenRun,
  recentRuns: recentRunsProp,
}: HomeLaunchGridProps) {
  const router = useRouter();
  const getWorkflowLabel = useWorkflowLabels();

  // Redux-sourced (store/slices/globalSlice.ts) — populated once per sign-in,
  // persists across client-side navigation for the session.
  const allWorkflows = useAppSelector((state) => state.global.workflows);
  const workflowsStatus = useAppSelector((state) => state.global.workflowsStatus);
  const workflowsError = useAppSelector((state) => state.global.workflowsError);
  // user_launchable gates catalog visibility. Beta ("Coming Soon") vs. active
  // rows are split into two separate sections below (not interleaved in one
  // grid) so the distinction is a visual heading, not just a small per-card
  // badge. Within the active set, `custom` (the open-ended composer) sorts
  // last — every OTHER active workflow is a concrete, pre-built pipeline;
  // custom is the escape hatch, so it belongs at the tail of the "ready to
  // use" set, not mixed in among them. Stable sort otherwise preserves the
  // catalog's own manifest order.
  const workflows = allWorkflows
    .filter((w) => w.user_launchable)
    .slice()
    .sort((a, b) => Number(a.id === "custom") - Number(b.id === "custom"));

  const reduxRecentRuns = useAppSelector((state) => state.global.recentRuns);
  const recentRunsStatus = useAppSelector((state) => state.global.recentRunsStatus);
  const recentRunsError = useAppSelector((state) => state.global.recentRunsError);

  // Redux is the instant-paint seed (fetchRecentRuns, same preload as
  // workflows — see store/listenerMiddleware.ts); dashboard/page.tsx's own
  // live-synced recentRuns prop (kept fresh via SSE) supersedes it once it
  // arrives, via the effect below.
  const [recents, setRecents] = useState<WorkflowRun[]>(() => {
    if (recentRunsProp && recentRunsProp.length > 0) return recentRunsProp.slice(0, RECENTS_LIMIT);
    if (reduxRecentRuns.length > 0) return reduxRecentRuns.slice(0, RECENTS_LIMIT);
    return readCache<WorkflowRun>(CACHE_KEY_RECENTS);
  });
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [inspectId, setInspectId] = useState<string | null>(null);

  // Only show a loading skeleton when there is truly nothing to show yet
  // (Redux hasn't settled and we have no workflows in the store).
  const loading = workflowsStatus !== "succeeded" && workflowsStatus !== "failed" && workflows.length === 0;
  const error = workflowsError ?? recentRunsError;

  // dashboard/page.tsx's live-synced recentRuns wins once it resolves.
  useEffect(() => {
    if (recentRunsProp && recentRunsProp.length > 0) {
      const sliced = recentRunsProp.slice(0, RECENTS_LIMIT);
      setRecents(sliced);
      writeCache(CACHE_KEY_RECENTS, sliced);
    }
  }, [recentRunsProp]);

  // If neither the live prop nor cache had anything on mount, adopt the
  // Redux preload result as soon as it lands.
  useEffect(() => {
    if ((!recentRunsProp || recentRunsProp.length === 0) && reduxRecentRuns.length > 0 && recents.length === 0) {
      const sliced = reduxRecentRuns.slice(0, RECENTS_LIMIT);
      setRecents(sliced);
      writeCache(CACHE_KEY_RECENTS, sliced);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduxRecentRuns]);

  // Fetch per-deliverable analytics (38-05: time estimate) on mount.
  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const token = getToken();
        if (!token) return;
        const summary = await getAnalyticsSummary(token, "all");
        setAnalytics(summary);
      } catch {
        // Tolerate analytics fetch failure; cards render without time estimate.
      }
    };
    void fetchAnalytics();
  }, []);

  void recentRunsStatus;

  // ─── Prompt (controlled-optional) ─────────────────────────────────────────
  // Brief/onBriefChange/onBuild props retained in interface for API compat
  // but the prompt textarea has been removed from the home screen (FIX-181).

  // ─── Launch ────────────────────────────────────────────────────────────────
  const handleClick = (type: WorkflowType) => {
    if (!canRunPipeline(userTier, type)) return;
    const wizardPath = selectWorkflowWizardPath(baseWorkflowType(type));
    if (wizardPath) { router.push(wizardPath); return; }
    onSelectFeature(type);
  };

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full flex-col overflow-y-auto bg-surface-paper" style={{ scrollbarGutter: "stable" }}>
      <div className="mx-auto w-full max-w-[1000px] px-6 pt-12 pb-16 sm:px-10">

        {/* Header */}
        <div className="text-center">
          <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-ink-400">
            VelocityAI
          </p>
          <h1 className="mb-7 font-serif text-[38px] font-normal italic leading-tight tracking-tight text-ink-900 sm:text-[44px]">
            What would you like to build today?
          </h1>
        </div>

        {error && (
          <div className="mt-6 flex items-center gap-1.5 rounded-lg bg-[var(--status-failed-fill)] px-2.5 py-1.5 text-[11px] text-status-failed">
            <AlertCircle className="h-3 w-3 flex-shrink-0" /> {error}
          </div>
        )}

        {/* Loading skeleton — only shown on true first visit (no cache) */}
        {loading && (
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="relative overflow-hidden rounded-[14px] border border-line-border bg-surface-card h-[168px] shimmer-effect" />
            ))}
          </div>
        )}

        {!loading && !error && workflows.length === 0 && (
          <p className="mt-10 py-2 text-[11px] text-ink-400">No workflows available for your plan yet.</p>
        )}

        {/* Deliverable card grid — split into two sections so "ready now" and
            "Coming Soon" are visually distinct groups, not one blurred list
            where the only signal is a small per-card badge. */}
        {!loading && !error && workflows.length > 0 && (() => {
          const activeRows = workflows.filter((w) => !w.is_beta);
          const betaRows   = workflows.filter((w) => w.is_beta);

          const renderCard = (row: WorkflowSummary) => {
            const type      = row.id as WorkflowType;
            const label     = row.display_name ?? getWorkflowLabel(row.id);
            const subtitle  = row.description;
            const agents    = row.step_count ?? (row as WorkflowSummary & { agent_count?: number }).agent_count;
            // 38-05: time estimate keyed on row.id when history exists
            const durationSec = analytics?.type_avg_duration_sec?.[row.id];
            const timeMinutes = durationSec ? Math.round(durationSec / 60) : null;
            const estimate  = timeMinutes ? `~${agents} agents · ~${timeMinutes}m` : `~${agents} agents`;
            const isBeta    = !!row.is_beta;
            // Beta rows are never actionable (no tier can unlock a "Coming
            // Soon" workflow), regardless of the tier gate below.
            const allowed   = !isBeta && canRunPipeline(userTier, type);
            const upgradeTo = isBeta ? null : getUpgradeTier(userTier, type);
            // Authored per-workflow icon (manifest `icon` field — a Lucide
            // component name string, e.g. "Presentation") — falls back to
            // Sparkles when the manifest hasn't authored one.
            const RowIcon   = getWorkflowIcon(row.icon);
            return (
              <div key={row.id} className="relative">
                <button onClick={() => handleClick(type)} disabled={!allowed}
                  className={`group flex h-full w-full flex-col rounded-[14px] border p-[18px] text-left transition-all ${
                    allowed
                      ? "cursor-pointer border-line-border bg-surface-card hover:border-line-faint hover:shadow-md hover:-translate-y-0.5"
                      : "cursor-not-allowed border-line-border bg-surface-card opacity-60"
                  }`}>
                  <div className="mb-3.5 flex items-center justify-between pr-7">
                    <span className={`grid h-[38px] w-[38px] place-items-center rounded-[10px] transition-colors ${
                      allowed ? "bg-brand-fill text-brand" : "bg-surface-warm text-ink-400"
                    }`}>
                      {allowed
                        ? <RowIcon className="h-[19px] w-[19px]" />
                        : isBeta
                          ? <Construction className="h-[19px] w-[19px]" />
                          : <Lock className="h-[19px] w-[19px]" />}
                    </span>
                    <ArrowRight className="h-[17px] w-[17px] text-ink-300 transition-all group-hover:text-brand group-hover:translate-x-0.5" />
                  </div>
                  <h2 className={`mb-1.5 text-[14.5px] font-semibold leading-snug ${allowed ? "text-ink-900 group-hover:text-brand" : "text-ink-400"}`}>
                    {label}
                  </h2>
                  <p className={`mb-3 text-[12.5px] leading-relaxed ${allowed ? "text-ink-500" : "text-ink-400"}`}>
                    {subtitle}
                  </p>
                  <span className="mt-auto text-[11px] font-medium text-ink-400">{estimate}</span>
                  {isBeta ? (
                    <span className="mt-1.5 inline-flex w-fit items-center rounded-[5px] border border-line-border bg-surface-paper px-2 py-1 text-[10px] font-medium text-ink-500">
                      Coming Soon
                    </span>
                  ) : (
                    !allowed && upgradeTo && (
                      <span className="mt-1.5 inline-flex w-fit items-center rounded-[5px] border border-brand/20 bg-brand-fill px-2 py-1 text-[10px] font-semibold text-brand">
                        Requires {TIER_LABELS[upgradeTo]} plan
                      </span>
                    )
                  )}
                </button>
                {/* SURF-03: inspect compiled workflow capabilities */}
                <button type="button" onClick={() => setInspectId(row.id)}
                  aria-label={`Inspect ${label} details`}
                  disabled={isBeta}
                  className="absolute right-2.5 top-2.5 flex h-7 w-7 items-center justify-center rounded-lg text-ink-300 transition-colors hover:bg-surface-warm hover:text-ink-700 disabled:pointer-events-none disabled:opacity-0">
                  <Info className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          };

          return (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {activeRows.map(renderCard)}
              </div>

              {betaRows.length > 0 && (
                <>
                  <div className="mt-10 mb-3.5 flex items-center gap-2">
                    <h3 className="text-[13px] font-semibold text-ink-500">Coming Soon</h3>
                    <span className="text-[11px] text-ink-400">Not yet available on any plan</span>
                  </div>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {betaRows.map(renderCard)}
                  </div>
                </>
              )}
            </>
          );
        })()}

        {/* Jump back in */}
        {recents.length > 0 && (
          <>
            <div className="mt-10 mb-3.5 flex items-center justify-between">
              <span className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">
                Jump back in
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {recents.map((run) => {
                const tone = STATUS_TONE[run.status] ?? { label: run.status, dot: "bg-ink-300", text: "text-ink-400" };
                return (
                  <button key={run.id} type="button" onClick={() => onOpenRun?.(run)}
                    className="group flex flex-col rounded-[13px] border border-line-border bg-surface-card p-[15px] text-left transition-colors hover:border-line-faint">
                    <div className="mb-2.5 flex items-center gap-2">
                      <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${tone.dot}`} />
                      <span className={`text-[10.5px] font-semibold uppercase tracking-[0.08em] ${tone.text}`}>{tone.label}</span>
                      <span className="flex-1" />
                      <span className="text-[11px] text-ink-400">{relativeTime(run.createdAt)}</span>
                    </div>
                    <p className="mb-1 truncate text-[13.5px] font-semibold text-ink-900 group-hover:text-brand">{run.title}</p>
                    <p className="truncate text-[11.5px] text-ink-400">
                      {/* KAN-130: append "(Chained)" when the run was launched by chaining
                          from a prior run's output (sourceRunId non-null). SC-001: keyed
                          on the generic sourceRunId field, never a workflow-name literal. */}
                      {getWorkflowLabel(run.type)}{run.sourceRunId ? " (Chained)" : ""}
                    </p>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>

      {inspectId && <WorkflowDialog workflowId={inspectId} onClose={() => setInspectId(null)} />}
    </div>
  );
}
