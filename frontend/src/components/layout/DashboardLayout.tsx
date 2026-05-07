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
import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import { AgentProgressPanel } from "@/components/workflow/AgentProgressPanel";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import { QuestionnairePanel } from "@/components/preview/QuestionnairePanel";
import type { ChatMessage, ChatSession, ProcessStep, PipelineRunState, WorkflowRun, WorkflowType } from "@/types/index";
import type { ConnectionStatus } from "@/hooks/useWebSocket";
import type { ChatMode } from "@/components/chat/ChatInput";

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
  onStartPipeline?: (type: string, message: string, agentIds?: string[]) => void;
  onResetPipeline?: () => void;
  recentRuns?: WorkflowRun[];
  onSelectWorkflowRun?: (run: WorkflowRun) => void;
  questionnaireData?: { questions: { id: string; question: string; options: string[] }[] } | null;
}

type MainView = "home" | "library" | "history" | "settings" | "input" | "execution";

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

  // Detect when pipeline starts running → switch to execution view
  useEffect(() => {
    if (pipelineState?.isRunning && mainView !== "execution") {
      setMainView("execution");
    }
  }, [pipelineState?.isRunning, mainView]);

  // Capture output when pipeline completes (for chaining)
  useEffect(() => {
    if (pipelineState && !pipelineState.isRunning && pipelineState.agents.length > 0) {
      const allDone = pipelineState.agents.every((a) => a.status === "done" || a.status === "error");
      if (allDone && pipelineState.agents.some((a) => a.status === "done")) {
        // Pipeline just completed — track it
        setCompletedPipelineTypes((prev) => {
          if (prev.includes(workflowType)) return prev;
          return [...prev, workflowType];
        });
        // Capture the latest output for chaining
        const output = pptContent || userStoryContent || prototypeContent;
        if (output) setLastPipelineOutput(output);
      }
    }
  }, [pipelineState, workflowType, pptContent, userStoryContent, prototypeContent]);

  // Check if pipeline is running (blocks navigation)
  const isPipelineRunning = pipelineState?.isRunning || false;

  // Handle incoming questionnaire data from WebSocket
  useEffect(() => {
    if (questionnaireData && questionnaireData.questions) {
      setQuestionnaireQuestions(questionnaireData.questions);
      setQuestionnaireLoading(false);
    }
  }, [questionnaireData]);

  // Navigate from Home to Input page
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    if (isPipelineRunning) return;
    setWorkflowType(type);
    setMainView("input");
  }, [isPipelineRunning]);

  // Run the pipeline from Input page — triggers questionnaire first
  const handleRunPipeline = useCallback((message: string, agentIds: string[]) => {
    setWorkflowInput(message);
    setMainView("execution");
    setPendingPipelineRun({ type: workflowType, message, agentIds });
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(true);

    // Request questionnaire from backend
    if (websocketSend) {
      websocketSend(JSON.stringify({
        type: "generate_questions",
        pipeline_type: workflowType,
        message,
      }));
    }
  }, [workflowType, websocketSend]);

  // Go back to home
  const handleGoHome = useCallback(() => {
    if (isPipelineRunning) return;
    setMainView("home");
    // Clear any pending questionnaire state
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onResetPipeline) onResetPipeline();
  }, [onResetPipeline, isPipelineRunning]);

  // Chain to another pipeline using previous output as context
  const handleChainPipeline = useCallback((nextType: WorkflowType) => {
    setWorkflowType(nextType);

    // Build enriched input: original prompt + summary of previous output
    const prevSummary = lastPipelineOutput.slice(0, 4000);
    const enrichedInput = `${workflowInput}\n\n=== CONTEXT FROM PREVIOUS PIPELINE (${workflowType}) ===\n${prevSummary}\n=== END PREVIOUS CONTEXT ===`;

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
  }, [workflowType, workflowInput, lastPipelineOutput, websocketSend]);

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
      onStartPipeline(pendingPipelineRun.type, enrichedMessage, pendingPipelineRun.agentIds);
    }
  }, [pendingPipelineRun, questionnaireQuestions, onStartPipeline]);

  // Skip questionnaire — run pipeline directly
  const handleQuestionnaireSkip = useCallback(() => {
    if (!pendingPipelineRun) return;
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onStartPipeline) {
      onStartPipeline(pendingPipelineRun.type, pendingPipelineRun.message, pendingPipelineRun.agentIds);
    }
  }, [pendingPipelineRun, onStartPipeline]);

  // Header navigation
  const handleNavigate = useCallback((page: "home" | "library" | "history" | "settings") => {
    if (isPipelineRunning) return;
    setMainView(page);
  }, [isPipelineRunning]);

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
    mainView === "input" ? "workflow" :
    mainView === "execution" ? "execution" : "home";

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden bg-[#f5f4ed]">
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
        disabled={isPipelineRunning}
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
              <WorkflowHistory onBack={handleGoHome} />
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
            >
              {/* Left Panel — Agent Progress */}
              <div className="w-full md:w-[340px] lg:w-[360px] flex-shrink-0 h-[45vh] md:h-full border-b md:border-b-0 md:border-r border-[#e8e6dc] overflow-y-auto">
                <ErrorBoundary fallbackLabel="AgentProgress">
                  <AgentProgressPanel
                    pipelineState={pipelineState || { isRunning: false, pipeline_type: "", agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0 }}
                    workflowType={workflowType}
                    onViewResults={() => {}}
                    onRunAnother={handleGoHome}
                    onFollowUp={handleFollowUp}
                    onChainPipeline={handleChainPipeline}
                    completedPipelineTypes={completedPipelineTypes}
                  />
                </ErrorBoundary>
              </div>

              {/* Right Panel — Questionnaire or Preview */}
              <div className="flex-1 h-[55vh] md:h-full min-w-0">
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
                    />
                  )}
                </ErrorBoundary>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
