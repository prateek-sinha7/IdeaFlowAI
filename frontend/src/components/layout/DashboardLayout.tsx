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
  onStartPipeline?: (type: string, message: string, agentIds?: string[], attachedSkills?: import("@/types/index").AttachedSkill[], attachedHooks?: import("@/types/index").AttachedHook[]) => void;
  onResetPipeline?: () => void;
  recentRuns?: WorkflowRun[];
  onSelectWorkflowRun?: (run: WorkflowRun) => void;
  questionnaireData?: { questions: { id: string; question: string; options: string[] }[] } | null;
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
}: DashboardLayoutProps) {
  const [mainView, setMainView] = useState<MainView>("home");
  const [workflowType, setWorkflowType] = useState<WorkflowType>("user_stories");
  const [workflowInput, setWorkflowInput] = useState("");
  const [completedPipelineTypes, setCompletedPipelineTypes] = useState<WorkflowType[]>([]);
  const [lastPipelineOutput, setLastPipelineOutput] = useState<string>("");
  const [questionnaireQuestions, setQuestionnaireQuestions] = useState<{ id: string; question: string; options: string[] }[]>([]);
  const [questionnaireLoading, setQuestionnaireLoading] = useState(false);
  const [pendingPipelineRun, setPendingPipelineRun] = useState<{ type: WorkflowType; message: string; agentIds?: string[] } | null>(null);

  // Read attached skills/hooks from global context — set by user in AgentsPopup
  const { attachedSkills, attachedHooks } = useSkillsHooks();

  // Notifications + toasts
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
  // Stable ID for the current pipeline run (used to correlate notifications)
  const currentPipelineNotifId = useRef<string | null>(null);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Switch to execution view when pipeline first starts.
  // We track the previous isRunning value via ref so we only navigate
  // on the false→true transition, not on every render while running.
  // This prevents the effect from snapping the user back to execution
  // every time they navigate away while the pipeline is running.
  const wasRunningRef = useRef(false);
  useEffect(() => {
    const isNowRunning = pipelineState?.isRunning ?? false;
    if (isNowRunning && !wasRunningRef.current) {
      setMainView("execution");
    }
    wasRunningRef.current = isNowRunning;
  }, [pipelineState?.isRunning]);

  // Capture output when pipeline completes (for chaining) + fire notifications
  useEffect(() => {
    if (pipelineState && !pipelineState.isRunning && pipelineState.agents.length > 0) {
      const allDone = pipelineState.agents.every((a) => a.status === "done" || a.status === "error");
      const anyCancelled = pipelineState.agents.some((a) => a.status === "idle" && pipelineState.completedCount > 0);
      if (allDone && pipelineState.agents.some((a) => a.status === "done")) {
        // Pipeline just completed — track it
        setCompletedPipelineTypes((prev) => {
          if (prev.includes(workflowType)) return prev;
          return [...prev, workflowType];
        });
        // Capture the latest output for chaining
        const output = pptContent || userStoryContent || prototypeContent;
        if (output) setLastPipelineOutput(output);

        // Fire completion notification + toast
        if (currentPipelineNotifId.current) {
          const notifId = currentPipelineNotifId.current;
          markCompleted(notifId);
          const runTitle = recentRuns?.[0]?.title || workflowType;
          setToasts(prev => [...prev, {
            id: notifId + "-toast",
            workflowType,
            title: runTitle,
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

  // Update agentsTotal when pipeline_start arrives with the real agent list.
  // At notification creation time pipelineState.agents is still empty (the
  // pipeline_start WS event hasn't arrived yet). This effect fires as soon
  // as agents are populated, giving us the correct count for any pipeline
  // type — including PPT (4 agents), custom agent sets, etc.
  useEffect(() => {
    const agentCount = pipelineState?.agents?.length ?? 0;
    if (agentCount > 0 && currentPipelineNotifId.current) {
      updateAgentsTotal(currentPipelineNotifId.current, agentCount);
    }
  }, [pipelineState?.agents?.length]);

  // Update notification title when the backend generates a clean title
  // (workflow_title_update event → recentRuns[0].title updates ~5s after start)
  useEffect(() => {
    const latestRun = recentRuns?.[0];
    if (latestRun?.title && latestRun.title !== "Untitled" && currentPipelineNotifId.current) {
      updateAgentsTotal(currentPipelineNotifId.current, pipelineState?.agents?.length ?? 0, latestRun.title);
    }
  }, [recentRuns?.[0]?.title]);

  // Check if pipeline is running (used for cancel button, NOT for blocking navigation)
  const isPipelineRunning = pipelineState?.isRunning || false;

  // Extract Agent 3's (ppt-code-generator) output for early PPTX download
  const pptxCode = pipelineState?.agents.find(a => a.id === "ppt-code-generator" && a.status === "done")?.output || undefined;

  // Track the current workflow run ID for revision updates
  const currentWorkflowRunId = recentRuns?.find(
    r => (r.type === workflowType || r.type === workflowType + "_revision") && r.status === "completed"
  )?.id || "";

  // Handle PPT revision — re-run pipeline with existing code + change instruction
  const handleRevisePpt = useCallback((instruction: string) => {
    if (!pptxCode && !pptContent) return;
    const existingCode = pptxCode || "";
    const revisionMessage = `=== EXISTING PRESENTATION CODE ===\n${existingCode}\n=== END EXISTING CODE ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("ppt_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      onStartPipeline("ppt_revision", revisionMessage);
    }
  }, [pptxCode, pptContent, onStartPipeline, onResetPipeline]);

  // Handle User Story revision — re-run pipeline with existing backlog + change instruction
  const handleReviseUserStory = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING PRODUCT BACKLOG ===\n${userStoryContent}\n=== END EXISTING BACKLOG ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("user_stories_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      onStartPipeline("user_stories_revision", revisionMessage);
    }
  }, [userStoryContent, onStartPipeline, onResetPipeline]);

  // Handle Prototype revision — re-run pipeline with existing HTML + change instruction
  const handleRevisePrototype = useCallback((instruction: string) => {
    if (!prototypeContent) return;
    const revisionMessage = `=== EXISTING PROTOTYPE HTML ===\n${prototypeContent.slice(0, 40000)}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("prototype_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      onStartPipeline("prototype_revision", revisionMessage);
    }
  }, [prototypeContent, onStartPipeline, onResetPipeline]);

  // Handle App Builder revision — re-run pipeline with existing blueprint + change instruction
  const handleReviseAppBuilder = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING APP BLUEPRINT ===\n${userStoryContent.slice(0, 40000)}\n=== END EXISTING BLUEPRINT ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("app_builder_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      onStartPipeline("app_builder_revision", revisionMessage);
    }
  }, [userStoryContent, onStartPipeline, onResetPipeline]);

  // Handle incoming questionnaire data from WebSocket
  useEffect(() => {
    if (questionnaireData && questionnaireData.questions) {
      setQuestionnaireQuestions(questionnaireData.questions);
      setQuestionnaireLoading(false);
    }
  }, [questionnaireData]);

  // Navigate from Home to Input page
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    setWorkflowType(type);
    setMainView("input");
  }, []);

  // Run the pipeline from Input page — triggers questionnaire first
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

  // Go back to home — no longer blocked by pipeline running
  const handleGoHome = useCallback(() => {
    setMainView("home");
    // Clear any pending questionnaire state
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
      // Generate a stable notification ID for this run
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // agentsTotal starts at 0 — updated when pipeline_start WS event arrives
      // with the real agent list (which accounts for custom agents too)
      addRunningNotification(notifId, pendingPipelineRun.type, pendingPipelineRun.message.slice(0, 60), 0);
      onStartPipeline(pendingPipelineRun.type, enrichedMessage, pendingPipelineRun.agentIds, attachedSkills, attachedHooks);
    }
  }, [pendingPipelineRun, questionnaireQuestions, onStartPipeline, attachedSkills, attachedHooks, pipelineState?.agents?.length, addRunningNotification]);

  // Skip questionnaire — run pipeline directly with skills/hooks
  const handleQuestionnaireSkip = useCallback(() => {
    if (!pendingPipelineRun) return;
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // agentsTotal starts at 0 — updated when pipeline_start WS event arrives
      addRunningNotification(notifId, pendingPipelineRun.type, pendingPipelineRun.message.slice(0, 60), 0);
      onStartPipeline(pendingPipelineRun.type, pendingPipelineRun.message, pendingPipelineRun.agentIds, attachedSkills, attachedHooks);
    }
  }, [pendingPipelineRun, onStartPipeline, attachedSkills, attachedHooks, pipelineState?.agents?.length, addRunningNotification]);

  // Header navigation — no longer blocked by pipeline running
  const handleNavigate = useCallback((page: "home" | "library" | "history" | "settings" | "analytics") => {
    setMainView(page);
  }, []);

  // Follow-up / steer agents
  const handleFollowUp = useCallback((message: string) => {
    const refinedInput = `${workflowInput}\n\n---\nRefinement: ${message}`;
    setWorkflowInput(refinedInput);
    if (onStartPipeline) {
      onStartPipeline(workflowType, refinedInput);
    }
  }, [workflowInput, workflowType, onStartPipeline]);

  // Map mainView to header page type
  const headerPage = mainView === "library" ? "library" :
    mainView === "history" ? "history" :
    mainView === "settings" ? "history" :
    mainView === "analytics" ? "analytics" :
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
          // Navigate to execution view if running or just completed, else history
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
              <CreationHub onSelectFeature={handleSelectFeature} />
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
              <WorkflowHistory onBack={handleGoHome} onChainPipeline={handleChainFromHistory} />
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

          {/* ANALYTICS — Token usage and cost analytics */}
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
                      if (onResetPipeline) onResetPipeline();
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
                      pptxCode={pptxCode}
                      onRevisePpt={(workflowType === "ppt" || workflowType === "ppt_revision") ? handleRevisePpt : undefined}
                      onReviseUserStory={(workflowType === "user_stories" || workflowType === "user_stories_revision") ? handleReviseUserStory : undefined}
                      onRevisePrototype={(workflowType === "prototype" || workflowType === "prototype_revision") ? handleRevisePrototype : undefined}
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
          // Go to execution view first so user sees the results panel
          setMainView("execution");
        }}
      />
    </div>
  );
}
