"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { WifiOff, RefreshCw } from "lucide-react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { AppHeader } from "./AppHeader";
import { CreationHub } from "@/components/home/CreationHub";
import { LibraryPage } from "@/components/library/LibraryPage";
import { WorkflowHistory } from "@/components/history/WorkflowHistory";
import { AccountSettings } from "@/components/settings/AccountSettings";
import { AnalyticsPage } from "@/components/analytics/AnalyticsPage";
import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import { AgentProgressPanel } from "@/components/workflow/AgentProgressPanel";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import { QuestionnairePanel } from "@/components/preview/QuestionnairePanel";
import { CompletionToast } from "@/components/ui/CompletionToast";
import type { ToastItem } from "@/components/ui/CompletionToast";
import { useNotifications } from "@/hooks/useNotifications";
import type { ChatMessage, ChatSession, ProcessStep, PipelineRunState, WorkflowRun, WorkflowType } from "@/types/index";
import { canChainFrom } from "@/lib/workflowChaining";
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
  questionnaireData?: { questions: { id: string; question: string; options: string[] }[] } | null;
  pendingOdProtoParams?: {
    brief: string; templateId: string; designSystemId: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string;
  } | null;
  onClearPendingOdProto?: () => void;
  pendingOdPptParams?: {
    brief: string; templateId: string; designSystemId: string | null; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string;
  } | null;
  onClearPendingOdPpt?: () => void;
  userTier?: "basic" | "pro" | "enterprise";
  userEmail?: string;
}

type MainView = "home" | "library" | "history" | "settings" | "analytics" | "input" | "execution";

export function DashboardLayout({
  activeChatId,
  messages,
  isStreaming,
  streamingContent,
  userStoryContent,
  pptContent,
  prototypeContent,
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
  onStartPipeline,
  onResetPipeline,
  recentRuns,
  onSelectWorkflowRun,
  questionnaireData,
  pendingOdProtoParams,
  onClearPendingOdProto,
  pendingOdPptParams,
  onClearPendingOdPpt,
  userTier = "basic",
  userEmail,
}: DashboardLayoutProps) {
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

  // Handle PPT revision — branches on pipeline type:
  // - od_ppt: sends existing HTML + instruction to od_ppt_revision (single HTML-aware agent)
  // - ppt: sends existing PptxGenJS code + instruction to ppt_revision (old PptxGenJS agents)
  const handleRevisePpt = useCallback((instruction: string) => {
    if (!pptxCode && !pptContent) return;

    const isOdPpt = workflowType === "od_ppt" || workflowType === "od_ppt_revision";

    if (isOdPpt) {
      // od_ppt revision — pass existing HTML deck + instruction
      const existingHtml = pptContent || "";
      const revisionMessage = `=== EXISTING HTML DECK ===\n${existingHtml.slice(0, 60000)}\n=== END EXISTING DECK ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
      setWorkflowType("od_ppt_revision" as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      if (onStartPipeline) {
        onStartPipeline("od_ppt_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
      }
    } else {
      // ppt revision — pass existing PptxGenJS code + instruction
      const existingCode = pptxCode || "";
      const revisionMessage = `=== EXISTING PRESENTATION CODE ===\n${existingCode}\n=== END EXISTING CODE ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
      setWorkflowType("ppt_revision" as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      if (onStartPipeline) {
        onStartPipeline("ppt_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
      }
    }
  }, [workflowType, pptxCode, pptContent, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

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

  // Handle Prototype revision — re-run pipeline with existing HTML + change instruction
  const handleRevisePrototype = useCallback((instruction: string) => {
    if (!prototypeContent) return;
    const revisionMessage = `=== EXISTING PROTOTYPE HTML ===\n${prototypeContent.slice(0, 40000)}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("prototype_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      onStartPipeline("prototype_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
    }
  }, [prototypeContent, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

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

  // When pendingOdProtoParams arrives (set by dashboard/page.tsx after the
  // WebSocket fires generate_questions), set up the questionnaire pending state
  // so QuestionnairePanel shows and the submit/skip handlers know the extraParams.
  useEffect(() => {
    if (!pendingOdProtoParams) return;
    setMainView("execution");
    setWorkflowType("prototype");
    setPendingPipelineRun({
      type: "od_prototype" as WorkflowType,
      message: pendingOdProtoParams.brief,
      extraParams: {
        template_id: pendingOdProtoParams.templateId,
        design_system_id: pendingOdProtoParams.designSystemId,
        ...(pendingOdProtoParams.customDsBody ? { custom_design_system_body: pendingOdProtoParams.customDsBody } : {}),
        ...(pendingOdProtoParams.customTemplateBody ? { custom_template_body: pendingOdProtoParams.customTemplateBody } : {}),
        discovery: pendingOdProtoParams.discovery,
      },
    });
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(true);
    // NOTE: do NOT call onResetPipeline here — there's no running pipeline to
    // reset, and calling it causes unnecessary state churn that can disrupt
    // the WebSocket connection before the pipeline fires.
    if (onClearPendingOdProto) onClearPendingOdProto();

    // Timeout: if questionnaire doesn't respond in 15s, skip it
    setTimeout(() => {
      setQuestionnaireLoading((loading) => {
        if (loading) {
          setQuestionnaireQuestions([]);
          return false;
        }
        return loading;
      });
    }, 15000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOdProtoParams]);

  // When pendingOdPptParams arrives, set up the questionnaire for od_ppt.
  useEffect(() => {
    if (!pendingOdPptParams) return;
    setMainView("execution");
    setWorkflowType("ppt");
    setPendingPipelineRun({
      type: "od_ppt" as WorkflowType,
      message: pendingOdPptParams.brief,
      extraParams: {
        template_id: pendingOdPptParams.templateId,
        ...(pendingOdPptParams.designSystemId ? { design_system_id: pendingOdPptParams.designSystemId } : {}),
        ...(pendingOdPptParams.customDsBody ? { custom_design_system_body: pendingOdPptParams.customDsBody } : {}),
        ...(pendingOdPptParams.customTemplateBody ? { custom_template_body: pendingOdPptParams.customTemplateBody } : {}),
        discovery: pendingOdPptParams.discovery,
      },
    });
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(true);
    if (onClearPendingOdPpt) onClearPendingOdPpt();
    setTimeout(() => {
      setQuestionnaireLoading((loading) => {
        if (loading) { setQuestionnaireQuestions([]); return false; }
        return loading;
      });
    }, 15000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOdPptParams]);

  // Navigate from Home to Input page
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    setWorkflowType(type);
    setMainView("input");
  }, []);

  // Run the pipeline from Input page — triggers questionnaire first
  // `resolvedType` is the concrete pipeline the backend will dispatch. For
  // most workflows it matches the parent state; for the `migration` meta
  // type the IdeaInputPage resolves it to a real sub-pipeline (Mulesoft→
  // Spring Boot or .NET→Azure) before invoking us. We sync `workflowType`
  // here so downstream effects (chaining, sidebar labels, completion
  // tracking) see the real pipeline.
  const handleRunPipeline = useCallback((message: string, agentIds: string[], resolvedType: WorkflowType) => {
    setWorkflowInput(message);
    setMainView("execution");
    setWorkflowType(resolvedType);
    setPendingPipelineRun({ type: resolvedType, message, agentIds });
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(true);

    // Reset previous pipeline state so left panel clears
    if (onResetPipeline) onResetPipeline();

    // Timeout: if questionnaire doesn't respond in 15s, skip it
    setTimeout(() => {
      setQuestionnaireLoading((loading) => {
        if (loading) {
          setQuestionnaireQuestions([]);
          return false;
        }
        return loading;
      });
    }, 15000);

    // Request questionnaire from backend
    if (websocketSend) {
      websocketSend(JSON.stringify({
        type: "generate_questions",
        pipeline_type: resolvedType,
        message,
      }));
    }
  }, [websocketSend, onResetPipeline]);

  // Go back to home
  const handleGoHome = useCallback(() => {
    setMainView("home");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (!isPipelineRunning && onResetPipeline) onResetPipeline();
  }, [onResetPipeline, isPipelineRunning]);

  // Chain to another pipeline using previous output as context
  const handleChainPipeline = useCallback((nextType: WorkflowType) => {
    setWorkflowType(nextType);

    // Build enriched input: original prompt + summary of previous output
    const prevSummary = lastPipelineOutput.slice(0, 4000);
    const enrichedInput = `${workflowInput}\n\n=== CONTEXT FROM PREVIOUS PIPELINE (${workflowType}) ===\n${prevSummary}\n=== END PREVIOUS CONTEXT ===`;

    // Reset previous pipeline state so left panel clears
    if (onResetPipeline) onResetPipeline();

    // Trigger questionnaire first (same as handleRunPipeline)
    setWorkflowInput(enrichedInput);
    setPendingPipelineRun({ type: nextType, message: enrichedInput });
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(true);

    // Request questionnaire from backend
    if (websocketSend) {
      websocketSend(JSON.stringify({
        type: "generate_questions",
        pipeline_type: nextType,
        message: enrichedInput,
      }));
    }
  }, [workflowType, workflowInput, lastPipelineOutput, websocketSend, onResetPipeline]);

  // Chain to another pipeline starting from a historical run. The user is
  // viewing a past WorkflowRun in the history view; they pick a next
  // pipeline. We must use the historical run's input/output for the
  // enrichment (NOT the current dashboard state, which is stale for the
  // run they just opened from history). After dispatching we switch to
  // the execution view so the new pipeline shows the agent progress.
  const handleChainFromHistory = useCallback((run: WorkflowRun, nextType: WorkflowType) => {
    const baseInput = run.input || "";
    const baseOutput = (run.output || "").slice(0, 4000);
    const enrichedInput = `${baseInput}\n\n=== CONTEXT FROM PREVIOUS PIPELINE (${run.type}) ===\n${baseOutput}\n=== END PREVIOUS CONTEXT ===`;

    setWorkflowType(nextType);
    setWorkflowInput(enrichedInput);
    setLastPipelineOutput(run.output || "");
    setCompletedPipelineTypes((prev) =>
      prev.includes(run.type as WorkflowType) ? prev : [...prev, run.type as WorkflowType],
    );
    setMainView("execution");
    if (onResetPipeline) onResetPipeline();

    setPendingPipelineRun({ type: nextType, message: enrichedInput });
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(true);

    if (websocketSend) {
      websocketSend(JSON.stringify({
        type: "generate_questions",
        pipeline_type: nextType,
        message: enrichedInput,
      }));
    }
  }, [websocketSend, onResetPipeline]);

  // Handle questionnaire answers — run pipeline with enriched input
  const handleQuestionnaireSubmit = useCallback((answers: Record<string, string[]>, freeformInput: string) => {
    if (!pendingPipelineRun) return;

    // Build enriched message with user's answers
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

    // Clear questionnaire state and run pipeline
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      addRunningNotification(notifId, pendingPipelineRun.type, pendingPipelineRun.message.slice(0, 60), 0);
      // If the WebSocket is connected, fire immediately. Otherwise store in
      // the ref so the connectionStatus effect fires it on reconnect.
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
  }, [pendingPipelineRun, questionnaireQuestions, onStartPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Skip questionnaire — run pipeline directly with skills/hooks
  const handleQuestionnaireSkip = useCallback(() => {
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
  }, [pendingPipelineRun, onStartPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Header navigation — free navigation even while pipeline runs
  const handleNavigate = useCallback((page: "home" | "library" | "history" | "settings" | "analytics") => {
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
          {/* HOME — Full-width cards */}
          {mainView === "home" && (
            <motion.div
              key="home"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <CreationHub onSelectFeature={handleSelectFeature} userTier={userTier} />
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
                const msg = `=== EXISTING PROTOTYPE HTML ===\n${content.slice(0, 40000)}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
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
              {/* Left Panel — Agent Progress */}
              <div className="w-full md:w-[340px] lg:w-[360px] flex-shrink-0 h-[45vh] md:h-full border-b md:border-b-0 md:border-r border-gray-200 overflow-y-auto bg-white">
                <ErrorBoundary fallbackLabel="AgentProgress">
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
                </ErrorBoundary>
              </div>

              {/* Right Panel — Questionnaire or Preview */}
              <div className="flex-1 h-[55vh] md:h-full min-w-0 bg-white rounded-none md:rounded-l-none">
                <ErrorBoundary fallbackLabel="Preview">
                  {(questionnaireLoading || questionnaireQuestions.length > 0) && pendingPipelineRun ? (
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
