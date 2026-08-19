"use client";

import { useCallback, useEffect, useState } from "react";
import type { WorkflowType } from "@/types/index";

export interface PipelineNotification {
  id: string;
  workflowRunId?: string;
  workflowType: WorkflowType;
  title: string;
  status: "running" | "completed" | "failed" | "cancelled" | "gate";
  agentsCompleted?: number;
  agentsTotal?: number;
  // Stored as ISO string in localStorage, hydrated as Date on load.
  createdAt: Date;
  completedAt?: Date;
  read: boolean;
}

// ── localStorage persistence (FIX-202) ────────────────────────────────────────
// v3 schema — bumped from v2 to purge old notifications that lack workflowRunId.
// Without workflowRunId, clicking a completed notification opens the wrong run.
// All new notifications now get workflowRunId stamped at markCompleted time.
const STORAGE_KEY = "flowin.notifications.v3";
const DISMISSED_KEY = "flowin.notifications.dismissed.v3";

function loadFromStorage(): PipelineNotification[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<Record<string, unknown>>;
    const dismissed = loadDismissed();
    return parsed
      // Drop notifications the user explicitly dismissed.
      .filter((n) => !dismissed.has(n.id as string))
      // FIX-204: drop "running" and "gate" notifications on hydration.
      // After a page refresh, in-flight runs are no longer live — the SSE
      // connection is gone and the run may have completed, failed, or been
      // cancelled while the page was closed. Rehydrating them as "running"
      // produces stale eternally-spinning entries that never resolve.
      // Terminal notifications (completed / failed / cancelled) are safe to
      // persist and are the only ones worth showing after a refresh.
      .filter((n) => n.status !== "running" && n.status !== "gate")
      .map((n) => ({
        ...n,
        // Hydrate ISO strings back to Date objects.
        createdAt: new Date(n.createdAt as string),
        completedAt: n.completedAt ? new Date(n.completedAt as string) : undefined,
      })) as PipelineNotification[];
  } catch {
    return [];
  }
}

function saveToStorage(notifications: PipelineNotification[]): void {
  if (typeof window === "undefined") return;
  try {
    // FIX-204: only persist terminal notifications (completed/failed/cancelled).
    // Running and gate notifications are ephemeral — they belong to a live SSE
    // session and become stale the moment the page is refreshed. Writing them
    // to storage is what caused duplicate/stale entries to rehydrate on load.
    const persistable = notifications.filter(
      (n) => n.status !== "running" && n.status !== "gate"
    );
    if (persistable.length === 0) {
      // Don't persist empty arrays; remove the key so it stays null.
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(persistable));
    }
  } catch {
    // Storage quota exceeded or unavailable — fail silently; next write retries.
  }
}

function loadDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveDismissed(ids: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids]));
  } catch {
    // fail silently
  }
}

const WORKFLOW_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  user_stories_revision: "User Stories (Revised)",
  ppt: "Presentation",
  ppt_revision: "Presentation (Revised)",
  // KAN-130: od_ppt and od_prototype are the actual pipeline_type values stored
  // in WorkflowRun.type; they had no entry and fell back to the raw alias string.
  prototype: "Prototype",
  prototype_revision: "Prototype (Revised)",
  app_builder: "App Builder",
  app_builder_revision: "App Builder (Revised)",
  mulesoft_to_springboot: "Mulesoft Migration",
  dotnet_to_azure: ".NET Migration",
  reverse_engineer: "Reverse Engineer",
  custom: "Custom Workflow",
};

export function getWorkflowLabel(type: string): string {
  return WORKFLOW_LABELS[type] || type;
}

export function useNotifications() {
  // FIX-202: hydrate from localStorage on mount so notifications survive refresh.
  const [notifications, setNotifications] = useState<PipelineNotification[]>(() =>
    loadFromStorage()
  );

  // FIX-202: persist to localStorage on every state change.
  useEffect(() => {
    saveToStorage(notifications);
  }, [notifications]);

  const addRunningNotification = useCallback((
    id: string,
    workflowType: WorkflowType,
    title: string,
    agentsTotal: number,
  ) => {
    setNotifications(prev => {
      // Replace if same id already exists (e.g. re-run)
      const filtered = prev.filter(n => n.id !== id);
      return [{
        id,
        workflowType,
        title,
        status: "running",
        agentsCompleted: 0,
        agentsTotal,
        createdAt: new Date(),
        read: false,
      }, ...filtered];
    });
  }, []);

  const updateProgress = useCallback((id: string, agentsCompleted: number) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, agentsCompleted } : n)
    );
  }, []);

  const markCompleted = useCallback((id: string, workflowRunId?: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id
        ? { ...n, status: "completed" as const, completedAt: new Date(), workflowRunId, read: false }
        : n
      )
    );
  }, []);

  const markFailed = useCallback((id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id
        ? { ...n, status: "failed" as const, completedAt: new Date() }
        : n
      )
    );
  }, []);

  const markCancelled = useCallback((id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id
        ? { ...n, status: "cancelled" as const, completedAt: new Date() }
        : n
      )
    );
  }, []);

  // A review gate opened — the run is PAUSED awaiting the owner, not terminal.
  // Mirrors markFailed but sets status:"gate" and does NOT stamp completedAt
  // (there is no terminal timestamp for a paused run). read:false surfaces it.
  const markGatePaused = useCallback((id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id
        ? { ...n, status: "gate" as const, read: false }
        : n
      )
    );
  }, []);

  // The review gate RESOLVED (approved/edited/rejected) and the run RESUMED —
  // return a PAUSED notification to "running". Inverse of markGatePaused; guarded
  // on status==="gate" so it never clobbers a terminal (completed/failed/
  // cancelled) mark or a fresh running run. Generic — no workflow-name branch.
  const markGateResumed = useCallback((id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id && n.status === "gate"
        ? { ...n, status: "running" as const }
        : n
      )
    );
  }, []);

  // Called when pipeline_start arrives with the real agent count
  const updateAgentsTotal = useCallback((id: string, agentsTotal: number, title?: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id
        ? {
            ...n,
            agentsTotal,
            ...(title ? { title } : {}),
          }
        : n
      )
    );
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  }, []);

  // FIX-202: per-item dismiss — removes the notification from the list and
  // records its id in the persisted dismissed set so it does not re-appear
  // after a page refresh (unlike "Clear all" which only clears in-memory state).
  const dismissOne = useCallback((id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
    // Persist the dismissal so the notification stays gone after a refresh.
    const dismissed = loadDismissed();
    dismissed.add(id);
    saveDismissed(dismissed);
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
    // FIX-202: also clear the persistence layer so notifications don't
    // rehydrate on the next page load after a "Clear all".
    if (typeof window !== "undefined") {
      try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
      try { localStorage.removeItem(DISMISSED_KEY); } catch { /* ignore */ }
    }
  }, []);

  // KAN-132 (FIX-148): store the backend run id on a running notification so
  // the header dropdown can navigate to the specific run that was clicked, not
  // just the active building run. Called from page.tsx's onStartPipeline .then()
  // once the launchedRunId is available.
  const setNotifWorkflowRunId = useCallback((id: string, workflowRunId: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, workflowRunId } : n)
    );
  }, []);

  const unreadCount = notifications.filter(n => !n.read && n.status !== "running").length;

  return {
    notifications,
    addRunningNotification,
    updateProgress,
    updateAgentsTotal,
    markCompleted,
    markFailed,
    markCancelled,
    markGatePaused,
    markGateResumed,
    setNotifWorkflowRunId,
    markAllRead,
    dismissOne,
    clearAll,
    unreadCount,
  };
}
