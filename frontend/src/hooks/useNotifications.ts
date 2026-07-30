"use client";

import { useCallback, useState } from "react";
import type { WorkflowType } from "@/types/index";

export interface PipelineNotification {
  id: string;
  workflowRunId?: string;
  workflowType: WorkflowType;
  title: string;
  status: "running" | "completed" | "failed" | "cancelled" | "gate";
  agentsCompleted?: number;
  agentsTotal?: number;
  createdAt: Date;
  completedAt?: Date;
  read: boolean;
}

const WORKFLOW_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  user_stories_revision: "User Stories (Revised)",
  ppt: "Presentation",
  ppt_revision: "Presentation (Revised)",
  // KAN-130: od_ppt and od_prototype are the actual pipeline_type values stored
  // in WorkflowRun.type; they had no entry and fell back to the raw alias string.
  od_ppt: "Presentation",
  od_ppt_revision: "Presentation (Revised)",
  prototype: "Prototype",
  prototype_revision: "Prototype (Revised)",
  od_prototype: "Prototype",
  od_prototype_revision: "Prototype (Revised)",
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
  const [notifications, setNotifications] = useState<PipelineNotification[]>([]);

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

  const clearAll = useCallback(() => {
    setNotifications([]);
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
    markAllRead,
    clearAll,
    unreadCount,
  };
}
