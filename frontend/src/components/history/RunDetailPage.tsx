"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ChevronRight, Zap, Radio, RefreshCw, Loader2 } from "lucide-react";
import {
  getToken,
  getRunSummary,
  type RunSummary,
  type RunSummaryAgent,
} from "@/lib/api";
import type { RunFamily } from "@/types/index";
import { formatDuration, formatTokenCount } from "@/lib/runStats";
import { parseFailedAgentIds, buildAgentNameById } from "@/lib/parseFailedAgents";
import { VersionTimeline } from "./RevisionFamilyView";
import { DegradedRunAffordance } from "@/components/preview/PreviewPanel";
import { Badge } from "@/components/ui/Badge";
import { Tabs } from "@/components/ui/Tabs";

export interface RunDetailPageProps {
  /** The run whose summary this page renders. */
  runId: string;
  /** Return to the calling surface (History list / Home recents). */
  onBack: () => void;
  /** The id of the currently-LIVE building run, if any — enables the "view
   *  live pipeline" affordance when this detail IS that run (generic, name-free). */
  activeRunId?: string | null;
  /** Jump to the live pipeline view for a still-running run. */
  onViewRunningPipeline?: (runId: string) => void;
  /** Optional: let the CALLER own version switching so both the summary column AND
   *  the caller's own surfaces (e.g. the History deliverable panel) re-sync to the
   *  chosen version. When omitted, the timeline switches this page's summary only
   *  (standalone use). Generic run id — never a workflow-name branch (SC-001). */
  onSelectVersion?: (runId: string) => void;
}

// Neutral avatar tints — Phase-32 @theme tokens only (no raw hex / retired
// palette). Rotated per agent index, purely decorative.
const AVATAR_TINTS = [
  "bg-brand-fill text-brand",
  "bg-surface-warm text-ink-700",
  "bg-[var(--status-done-fill)] text-status-done",
  "bg-[var(--status-running-fill)] text-status-running",
  "bg-[var(--status-amber-fill)] text-status-amber",
  "bg-surface-card text-ink-500",
];

function agentInitials(name?: string): string {
  return (name || "Agent")
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

/**
 * RunDetailPage — the self-contained Run detail/reopen page fed by
 * `GET /api/runs/{id}/summary` (SHELL-03). Promotes the in-panel `WorkflowHistory`
 * detail into a page: KPI strip, per-agent breakdown, revision/version timeline,
 * and a terminal-failure banner — all keyed on GENERIC run fields (status /
 * agents / tokens), NEVER a workflow-name branch (SC-001 / INV-1).
 *
 * REUSES the shared surfaces rather than re-implementing them (D-15 / no dual
 * implementation): `VersionTimeline`, `DegradedRunAffordance`,
 * `parseFailedAgentIds` / `buildAgentNameById`, and the `formatDuration` /
 * `formatTokenCount` formatters.
 */
export function RunDetailPage({
  runId,
  onBack,
  activeRunId,
  onViewRunningPipeline,
  onSelectVersion,
}: RunDetailPageProps) {
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"agents" | "timeline">("agents");
  // The version currently shown — clicking a VersionTimeline chip refetches that
  // member's summary (the family walk shares the same read model).
  const [activeVersionId, setActiveVersionId] = useState(runId);
  // When the caller opens a DIFFERENT run, reset the shown version during render
  // (React's sanctioned "adjust state on prop change" pattern — no sync effect,
  // no cascading-render warning).
  const [prevRunId, setPrevRunId] = useState(runId);
  if (runId !== prevRunId) {
    setPrevRunId(runId);
    setActiveVersionId(runId);
  }

  // Cancellable mount-fetch (the SavedWorkflowsPage guard idiom): no stale set
  // after unmount, and re-fetch when the active version changes.
  useEffect(() => {
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getRunSummary(jwt, activeVersionId)
      .then((s) => {
        if (!cancelled) {
          setSummary(s);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled)
          setError((e as Error)?.message ?? "Could not load this run.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeVersionId]);

  // Manual + auto refresh: re-fetch the same summary in place (no `loading`
  // flip, so it doesn't retrigger the full-page skeleton above on every tick).
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshMs, setRefreshMs] = useState(0);
  // Counts down in whole seconds so the Refresh button can show it directly —
  // ticks the actual refresh at 0 rather than running a second, driftable timer.
  const [secondsLeft, setSecondsLeft] = useState(0);
  const refreshSummary = useCallback(() => {
    const jwt = getToken();
    if (!jwt) return;
    setIsRefreshing(true);
    getRunSummary(jwt, activeVersionId)
      .then((s) => {
        setSummary(s);
        setError(null);
      })
      .catch((e) => {
        setError((e as Error)?.message ?? "Could not load this run.");
      })
      .finally(() => {
        setIsRefreshing(false);
        // Resume the countdown only once the fetch actually finishes, so a
        // slow refresh doesn't silently eat into the next interval.
        if (refreshMs) setSecondsLeft(refreshMs / 1000);
      });
  }, [activeVersionId, refreshMs]);
  const handleManualRefresh = useCallback(() => {
    refreshSummary();
    if (refreshMs) setSecondsLeft(refreshMs / 1000);
  }, [refreshSummary, refreshMs]);
  // Ticks the countdown down to 0 and HOLDS there — it does not trigger the
  // refresh or reset itself. That split matters: "Reloading" must reflect
  // however long the fetch actually takes, not just the one tick it started
  // on, so the reset-to-full lives in refreshSummary's `.finally()` above,
  // fired only when the fetch truly completes.
  useEffect(() => {
    if (!refreshMs) {
      setSecondsLeft(0);
      return;
    }
    setSecondsLeft(refreshMs / 1000);
    const id = setInterval(() => {
      setSecondsLeft((s) => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => clearInterval(id);
  }, [refreshMs]);
  // Fires the refresh exactly once, the moment the countdown reaches 0.
  useEffect(() => {
    if (refreshMs && secondsLeft === 0 && !isRefreshing) {
      refreshSummary();
    }
  }, [secondsLeft, refreshMs, isRefreshing, refreshSummary]);

  const backButton = (
    <button
      type="button"
      onClick={onBack}
      aria-label="Back to history"
      className="inline-flex items-center gap-1.5 text-[11px] font-medium text-ink-400 transition-colors hover:text-ink-700"
    >
      <ArrowLeft aria-hidden className="h-3.5 w-3.5" /> Back
    </button>
  );

  // ── Loading skeleton ─────────────────────────────────────────────
  if (loading) {
    return (
      <section
        aria-label="Run detail"
        aria-busy="true"
        className="flex h-full flex-col bg-surface-paper"
      >
        <header className="flex items-center gap-3 border-b border-line-border px-6 py-4">
          {backButton}
        </header>
        <div className="flex-1 space-y-3 p-6">
          <div className="h-6 w-1/3 animate-pulse rounded-[var(--radius-button)] bg-surface-warm" />
          <div className="h-20 w-full animate-pulse rounded-[var(--radius-card)] bg-surface-warm" />
          <div className="h-16 w-full animate-pulse rounded-[var(--radius-card)] bg-surface-warm" />
        </div>
      </section>
    );
  }

  // ── Graceful error / empty state ─────────────────────────────────
  if (error || !summary) {
    return (
      <section
        aria-label="Run detail"
        className="flex h-full flex-col bg-surface-paper"
      >
        <header className="flex items-center gap-3 border-b border-line-border px-6 py-4">
          {backButton}
        </header>
        <div className="flex flex-1 items-center justify-center px-6">
          <div className="flex max-w-sm flex-col items-center gap-2 text-center">
            <p className="text-sm font-semibold text-ink-900">
              Could not load this run
            </p>
            <p className="text-xs text-ink-500">
              {error ?? "The run summary is unavailable."}
            </p>
          </div>
        </div>
      </section>
    );
  }

  // ── Loaded — generic-keyed rendering (SC-001: status/agents/tokens) ──
  // ISS-395: "diverted" is a terminal, non-resumable status too — without it the
  // Agents tab lists a diverted run's partially-run agents as if the run had
  // completed normally, with nothing saying the pipeline handed off and the
  // remaining agents never ran. The affordance carries diverted-specific copy
  // (see `diverted` below), never the "failed or degraded" line.
  const terminalFailure =
    summary.status === "failed" ||
    summary.status === "cancelled" ||
    summary.status === "degraded" ||
    summary.status === "diverted";
  const cancelled = summary.status === "cancelled";
  const diverted = summary.status === "diverted";
  const failedAgents = parseFailedAgentIds(summary.error ?? undefined);
  const agentNameById = buildAgentNameById(
    summary.agents.map((a: RunSummaryAgent) => ({
      id: a.agent_id ?? "",
      name: a.name ?? "",
    })),
  );

  const family: RunFamily = {
    root_id: summary.root_id,
    members: summary.members,
  };
  const tu = summary.token_usage ?? {};
  const total = tu.total_tokens ?? 0;
  const input = tu.total_input_tokens ?? 0;
  const output = tu.total_output_tokens ?? 0;

  const isLive = !!activeRunId && activeRunId === summary.id;

  return (
    <section
      aria-label="Run detail"
      className="flex h-full flex-col bg-surface-paper"
    >
      {/* Header — back + title + status + optional live affordance */}
      <header className="flex flex-col gap-3 border-b border-line-border px-6 pb-4 pt-4">
        <div className="flex items-center justify-between gap-3">
          {backButton}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleManualRefresh}
              disabled={isRefreshing}
              aria-label={refreshMs ? `Refresh run data — next auto-refresh in ${secondsLeft}s` : "Refresh run data"}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border border-line-border bg-surface-white px-2.5 py-1 text-[11px] font-medium text-ink-600 transition-colors hover:bg-surface-warm disabled:opacity-50"
            >
              {isRefreshing ? (
                <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw aria-hidden className="h-3.5 w-3.5" />
              )}
              {refreshMs ? `${secondsLeft}s` : "Refresh"}
            </button>
            <select
              aria-label="Auto-refresh interval"
              value={refreshMs}
              onChange={(e) => setRefreshMs(Number(e.target.value))}
              className="appearance-none rounded-[var(--radius-button)] border border-line-border bg-surface-white px-2 py-1 text-[11px] font-medium text-ink-600 transition-colors hover:bg-surface-warm"
            >
              <option value={0}>Auto-refresh: Off</option>
              <option value={10000}>Every 10s</option>
              <option value={15000}>Every 15s</option>
              <option value={30000}>Every 30s</option>
              <option value={60000}>Every 1m</option>
            </select>
            {isLive && onViewRunningPipeline && (
              <button
                type="button"
                onClick={() => onViewRunningPipeline(summary.id)}
                className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] bg-brand px-2.5 py-1 text-[11px] font-medium text-white transition-colors hover:bg-brand-pressed"
              >
                <Radio aria-hidden className="h-3.5 w-3.5" /> View live pipeline
              </button>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <h1 className="min-w-0 flex-1 truncate text-[15px] font-semibold text-ink-900">
            {summary.title}
          </h1>
          <Badge status={summary.status} />
        </div>

        {/* KPI strip — total / input / output tokens + duration (reused fmts) */}
        {(total > 0 || summary.duration) && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {total > 0 && (
              <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-500">
                <Zap aria-hidden className="h-3 w-3 text-brand" />
                <span className="font-semibold text-ink-900">
                  {formatTokenCount(total)}
                </span>{" "}
                total
              </span>
            )}
            {total > 0 && (
              <span className="text-[11px] text-ink-500">
                {formatTokenCount(input)} input
              </span>
            )}
            {total > 0 && (
              <span className="text-[11px] text-ink-500">
                {formatTokenCount(output)} output
              </span>
            )}
            {summary.duration ? (
              <span className="text-[11px] text-ink-500">
                {formatDuration(summary.duration)}
              </span>
            ) : null}
            <span className="text-[11px] text-ink-400">
              {summary.agent_count} agents
            </span>
          </div>
        )}
      </header>

      {/* Revision/version timeline — REUSED (self-hides when < 2 members) */}
      <VersionTimeline
        family={family}
        activeRunId={activeVersionId}
        activeInput={summary.input ?? ""}
        onSelectVersion={(id) => {
          // Caller-owned switch (History): re-sync BOTH columns via the caller,
          // which changes runId → this page re-derives activeVersionId + refetches.
          // Standalone: switch this page's summary only.
          if (onSelectVersion) onSelectVersion(id);
          else setActiveVersionId(id);
        }}
      />

      {/* Accessible tab controls (reused Tabs primitive) */}
      <div className="px-6 pt-3">
        <Tabs
          tabs={[
            { id: "agents", label: "Agents" },
            { id: "timeline", label: "Timeline" },
          ]}
          active={activeTab}
          onChange={(id) => setActiveTab(id as "agents" | "timeline")}
        />
      </div>

      <div
        role="tabpanel"
        aria-label={activeTab === "agents" ? "Agents" : "Timeline"}
        className="min-h-0 flex-1 overflow-y-auto px-6 py-4"
      >
        {activeTab === "agents" ? (
          terminalFailure ? (
            // Terminal-failure banner — REUSED, keyed on generic status.
            <div className="h-full">
              <DegradedRunAffordance
                failedAgents={failedAgents}
                agentNameById={agentNameById}
                cancelled={cancelled}
                diverted={diverted}
              />
            </div>
          ) : summary.agents.length > 0 ? (
            <ul className="space-y-2">
              {summary.agents.map((agent, idx) => (
                <li
                  key={`${agent.agent_id ?? "agent"}-${idx}`}
                  className="flex items-center gap-3 rounded-[var(--radius-card)] border border-line-border bg-surface-white px-4 py-3"
                >
                  <div
                    aria-hidden
                    className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[var(--radius-button)] text-[11px] font-bold ${AVATAR_TINTS[idx % AVATAR_TINTS.length]}`}
                  >
                    {agent.icon || agentInitials(agent.name)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-[12.5px] font-semibold text-ink-900">
                        {agent.name || "Agent"}
                      </p>
                      <div className="flex flex-shrink-0 items-center gap-2">
                        {agent.duration != null && (
                          <span className="text-[10px] text-ink-400">
                            {formatDuration(agent.duration)}
                          </span>
                        )}
                        {agent.total_tokens ? (
                          <span className="text-[10px] text-ink-400">
                            {formatTokenCount(agent.total_tokens)} tok
                          </span>
                        ) : null}
                        <Badge status={agent.error ? "failed" : "done"} />
                      </div>
                    </div>
                    {agent.role && (
                      <p className="mt-0.5 truncate text-[10.5px] text-ink-400">
                        {agent.role}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="flex h-full items-center justify-center">
              <p className="text-[11px] text-ink-400">No agent data</p>
            </div>
          )
        ) : (
          // Timeline pane — ordered family member list.
          <ol className="space-y-1.5">
            {[...summary.members]
              .sort((a, b) => a.revision_index - b.revision_index)
              .map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    onClick={() => setActiveVersionId(m.id)}
                    aria-current={m.id === activeVersionId ? "true" : undefined}
                    className={`flex w-full items-center gap-2 rounded-[var(--radius-list-row)] border px-3 py-2 text-left transition-colors ${
                      m.id === activeVersionId
                        ? "border-brand bg-brand-fill"
                        : "border-line-border bg-surface-white hover:bg-surface-warm"
                    }`}
                  >
                    <span className="text-[11px] font-semibold text-ink-900">
                      v{m.revision_index}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-ink-500">
                      {m.title}
                    </span>
                    <Badge status={m.status} />
                    <ChevronRight
                      aria-hidden
                      className="h-3.5 w-3.5 flex-shrink-0 text-ink-300"
                    />
                  </button>
                </li>
              ))}
          </ol>
        )}
      </div>
    </section>
  );
}

export default RunDetailPage;
