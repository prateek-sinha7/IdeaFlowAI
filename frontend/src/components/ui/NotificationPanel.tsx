"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Bell, CheckCircle2, XCircle, Loader2, ArrowRight, Trash2 } from "lucide-react";
import type { PipelineNotification } from "@/hooks/useNotifications";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import { Badge } from "@/components/ui/Badge";
import { Pill } from "@/components/ui/Pill";

interface NotificationPanelProps {
  notifications: PipelineNotification[];
  unreadCount: number;
  onMarkAllRead: () => void;
  onClearAll: () => void;
  onGoToPipeline: () => void;       // navigate to execution view
  onViewResults: (n: PipelineNotification) => void; // navigate to history detail
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
  if (status === "cancelled") return <XCircle className="h-3.5 w-3.5 text-status-queued flex-shrink-0" />;
  return null;
}

export function NotificationPanel({
  notifications,
  unreadCount,
  onMarkAllRead,
  onClearAll,
  onGoToPipeline,
  onViewResults,
}: NotificationPanelProps) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  // a11y: Escape closes the panel and returns focus to the bell.
  const bellRef = useRef<HTMLButtonElement>(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // a11y: Escape closes the dropdown + refocuses the bell (bound on the wrapper
  // so it fires whether focus is on the bell or inside the dropdown).
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" && open) {
      e.stopPropagation();
      setOpen(false);
      bellRef.current?.focus();
    }
  };

  const handleOpen = () => {
    setOpen(v => !v);
    if (!open && unreadCount > 0) {
      // Mark all read when panel opens
      onMarkAllRead();
    }
  };

  return (
    <div className="relative" ref={panelRef} onKeyDown={handleKeyDown}>
      {/* Bell button */}
      <button
        ref={bellRef}
        onClick={handleOpen}
        className="relative flex items-center justify-center h-8 w-8 rounded-[var(--radius-button)] text-ink-300 hover:text-white hover:bg-white/10 transition-all"
        aria-label="Notifications"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-brand text-[9px] font-bold text-white border border-surface-near-black">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-full mt-2 w-[340px] rounded-[var(--radius-menu)] border border-line-border bg-surface-white shadow-[var(--elevation-notif)] overflow-hidden z-50"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-line-divider bg-surface-warm">
              <div className="flex items-center gap-2">
                <Bell className="h-3.5 w-3.5 text-ink-500" />
                <span className="text-[12px] font-semibold text-ink-900">Notifications</span>
                {notifications.length > 0 && (
                  <Pill className="text-[10px] px-1.5 py-0 text-ink-500">
                    {notifications.length}
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
            <div className="max-h-[380px] overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
                  <div className="h-10 w-10 rounded-[var(--radius-menu)] bg-surface-warm flex items-center justify-center mb-3">
                    <Bell className="h-5 w-5 text-ink-400" />
                  </div>
                  <p className="text-[12px] font-medium text-ink-500">No notifications yet</p>
                  <p className="text-[11px] text-ink-400 mt-1">
                    Pipeline completions will appear here
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-line-divider">
                  {notifications.map((n) => (
                    <div
                      key={n.id}
                      className={`px-4 py-3 hover:bg-surface-warm transition-colors ${
                        !n.read && n.status !== "running" ? "bg-brand-fill" : ""
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5">
                          <StatusIcon status={n.status} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-[11px] font-semibold text-ink-900 truncate">
                              {getWorkflowLabel(n.workflowType)}
                            </p>
                            <span className="text-[10px] text-ink-400 flex-shrink-0">
                              {formatRelativeTime(n.createdAt)}
                            </span>
                          </div>
                          <p className="text-[11px] text-ink-500 truncate mt-0.5">{n.title}</p>

                          {/* Progress bar for running */}
                          {n.status === "running" && (n.agentsTotal ?? 0) > 0 && (
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
                          {/* Waiting for agent count — indeterminate pulse */}
                          {n.status === "running" && (n.agentsTotal ?? 0) === 0 && (
                            <div className="mt-2 h-1 bg-[var(--status-running-fill)] rounded-full overflow-hidden">
                              <div className="h-full bg-status-running/30 rounded-full animate-pulse w-full" />
                            </div>
                          )}

                          {/* Status label */}
                          <div className="flex items-center justify-between mt-2">
                            <Badge status={n.status} />

                            {/* CTA */}
                            {n.status === "running" ? (
                              <button
                                onClick={() => { setOpen(false); onGoToPipeline(); }}
                                className="flex items-center gap-1 text-[10px] font-medium text-brand hover:underline"
                              >
                                View progress <ArrowRight className="h-3 w-3" />
                              </button>
                            ) : n.status === "completed" ? (
                              <button
                                onClick={() => { setOpen(false); onViewResults(n); }}
                                className="flex items-center gap-1 text-[10px] font-medium text-brand hover:underline"
                              >
                                View results <ArrowRight className="h-3 w-3" />
                              </button>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </div>
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
