"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Bell, CheckCircle2, XCircle, Loader2, ArrowRight, Trash2, PauseCircle, X } from "lucide-react";
import type { PipelineNotification } from "@/hooks/useNotifications";
import { useWorkflowLabels } from "@/hooks/useWorkflowMetadata";
import { Badge } from "@/components/ui/Badge";
import { Pill } from "@/components/ui/Pill";
import { parseRunInput } from "@/lib/runInput";
import type { WorkflowRun } from "@/types/index";

// Status label map — mirrors AppHeader's RUN_STATUS_TONE labels.
// SC-001: keyed on generic status strings, never a workflow-name literal.
const LIVE_STATUS_LABEL: Record<string, string> = {
  running:          "Running",
  revising:         "Revising",
  planning:         "Planning",
  generating:       "Building",
  analyzing:        "Analyzing",
  waiting_for_user: "Waiting for you",
  clarifying:       "Clarifying",
  gate:             "Awaiting review",
};

interface NotificationPanelProps {
  // Terminal (completed / failed / cancelled) notifications from useNotifications.
  // Live/running notifications are NOT passed here — they come via liveRuns.
  notifications: PipelineNotification[];
  unreadCount: number;
  onMarkAllRead: () => void;
  onClearAll: () => void;
  onGoToPipeline: () => void;
  // Navigate to a specific run (live or terminal).
  onViewResults: (n: PipelineNotification) => void;
  // Per-item dismiss for terminal notifications.
  onDismissOne?: (id: string) => void;
  // Live runs — the SAME list the header badge uses (server-sourced recentRuns
  // mapped with live agent progress). This is the single source of truth for
  // in-flight runs; no parallel ephemeral tracking needed.
  liveRuns?: PipelineNotification[];
  // Keep recentRuns for the handleRunClick navigation (same as AppHeader).
  recentRuns?: WorkflowRun[];
}

function formatRelativeTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function StatusIcon({ status }: { status: PipelineNotification["status"] }) {
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 text-status-running animate-spin flex-shrink-0" />;
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5 text-status-done flex-shrink-0" />;
  if (status === "failed") return <XCircle className="h-3.5 w-3.5 text-status-failed flex-shrink-0" />;
  if (status === "cancelled") return <XCircle className="h-3.5 w-3.5 text-status-amber flex-shrink-0" />;
  if (status === "gate") return <PauseCircle className="h-3.5 w-3.5 text-status-amber flex-shrink-0" />;
  return null;
}

// Renders one row — shared between live and terminal sections.
function NotifRow({
  n,
  onRowClick,
  onDismiss,
  recentRuns = [],
}: {
  n: PipelineNotification;
  onRowClick: () => void;
  onDismiss?: () => void;
  recentRuns?: WorkflowRun[];
}) {
  const getWorkflowLabel = useWorkflowLabels();
  const isLive = n.status === "running" || n.status === "gate";

  // Resolve detailed status from server run when available.
  const serverRun = recentRuns.find(r => r.id === n.workflowRunId);
  const rawStatus = serverRun?.status ?? (n.status === "gate" ? "waiting_for_user" : n.status);
  const statusLabel = LIVE_STATUS_LABEL[rawStatus] ?? LIVE_STATUS_LABEL["running"];
  const isGate = rawStatus === "waiting_for_user" || n.status === "gate";

  const cleanTitle = (() => {
    const t = n.title;
    if (!t) return t;
    const stripped = t.startsWith("Title: ") ? t.slice("Title: ".length).trim() : t;
    if (!stripped.includes("===")) return stripped;
    if (stripped.trimStart().startsWith("===")) return getWorkflowLabel(n.workflowType);
    const p = parseRunInput(stripped);
    return (p.revisionInstruction ?? p.brief ?? stripped).split("\n")[0].trim() || getWorkflowLabel(n.workflowType);
  })();

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onRowClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(); }
      }}
      className={`px-4 py-3 cursor-pointer hover:bg-surface-warm transition-colors ${
        !n.read && !isLive ? "bg-brand-fill" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          <StatusIcon status={n.status} />
        </div>
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold text-ink-900 truncate">
              {getWorkflowLabel(n.workflowType)}
            </p>
            <span className="text-[10px] text-ink-400 flex-shrink-0">
              {formatRelativeTime(n.createdAt)}
            </span>
          </div>

          {/* Brief / subtitle */}
          {cleanTitle && (
            <p className="text-[11px] text-ink-500 truncate mt-0.5">{cleanTitle}</p>
          )}

          {/* Progress bar — live runs with known agent count */}
          {isLive && (n.agentsTotal ?? 0) > 0 && (
            <div className="mt-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-ink-400">
                  {n.agentsCompleted ?? 0} of {n.agentsTotal} agents
                </span>
                <span className="text-[10px] text-status-running font-medium">
                  {Math.round(((n.agentsCompleted ?? 0) / (n.agentsTotal ?? 1)) * 100)}%
                </span>
              </div>
              <div className="h-1 bg-[var(--status-running-fill)] rounded-full overflow-hidden">
                <div
                  className="h-full bg-status-running rounded-full transition-all duration-500"
                  style={{ width: `${Math.round(((n.agentsCompleted ?? 0) / (n.agentsTotal ?? 1)) * 100)}%` }}
                />
              </div>
            </div>
          )}
          {/* Indeterminate pulse while waiting for agent count */}
          {isLive && (n.agentsTotal ?? 0) === 0 && (
            <div className="mt-2 h-1 bg-[var(--status-running-fill)] rounded-full overflow-hidden">
              <div className="h-full bg-status-running/30 rounded-full animate-pulse w-full" />
            </div>
          )}

          {/* Status label + CTA */}
          <div className="flex items-center justify-between mt-2">
            {isLive ? (
              <span className={`text-[10px] font-semibold uppercase tracking-[0.06em] ${isGate ? "text-status-amber" : "text-status-running"}`}>
                {statusLabel}
              </span>
            ) : (
              <Badge status={n.status} />
            )}

            {isLive ? (
              <button
                onClick={(e) => { e.stopPropagation(); onRowClick(); }}
                className="flex items-center gap-1 text-[10px] font-medium text-brand hover:underline"
              >
                View progress <ArrowRight className="h-3 w-3" />
              </button>
            ) : n.status === "completed" ? (
              <button
                onClick={(e) => { e.stopPropagation(); onRowClick(); }}
                className="flex items-center gap-1 text-[10px] font-medium text-brand hover:underline"
              >
                Open <ArrowRight className="h-3 w-3" />
              </button>
            ) : null}
          </div>
        </div>

        {/* Per-item dismiss — only on terminal notifications */}
        {!isLive && onDismiss && (
          <button
            aria-label={`Dismiss notification for ${getWorkflowLabel(n.workflowType)}`}
            onClick={(e) => { e.stopPropagation(); onDismiss(); }}
            className="flex-shrink-0 mt-0.5 text-ink-300 hover:text-ink-600 transition-colors"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}

export function NotificationPanel({
  notifications: notificationsProp,
  unreadCount,
  onMarkAllRead,
  onClearAll,
  onGoToPipeline,
  onViewResults,
  onDismissOne,
  liveRuns = [],
  recentRuns = [],
}: NotificationPanelProps) {
  const getWorkflowLabel = useWorkflowLabels();
  // Defensive: only show terminal notifications here — live runs come via liveRuns.
  // This prevents duplicates if a caller accidentally passes running notifications.
  const notifications = notificationsProp.filter(
    n => n.status !== "running" && n.status !== "gate"
  );
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" && open) {
      e.stopPropagation();
      setOpen(false);
      bellRef.current?.focus();
    }
  };

  const handleOpen = () => {
    setOpen(v => !v);
    if (!open && unreadCount > 0) onMarkAllRead();
  };

  // Total count shown in the badge pill: live runs + terminal notifications.
  const totalCount = liveRuns.length + notifications.length;
  const isEmpty = totalCount === 0;

  return (
    <div className="relative" ref={panelRef} onKeyDown={handleKeyDown}>
      {/* Bell button */}
      <button
        ref={bellRef}
        onClick={handleOpen}
        className="relative flex items-center justify-center h-8 w-8 rounded-[var(--radius-button)] text-ink-300 hover:text-white hover:bg-white/10 transition-all"
        aria-label="Notifications"
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-brand text-[9px] font-bold text-white border border-surface-near-black">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="Notifications"
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-full mt-2 w-[340px] rounded-[var(--radius-menu)] border border-line-border bg-surface-white shadow-[var(--elevation-notif)] overflow-hidden z-50"
          >
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-line-divider bg-surface-warm">
              <div className="flex items-center gap-2">
                <Bell className="h-3.5 w-3.5 text-ink-500" />
                <span className="text-[12px] font-semibold text-ink-900">Notifications</span>
                {totalCount > 0 && (
                  <Pill className="text-[10px] px-1.5 py-0 text-ink-500">
                    {totalCount}
                  </Pill>
                )}
              </div>
              {notifications.length > 0 && (
                <button
                  onClick={onClearAll}
                  className="flex items-center gap-1 text-[10px] text-ink-400 hover:text-ink-700 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Clear all
                </button>
              )}
            </div>

            {/* Notification list */}
            <div className="max-h-[420px] overflow-y-auto">
              {isEmpty ? (
                <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
                  <div className="h-10 w-10 rounded-[var(--radius-menu)] bg-surface-warm flex items-center justify-center mb-3">
                    <Bell className="h-5 w-5 text-ink-400" />
                  </div>
                  <p className="text-[12px] font-medium text-ink-500">No notifications yet</p>
                  <p className="text-[11px] text-ink-400 mt-1">Pipeline completions will appear here</p>
                </div>
              ) : (
                <div className="divide-y divide-line-divider">
                  {/* ── Live runs (server-sourced, same as header badge) ── */}
                  {liveRuns.map((n) => (
                    <NotifRow
                      key={n.id}
                      n={n}
                      recentRuns={recentRuns}
                      onRowClick={() => { setOpen(false); onViewResults(n); }}
                    />
                  ))}

                  {/* ── Terminal notifications (completed / failed / cancelled) ── */}
                  {notifications.map((n) => (
                    <NotifRow
                      key={n.id}
                      n={n}
                      recentRuns={recentRuns}
                      onRowClick={() => { setOpen(false); onViewResults(n); }}
                      onDismiss={onDismissOne ? () => onDismissOne(n.id) : undefined}
                    />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
