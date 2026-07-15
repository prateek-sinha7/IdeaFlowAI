"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import { WifiOff, RefreshCw, Loader2 } from "lucide-react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { AppHeader } from "./AppHeader";
import { HomeLaunchGrid } from "@/components/catalog/HomeLaunchGrid";
import { LibraryPage } from "@/components/library/LibraryPage";
import { WorkflowHistory } from "@/components/history/WorkflowHistory";
import { AccountSettings } from "@/components/settings/AccountSettings";
import { AnalyticsPage } from "@/components/analytics/AnalyticsPage";
import { SavedWorkflowsPage } from "@/components/savedworkflows/SavedWorkflowsPage";
import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import { ComposerPage } from "@/components/workflow/composer/ComposerPage";
// INV-3 (plan 06): the AgentProgressPanel run-lane mount was removed here — its
// Stop/revise/suggestions controls are fully absorbed by RunChatLane. The
// component itself is retained (its own suite + the plan-08 Steps relocation);
// DashboardLayout no longer imports or mounts it.
// Phase 31 (CHATUI-01/02/03) — the run-screen chat lane composition root. Mounted
// as the execution-surface left column; it ABSORBS the AgentProgressPanel
// Stop/revise/suggestions controls (D-12 composer-per-state, SC-001 generic).
import { RunChatLane, type RunLaneState, type GateContext, type LaneSuggestion, type LaneProposal } from "@/components/chat/RunChatLane";
import type { SendMessageOptions } from "@/hooks/useRunChat";
import type { ClarifyResponse } from "@/components/chat/InlineClarifyActions";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import { CompletionToast } from "@/components/ui/CompletionToast";
import type { ToastItem } from "@/components/ui/CompletionToast";
import { useNotifications } from "@/hooks/useNotifications";
import type { ChatMessage, ChatSession, ProcessStep, PipelineRunState, WaveGroup, WorkflowRun, WorkflowType, GenericDeliverable, RunFamily } from "@/types/index";
import { canChainFrom, CHAIN_OPTIONS, CHAIN_BRIEF_KEY, CHAIN_FROM_KEY, CHAIN_SOURCE_RUN_ID_KEY, baseWorkflowType } from "@/lib/workflowChaining";
import { parseRunInput } from "@/lib/runInput";
import { getToken, getChainContext, getRunFamily } from "@/lib/api";
import type { UserWorkflowSummary } from "@/lib/api";
import type { ConnectionStatus } from "@/hooks/useWebSocket";
import type { ChatMode } from "@/components/chat/ChatInput";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import { useRunConnection } from "@/providers/RunConnectionProvider";

export interface DashboardLayoutProps {
  activeChatId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  userStoryContent: string;
  pptContent: string;
  prototypeContent: string;
  // ISS-021 (18-03) — generic deliverable channel for any pipeline_type that
  // matched no known FE render branch (live pipeline_complete + history-reopen).
  // Threaded straight down to PreviewPanel/FilesTab; the mimetype drives the
  // generic fallback renderer (SC-001 — never a workflow-name branch).
  genericDeliverable?: GenericDeliverable;
  connectionStatus: ConnectionStatus;
  onSendMessage: (content: string) => void;
  onSendMessageWithMode?: (content: string, mode: ChatMode) => void;
  onSelectChat: (chatId: string) => void;
  onNewChat: (chatSession: ChatSession) => void;
  onDeleteChat: (chatId: string) => void;
  onLogout: () => void;
  onReconnect: () => void;
  messageMode?: ChatMode;
  chatTitleUpdate?: { chat_session_id: string; title: string } | null;
  processSteps?: ProcessStep[];
  websocketSend?: (msg: string) => void;
  pipelineState?: PipelineRunState;
  onStartPipeline?: (type: string, message: string, agentIds?: string[], attachedSkills?: import("@/types/index").AttachedSkill[], attachedHooks?: import("@/types/index").AttachedHook[], extraParams?: Record<string, unknown>) => void;
  onResetPipeline?: () => void;
  recentRuns?: WorkflowRun[];
  // Revision Families (B1 / D1-D7): the reliable "run id that produced the
  // on-screen content", owned by page.tsx (pipeline_complete + reopen). Every
  // revision launch path sources parent linkage from this — replaces the fragile
  // currentWorkflowRunId heuristic (which mis-matched on double-revision types).
  contentSourceRunId?: string | null;
  onSelectWorkflowRun?: (run: WorkflowRun) => void;
  // Phase 16 (ISS-017) — the persisted status of a history-reopened run. When a
  // failed/cancelled run is reopened it carries no content, so the run's
  // server-persisted status is threaded down to PreviewPanel to render the
  // terminal-empty degraded/failed affordance on the history path. Undefined for
  // fresh/live runs and successful reopens.
  reopenedRunStatus?: import("@/types/index").WorkflowStatus;
  // Phase 16 (IN-01) — the failed-agent ids of a history-reopened terminal run,
  // parsed from the persisted run detail. Threaded to PreviewPanel so the reopen
  // affordance lists the real failed agents instead of an empty list.
  reopenedFailedAgents?: string[];
  // ISS-024 (16 review IN-02) — id→name lookup for a history-reopened run's
  // failed agents (the live pipelineState can't name them). Threaded straight to
  // PreviewPanel's DegradedRunAffordance; unknown ids fall back to the raw id.
  reopenedAgentNameById?: Record<string, string>;
  questionnaireData?: {
    questions: {
      id: string; question: string; options: string[]; answerType?: string;
      recommendedAnswer?: string; recommendedReasoning?: string;
      recommendedDisplay?: string; ambiguityCategory?: string; impactLevel?: string;
    }[]
  } | null;
  // Phase 2 (Universal Engine) — clarify gate resume wiring.
  activePipelineRunId?: string | null;
  // Phase 12 (RESUME-03) — reads the last-received seq for the active run so the
  // reconnect_pipeline send can include `after_seq` for the durable replay
  // (12-03). Returns 0 on a fresh load (no recorded seq ⇒ full-tail replay).
  getLastSeq?: () => number;
  onSubmitQuestionnaire?: (pipelineRunId: string, responses: Array<{ question_id: string; answer: string }>, skipClarification?: boolean) => void;
  // Workstream C1 (POR §6.5) — fold an answered clarify round into run-scoped
  // state before the questionnaire panel clears (consumed by C2's ClarificationsCard).
  onRetainClarifyRound?: (round: import("@/types/index").ClarifyRound) => void;
  // Review gate — shown when an agent with gate: Human_Gate completes
  reviewGateData?: {
    gateKey: string;
    agentId: string;
    agentName: string;
    output: string;
    pipelineRunId: string;
    // REDO-GATE (F-fe2): generic server-set flag threaded into the panel so the
    // Redo control renders only on redoable (inline) gates.
    redoable?: boolean;
    // SC-001 (plan 04→06, KAN-101): name-free server flags parsed in page.tsx —
    // the lane maps updateSpecsEligible into the InlineGateActions "Update the
    // Specs" affordance and artifactKind into the approve relabel. Additive.
    updateSpecsEligible?: boolean;
    artifactKind?: string;
  } | null;
  onApproveReview?: (gateKey: string, editedContent?: string) => void;
  onRejectReview?: (gateKey: string) => void;
  // REDO-GATE (F-fe2): pass-through redo callback to the ReviewGatePanel.
  onRedoReview?: (gateKey: string, instructions: string) => void;
  // KAN-101: pass-through update-specs callback to the ReviewGatePanel.
  onUpdateSpecsReview?: (gateKey: string, analysisReport: string) => void;
  pendingOdProtoParams?: {
    brief: string; templateId: string; designSystemId: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string;
    gateAgentIds?: string[];
    modelOverrides?: Record<string, string>;
    selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null;
  onClearPendingOdProto?: () => void;
  pendingOdPptParams?: {
    brief: string; templateId: string; designSystemId: string | null; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string;
    gateAgentIds?: string[];
    modelOverrides?: Record<string, string>;
    selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null;
  onClearPendingOdPpt?: () => void;
  userTier?: "basic" | "pro" | "enterprise";
  userEmail?: string;
  // Phase 12 (WAVE-03) — wave groups assembled from the live `wave_*` /
  // `subagent_*` WS events by dashboard/page.tsx. Optional + defaulted to []
  // so existing callers/tests that omit it are unaffected; a non-wave run
  // feeds an empty list and AgentDetailPanel's inline construction/wave tree
  // renders its own empty state.
  waves?: WaveGroup[];
  // Workstream C2 (POR §5 D3 / §6.2) — the live run's captured input (submittedBrief
  // in page.tsx, set in onStartPipeline). Threaded as PreviewPanel.runInput so the
  // StartingPointCard + Files "Run input" section render on the LIVE mount. Optional
  // and default-undefined → non-live callers/tests render unchanged.
  submittedBrief?: string;
  // ─── Phase 31 (CHATUI-01/02/03) — run chat lane wiring ──────────────────────
  // The family-anchored transcript + the transport-agnostic send from page.tsx's
  // `useRunChat` (fed by the active transport — SSE flag ON or legacy WS OFF).
  // Consumed by the RunChatLane mounted in the execution left column. Optional /
  // default-undefined → non-live callers and existing test renders unchanged.
  runChatMessages?: ChatMessage[];
  onRunChatSend?: (
    text: string,
    attachments?: import("@/types/index").ChatAttachment[],
    options?: SendMessageOptions,
  ) => void;
  // The nonce'd deep-link seam (borrow #6): the lane's result cards call
  // onRequestOpenTab; PreviewPanel consumes deepLinkTarget for all tabs.
  onRequestOpenTab?: (tab: string) => void;
  deepLinkTarget?: import("@/hooks/useTabDeepLink").TabDeepLinkTarget | null;
}

type MainView = "home" | "library" | "history" | "settings" | "analytics" | "input" | "execution" | "catalog" | "saved-workflows" | "composer";

// 43-02: a stable empty held-proposal list (referential identity preserved across
// renders). The concierge_proposal holds arrive with the Part-C SSE transport
// (43-06); wiring the confirm chip now keeps that a data change, not a re-wire.
const RUN_CONCIERGE_PROPOSALS: LaneProposal[] = [];

export function DashboardLayout({
  activeChatId,
  messages,
  isStreaming,
  streamingContent,
  userStoryContent,
  pptContent,
  prototypeContent,
  genericDeliverable,
  connectionStatus,
  onSendMessage,
  onSendMessageWithMode,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onLogout,
  onReconnect,
  messageMode,
  chatTitleUpdate,
  processSteps,
  websocketSend,
  pipelineState,
  reopenedRunStatus,
  reopenedFailedAgents,
  reopenedAgentNameById,
  onStartPipeline,
  onResetPipeline,
  recentRuns,
  contentSourceRunId,
  onSelectWorkflowRun,
  questionnaireData,
  activePipelineRunId,
  getLastSeq,
  onSubmitQuestionnaire,
  onRetainClarifyRound,
  reviewGateData,
  onApproveReview,
  onRejectReview,
  onRedoReview,
  onUpdateSpecsReview,
  pendingOdProtoParams,
  onClearPendingOdProto,
  pendingOdPptParams,
  onClearPendingOdPpt,
  userTier = "basic",
  userEmail,
  waves = [],
  submittedBrief,
  runChatMessages,
  onRunChatSend,
  onRequestOpenTab,
  deepLinkTarget,
}: DashboardLayoutProps) {
  const router = useRouter();
  // W1 (44-01) — the app-level SSE connection (inert when the flag is OFF). Used
  // only to make the WS-specific reconnect_pipeline frame dormant while SSE is the
  // active transport (useRunStream owns Last-Event-ID replay there).
  const runConnection = useRunConnection();
  const [mainView, setMainView] = useState<MainView>(() => {
    // If an od_prototype or od_ppt run is staged (user came from the wizard),
    // start directly in execution view — avoids the home screen flash while
    // waiting for the WebSocket to connect and fire the pipeline.
    if (typeof window !== "undefined" && (
      sessionStorage.getItem("od_prototype.pending") ||
      sessionStorage.getItem("od_ppt.pending")
    )) {
      return "execution";
    }
    return "home";
  });
  const [workflowType, setWorkflowType] = useState<WorkflowType>(() => {
    if (typeof window !== "undefined") {
      if (sessionStorage.getItem("od_prototype.pending")) return "prototype";
      if (sessionStorage.getItem("od_ppt.pending")) return "ppt";
    }
    return "user_stories";
  });
  const [workflowInput, setWorkflowInput] = useState("");
  // Tracks completed pipeline types (fed by the WS completion handlers). The
  // run-lane chaining suggestions derive from canChainFrom(workflowType); this
  // state is retained for the completion bookkeeping its setters perform.
  const [completedPipelineTypes, setCompletedPipelineTypes] = useState<WorkflowType[]>([]);
  const [lastPipelineOutput, setLastPipelineOutput] = useState<string>("");
  const [questionnaireQuestions, setQuestionnaireQuestions] = useState<{
    id: string; question: string; options: string[]; answerType?: string;
    recommendedAnswer?: string; recommendedReasoning?: string;
    recommendedDisplay?: string; ambiguityCategory?: string; impactLevel?: string;
  }[]>([]);
  const [questionnaireLoading, setQuestionnaireLoading] = useState(false);
  const [pendingPipelineRun, setPendingPipelineRun] = useState<{
    type: WorkflowType;
    message: string;
    agentIds?: string[];
    extraParams?: {
      template_id?: string;
      design_system_id?: string;
      custom_design_system_body?: string;
      custom_template_body?: string;
      discovery?: unknown;
    };
  } | null>(null);

  // Read attached skills/hooks from global context — set by user in AgentsPopup
  const { attachedSkills, attachedHooks } = useSkillsHooks();

  // ── Notifications + toasts ──────────────────────────────────────────────
  const {
    notifications,
    unreadCount,
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
  } = useNotifications();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const currentPipelineNotifId = useRef<string | null>(null);
  // KAN-90: when user explicitly cancels from the clarification step, block
  // the auto-redirect-to-execution effect for one render cycle so the home
  // navigation isn't immediately overridden by pipelineState.isRunning=true.
  const cancelNavigatingHomeRef = useRef(false);

  // ─── B3 (POR §5 D5) — revision family for the on-screen content ──────────────
  // Fetched here (the minimal seam — DashboardLayout already receives
  // contentSourceRunId AND mounts PreviewPanel) keyed on contentSourceRunId, and
  // threaded into PreviewPanel as an optional prop. The .catch guarantees it
  // never throws even if the endpoint is unavailable.
  const [runFamily, setRunFamily] = useState<RunFamily | null>(null);
  useEffect(() => {
    if (!contentSourceRunId) { setRunFamily(null); return; }
    getRunFamily(getToken() || "", contentSourceRunId)
      .then(setRunFamily)
      .catch(() => setRunFamily(null));
  }, [contentSourceRunId]);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Detect when pipeline starts running → switch to execution view.
  // Also sync workflowType from the pipeline's declared type so PreviewPanel
  // renders the right output component. Without this, od_prototype (which is
  // triggered programmatically, not via handleSelectFeature) would leave
  // workflowType at its "user_stories" default, causing PreviewPanel to render
  // UserStoryPreview instead of PrototypePreview.
  useEffect(() => {
    if (pipelineState?.isRunning) {
      // KAN-90: if user just cancelled from the clarification step, don't
      // force the execution view — they want to stay on home/dashboard.
      if (cancelNavigatingHomeRef.current) {
        cancelNavigatingHomeRef.current = false; // consume the flag
        return;
      }
      if (mainView !== "execution") {
        setMainView("execution");
      }
      const pt = pipelineState.pipeline_type as WorkflowType | "od_prototype" | "od_ppt";
      // Normalise od_prototype → prototype, od_ppt → ppt
      const normalised: WorkflowType = pt === "od_prototype" ? "prototype" : pt === "od_ppt" ? "ppt" : (pt as WorkflowType);
      if (normalised && normalised !== workflowType) {
        setWorkflowType(normalised);
      }
      // KAN-88 stale label fix: if currentPipelineNotifId still holds an old
      // run's id when a new pipeline starts (the previous completion effect may
      // not have run yet), clear it so the od_prototype notification guard
      // (!currentPipelineNotifId.current) fires correctly and creates a fresh
      // notification with the right type. Without this, a prototype run started
      // after a user_stories run keeps showing "User Stories" in the header.
      // We compare against the pipelineRunId so we only reset when a genuinely
      // NEW run starts, not on every isRunning re-render.
      const incomingRunId = pipelineState.pipelineRunId;
      if (incomingRunId && currentPipelineNotifId.current) {
        // If the current notif was created for a different run, reset it.
        // We detect this by checking if the notification was created for the
        // pipeline that just started (odProtoNotifCreated resets on !isRunning).
        // A simple guard: if isRunning just became true AND odProtoNotifCreated
        // is false (reset after last run), we're in a new run context.
        if (!odProtoNotifCreated.current) {
          currentPipelineNotifId.current = null;
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineState?.isRunning, pipelineState?.pipeline_type]);

  // Capture output when pipeline completes (for chaining)
  useEffect(() => {
    if (pipelineState && !pipelineState.isRunning && pipelineState.agents.length > 0) {
      const allDone = pipelineState.agents.every((a) => a.status === "done" || a.status === "error");
      if (allDone && pipelineState.agents.some((a) => a.status === "done")) {
        setCompletedPipelineTypes((prev) => {
          if (prev.includes(workflowType)) return prev;
          return [...prev, workflowType];
        });
        const output = pptContent || userStoryContent || prototypeContent;
        if (output) setLastPipelineOutput(output);

        // Fire completion notification + toast
        if (currentPipelineNotifId.current) {
          const notifId = currentPipelineNotifId.current;
          currentPipelineNotifId.current = null;  // reset so next run gets a fresh notification
          markCompleted(notifId);
          setToasts(prev => [...prev, {
            id: notifId + "-toast",
            workflowType,
            title: workflowType,
            status: "completed",
          }]);
        }
      }

      // Terminal failure / cancellation — fire the matching notification off the
      // GENERIC plan-05 pipelineState markers (failed / cancelled), NEVER a
      // workflow name (SC-001/INV-1). The completed branch above already reset
      // currentPipelineNotifId on success, so this only fires for a non-completed
      // terminal run that still owns a notification id.
      if (currentPipelineNotifId.current) {
        if (pipelineState.failed) {
          const notifId = currentPipelineNotifId.current;
          currentPipelineNotifId.current = null;
          markFailed(notifId);
        } else if (pipelineState.cancelled) {
          const notifId = currentPipelineNotifId.current;
          currentPipelineNotifId.current = null;
          markCancelled(notifId);
        }
      }
    }
  }, [pipelineState, workflowType, pptContent, userStoryContent, prototypeContent]);

  // Gate pause/resume — a review gate OPENING pauses the notification and its
  // RESOLVING resumes it, both off the GENERIC markers (reviewGateData +
  // running), the SAME condition that drives runLaneState==="gate" (:1311) —
  // never a workflow name (SC-001/INV-1). markGateResumed no-ops unless the
  // notification is actually paused, so it never clobbers a terminal mark.
  useEffect(() => {
    if (!currentPipelineNotifId.current || !pipelineState?.isRunning) return;
    if (reviewGateData) {
      markGatePaused(currentPipelineNotifId.current);
    } else {
      markGateResumed(currentPipelineNotifId.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewGateData, pipelineState?.isRunning]);

  // Update notification progress as agents complete
  useEffect(() => {
    if (pipelineState?.isRunning && currentPipelineNotifId.current) {
      updateProgress(currentPipelineNotifId.current, pipelineState.completedCount);
    }
  }, [pipelineState?.completedCount, pipelineState?.isRunning]);

  // Detect when od_prototype/od_ppt starts (fired from dashboard/page.tsx directly,
  // not through handleQuestionnaireSubmit) and create a notification for it.
  const odProtoNotifCreated = useRef(false);
  useEffect(() => {
    if (
      pipelineState?.isRunning &&
      (pipelineState.pipeline_type === "od_prototype" || pipelineState.pipeline_type === "prototype" ||
       pipelineState.pipeline_type === "od_ppt") &&
      !currentPipelineNotifId.current
    ) {
      if (odProtoNotifCreated.current) return;
      odProtoNotifCreated.current = true;
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // Use correct workflowType for od_ppt vs prototype
      const wfType: WorkflowType = (pipelineState.pipeline_type === "od_ppt") ? "ppt" : "prototype";
      const label = (pipelineState.pipeline_type === "od_ppt") ? "Presentation" : "Prototype";
      addRunningNotification(notifId, wfType, label, 0);
    }
    if (!pipelineState?.isRunning) {
      odProtoNotifCreated.current = false;
    }
  }, [pipelineState?.isRunning, pipelineState?.pipeline_type]);

  // Update agentsTotal when pipeline_start arrives with the real agent list
  useEffect(() => {
    const agentCount = pipelineState?.agents?.length ?? 0;
    if (agentCount > 0 && currentPipelineNotifId.current) {
      updateAgentsTotal(currentPipelineNotifId.current, agentCount);
    }
  }, [pipelineState?.agents?.length]);

  // Update notification title when backend generates a clean title
  useEffect(() => {
    const latestRun = recentRuns?.[0];
    if (latestRun?.title && latestRun.title !== "Untitled" && currentPipelineNotifId.current) {
      updateAgentsTotal(currentPipelineNotifId.current, pipelineState?.agents?.length ?? 0, latestRun.title);
    }
  }, [recentRuns?.[0]?.title]);

  // Check if pipeline is running (blocks navigation)
  const isPipelineRunning = pipelineState?.isRunning || false;

  // Extract Agent 3's (ppt-code-generator) output for early PPTX download
  const pptxCode = pipelineState?.agents.find(a => a.id === "ppt-code-generator" && a.status === "done")?.output || undefined;

  // Revision Families (B1 / D1-D7): the fragile currentWorkflowRunId heuristic is
  // GONE — it guessed the parent by matching recentRuns on the current workflow
  // type (with a double-revision-suffix branch that could never match) and
  // orphaned every history-launched revision. Parent linkage now comes from the
  // contentSourceRunId prop (page.tsx tracks the actual on-screen run).

  // Handle PPT revision — Phase 3: send run_revision WS message when a
  // completed run exists; fall back to the legacy text-injection pattern
  // for backward compat with pre-Phase3 runs.
  const handleRevisePpt = useCallback((instruction: string) => {
    if (!pptxCode && !pptContent) return;

    const isOdPpt = workflowType === "od_ppt" || workflowType === "od_ppt_revision";

    // Phase 3: use run_revision if we have a completed run ID
    if (contentSourceRunId && websocketSend) {
      const targetType = isOdPpt ? "od_ppt_output" : "ppt_output";
      websocketSend(JSON.stringify({
        type: "run_revision",
        parent_run_id: contentSourceRunId,
        target_artifact_type: targetType,
        instruction,
      }));
      setWorkflowType((isOdPpt ? "od_ppt_revision" : "ppt_revision") as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      return;
    }

    // Legacy fallback
    if (isOdPpt) {
      const existingHtml = pptContent || "";
      const revisionMessage = `=== EXISTING HTML DECK ===\n${existingHtml.slice(0, 60000)}\n=== END EXISTING DECK ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
      setWorkflowType("od_ppt_revision" as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      if (onStartPipeline) {
        onStartPipeline("od_ppt_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
      }
    } else {
      const existingCode = pptxCode || "";
      const revisionMessage = `=== EXISTING PRESENTATION CODE ===\n${existingCode}\n=== END EXISTING CODE ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
      setWorkflowType("ppt_revision" as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      if (onStartPipeline) {
        onStartPipeline("ppt_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
      }
    }
  }, [workflowType, pptxCode, pptContent, contentSourceRunId, websocketSend, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle User Story revision — re-run pipeline with existing backlog + change instruction
  const handleReviseUserStory = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING PRODUCT BACKLOG ===\n${userStoryContent}\n=== END EXISTING BACKLOG ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("user_stories_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      // Revision Families (B1): link the parent so the backend assembles the family.
      onStartPipeline("user_stories_revision", revisionMessage, undefined, attachedSkills, attachedHooks, contentSourceRunId ? { source_workflow_run_id: contentSourceRunId } : undefined);
    }
  }, [userStoryContent, contentSourceRunId, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle Prototype revision — surgical diff approach
  // Instead of asking the agent to reproduce the full HTML (which exceeds
  // model output token limits), we pass the full HTML but instruct the agent
  // to output ONLY the changed sections in a structured diff format.
  // The engine then merges the diff back into the original HTML.
  const handleRevisePrototype = useCallback((instruction: string) => {
    if (!prototypeContent) return;
    // Pass the full prototype HTML — no slice. The agent will output only the
    // changed sections, not the full document.
    const revisionMessage = `=== EXISTING PROTOTYPE HTML ===\n${prototypeContent}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("prototype_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      // Phase 5: send source_workflow_run_id so the backend can seed the
      // original run's spec/design into the revision sandbox. B1: sourced from the
      // contentSourceRunId prop (the actual on-screen run) — undefined when none.
      onStartPipeline("prototype_revision", revisionMessage, undefined, attachedSkills, attachedHooks, contentSourceRunId ? { source_workflow_run_id: contentSourceRunId } : undefined);
    }
  }, [prototypeContent, contentSourceRunId, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle App Builder revision — re-run pipeline with existing blueprint + change instruction
  const handleReviseAppBuilder = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING APP BLUEPRINT ===\n${userStoryContent.slice(0, 40000)}\n=== END EXISTING BLUEPRINT ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("app_builder_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      // Revision Families (B1): link the parent so the backend assembles the family.
      onStartPipeline("app_builder_revision", revisionMessage, undefined, attachedSkills, attachedHooks, contentSourceRunId ? { source_workflow_run_id: contentSourceRunId } : undefined);
    }
  }, [userStoryContent, contentSourceRunId, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle incoming questionnaire data from WebSocket
  useEffect(() => {
    if (questionnaireData && questionnaireData.questions) {
      setQuestionnaireQuestions(questionnaireData.questions);
      setQuestionnaireLoading(false);
    }
  }, [questionnaireData]);

  // If the WebSocket reconnects while a pipeline run is in-flight (i.e. the
  // user submitted the questionnaire but the connection dropped before the
  // run_pipeline message was delivered), re-send it on the new connection.
  const pendingPipelineRunRef = useRef<typeof pendingPipelineRun>(null);
  useEffect(() => {
    pendingPipelineRunRef.current = pendingPipelineRun;
  }, [pendingPipelineRun]);

  // Ref to store a pipeline start that needs to be fired once connected.
  // Used to survive WebSocket reconnects that happen between questionnaire
  // submit and pipeline_start arriving (e.g. hot-reload in dev, network blip).
  const pendingStartOnConnectRef = useRef<{
    type: string; message: string; agentIds?: string[];
    extraParams?: Record<string, unknown>;
  } | null>(null);

  // Fire any pending pipeline start as soon as the WebSocket is connected.
  useEffect(() => {
    if (connectionStatus !== "connected") return;
    const pending = pendingStartOnConnectRef.current;
    if (!pending) return;
    pendingStartOnConnectRef.current = null;
    if (onStartPipeline) {
      onStartPipeline(pending.type, pending.message, pending.agentIds, attachedSkills, attachedHooks, pending.extraParams);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionStatus]);

  // When the WebSocket reconnects while a pipeline is running, send
  // reconnect_pipeline so the backend attaches the new WS to the running queue.
  const activePipelineRunIdRef = useRef<string | null>(null);
  useEffect(() => {
    activePipelineRunIdRef.current = activePipelineRunId ?? null;
  }, [activePipelineRunId]);

  // Also track pipelineState.pipelineRunId for reconnection
  const pipelineRunIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (pipelineState?.pipelineRunId) {
      pipelineRunIdRef.current = pipelineState.pipelineRunId;
    }
  }, [pipelineState?.pipelineRunId]);

  useEffect(() => {
    // W1 (44-01) — under SSE this WS reconnect_pipeline frame is redundant:
    // useRunStream reconnects natively and replays from Last-Event-ID. Guard it
    // to a no-op while SSE is the active transport (its full removal + the
    // ConnectionStatus migration is W4's useWebSocket deletion). Flag-OFF path
    // is unchanged.
    if (runConnection.enabled) return;
    if (connectionStatus !== "connected") return;
    // If a pipeline was running when we disconnected, reconnect to it.
    // Check both in-memory state and sessionStorage (handles tab close/reopen).
    const runId = pipelineRunIdRef.current
      ?? activePipelineRunIdRef.current
      ?? (typeof window !== "undefined" ? sessionStorage.getItem("active_pipeline_run_id") : null);

    const isRunning = pipelineState?.isRunning
      || (typeof window !== "undefined" && !!sessionStorage.getItem("active_pipeline_run_id"));

    if (runId && isRunning && websocketSend) {
      // Phase 12 (RESUME-03) — send the last-received seq as after_seq so the
      // durable replay (12-03) delivers exactly the missed tail. 0 on a fresh
      // load (no recorded seq) ⇒ the backend replays the full tail from 0; a
      // legacy client that never recorded a seq is byte-identical (after_seq 0).
      const afterSeq = getLastSeq ? getLastSeq() : 0;
      websocketSend(JSON.stringify({
        type: "reconnect_pipeline",
        pipeline_run_id: runId,
        after_seq: afterSeq,
      }));
      // If we recovered from sessionStorage but pipelineState doesn't know,
      // at least update the run ID ref so future reconnects work
      if (!pipelineRunIdRef.current) {
        pipelineRunIdRef.current = runId;
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionStatus]);

  // When pendingOdProtoParams arrives (set by dashboard/page.tsx after the
  // When pendingOdProtoParams arrives, immediately start the od_prototype pipeline.
  // Phase 2 (Universal Engine): the legacy generate_questions pre-flight is
  // retired. We fire run_pipeline straight away; the Deep_Planner_Agent will
  // emit questionnaire_ready mid-run if it needs clarification (CLARIFY_REQUIRED).
  useEffect(() => {
    if (!pendingOdProtoParams) return;
    setMainView("execution");
    setWorkflowType("prototype");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    if (onClearPendingOdProto) onClearPendingOdProto();

    const extraParams = {
      template_id: pendingOdProtoParams.templateId,
      design_system_id: pendingOdProtoParams.designSystemId,
      ...(pendingOdProtoParams.customDsBody ? { custom_design_system_body: pendingOdProtoParams.customDsBody } : {}),
      ...(pendingOdProtoParams.customTemplateBody ? { custom_template_body: pendingOdProtoParams.customTemplateBody } : {}),
      discovery: pendingOdProtoParams.discovery,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pendingOdProtoParams.sourceRunId ? { source_workflow_run_id: pendingOdProtoParams.sourceRunId } : {}),
      // Phase 6: per-run gate selection. Only when explicitly provided (touched);
      // an empty array is a valid "no gates" choice, so guard on presence (!== undefined),
      // NOT truthiness. Absent ⇒ omitted ⇒ backend static default (byte-identical).
      ...(pendingOdProtoParams.gateAgentIds !== undefined ? { gate_agent_ids: pendingOdProtoParams.gateAgentIds } : {}),
      // Advanced agent config from wizard AgentsPopup
      ...(pendingOdProtoParams.modelOverrides && Object.keys(pendingOdProtoParams.modelOverrides).length > 0 ? { model_overrides: pendingOdProtoParams.modelOverrides } : {}),
      ...(pendingOdProtoParams.selections && Object.keys(pendingOdProtoParams.selections).length > 0 ? { selections: pendingOdProtoParams.selections } : {}),
      ...(pendingOdProtoParams.images && pendingOdProtoParams.images.length > 0 ? { images: pendingOdProtoParams.images } : {}),
    };

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      addRunningNotification(notifId, "prototype", pendingOdProtoParams.brief.slice(0, 60), 0);
      const agentIds = pendingOdProtoParams.agentIds ?? [];
      if (connectionStatus === "connected") {
        onStartPipeline("od_prototype" as WorkflowType, pendingOdProtoParams.brief, agentIds, attachedSkills, attachedHooks, extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: "od_prototype" as WorkflowType,
          message: pendingOdProtoParams.brief,
          agentIds,
          extraParams,
        };
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOdProtoParams]);

  // When pendingOdPptParams arrives, immediately start the od_ppt pipeline.
  // Phase 2 (Universal Engine): the legacy generate_questions pre-flight is
  // retired. We fire run_pipeline straight away; the Deep_Planner_Agent will
  // emit questionnaire_ready mid-run if it needs clarification (CLARIFY_REQUIRED).
  useEffect(() => {
    if (!pendingOdPptParams) return;
    setMainView("execution");
    setWorkflowType("ppt");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    if (onClearPendingOdPpt) onClearPendingOdPpt();

    const extraParams = {
      template_id: pendingOdPptParams.templateId,
      ...(pendingOdPptParams.designSystemId ? { design_system_id: pendingOdPptParams.designSystemId } : {}),
      ...(pendingOdPptParams.customDsBody ? { custom_design_system_body: pendingOdPptParams.customDsBody } : {}),
      ...(pendingOdPptParams.customTemplateBody ? { custom_template_body: pendingOdPptParams.customTemplateBody } : {}),
      discovery: pendingOdPptParams.discovery,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pendingOdPptParams.sourceRunId ? { source_workflow_run_id: pendingOdPptParams.sourceRunId } : {}),
      // Phase 6: per-run gate selection. Only when explicitly provided (touched);
      // empty array = valid "no gates" → guard on presence, not truthiness.
      ...(pendingOdPptParams.gateAgentIds !== undefined ? { gate_agent_ids: pendingOdPptParams.gateAgentIds } : {}),
      // Advanced agent config from wizard AgentsPopup
      ...(pendingOdPptParams.modelOverrides && Object.keys(pendingOdPptParams.modelOverrides).length > 0 ? { model_overrides: pendingOdPptParams.modelOverrides } : {}),
      ...(pendingOdPptParams.selections && Object.keys(pendingOdPptParams.selections).length > 0 ? { selections: pendingOdPptParams.selections } : {}),
      ...(pendingOdPptParams.images && pendingOdPptParams.images.length > 0 ? { images: pendingOdPptParams.images } : {}),
    };

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      addRunningNotification(notifId, "ppt", pendingOdPptParams.brief.slice(0, 60), 0);
      const agentIds = pendingOdPptParams.agentIds ?? [];
      if (connectionStatus === "connected") {
        onStartPipeline("od_ppt" as WorkflowType, pendingOdPptParams.brief, agentIds, attachedSkills, attachedHooks, extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: "od_ppt" as WorkflowType,
          message: pendingOdPptParams.brief,
          agentIds,
          extraParams,
        };
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOdPptParams]);

  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — a saved workflow carries a persisted
  // composition (`agent_ids` + `model_overrides`) that `onSelectFeature` (a bare
  // WorkflowType) cannot express. We stash it here and thread it into IdeaInputPage
  // as the launch-preload seeds. Cleared on a normal select so a non-saved launch
  // starts from the empty filter (no stale seed bleed — T-21-12).
  const [savedComposition, setSavedComposition] = useState<{
    agentIds: string[];
    modelOverrides: Record<string, string>;
    selections: Record<string, Record<string, unknown>>;
    brief?: string;
    gateAgentIds?: string[];
    // 41-04 — edit-from-My-Workflows carries the saved name/description into the
    // full-page Composer (mainView='composer') so it mounts PRE-LOADED.
    name?: string;
    description?: string;
  } | null>(null);

  // Fused Home (SHELL-02 SC-1) — the launcher-brief captured on the home landing,
  // and the pending brief handed to the input view for the generic launch path.
  const [homeBrief, setHomeBrief] = useState("");
  const [pendingHomeBrief, setPendingHomeBrief] = useState<string | undefined>(undefined);

  // Navigate from Home to Input page — EXCEPT the custom-compose entry, which
  // (41-04, D-CMP-ENTRY) opens the full-page Composer surface (mainView='composer')
  // fresh instead of the brief/input view. All other deliverable types keep the
  // existing home→input seam unchanged.
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    setSavedComposition(null);
    setWorkflowType(type);
    setMainView(type === ("custom" as WorkflowType) ? "composer" : "input");
  }, []);

  // Fused Home launcher: carry the typed brief into the input view, then reuse the
  // existing home→input seam. Wizard-routed types (prototype/ppt/requiresWizard) are
  // intercepted INSIDE HomeLaunchGrid before this runs, so they keep their own brief
  // entry. SC-001: keyed on the generic WorkflowType, never a workflow-name branch.
  const handleHomeSelectFeature = useCallback((type: WorkflowType) => {
    setPendingHomeBrief(homeBrief.trim() || undefined);
    handleSelectFeature(type);
  }, [homeBrief, handleSelectFeature]);

  // Launch a saved workflow — mirrors handleSelectFeature but carries the saved
  // composition into state so IdeaInputPage mounts PRE-LOADED. Run then flows
  // UNCHANGED through handleRunPipeline → useWorkflow.startPipeline (which already
  // sends agent_ids + merges model_overrides) → re-validated server-side at launch
  // (SC-001: pure-data replay, no engine/run-path edit, no `if saved` fork).
  const handleLaunchSaved = useCallback((saved: UserWorkflowSummary) => {
    // Fused Home: a saved-workflow launch owns its own preload (initialInput via
    // savedComposition.brief); clear any stale home-launcher brief so it can't leak.
    setPendingHomeBrief(undefined);
    // WR-01: carry the persisted Advanced-lever selections so the launched saved
    // workflow re-loads AND re-sends them (previously selections never reached launch).

    // For PPT and Prototype saved workflows, extract _wizard config and route
    // directly to the wizard page (restoring templateId, designSystemId, brief, etc.)
    if (saved.base_pipeline_type === "od_ppt" || saved.base_pipeline_type === "ppt") {
      const wizard = (saved.selections?._wizard ?? {}) as Record<string, unknown>;
      const draft: Record<string, unknown> = {
        templateId: wizard.templateId ?? null,
        designSystemId: wizard.designSystemId ?? null,
        brief: wizard.brief ?? "",
        ...(wizard.customDsBody ? { customDsBody: wizard.customDsBody } : {}),
        ...(wizard.customTemplateBody ? { customTemplateBody: wizard.customTemplateBody } : {}),
        ...(wizard.gateAgentIds !== undefined ? { gateAgentIds: wizard.gateAgentIds } : {}),
        ...(saved.model_overrides && Object.keys(saved.model_overrides).length > 0 ? { modelOverrides: saved.model_overrides } : {}),
        // Pass selections (without _wizard key) so AgentsPopup can restore them
        ...(saved.selections && Object.keys(saved.selections).filter(k => k !== "_wizard").length > 0
          ? { selections: Object.fromEntries(Object.entries(saved.selections).filter(([k]) => k !== "_wizard")) }
          : {}),
        agentIds: saved.agent_ids,
      };
      sessionStorage.setItem("ppt.draft", JSON.stringify(draft));
      router.push("/workflow/create?mode=ppt");
      return;
    }

    if (saved.base_pipeline_type === "od_prototype" || saved.base_pipeline_type === "prototype") {
      const wizard = (saved.selections?._wizard ?? {}) as Record<string, unknown>;
      const draft: Record<string, unknown> = {
        templateId: wizard.templateId ?? null,
        designSystemId: wizard.designSystemId ?? null,
        brief: wizard.brief ?? "",
        ...(wizard.customDsBody ? { customDsBody: wizard.customDsBody } : {}),
        ...(wizard.customTemplateBody ? { customTemplateBody: wizard.customTemplateBody } : {}),
        ...(wizard.gateAgentIds !== undefined ? { gateAgentIds: wizard.gateAgentIds } : {}),
        ...(saved.model_overrides && Object.keys(saved.model_overrides).length > 0 ? { modelOverrides: saved.model_overrides } : {}),
        // Pass selections (without _wizard key) so AgentsPopup can restore them
        ...(saved.selections && Object.keys(saved.selections).filter(k => k !== "_wizard").length > 0
          ? { selections: Object.fromEntries(Object.entries(saved.selections).filter(([k]) => k !== "_wizard")) }
          : {}),
        agentIds: saved.agent_ids,
      };
      sessionStorage.setItem("prototype.draft", JSON.stringify(draft));
      router.push("/workflow/create?mode=prototype");
      return;
    }

    setSavedComposition({
      agentIds: saved.agent_ids,
      modelOverrides: saved.model_overrides ?? {},
      selections: saved.selections ?? {},
      brief: typeof saved.selections?._wizard?.brief === "string"
        ? (saved.selections._wizard.brief as string)
        : undefined,
      gateAgentIds: Array.isArray(saved.selections?._wizard?.gateAgentIds)
        ? (saved.selections!._wizard!.gateAgentIds as string[])
        : undefined,
      name: saved.name,
      description: saved.description ?? undefined,
    });
    setWorkflowType(saved.base_pipeline_type as WorkflowType);
    // 41-04 — edit-from-My-Workflows opens the full-page Composer PRE-LOADED with
    // the saved agents + selections (D-CMP-ENTRY). The composer's per-run Run wiring
    // lands in 41-06; until then this is the authoring/edit entry for saved workflows.
    setMainView("composer");
  }, [router]);

  // Run the pipeline from Input page — triggers questionnaire first
  // `resolvedType` is the concrete pipeline the backend will dispatch. For
  // most workflows it matches the parent state; for the `migration` meta
  // type the IdeaInputPage resolves it to a real sub-pipeline (Mulesoft→
  // Spring Boot or .NET→Azure) before invoking us. We sync `workflowType`
  // here so downstream effects (chaining, sidebar labels, completion
  // tracking) see the real pipeline.
  const handleRunPipeline = useCallback((message: string, agentIds: string[], resolvedType: WorkflowType, extraParams?: Record<string, unknown>) => {
    setWorkflowInput(message);
    setMainView("execution");
    setWorkflowType(resolvedType);

    // Reset previous pipeline state so left panel clears
    if (onResetPipeline) onResetPipeline();

    // Phase 2 (Universal Engine): start the pipeline directly. The Deep_Planner_Agent
    // runs first and gates execution; the clarify questionnaire now appears mid-run
    // ONLY when the planner issues CLARIFY_REQUIRED (via the `questionnaire_ready`
    // event). The legacy `generate_questions` pre-step and its 15s timeout are retired.
    //
    // `extraParams` (Phase 6) carries the per-run Human-review gate selection as
    // `{ gate_agent_ids: string[] }` — but ONLY when the user touched the
    // Review-gates section in IdeaInputPage. When undefined we pass nothing, so
    // the run_pipeline payload is byte-identical to before this feature.
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // Strip injected context/revision markers before using as notification title
      // so the panel never shows raw "=== EXISTING PROTOTYPE HTML ===" text.
      const parsedMsg = parseRunInput(message);
      const notifTitle = (parsedMsg.revisionInstruction ?? parsedMsg.brief ?? message).slice(0, 60);
      addRunningNotification(notifId, resolvedType, notifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(resolvedType, message, agentIds, attachedSkills, attachedHooks, extraParams);
      } else {
        pendingStartOnConnectRef.current = { type: resolvedType, message, agentIds, extraParams };
      }
    }
  }, [onStartPipeline, onResetPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Go back to home
  const handleGoHome = useCallback(() => {
    setMainView("home");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (!isPipelineRunning && onResetPipeline) onResetPipeline();
  }, [onResetPipeline, isPipelineRunning]);

  // Chain to another pipeline using previous output as context
  const handleChainPipeline = useCallback(async (nextType: WorkflowType) => {
    // Check if this chain target requires a wizard (prototype, ppt)
    const option = CHAIN_OPTIONS.find((o) => o.type === nextType);

    // Find the source run ID for context fetching
    // Match on the BASE pipeline type so a completed `od_ppt`/`od_prototype`
    // run is found when chaining from the normalized `ppt`/`prototype` state
    // (baseWorkflowType maps od_ppt→ppt, od_prototype→prototype, and strips
    // the _revision suffix). Without this, the source run is never found and
    // getChainContext is skipped, so the next pipeline starts with no context.
    const sourceRun = recentRuns?.find(
      r => baseWorkflowType(r.type as WorkflowType) === baseWorkflowType(workflowType) && r.status === "completed"
    );
    const sourceRunId = sourceRun?.id;

    if (option?.requiresWizard && option.wizardPath) {
      // Store the current brief so the wizard can pre-fill it
      const cleanBrief = workflowInput.split("\n\n===")[0].trim();
      sessionStorage.setItem(CHAIN_BRIEF_KEY, cleanBrief);
      sessionStorage.setItem(CHAIN_FROM_KEY, workflowType);
      if (sourceRunId) {
        sessionStorage.setItem(CHAIN_SOURCE_RUN_ID_KEY, sourceRunId);
        // Also store the structured context so the wizard can pass it
        // as part of the brief when the pipeline fires
        try {
          const token = getToken();
          if (token) {
            const ctx = await getChainContext(token, sourceRunId);
            if (ctx.context_block) {
              sessionStorage.setItem("chain.context_block", ctx.context_block);
            }
          }
        } catch { /* non-fatal */ }
      } else {
        sessionStorage.removeItem(CHAIN_SOURCE_RUN_ID_KEY);
        sessionStorage.removeItem("chain.context_block");
      }
      router.push(option.wizardPath);
      return;
    }

    setWorkflowType(nextType);

    // Fetch structured context from the source run
    let contextBlock = "";
    if (sourceRunId) {
      try {
        const token = getToken();
        if (token) {
          const ctx = await getChainContext(token, sourceRunId);
          contextBlock = ctx.context_block;
        }
      } catch {
        // Fallback: use the old approach
        const isHtmlOutput = workflowType === "od_ppt" || workflowType === "od_ppt_revision" ||
          workflowType === "od_prototype" || workflowType === "prototype" || workflowType === "prototype_revision";
        contextBlock = isHtmlOutput
          ? `=== CONTEXT FROM PREVIOUS PIPELINE (${workflowType}) ===\n[${workflowType} output — HTML file]\n=== END PREVIOUS CONTEXT ===`
          : `=== CONTEXT FROM PREVIOUS PIPELINE (${workflowType}) ===\n${lastPipelineOutput.slice(0, 4000)}\n=== END PREVIOUS CONTEXT ===`;
      }
    }

    // Workstream C1 (INV-12): the single parser owns marker extraction. For a
    // plain brief -> its clean brief; for a revision blob (starts with ===) ->
    // the revision instruction (parseRunInput returns brief='' for a pure blob,
    // so the empty-string fallback is subsumed).
    const parsedChain = parseRunInput(workflowInput);
    const chainBrief = parsedChain.revisionInstruction ?? parsedChain.brief;
    const enrichedInput = contextBlock
      ? `${chainBrief}\n\n${contextBlock}`.trim()
      : chainBrief;

    if (onResetPipeline) onResetPipeline();
    setWorkflowInput(enrichedInput);

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // chainBrief is the stripped user brief (no markers); use it as the
      // notification title so the panel never shows raw context block text.
      const chainNotifTitle = (chainBrief || enrichedInput).slice(0, 60);
      addRunningNotification(notifId, nextType, chainNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(nextType, enrichedInput, [], attachedSkills, attachedHooks);
      } else {
        pendingStartOnConnectRef.current = { type: nextType, message: enrichedInput, agentIds: [] };
      }
    }
  }, [workflowType, workflowInput, lastPipelineOutput, recentRuns, onStartPipeline, onResetPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Chain to another pipeline starting from a historical run. The user is
  // viewing a past WorkflowRun in the history view; they pick a next
  // pipeline. We must use the historical run's input/output for the
  // enrichment (NOT the current dashboard state, which is stale for the
  // run they just opened from history). After dispatching we switch to
  // the execution view so the new pipeline shows the agent progress.
  const handleChainFromHistory = useCallback(async (run: WorkflowRun, nextType: WorkflowType) => {
    const option = CHAIN_OPTIONS.find((o) => o.type === nextType);
    if (option?.requiresWizard && option.wizardPath) {
      const cleanBrief = (run.input || "").split("\n\n===")[0].trim();
      sessionStorage.setItem(CHAIN_BRIEF_KEY, cleanBrief);
      sessionStorage.setItem(CHAIN_FROM_KEY, run.type);
      if (run.id) {
        sessionStorage.setItem(CHAIN_SOURCE_RUN_ID_KEY, run.id);
        try {
          const token = getToken();
          if (token) {
            const ctx = await getChainContext(token, run.id);
            if (ctx.context_block) {
              sessionStorage.setItem("chain.context_block", ctx.context_block);
            }
          }
        } catch { /* non-fatal */ }
      } else {
        sessionStorage.removeItem(CHAIN_SOURCE_RUN_ID_KEY);
        sessionStorage.removeItem("chain.context_block");
      }
      router.push(option.wizardPath);
      return;
    }

    // Fetch structured context from the source run
    let contextBlock = "";
    try {
      const token = getToken();
      if (token && run.id) {
        const ctx = await getChainContext(token, run.id);
        contextBlock = ctx.context_block;
      }
    } catch {
      // Fallback
      const isHtmlOutput = run.type === "od_ppt" || run.type === "od_ppt_revision" ||
        run.type === "od_prototype" || run.type === "prototype" || run.type === "prototype_revision";
      const baseOutput = isHtmlOutput
        ? `[${run.title || run.type} output — HTML file]`
        : (run.output || "").slice(0, 4000);
      if (baseOutput) {
        contextBlock = `=== CONTEXT FROM PREVIOUS PIPELINE (${run.type}) ===\n${baseOutput}\n=== END PREVIOUS CONTEXT ===`;
      }
    }

    // Workstream C1 (INV-12): same single-parser rewire as handleChainPipeline.
    const parsedHistory = parseRunInput(run.input || "");
    const historyBrief = parsedHistory.revisionInstruction ?? parsedHistory.brief;
    const enrichedInput = contextBlock ? `${historyBrief}\n\n${contextBlock}`.trim() : historyBrief;

    setWorkflowType(nextType);
    setWorkflowInput(enrichedInput);
    setLastPipelineOutput(run.output || "");
    setCompletedPipelineTypes((prev) =>
      prev.includes(run.type as WorkflowType) ? prev : [...prev, run.type as WorkflowType],
    );
    setMainView("execution");
    if (onResetPipeline) onResetPipeline();

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // historyBrief is the stripped user brief (no markers); use it so the
      // panel never shows raw context block text for history-chained runs.
      const historyNotifTitle = (historyBrief || enrichedInput).slice(0, 60);
      addRunningNotification(notifId, nextType, historyNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(nextType, enrichedInput, [], attachedSkills, attachedHooks);
      } else {
        pendingStartOnConnectRef.current = { type: nextType, message: enrichedInput, agentIds: [] };
      }
    }
  }, [websocketSend, onStartPipeline, onResetPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Handle questionnaire answers.
  //
  // Phase 2 (Universal Engine): when the questionnaire was raised mid-run by the
  // Clarify_Engine (CLARIFY_REQUIRED gate), `activePipelineRunId` is set — we send
  // `submit_questionnaire` to resume the paused run from the gate (no restart).
  //
  // Legacy path (no active run id): build an enriched message and start the
  // pipeline — retained for any flow still pre-questioning.
  const handleQuestionnaireSubmit = useCallback((answers: Record<string, string[]>, freeformInput: string) => {
    // ── New flow: resume a paused run ────────────────────────────────────
    if (activePipelineRunId && onSubmitQuestionnaire) {
      const responses: Array<{ question_id: string; answer: string }> = [];
      questionnaireQuestions.forEach((q) => {
        const selected = answers[q.id];
        if (selected && selected.length > 0) {
          responses.push({ question_id: q.id, answer: selected.join(", ") });
        }
      });
      if (freeformInput) {
        responses.push({ question_id: "freeform", answer: freeformInput });
      }
      // Workstream C1 (POR §6.5): fold the answered Q&A into run-scoped state
      // BEFORE clearing the panel — order matters, else the round is lost.
      if (onRetainClarifyRound) {
        const round = {
          round: (pipelineState?.clarifications?.length ?? 0) + 1,
          qa: questionnaireQuestions.map((q) => {
            const selected = answers[q.id];
            return {
              question_id: q.id,
              question_text: q.question,
              impact_level: q.impactLevel ?? "",
              answer: selected && selected.length > 0 ? selected.join(", ") : null,
            };
          }),
        };
        onRetainClarifyRound(round);
      }
      setQuestionnaireQuestions([]);
      setQuestionnaireLoading(false);
      onSubmitQuestionnaire(activePipelineRunId, responses);
      return;
    }

    // ── Legacy flow: enrich message + start pipeline ─────────────────────
    if (!pendingPipelineRun) return;

    let enrichedMessage = pendingPipelineRun.message;
    const answerLines: string[] = [];
    questionnaireQuestions.forEach((q) => {
      const selected = answers[q.id];
      if (selected && selected.length > 0) {
        answerLines.push(`- ${q.question}: ${selected.join(", ")}`);
      }
    });
    if (freeformInput) {
      answerLines.push(`- Additional notes: ${freeformInput}`);
    }
    if (answerLines.length > 0) {
      enrichedMessage = `${pendingPipelineRun.message}\n\n=== USER PREFERENCES ===\n${answerLines.join("\n")}\n=== END PREFERENCES ===`;
    }

    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      const parsedPending = parseRunInput(pendingPipelineRun.message);
      const pendingNotifTitle = (parsedPending.revisionInstruction ?? parsedPending.brief ?? pendingPipelineRun.message).slice(0, 60);
      addRunningNotification(notifId, pendingPipelineRun.type, pendingNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(pendingPipelineRun.type, enrichedMessage, pendingPipelineRun.agentIds, attachedSkills, attachedHooks, pendingPipelineRun.extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: pendingPipelineRun.type,
          message: enrichedMessage,
          agentIds: pendingPipelineRun.agentIds,
          extraParams: pendingPipelineRun.extraParams,
        };
      }
    }
  }, [activePipelineRunId, onSubmitQuestionnaire, onRetainClarifyRound, pipelineState, pendingPipelineRun, questionnaireQuestions, onStartPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Skip questionnaire.
  // New flow (ISS-027): submit empty answers WITH skip_clarification=true so the
  // backend ClarifyEngine force-proceeds immediately and runs with best-available
  // context — instead of re-asking the same questions for up to 3 rounds (which
  // an empty submit alone triggered, contradicting the "run directly" label).
  // Legacy flow: start the pipeline with the un-enriched message.
  const handleQuestionnaireSkip = useCallback(() => {
    if (activePipelineRunId && onSubmitQuestionnaire) {
      setQuestionnaireQuestions([]);
      setQuestionnaireLoading(false);
      onSubmitQuestionnaire(activePipelineRunId, [], true);
      return;
    }

    if (!pendingPipelineRun) return;
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      const parsedSkip = parseRunInput(pendingPipelineRun.message);
      const skipNotifTitle = (parsedSkip.revisionInstruction ?? parsedSkip.brief ?? pendingPipelineRun.message).slice(0, 60);
      addRunningNotification(notifId, pendingPipelineRun.type, skipNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(pendingPipelineRun.type, pendingPipelineRun.message, pendingPipelineRun.agentIds, attachedSkills, attachedHooks, pendingPipelineRun.extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: pendingPipelineRun.type,
          message: pendingPipelineRun.message,
          agentIds: pendingPipelineRun.agentIds,
          extraParams: pendingPipelineRun.extraParams,
        };
      }
    }
  }, [activePipelineRunId, onSubmitQuestionnaire, pendingPipelineRun, onStartPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Cancel the active pipeline from the clarification step and navigate to dashboard.
  // Two-step sequence: submit_questionnaire(skip=true) unblocks the gate, then
  // cancel_pipeline terminates the now-running pipeline. All state resets to initial.
  // KAN-90: "Cancel Workflow" button in QuestionnairePanel confirmation dialog.
  const handleCancelWorkflow = useCallback(() => {
    // Set the flag BEFORE navigating so the isRunning effect doesn't fight us
    cancelNavigatingHomeRef.current = true;
    // Navigate home and reset state IMMEDIATELY — before any async work
    setMainView("home");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onResetPipeline) onResetPipeline();

    if (activePipelineRunId && onSubmitQuestionnaire) {
      // Step 1: unblock the clarify gate (fire and forget)
      onSubmitQuestionnaire(activePipelineRunId, [], true);
      // Step 2: cancel the now-unblocked pipeline after a short delay
      setTimeout(() => {
        if (websocketSend) {
          websocketSend(JSON.stringify({ type: "cancel_pipeline" }));
        }
      }, 200);
    }
  }, [activePipelineRunId, onSubmitQuestionnaire, websocketSend, onResetPipeline]);

  // Handle "Reject & cancel pipeline" from the ReviewGatePanel.
  // KAN-95: the raw onRejectReview prop (from page.tsx) only sends the WS message
  // and clears reviewGateData — it does not navigate. This wrapper sets
  // cancelNavigatingHomeRef first (so the pipelineState.isRunning effect doesn't
  // snap the view back to "execution"), resets pipeline state, and navigates home
  // before delegating to the prop for the actual WS send.
  const handleRejectReview = useCallback((gateKey: string) => {
    // Set the guard BEFORE any state changes so the isRunning effect can't fight us
    cancelNavigatingHomeRef.current = true;
    // Navigate home and reset state immediately
    setMainView("home");
    if (onResetPipeline) onResetPipeline();
    // Delegate to page.tsx for the WS send + reviewGateData clear
    if (onRejectReview) onRejectReview(gateKey);
  }, [onRejectReview, onResetPipeline]);

  // Header navigation — free navigation even while pipeline runs
  const handleNavigate = useCallback((page: "home" | "library" | "history" | "settings" | "analytics" | "catalog" | "saved-workflows") => {
    setMainView(page as MainView);
  }, []);

  // ─── Phase 31 (CHATUI-01/02/03) — run chat lane derivations ──────────────────
  // The workflowType-selected revise handler (the SAME expression the left-column
  // AgentProgressPanel used before the lane absorbed it). Undefined when the
  // current output type has no revise path.
  const activeReviseHandler =
    (workflowType === "ppt" || workflowType === "ppt_revision" || workflowType === "od_ppt") ? handleRevisePpt :
    (workflowType === "user_stories" || workflowType === "user_stories_revision") ? handleReviseUserStory :
    (workflowType === "prototype" || workflowType === "prototype_revision" || !!prototypeContent) ? handleRevisePrototype :
    (workflowType === "app_builder" || workflowType === "app_builder_revision") ? handleReviseAppBuilder :
    undefined;

  // ─── 43-02 (A.1 CRUX) — Concierge send seam + confirm round-trip ─────────────
  // The lane's send seam: the options-capable `onRunChatSend` (POST /messages)
  // when supplied, else the legacy `onSendMessage`. A settled-run ASK folds
  // `{ concierge: true }` here; a confirm chip folds the held proposal's
  // `{ concierge: true, confirm_proposal: { channel, params } }`. Per LOCK-B the
  // WS transport does not deliver the concierge fields to the Concierge until the
  // Part-C SSE cutover — this wires the DECISION + payload shape, not a live flip.
  const runChatSend = useCallback(
    (
      text: string,
      attachments?: import("@/types/index").ChatAttachment[],
      options?: SendMessageOptions,
    ) => {
      if (onRunChatSend) onRunChatSend(text, attachments, options);
      else onSendMessage(text);
    },
    [onRunChatSend, onSendMessage],
  );

  // Confirm a held consequential Concierge proposal: replay the confirm turn
  // through the SAME send seam, carrying the durable proposal's channel + params
  // verbatim (the backend H1 fence — 43-01 — locates its durable pending row and
  // disposes from THAT, never from this client body). Reject simply dismisses.
  const handleConfirmProposal = useCallback(
    (p: LaneProposal) => {
      runChatSend("", [], {
        concierge: true,
        confirm_proposal: { channel: p.channel, params: p.params },
      });
    },
    [runChatSend],
  );

  // Held Concierge proposals surface. Empty until the Part-C SSE transport
  // (43-06) delivers `concierge_proposal` holds onto the transcript-adjacent
  // state; the confirm chip + handleConfirmProposal are wired now so that flip is
  // a data change, not a wiring change (LOCK-B — no live transport in this plan).
  const runConciergeProposals = RUN_CONCIERGE_PROPOSALS;

  // Reject dismisses a held proposal WITHOUT executing anything (T-33-04-01).
  // No local proposal state exists yet (the holds arrive with the Part-C
  // transport), so this is a safe no-op until then.
  const handleRejectProposal = useCallback((_id: string) => {
    /* dismiss — nothing executes; real removal lands with the 43-06 holds surface */
  }, []);

  // Compaction has no backend trigger wired yet; the FE only ever SIGNALS (it
  // never compresses, D-08). A no-op-safe handler until the Part-C trigger lands
  // — deliberately NOT an invented backend call.
  const handleCompact = useCallback(() => {
    /* no-op: compaction trigger arrives with the Part-C transport (43-06) */
  }, []);

  // Stop (absorbed) — the SAME cooperative cancel the AgentProgressPanel fired.
  // The pipeline_cancelled WS event drives the state reset (no eager onReset).
  const handleStopPipeline = useCallback(() => {
    if (websocketSend) websocketSend(JSON.stringify({ type: "cancel_pipeline" }));
  }, [websocketSend]);

  // GENERIC live-run state that drives the D-12 composer mode (SC-001 — never a
  // workflow name). Priority: gate > clarify > building > terminal-failure >
  // complete (has deliverable) > idle.
  const laneHasDeliverable = !!(userStoryContent || pptContent || prototypeContent || genericDeliverable?.content);
  const laneClarifyOpen = questionnaireQuestions.length > 0 && (!!pendingPipelineRun || !!activePipelineRunId);
  // Terminal keys off the GENERIC plan-05 markers (cancelled / failed /
  // degraded) — never a workflow name (SC-001, LIVE-STATE-CONTRACT §1).
  const runLaneState: RunLaneState =
    reviewGateData && isPipelineRunning ? "gate" :
    laneClarifyOpen ? "clarify" :
    isPipelineRunning ? "building" :
    (pipelineState?.failed || pipelineState?.cancelled || pipelineState?.degraded) ? "terminal" :
    laneHasDeliverable ? "complete" :
    "idle";

  // Phase 39 (RUNUI-06) — the live run title for the lane header. Prefer the
  // clean backend-generated title of the active run (recentRuns[0], the same
  // source the notification title uses at :543), else fall back to the submitted
  // brief; the lane itself falls back further to the first user turn.
  const latestRunTitle = recentRuns?.[0]?.title;
  const runHeaderTitle =
    latestRunTitle && latestRunTitle !== "Untitled" ? latestRunTitle : submittedBrief;

  // The gate the lane surfaces (mirrors the Steps ReviewGatePanel props). The
  // KAN-101 spec-loop affordance + approve relabel are mapped off the declared
  // reviewGateData flags (SC-001) — mirrors the redoable mapping, no literal.
  const laneGate: GateContext | undefined = reviewGateData
    ? {
        agentId: reviewGateData.agentId,
        agentName: reviewGateData.agentName,
        output: reviewGateData.output,
        gateKey: reviewGateData.gateKey,
        redoable: reviewGateData.redoable,
        updateSpecsEligible: reviewGateData.updateSpecsEligible,
        approveLabel: reviewGateData.artifactKind
          ? `Approve the ${reviewGateData.artifactKind.replace(/_/g, " ")}`
          : undefined,
      }
    : undefined;

  // Clarify quick-actions → the SAME resume path the QuestionnairePanel uses.
  // Maps the lane's ClarifyResponse[] onto the (answers, freeform) submit.
  const handleLaneSubmitAnswers = useCallback(
    (responses: ClarifyResponse[]) => {
      const answers: Record<string, string[]> = {};
      let freeform = "";
      for (const r of responses) {
        if (r.question_id === "freeform") {
          freeform = r.answer;
          continue;
        }
        answers[r.question_id] = r.answer ? [r.answer] : [];
      }
      handleQuestionnaireSubmit(answers, freeform);
    },
    [handleQuestionnaireSubmit],
  );

  // Suggested next steps (absorbed) — the chainable workflows as generic chips.
  const laneSuggestions: LaneSuggestion[] = canChainFrom(workflowType)
    ? CHAIN_OPTIONS
        .filter((o) => baseWorkflowType(o.type) !== baseWorkflowType(workflowType))
        .map((o) => ({ id: o.type, label: o.label }))
    : [];
  const handleLaneSuggestion = useCallback(
    (id: string) => { handleChainPipeline(id as WorkflowType); },
    [handleChainPipeline],
  );

  // Map mainView to header page type
  const headerPage = mainView === "library" ? "library" :
    mainView === "catalog" ? "catalog" :
    mainView === "history" ? "history" :
    mainView === "settings" ? "history" :
    mainView === "saved-workflows" ? "saved-workflows" :
    mainView === "input" ? "workflow" :
    mainView === "execution" ? "execution" : "home";

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden bg-surface-paper">
      {/* Connection status banner */}
      <AnimatePresence>
        {connectionStatus === "reconnecting" && (
          <motion.div
            initial={{ y: -40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -40, opacity: 0 }}
            className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-yellow-600/90 px-4 py-2 text-xs text-white backdrop-blur-sm"
          >
            <RefreshCw className="h-3 w-3 animate-spin" />
            Reconnecting...
          </motion.div>
        )}
        {connectionStatus === "failed" && (
          <motion.div
            initial={{ y: -40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -40, opacity: 0 }}
            className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-red-600/90 px-4 py-2 text-xs text-white backdrop-blur-sm"
          >
            <WifiOff className="h-3 w-3" />
            Connection lost.
            <button onClick={onReconnect} className="ml-1 underline hover:no-underline">Reconnect</button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Global Header — visible on all pages */}
      <AppHeader
        currentPage={headerPage}
        onNavigate={handleNavigate}
        onLogout={onLogout}
        userTier={userTier}
        userEmail={userEmail}
        isPipelineRunning={isPipelineRunning}
        pipelineType={workflowType}
        pipelineAgentsCompleted={pipelineState?.completedCount ?? 0}
        pipelineAgentsTotal={pipelineState?.agents?.length ?? 0}
        onGoToPipeline={() => setMainView("execution")}
        notifications={notifications}
        unreadCount={unreadCount}
        onMarkAllRead={markAllRead}
        onClearNotifications={clearAll}
        onViewResults={(n) => {
          if (n.status === "running" || n.status === "completed") {
            setMainView("execution");
          } else {
            setMainView("history");
          }
        }}
      />

      {/* Main Content */}
      <div className="flex-1 min-h-0">
        <AnimatePresence mode="wait">
          {/* HOME — the data-driven HomeLaunchGrid is the DEFAULT landing
              (UXFIX-03 / D-20). The hardcoded `CreationHub.WORKFLOWS` array no
              longer drives the default home — the catalog sources its rows from
              `GET /api/workflows`, so a brand-new launchable manifest appears
              with zero FE edit (SC-001). This is a re-route, not a new visual:
              the same launch/select wiring (`handleSelectFeature` +
              `handleLaunchSaved`, P21) is preserved. */}
          {mainView === "home" && (
            <motion.div
              key="home"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              {/* FUSED HOME (SHELL-02 SC-1, restyled 40-02) — one landing owned by
                  HomeLaunchGrid: the mock's prompt UNDER the h1 (Attach + Build,
                  no Voice — ND-X), the SC-001 data-driven deliverable card grid,
                  and the live "Jump back in" recents. The prompt state stays here
                  (homeBrief) so it can ride into the launch via pendingHomeBrief;
                  it is threaded down as controlled props. Build carries the brief
                  down the existing launch fork (handleHomeSelectFeature). Wizard-
                  routed types (prototype/ppt) still router.push inside
                  HomeLaunchGrid — the fork is preserved. The `input` view is
                  UNCHANGED and still reachable for the saved-workflow preload path
                  (handleLaunchSaved). Recents deep-link via onSelectWorkflowRun →
                  the execution view. Page-keys stay generic (SC-001/INV-1). */}
              <div className="flex h-full flex-col bg-surface-paper">
                <HomeLaunchGrid
                  onSelectFeature={handleHomeSelectFeature}
                  onLaunchSaved={handleLaunchSaved}
                  userTier={userTier}
                  brief={homeBrief}
                  onBriefChange={setHomeBrief}
                  onBuild={() => handleHomeSelectFeature("custom" as WorkflowType)}
                  onOpenRun={(run) => { onSelectWorkflowRun?.(run); setMainView("execution"); }}
                />
              </div>
            </motion.div>
          )}


          {/* LIBRARY — Agent catalog */}
          {mainView === "library" && (
            <motion.div
              key="library"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <LibraryPage />
            </motion.div>
          )}

          {/* HISTORY — Workflow history */}
          {mainView === "history" && (
            <motion.div
              key="history"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <WorkflowHistory onBack={handleGoHome} onChainPipeline={handleChainFromHistory}
            activeRunId={pipelineState?.pipelineRunId ?? null}
            onViewRunningPipeline={() => setMainView("execution")}
            onReviseUserStory={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("user_stories_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PRODUCT BACKLOG ===\n${content}\n=== END EXISTING BACKLOG ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                // Revision Families (B1): history revisions previously sent NO
                // parent → orphan runs. Thread selectedRun.id so the backend links it.
                onStartPipeline("user_stories_revision", msg, undefined, attachedSkills, attachedHooks, sourceRunId ? { source_workflow_run_id: sourceRunId } : undefined);
              }
            }}
            onRevisePpt={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("ppt_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PRESENTATION CODE ===\n${content}\n=== END EXISTING CODE ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("ppt_revision", msg, undefined, attachedSkills, attachedHooks, sourceRunId ? { source_workflow_run_id: sourceRunId } : undefined);
              }
            }}
            onRevisePrototype={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("prototype_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PROTOTYPE HTML ===\n${content}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("prototype_revision", msg, undefined, attachedSkills, attachedHooks, sourceRunId ? { source_workflow_run_id: sourceRunId } : undefined);
              }
            }}
            onReviseAppBuilder={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("app_builder_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING APP BLUEPRINT ===\n${content.slice(0, 40000)}\n=== END EXISTING BLUEPRINT ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("app_builder_revision", msg, undefined, attachedSkills, attachedHooks, sourceRunId ? { source_workflow_run_id: sourceRunId } : undefined);
              }
            }}
          />
            </motion.div>
          )}

          {/* SETTINGS — Account settings */}
          {mainView === "settings" && (
            <motion.div
              key="settings"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <AccountSettings onBack={handleGoHome} />
            </motion.div>
          )}

          {/* ANALYTICS */}
          {mainView === "analytics" && (
            <motion.div
              key="analytics"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <AnalyticsPage onBack={handleGoHome} />
            </motion.div>
          )}

          {/* SAVED WORKFLOWS — user's saved custom workflows */}
          {mainView === "saved-workflows" && (
            <motion.div
              key="saved-workflows"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <SavedWorkflowsPage onLaunchSaved={handleLaunchSaved} />
            </motion.div>
          )}

          {/* INPUT — Idea input page */}
          {mainView === "input" && (
            <motion.div
              key="input"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
              className="h-full"
            >
              <IdeaInputPage
                workflowType={workflowType}
                onBack={handleGoHome}
                onRun={handleRunPipeline}
                initialAgentIds={savedComposition?.agentIds}
                initialModelOverrides={savedComposition?.modelOverrides}
                initialSelections={savedComposition?.selections}
                initialInput={savedComposition?.brief ?? pendingHomeBrief}
                initialGateIds={savedComposition?.gateAgentIds}
                // SURF-03 — the backend workflow id whose compiled per-step
                // capabilities the composer surfaces. For a built-in launchable
                // workflow opened from the catalog, `workflowType` IS the workflow id
                // (HomeLaunchGrid launches via `row.id as WorkflowType`); for a saved
                // workflow it is the persisted `base_pipeline_type` (set in
                // handleLaunchSaved). Unknown ids (e.g. `custom`/`migration` meta) 404
                // server-side and the strip simply does not render.
                workflowId={workflowType}
              />
            </motion.div>
          )}

          {/* COMPOSER — full-page custom-workflow authoring surface (41-04).
              ADDITIVE: reached from Home's "Compose a custom workflow" card and
              edit-from-My-Workflows (pre-loaded). Reuses the AgentsPopup shared
              data model + exported sub-components; the modal wrapper is retained
              for the wizard/input inline-edit flow (INV-3). */}
          {mainView === "composer" && (
            <motion.div
              key="composer"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
              className="h-full"
            >
              <ComposerPage
                workflowType={workflowType}
                onBack={handleGoHome}
                // 41-06 (D-05 / D-CMP-RUN) — Run-once launches the composed workflow
                // through the EXISTING onStartPipeline → startPipeline seam, mirroring
                // the revision launch sites (reset → onStartPipeline with the SAME arg
                // convention). `type` is the composer's fixed-at-entry base_pipeline_type
                // ("custom" for the compose entry, ND-AH) — the SAME value Save persists.
                // startPipeline flips pipelineState.isRunning → the surface auto-transitions
                // to mainView='execution'. No new contract / endpoint / fabricated cost (ND-AG).
                onRun={(type, brief, agentIds, extraParams) => {
                  if (onResetPipeline) onResetPipeline();
                  if (onStartPipeline) {
                    onStartPipeline(type, brief, agentIds, attachedSkills, attachedHooks, extraParams);
                  }
                }}
                initialAgentIds={savedComposition?.agentIds}
                initialSelections={
                  savedComposition?.selections
                    ? (Object.fromEntries(
                        Object.entries(savedComposition.selections).filter(
                          ([k]) => k !== "_wizard",
                        ),
                      ) as import("@/components/workflow/AgentsPopup").SelectionsMap)
                    : undefined
                }
                initialName={savedComposition?.name}
                initialDescription={savedComposition?.description}
              />
            </motion.div>
          )}

          {/* EXECUTION — 2-panel layout */}
          {mainView === "execution" && (
            <motion.div
              key="execution"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full flex flex-col md:flex-row"
              style={{ background: "var(--surface-paper)" }}
            >
              {/* Left Panel — Phase 31/32 (CHATUI/SC-4): the RunChatLane is the
                  primary left-column surface. It FULLY ABSORBS the AgentProgressPanel
                  Stop / revise / suggestions controls (D-12 composer-per-state,
                  SC-001 generic) and mounts the plan-05 gate/clarify quick-actions.
                  INV-3 (plan 06): the duplicate AgentProgressPanel run-lane mount is
                  REMOVED — the lane is now the SOLE stop/revise implementation. The
                  AgentProgressPanel component is retained for the plan-08 Steps
                  relocation (its per-agent detail also lives in the Thinking tab).
                  ISS-019: the column is a height-owning flex parent — the lane
                  flexes to remaining space and owns its own scroll; the wave panel
                  is a non-shrinking capped bottom region. */}
              <div className="w-full md:w-[340px] lg:w-[360px] flex-shrink-0 h-[45vh] md:h-full border-b md:border-b-0 md:border-r border-gray-200 flex flex-col overflow-hidden bg-white">
                {/* The run chat lane — primary conversational surface. */}
                <div data-testid="execution-chat-lane" className="flex-1 min-h-0 overflow-hidden">
                  <ErrorBoundary fallbackLabel="RunChatLane">
                    <RunChatLane
                      messages={runChatMessages ?? messages}
                      runState={runLaneState}
                      // 43-02 (A.1 CRUX): the options-capable send seam so a
                      // settled-run ASK can fold { concierge: true } onto the
                      // payload (Concierge answer vs. onRevise revision).
                      sendMessage={runChatSend}
                      isStreaming={isStreaming}
                      streamingContent={streamingContent}
                      pipelineState={pipelineState}
                      onRequestOpenTab={onRequestOpenTab}
                      // Phase 39 (RUNUI-06) — wire the lane run header's 39-01
                      // slots with the real DashboardLayout data: Back-to-history
                      // navigation, the live run title (clean backend title, else
                      // the submitted brief), and the generic run type (SC-001 —
                      // the pipeline_type string, never a workflow-name branch).
                      onBackToHistory={() => setMainView("history")}
                      runTitle={runHeaderTitle}
                      runType={workflowType || pipelineState?.pipeline_type}
                      // Absorbed AgentProgressPanel controls (Stop / revise / suggestions).
                      onStop={handleStopPipeline}
                      onRevise={activeReviseHandler}
                      onRelaunch={handleGoHome}
                      suggestions={laneSuggestions}
                      onSuggestion={handleLaneSuggestion}
                      // 43-02 (A.1 CRUX) — Concierge props wired at the mount.
                      // `proposals` is the held-proposal surface: empty until the
                      // Part-C SSE transport (43-06) delivers concierge_proposal
                      // holds, then the SAME confirm chip fires handleConfirmProposal
                      // (POST { concierge:true, confirm_proposal:{channel,params} }).
                      // Reject dismisses without executing; compaction has no
                      // backend trigger yet (no invented call) — a no-op-safe
                      // onCompact + no explicit availability signal (LOCK-B).
                      proposals={runConciergeProposals}
                      onConfirmProposal={handleConfirmProposal}
                      onRejectProposal={handleRejectProposal}
                      compactAvailable={false}
                      onCompact={handleCompact}
                      // Plan-05 gate quick-actions (KAN-100/101 fences owned by the component).
                      gate={laneGate}
                      onApprove={onApproveReview}
                      onReject={handleRejectReview}
                      onRedo={onRedoReview}
                      onUpdateSpecs={onUpdateSpecsReview}
                      // Plan-05 clarify quick-actions.
                      clarifyQuestions={questionnaireQuestions}
                      onSubmitAnswers={handleLaneSubmitAnswers}
                      onSkipClarify={handleQuestionnaireSkip}
                      // Phase 42-02 (§A2 re-home) — Cancel-Workflow on the inline
                      // clarify, bound to the existing owner-scoped handler (guarded
                      // by an active run, matching the old QuestionnairePanel wiring).
                      onCancelWorkflow={activePipelineRunId ? handleCancelWorkflow : undefined}
                    />
                  </ErrorBoundary>
                </div>
                {/* INV-3 (plan 06): the demoted per-agent AgentProgressPanel mount
                    was REMOVED here — its Stop/revise/suggestions controls are fully
                    absorbed by the RunChatLane composer above, leaving ONE stop/revise
                    implementation. Per-agent detail relocates into Steps in plan 08. */}
                {/* Phase 32 (plan 08 / ISS-019) + Phase 39/42-04: the separate
                    below-the-fold wave-tree panel is gone. The live wave/subagent
                    tree renders inside AgentDetailPanel's inline construction block
                    (Steps drill-down) via the `waves` passthrough to PreviewPanel
                    below. INV-12 — one wave-tree implementation. */}
              </div>

              {/* Right Panel — always PreviewPanel */}
              <div className="flex-1 h-[55vh] md:h-full min-w-0 bg-white rounded-none md:rounded-l-none">
                <ErrorBoundary fallbackLabel="Preview">
                  {/* Phase 42-02 (§A1/§A2/§A3): the three legacy full-screen takeover
                      branches (planning overlay / review-gate / questionnaire panels)
                      were removed from this cascade so PreviewPanel — the sole host of
                      the mock-matching inline Steps clarify/gate/planning surfaces —
                      mounts during those very states. Gate/clarify still flow inline via
                      the laneGate / clarifyQuestions passthrough below. */}
                  <PreviewPanel
                      userStoryContent={userStoryContent || undefined}
                      pptContent={pptContent || undefined}
                      prototypeContent={prototypeContent || undefined}
                      genericDeliverable={genericDeliverable}
                      isStreaming={isStreaming}
                      workflowType={workflowType}
                      rawPipelineType={pipelineState?.pipeline_type || workflowType}
                      pptxCode={pptxCode}
                      onRevisePpt={undefined}
                      onReviseUserStory={undefined}
                      onRevisePrototype={undefined}
                      onReviseAppBuilder={undefined}
                      agentOutputs={
                        pipelineState && pipelineState.agents.length > 0
                          ? pipelineState.agents
                              .filter((a) => a.status === "done" && a.output && a.output.trim().length > 0)
                              .map((a) => ({ name: a.name, role: a.role, output: a.output, agentId: a.id }))
                          : undefined
                      }
                      agents={pipelineState?.agents}
                      pipelineState={pipelineState}
                      reopenedRunStatus={reopenedRunStatus}
                      reopenedFailedAgents={reopenedFailedAgents}
                      reopenedAgentNameById={reopenedAgentNameById}
                      runFamily={runFamily}
                      liveRunId={contentSourceRunId ?? null}
                      runInput={submittedBrief}
                      deepLinkTarget={deepLinkTarget}
                      // Phase 32 (plan 06 → 07/08) — additive gate/clarify passthrough
                      // so a future Steps surface can host the SAME inline gate/clarify
                      // affordances the lane uses. Mirrors the RunChatLane wiring;
                      // pinned to the shared GateContext/clarify shapes (SC-001).
                      laneGate={laneGate}
                      onApproveGate={onApproveReview}
                      onRejectGate={handleRejectReview}
                      onRedoGate={onRedoReview}
                      onUpdateSpecsGate={onUpdateSpecsReview}
                      clarifyQuestions={questionnaireQuestions}
                      onSubmitClarify={handleLaneSubmitAnswers}
                      onSkipClarify={handleQuestionnaireSkip}
                      // Phase 42-02 (§A2 re-home) — Cancel-Workflow on the Steps
                      // inline clarify, bound to the existing owner-scoped handler.
                      onCancelWorkflow={activePipelineRunId ? handleCancelWorkflow : undefined}
                      // Phase 32 (plan 08 / ISS-019) — the live wave/subagent tree
                      // now mounts INSIDE the Steps drill-down (relocated from the
                      // below-the-fold left slot). Forward the assembled groups.
                      waves={waves}
                    />
                </ErrorBoundary>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Completion toasts — bottom-right, non-blocking */}
      <CompletionToast
        toasts={toasts}
        onDismiss={dismissToast}
        onViewResults={(toast) => {
          dismissToast(toast.id);
          setMainView("execution");
        }}
      />
    </div>
  );
}
