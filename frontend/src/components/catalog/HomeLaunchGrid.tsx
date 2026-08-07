"use client";

/**
 * HomeLaunchGrid — the data-driven Home landing (Plan 20-02 / WF-DB-01).
 *
 * FIX-100: Stale-while-revalidate pattern for instant rendering.
 * On first visit: fetches from API, stores in sessionStorage, shows shimmer skeleton.
 * On every subsequent visit (refresh / navigate back): reads from sessionStorage
 * cache synchronously in useState initialiser → renders instantly, then a
 * background refetch silently updates the cache.
 *
 * SC-001 / ND-D: every row + recent comes from live endpoints (never fabricated).
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Lock, AlertCircle, Info, Sparkles } from "lucide-react";
import type { WorkflowType } from "@/types/index";
import type { WorkflowRun } from "@/types/index";
import { WorkflowDialog } from "@/components/workflow/WorkflowDialog";
import type { Tier } from "@/lib/entitlements";
import { canRunPipeline, TIER_LABELS, getUpgradeTier } from "@/lib/entitlements";
import { CHAIN_OPTIONS } from "@/lib/workflowChaining";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import {
  getWorkflowDefinitions,
  getWorkflows,
  getToken,
  type WorkflowSummary,
  type UserWorkflowSummary,
} from "@/lib/api";

// ─── sessionStorage cache helpers ───────────────────────────────────────────
const CACHE_KEY_WORKFLOWS = "vlc_home_workflows_v1";
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
  homeWorkflows?: WorkflowSummary[];
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
  homeWorkflows: homeWorkflowsProp,
  recentRuns: recentRunsProp,
}: HomeLaunchGridProps) {
  const router = useRouter();

  // Seed state synchronously from sessionStorage cache (or prop if already
  // available). This is the key to instant rendering — no async wait on mount.
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>(() => {
    if (homeWorkflowsProp && homeWorkflowsProp.length > 0) return homeWorkflowsProp;
    return readCache<WorkflowSummary>(CACHE_KEY_WORKFLOWS);
  });
  const [recents, setRecents] = useState<WorkflowRun[]>(() => {
    if (recentRunsProp && recentRunsProp.length > 0) return recentRunsProp.slice(0, RECENTS_LIMIT);
    return readCache<WorkflowRun>(CACHE_KEY_RECENTS);
  });
  // Only show a loading skeleton when there is truly nothing to display yet
  // (first ever visit, no cache, no prop).
  const [loading, setLoading] = useState(() => {
    if (homeWorkflowsProp && homeWorkflowsProp.length > 0) return false;
    return readCache<WorkflowSummary>(CACHE_KEY_WORKFLOWS).length === 0;
  });
  const [error, setError] = useState<string | null>(null);
  const [inspectId, setInspectId] = useState<string | null>(null);

  // When the parent prop resolves (page.tsx fetch completes after mount), sync
  // it into local state and update the cache so the next visit is instant.
  useEffect(() => {
    if (homeWorkflowsProp && homeWorkflowsProp.length > 0) {
      setWorkflows(homeWorkflowsProp);
      setLoading(false);
      writeCache(CACHE_KEY_WORKFLOWS, homeWorkflowsProp);
    }
  }, [homeWorkflowsProp]);

  useEffect(() => {
    if (recentRunsProp && recentRunsProp.length > 0) {
      const sliced = recentRunsProp.slice(0, RECENTS_LIMIT);
      setRecents(sliced);
      writeCache(CACHE_KEY_RECENTS, sliced);
    }
  }, [recentRunsProp]);

  // Background fetch — runs whenever neither the prop nor the cache had data.
  // Also acts as the silent background revalidation on subsequent visits.
  useEffect(() => {
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) { setError("Not authenticated."); setLoading(false); return; }

    // Only show loading spinner if we have nothing to show yet.
    const hasWorkflows = workflows.length > 0;
    const hasRecents   = recents.length > 0;

    if (!hasWorkflows) {
      getWorkflowDefinitions(jwt)
        .then((rows) => {
          if (cancelled) return;
          const filtered = rows.filter((w) => w.user_launchable);
          setWorkflows(filtered);
          writeCache(CACHE_KEY_WORKFLOWS, filtered);
          setError(null);
        })
        .catch((e) => { if (!cancelled) setError(e?.message ?? "Failed to load workflows."); })
        .finally(() => { if (!cancelled) setLoading(false); });
    } else {
      // Background revalidation — update cache silently.
      getWorkflowDefinitions(jwt)
        .then((rows) => {
          if (cancelled) return;
          const filtered = rows.filter((w) => w.user_launchable);
          setWorkflows(filtered);
          writeCache(CACHE_KEY_WORKFLOWS, filtered);
        })
        .catch(() => { /* non-fatal — keep cached data */ });
    }

    if (!hasRecents) {
      getWorkflows(jwt, { limit: RECENTS_LIMIT })
        .then(({ runs }) => {
          if (cancelled) return;
          const sliced = runs.slice(0, RECENTS_LIMIT);
          setRecents(sliced);
          writeCache(CACHE_KEY_RECENTS, sliced);
        })
        .catch(() => { /* non-fatal */ });
    } else {
      // Background revalidation for recents.
      getWorkflows(jwt, { limit: RECENTS_LIMIT })
        .then(({ runs }) => {
          if (cancelled) return;
          const sliced = runs.slice(0, RECENTS_LIMIT);
          setRecents(sliced);
          writeCache(CACHE_KEY_RECENTS, sliced);
        })
        .catch(() => { /* non-fatal */ });
    }

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Prompt (controlled-optional) ─────────────────────────────────────────
  // Brief/onBriefChange/onBuild props retained in interface for API compat
  // but the prompt textarea has been removed from the home screen (FIX-181).

  // ─── Launch ────────────────────────────────────────────────────────────────
  const handleClick = (type: WorkflowType) => {
    if (!canRunPipeline(userTier, type)) return;
    const opt = CHAIN_OPTIONS.find((o) => o.type === type);
    if (opt?.requiresWizard && opt.wizardPath) { router.push(opt.wizardPath); return; }
    if (type === "prototype") { router.push("/workflow/create?mode=prototype"); return; }
    if (type === "ppt")       { router.push("/workflow/create?mode=ppt");       return; }
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
              <div key={i} className="h-[168px] animate-pulse rounded-[14px] border border-line-border bg-surface-card" />
            ))}
          </div>
        )}

        {!loading && !error && workflows.length === 0 && (
          <p className="mt-10 py-2 text-[11px] text-ink-400">No workflows available for your plan yet.</p>
        )}

        {/* Deliverable card grid */}
        {!loading && !error && workflows.length > 0 && (
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {workflows.map((row) => {
              const type      = row.id as WorkflowType;
              const label     = row.display_name ?? getWorkflowLabel(row.id);
              const subtitle  = row.description;
              const agents    = row.step_count ?? (row as WorkflowSummary & { agent_count?: number }).agent_count;
              const estimate  = `~${agents} agents`;
              const allowed   = canRunPipeline(userTier, type);
              const upgradeTo = getUpgradeTier(userTier, type);
              return (
                <div key={row.id} className="relative">
                  <button onClick={() => handleClick(type)} disabled={!allowed}
                    className={`group flex h-full w-full flex-col rounded-[14px] border p-[18px] text-left transition-colors ${
                      allowed
                        ? "cursor-pointer border-line-border bg-surface-card hover:border-line-faint"
                        : "cursor-not-allowed border-line-border bg-surface-card opacity-60"
                    }`}>
                    <div className="mb-3.5 flex items-center justify-between">
                      <span className="grid h-[38px] w-[38px] place-items-center rounded-[10px] bg-surface-warm text-ink-900">
                        {allowed ? <Sparkles className="h-[19px] w-[19px]" /> : <Lock className="h-[18px] w-[18px] text-ink-400" />}
                      </span>
                      <ArrowRight className="h-[17px] w-[17px] text-ink-300 transition-colors group-hover:text-ink-600" />
                    </div>
                    <h2 className={`mb-1.5 text-[14.5px] font-semibold leading-snug ${allowed ? "text-ink-900 group-hover:text-brand" : "text-ink-400"}`}>
                      {label}
                    </h2>
                    <p className={`mb-3 text-[12.5px] leading-relaxed ${allowed ? "text-ink-500" : "text-ink-400"}`}>
                      {subtitle}
                    </p>
                    <div className="mt-auto flex items-center gap-1.5">
                      <span className="text-[11px] font-medium text-ink-400">{estimate}</span>
                      {/* SURF-03: inspect compiled workflow capabilities — inline next to agent count */}
                      <span
                        role="button"
                        tabIndex={0}
                        onClick={(e) => { e.stopPropagation(); setInspectId(row.id); }}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); setInspectId(row.id); } }}
                        aria-label={`Inspect ${label} details`}
                        className="flex h-4 w-4 cursor-pointer items-center justify-center rounded text-ink-300 transition-colors hover:text-ink-600"
                      >
                        <Info className="h-3 w-3" />
                      </span>
                    </div>
                    {!allowed && upgradeTo && (
                      <span className="mt-1.5 text-[10px] font-semibold text-brand">
                        Requires {TIER_LABELS[upgradeTo]} plan
                      </span>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        )}

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
