"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { WifiOff, RefreshCw } from "lucide-react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { AppHeader } from "./AppHeader";
import { CreationHub } from "@/components/home/CreationHub";
import { LibraryPage } from "@/components/library/LibraryPage";
import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import { AgentProgressPanel } from "@/components/workflow/AgentProgressPanel";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
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
}

type MainView = "home" | "library" | "input" | "execution";

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
}: DashboardLayoutProps) {
  const [mainView, setMainView] = useState<MainView>("home");
  const [workflowType, setWorkflowType] = useState<WorkflowType>("user_stories");
  const [workflowInput, setWorkflowInput] = useState("");

  // Detect when pipeline starts running → switch to execution view
  useEffect(() => {
    if (pipelineState?.isRunning && mainView !== "execution") {
      setMainView("execution");
    }
  }, [pipelineState?.isRunning, mainView]);

  // Navigate from Home to Input page
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    setWorkflowType(type);
    setMainView("input");
  }, []);

  // Run the pipeline from Input page
  const handleRunPipeline = useCallback((message: string, agentIds: string[]) => {
    setWorkflowInput(message);
    setMainView("execution");
    if (onStartPipeline) {
      onStartPipeline(workflowType, message, agentIds);
    }
  }, [workflowType, onStartPipeline]);

  // Go back to home
  const handleGoHome = useCallback(() => {
    setMainView("home");
    if (onResetPipeline) onResetPipeline();
  }, [onResetPipeline]);

  // Header navigation
  const handleNavigate = useCallback((page: "home" | "library") => {
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
    mainView === "input" ? "workflow" :
    mainView === "execution" ? "execution" : "home";

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden" style={{ backgroundColor: "var(--theme-bg)" }}>
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
              className="h-full flex"
            >
              {/* Left Panel — Agent Progress */}
              <div className="w-[360px] flex-shrink-0 h-full border-r border-white/8">
                <ErrorBoundary fallbackLabel="AgentProgress">
                  <AgentProgressPanel
                    pipelineState={pipelineState || { isRunning: false, pipeline_type: "", agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0 }}
                    workflowType={workflowType}
                    onViewResults={() => {}}
                    onRunAnother={handleGoHome}
                    onFollowUp={handleFollowUp}
                  />
                </ErrorBoundary>
              </div>

              {/* Right Panel — Preview */}
              <div className="flex-1 h-full min-w-0">
                <ErrorBoundary fallbackLabel="Preview">
                  <PreviewPanel
                    userStoryContent={userStoryContent || undefined}
                    pptContent={pptContent || undefined}
                    prototypeContent={prototypeContent || undefined}
                    isStreaming={isStreaming}
                    workflowType={workflowType}
                    onFollowUp={handleFollowUp}
                  />
                </ErrorBoundary>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
