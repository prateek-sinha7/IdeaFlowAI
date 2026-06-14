"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import { WifiOff, RefreshCw, Brain, Sparkles, Loader2 } from "lucide-react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { AppHeader } from "./AppHeader";
import { WorkflowCatalog } from "@/components/catalog/WorkflowCatalog";
import { LibraryPage } from "@/components/library/LibraryPage";
import { WorkflowHistory } from "@/components/history/WorkflowHistory";
import { AccountSettings } from "@/components/settings/AccountSettings";
import { AnalyticsPage } from "@/components/analytics/AnalyticsPage";
import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import { AgentProgressPanel } from "@/components/workflow/AgentProgressPanel";
import { WaveTreePanel } from "@/components/workflow/WaveTreePanel";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import { QuestionnairePanel } from "@/components/preview/QuestionnairePanel";
import { ReviewGatePanel } from "@/components/preview/ReviewGatePanel";
import { CompletionToast } from "@/components/ui/CompletionToast";
import type { ToastItem } from "@/components/ui/CompletionToast";
import { useNotifications } from "@/hooks/useNotifications";
import type { ChatMessage, ChatSession, ProcessStep, PipelineRunState, WaveGroup, WorkflowRun, WorkflowType, GenericDeliverable } from "@/types/index";
import { canChainFrom, CHAIN_OPTIONS, CHAIN_BRIEF_KEY, CHAIN_FROM_KEY, CHAIN_SOURCE_RUN_ID_KEY, baseWorkflowType } from "@/lib/workflowChaining";
import { getToken, getChainContext } from "@/lib/api";
import type { UserWorkflowSummary } from "@/lib/api";
import type { ConnectionStatus } from "@/hooks/useWebSocket";
import type { ChatMode } from "@/components/chat/ChatInput";
import { useSkillsHooks } from "@/context/SkillsHooksContext";

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
  questionnaireData?: { questions: { id: string; question: string; options: string[] }[] } | null;
  // Phase 2 (Universal Engine) — clarify gate resume wiring.
  activePipelineRunId?: string | null;
  // Phase 12 (RESUME-03) — reads the last-received seq for the active run so the
  // reconnect_pipeline send can include `after_seq` for the durable replay
  // (12-03). Returns 0 on a fresh load (no recorded seq ⇒ full-tail replay).
  getLastSeq?: () => number;
  onSubmitQuestionnaire?: (pipelineRunId: string, responses: Array<{ question_id: string; answer: string }>, skipClarification?: boolean) => void;
  // Review gate — shown when an agent with gate: Human_Gate completes
  reviewGateData?: {
    gateKey: string;
    agentId: string;
    agentName: string;
    output: string;
    pipelineRunId: string;
  } | null;
  onApproveReview?: (gateKey: string, editedContent?: string) => void;
  onRejectReview?: (gateKey: string) => void;
  pendingOdProtoParams?: {
    brief: string; templateId: string; designSystemId: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string;
    // Phase 6 — per-run Human-review gate selection. Present only when the user
    // explicitly chose gates (touched); absent ⇒ omitted ⇒ backend static default.
    gateAgentIds?: string[];
  } | null;
  onClearPendingOdProto?: () => void;
  pendingOdPptParams?: {
    brief: string; templateId: string; designSystemId: string | null; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string;
    // Phase 6 — see pendingOdProtoParams.gateAgentIds.
    gateAgentIds?: string[];
  } | null;
  onClearPendingOdPpt?: () => void;
  userTier?: "basic" | "pro" | "enterprise";
  userEmail?: string;
  // Phase 12 (WAVE-03) — wave groups assembled from the live `wave_*` /
  // `subagent_*` WS events by dashboard/page.tsx. Optional + defaulted to []
  // so existing callers/tests that omit it are unaffected; a non-wave run
  // feeds an empty list and WaveTreePanel renders its own empty state.
  waves?: WaveGroup[];
}

type MainView = "home" | "library" | "history" | "settings" | "analytics" | "input" | "execution" | "catalog";

// ─── Planning overlay — shown while the planner analyzes the brief ─────────────
const PLANNING_STEPS = [
  { icon: "🔍", label: "Reading your brief…" },
  { icon: "🧠", label: "Analyzing intent & context…" },
  { icon: "📋", label: "Identifying what's needed…" },
  { icon: "⚡", label: "Preparing your pipeline…" },
];

function PlanningOverlay({ plannerSummary }: { plannerSummary?: string }) {
  const [stepIdx, setStepIdx] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStepIdx(i => (i + 1) % PLANNING_STEPS.length);
    }, 1800);
    return () => clearInterval(interval);
  }, []);

  const step = PLANNING_STEPS[stepIdx];

  return (
    <div className="flex flex-col items-center justify-center h-full bg-white gap-6 px-8">
      {/* Animated brain icon */}
      <div className="relative">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#1B2A4A] to-blue-600 flex items-center justify-center shadow-lg">
          <Brain className="h-8 w-8 text-white" />
        </div>
        {/* Pulse rings */}
        <div className="absolute inset-0 rounded-2xl bg-[#1B2A4A]/20 animate-ping" style={{ animationDuration: "2s" }} />
      </div>

      {/* Status */}
      <div className="text-center space-y-2">
        <p className="text-[14px] font-bold text-gray-900">Planner is thinking…</p>
        <AnimatePresence mode="wait">
          <motion.div
            key={stepIdx}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.3 }}
            className="flex items-center justify-center gap-2"
          >
            <span className="text-[16px]">{step.icon}</span>
            <p className="text-[12px] text-gray-500 font-medium">{step.label}</p>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* What the planner is doing */}
      <div className="w-full max-w-sm rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-2.5">
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
          <Sparkles className="h-3 w-3" /> What the planner does
        </p>
        {[
          "Detects if your brief has a clear topic",
          "Infers audience, tone & constraints",
          "Identifies what questions to ask",
          "Prepares context for all agents",
        ].map((item, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${i <= stepIdx ? "bg-[#1B2A4A]" : "bg-gray-300"}`} />
            <p className={`text-[11px] ${i <= stepIdx ? "text-gray-700" : "text-gray-400"}`}>{item}</p>
          </div>
        ))}
      </div>

      {/* Loading dots */}
      <div className="flex items-center gap-1.5">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-[#1B2A4A]/40 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

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
  onSelectWorkflowRun,
  questionnaireData,
  activePipelineRunId,
  getLastSeq,
  onSubmitQuestionnaire,
  reviewGateData,
  onApproveReview,
  onRejectReview,
  pendingOdProtoParams,
  onClearPendingOdProto,
  pendingOdPptParams,
  onClearPendingOdPpt,
  userTier = "basic",
  userEmail,
  waves = [],
}: DashboardLayoutProps) {
  const router = useRouter();
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
  const [completedPipelineTypes, setCompletedPipelineTypes] = useState<WorkflowType[]>([]);
  const [lastPipelineOutput, setLastPipelineOutput] = useState<string>("");
  const [questionnaireQuestions, setQuestionnaireQuestions] = useState<{ id: string; question: string; options: string[] }[]>([]);
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
    markAllRead,
    clearAll,
  } = useNotifications();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const currentPipelineNotifId = useRef<string | null>(null);

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
      if (mainView !== "execution") {
        setMainView("execution");
      }
      const pt = pipelineState.pipeline_type as WorkflowType | "od_prototype" | "od_ppt";
      // Normalise od_prototype → prototype, od_ppt → ppt
      const normalised: WorkflowType = pt === "od_prototype" ? "prototype" : pt === "od_ppt" ? "ppt" : (pt as WorkflowType);
      if (normalised && normalised !== workflowType) {
        setWorkflowType(normalised);
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
    }
  }, [pipelineState, workflowType, pptContent, userStoryContent, prototypeContent]);

  // Update notification progress as agents complete
  useEffect(() => {
    if (pipelineState?.isRunning && currentPipelineNotifId.current) {
      updateProgress(currentPipelineNotifId.current, pipelineState.completedCount);
    }
  }, [pipelineState?.completedCount, pipelineState?.isRunning]);

  // Detect when od_prototype starts (fired from dashboard/page.tsx directly,
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
      addRunningNotification(notifId, "prototype", "Prototype", 0);
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

  // Track the current workflow run ID for revision updates
  const currentWorkflowRunId = recentRuns?.find(
    r => (r.type === workflowType || r.type === workflowType + "_revision") && r.status === "completed"
  )?.id || "";

  // Handle PPT revision — Phase 3: send run_revision WS message when a
  // completed run exists; fall back to the legacy text-injection pattern
  // for backward compat with pre-Phase3 runs.
  const handleRevisePpt = useCallback((instruction: string) => {
    if (!pptxCode && !pptContent) return;

    const isOdPpt = workflowType === "od_ppt" || workflowType === "od_ppt_revision";

    // Phase 3: use run_revision if we have a completed run ID
    if (currentWorkflowRunId && websocketSend) {
      const targetType = isOdPpt ? "od_ppt_output" : "ppt_output";
      websocketSend(JSON.stringify({
        type: "run_revision",
        parent_run_id: currentWorkflowRunId,
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
  }, [workflowType, pptxCode, pptContent, currentWorkflowRunId, websocketSend, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle User Story revision — re-run pipeline with existing backlog + change instruction
  const handleReviseUserStory = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING PRODUCT BACKLOG ===\n${userStoryContent}\n=== END EXISTING BACKLOG ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("user_stories_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      onStartPipeline("user_stories_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
    }
  }, [userStoryContent, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

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
      // original run's spec/design into the revision sandbox. Only sent when a
      // completed parent run exists (currentWorkflowRunId falls back to "").
      onStartPipeline("prototype_revision", revisionMessage, undefined, attachedSkills, attachedHooks, currentWorkflowRunId ? { source_workflow_run_id: currentWorkflowRunId } : undefined);
    }
  }, [prototypeContent, currentWorkflowRunId, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle App Builder revision — re-run pipeline with existing blueprint + change instruction
  const handleReviseAppBuilder = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING APP BLUEPRINT ===\n${userStoryContent.slice(0, 40000)}\n=== END EXISTING BLUEPRINT ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("app_builder_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      onStartPipeline("app_builder_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
    }
  }, [userStoryContent, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

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
    };

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      addRunningNotification(notifId, "prototype", pendingOdProtoParams.brief.slice(0, 60), 0);
      if (connectionStatus === "connected") {
        onStartPipeline("od_prototype" as WorkflowType, pendingOdProtoParams.brief, [], attachedSkills, attachedHooks, extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: "od_prototype" as WorkflowType,
          message: pendingOdProtoParams.brief,
          agentIds: [],
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
    };

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      addRunningNotification(notifId, "ppt", pendingOdPptParams.brief.slice(0, 60), 0);
      if (connectionStatus === "connected") {
        onStartPipeline("od_ppt" as WorkflowType, pendingOdPptParams.brief, [], attachedSkills, attachedHooks, extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: "od_ppt" as WorkflowType,
          message: pendingOdPptParams.brief,
          agentIds: [],
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
  const [savedComposition, setSavedComposition] = useState<{ agentIds: string[]; modelOverrides: Record<string, string> } | null>(null);

  // Navigate from Home to Input page
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    setSavedComposition(null);
    setWorkflowType(type);
    setMainView("input");
  }, []);

  // Launch a saved workflow — mirrors handleSelectFeature but carries the saved
  // composition into state so IdeaInputPage mounts PRE-LOADED. Run then flows
  // UNCHANGED through handleRunPipeline → useWorkflow.startPipeline (which already
  // sends agent_ids + merges model_overrides) → re-validated server-side at launch
  // (SC-001: pure-data replay, no engine/run-path edit, no `if saved` fork).
  const handleLaunchSaved = useCallback((saved: UserWorkflowSummary) => {
    setSavedComposition({ agentIds: saved.agent_ids, modelOverrides: saved.model_overrides ?? {} });
    setWorkflowType(saved.base_pipeline_type as WorkflowType);
    setMainView("input");
  }, []);

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
      addRunningNotification(notifId, resolvedType, message.slice(0, 60), 0);
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

    const cleanBrief = workflowInput.split("\n\n===")[0].trim();
    const enrichedInput = contextBlock
      ? `${cleanBrief}\n\n${contextBlock}`
      : cleanBrief;

    if (onResetPipeline) onResetPipeline();
    setWorkflowInput(enrichedInput);

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      addRunningNotification(notifId, nextType, enrichedInput.slice(0, 60), 0);
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

    const cleanBrief = (run.input || "").split("\n\n===")[0].trim();
    const enrichedInput = contextBlock ? `${cleanBrief}\n\n${contextBlock}` : cleanBrief;

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
      addRunningNotification(notifId, nextType, enrichedInput.slice(0, 60), 0);
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
      addRunningNotification(notifId, pendingPipelineRun.type, pendingPipelineRun.message.slice(0, 60), 0);
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
  }, [activePipelineRunId, onSubmitQuestionnaire, pendingPipelineRun, questionnaireQuestions, onStartPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

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
      addRunningNotification(notifId, pendingPipelineRun.type, pendingPipelineRun.message.slice(0, 60), 0);
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

  // Header navigation — free navigation even while pipeline runs
  const handleNavigate = useCallback((page: "home" | "library" | "history" | "settings" | "analytics" | "catalog") => {
    setMainView(page as MainView);
  }, []);

  // Follow-up / steer agents
  const handleFollowUp = useCallback((message: string) => {
    const refinedInput = `${workflowInput}\n\n---\nRefinement: ${message}`;
    setWorkflowInput(refinedInput);
    if (onStartPipeline) {
      onStartPipeline(workflowType, refinedInput, undefined, attachedSkills, attachedHooks);
    }
  }, [workflowInput, workflowType, onStartPipeline, attachedSkills, attachedHooks]);

  // Map mainView to header page type
  const headerPage = mainView === "library" ? "library" :
    mainView === "catalog" ? "catalog" :
    mainView === "history" ? "history" :
    mainView === "settings" ? "history" :
    mainView === "input" ? "workflow" :
    mainView === "execution" ? "execution" : "home";

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden" style={{ background: "#f5f5f0" }}>
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
          {/* HOME — the data-driven WorkflowCatalog is the DEFAULT landing
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
              <WorkflowCatalog onSelectFeature={handleSelectFeature} onLaunchSaved={handleLaunchSaved} userTier={userTier} />
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
            onReviseUserStory={(instruction, content) => {
              setMainView("execution");
              setWorkflowType("user_stories_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PRODUCT BACKLOG ===\n${content}\n=== END EXISTING BACKLOG ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("user_stories_revision", msg, undefined, attachedSkills, attachedHooks);
              }
            }}
            onRevisePpt={(instruction, content) => {
              setMainView("execution");
              setWorkflowType("ppt_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PRESENTATION CODE ===\n${content}\n=== END EXISTING CODE ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("ppt_revision", msg, undefined, attachedSkills, attachedHooks);
              }
            }}
            onRevisePrototype={(instruction, content) => {
              setMainView("execution");
              setWorkflowType("prototype_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PROTOTYPE HTML ===\n${content}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("prototype_revision", msg, undefined, attachedSkills, attachedHooks);
              }
            }}
            onReviseAppBuilder={(instruction, content) => {
              setMainView("execution");
              setWorkflowType("app_builder_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING APP BLUEPRINT ===\n${content.slice(0, 40000)}\n=== END EXISTING BLUEPRINT ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("app_builder_revision", msg, undefined, attachedSkills, attachedHooks);
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
              style={{ background: "#f5f5f0" }}
            >
              {/* Left Panel — Agent Progress.
                  ISS-019: the column is a height-owning flex parent. The agent
                  panel flexes to remaining space + scrolls its own cards; the
                  wave panel is a non-shrinking bottom region that stays above
                  the 1440×950 fold. The column itself no longer scrolls — scroll
                  lives inside the two child regions. */}
              <div className="w-full md:w-[340px] lg:w-[360px] flex-shrink-0 h-[45vh] md:h-full border-b md:border-b-0 md:border-r border-gray-200 flex flex-col overflow-hidden bg-white">
                <ErrorBoundary fallbackLabel="AgentProgress">
                  <div className="flex-1 min-h-0 overflow-hidden">
                  <AgentProgressPanel
                    pipelineState={pipelineState || { isRunning: false, pipeline_type: "", agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0 }}
                    workflowType={workflowType}
                    onViewResults={() => {}}
                    onRunAnother={handleGoHome}
                    onFollowUp={handleFollowUp}
                    // Allow chaining from every "deliverable" workflow plus
                    // its revision counterpart (see lib/workflowChaining).
                    // Migration and custom are deliberately excluded — too
                    // heavy / too generic to auto-chain.
                    onChainPipeline={canChainFrom(workflowType) ? handleChainPipeline : undefined}
                    completedPipelineTypes={completedPipelineTypes}
                    onCancelPipeline={() => {
                      if (websocketSend) {
                        websocketSend(JSON.stringify({ type: "cancel_pipeline" }));
                      }
                      // Do NOT call onResetPipeline() here — the pipeline_cancelled
                      // WebSocket event drives the state reset. Calling reset
                      // immediately clears agents[] before the event arrives,
                      // so the graceful agent state transition (running→idle) is skipped.
                    }}
                  />
                  </div>
                </ErrorBoundary>
                {/* Phase 12 (WAVE-03) — live wave/subagent tree. Rendered
                    unconditionally so the panel slot is stable; WaveTreePanel
                    owns the "No waves running." empty state for non-wave runs.
                    ISS-019: non-shrinking bottom region (flex-shrink-0) capped
                    at 40% so it never eats the agent panel; its own
                    max-h-[260px] list scrolls within. */}
                <ErrorBoundary fallbackLabel="WaveTree">
                  <div className="flex-shrink-0 max-h-[40%] overflow-y-auto px-3 pt-3 pb-3 border-t border-gray-200">
                    <WaveTreePanel waves={waves} />
                  </div>
                </ErrorBoundary>
              </div>

              {/* Right Panel — Planning overlay, Questionnaire, or Preview */}
              <div className="flex-1 h-[55vh] md:h-full min-w-0 bg-white rounded-none md:rounded-l-none">
                <ErrorBoundary fallbackLabel="Preview">
                  {/* Show planning overlay while planner is running and no questionnaire yet */}
                  {pipelineState?.isRunning &&
                   pipelineState?.plannerStatus === "running" &&
                   !questionnaireLoading &&
                   questionnaireQuestions.length === 0 &&
                   !activePipelineRunId &&
                   !reviewGateData ? (
                    <PlanningOverlay plannerSummary={pipelineState?.plannerSummary} />
                  ) : reviewGateData ? (
                    <ReviewGatePanel
                      agentId={reviewGateData.agentId}
                      agentName={reviewGateData.agentName}
                      output={reviewGateData.output}
                      gateKey={reviewGateData.gateKey}
                      onApprove={onApproveReview || (() => {})}
                      onReject={onRejectReview || (() => {})}
                    />
                  ) : (questionnaireLoading || questionnaireQuestions.length > 0) && (pendingPipelineRun || activePipelineRunId) ? (
                    <QuestionnairePanel
                      questions={questionnaireQuestions}
                      isLoading={questionnaireLoading}
                      onSubmitAnswers={handleQuestionnaireSubmit}
                      onSkip={handleQuestionnaireSkip}
                      workflowType={workflowType}
                    />
                  ) : (
                    <PreviewPanel
                      userStoryContent={userStoryContent || undefined}
                      pptContent={pptContent || undefined}
                      prototypeContent={prototypeContent || undefined}
                      genericDeliverable={genericDeliverable}
                      isStreaming={isStreaming}
                      workflowType={workflowType}
                      rawPipelineType={pipelineState?.pipeline_type || workflowType}
                      pptxCode={pptxCode}
                      onRevisePpt={(workflowType === "ppt" || workflowType === "ppt_revision" || workflowType === "od_ppt") ? handleRevisePpt : undefined}
                      onReviseUserStory={(workflowType === "user_stories" || workflowType === "user_stories_revision") ? handleReviseUserStory : undefined}
                      onRevisePrototype={(workflowType === "prototype" || workflowType === "prototype_revision" || !!prototypeContent) ? handleRevisePrototype : undefined}
                      onReviseAppBuilder={(workflowType === "app_builder" || workflowType === "app_builder_revision") ? handleReviseAppBuilder : undefined}
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
                    />
                  )}
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
