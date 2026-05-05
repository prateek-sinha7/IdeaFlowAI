"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  PanelLeftOpen,
  Plus,
  Search,
  LogOut,
  WifiOff,
  RefreshCw,
  Eye,
} from "lucide-react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import { WorkflowView } from "@/components/workflow/WorkflowView";
import { CreationHub } from "@/components/home/CreationHub";
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

type MainView = "home" | "workflow";

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
  recentRuns: externalRecentRuns,
  onSelectWorkflowRun,
}: DashboardLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewManualClose, setPreviewManualClose] = useState(false);
  const [previewInitialTab, setPreviewInitialTab] = useState<string | undefined>(undefined);
  const [previewWidth, setPreviewWidth] = useState(480);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mainView, setMainView] = useState<MainView>("home");
  const [workflowType, setWorkflowType] = useState<WorkflowType>("user_stories");
  const [workflowInput, setWorkflowInput] = useState("");
  const [currentAgentOutputs, setCurrentAgentOutputs] = useState<import("@/types/index").AgentThinkingEntry[] | undefined>(undefined);
  const prevContentRef = useRef({ userStory: "", ppt: "", prototype: "" });

  // Merge external runs with any locally-tracked in-flight run
  const [localRunningRun, setLocalRunningRun] = useState<WorkflowRun | null>(null);
  const recentRuns: WorkflowRun[] = localRunningRun
    ? [localRunningRun, ...(externalRecentRuns || []).filter((r) => r.id !== localRunningRun.id)]
    : externalRecentRuns || [];

  // Check if any preview content exists
  const hasPreviewContent = !!(userStoryContent || pptContent || prototypeContent);

  // Auto-open preview when NEW content arrives
  useEffect(() => {
    const prev = prevContentRef.current;
    const hasNewUserStory = userStoryContent && !prev.userStory;
    const hasNewPpt = pptContent && !prev.ppt;
    const hasNewPrototype = prototypeContent && !prev.prototype;

    if (hasNewUserStory || hasNewPpt || hasNewPrototype) {
      setPreviewOpen(true);
      setPreviewManualClose(false);

      if (hasNewUserStory) setPreviewInitialTab("user-stories");
      else if (hasNewPpt) setPreviewInitialTab("ppt");
      else if (hasNewPrototype) setPreviewInitialTab("prototype");
    }

    prevContentRef.current = {
      userStory: userStoryContent,
      ppt: pptContent,
      prototype: prototypeContent,
    };
  }, [userStoryContent, pptContent, prototypeContent]);

  // When user manually closes preview
  const handlePreviewClose = useCallback(() => {
    setPreviewOpen(false);
    setPreviewManualClose(true);
  }, []);

  // When user manually opens preview
  const handlePreviewOpen = useCallback(() => {
    setPreviewOpen(true);
    setPreviewManualClose(false);
  }, []);

  // Navigate from Home (cards) to WorkflowView (build step) — Step 1 → Step 2
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    setWorkflowType(type);
    setWorkflowInput(""); // No input yet — user will type in WorkflowView
    setMainView("workflow");
  }, []);

  // Handle selecting a past run
  const handleSelectRun = useCallback((run: WorkflowRun) => {
    if (run.status === "completed") {
      setWorkflowType(run.type);
      setPreviewOpen(true);
      setPreviewManualClose(false);
      setPreviewInitialTab("preview");
      setCurrentAgentOutputs(run.agentOutputs);
    }
    // Notify parent to load the run's output
    onSelectWorkflowRun?.(run);
  }, [onSelectWorkflowRun]);

  // Go back to home
  const handleGoHome = useCallback(() => {
    setMainView("home");
    setPreviewOpen(false);
  }, []);

  // Track pipeline completion to update local running run status
  useEffect(() => {
    if (pipelineState && !pipelineState.isRunning && pipelineState.agents.length > 0 && pipelineState.completedCount === pipelineState.agents.length) {
      setLocalRunningRun((prev) =>
        prev && prev.status === "running"
          ? { ...prev, status: "completed" as const, duration: pipelineState.totalDuration ?? undefined, completedAt: new Date().toISOString() }
          : prev
      );
    }
  }, [pipelineState]);

  // Clear local running run once the external list includes it (backend refreshed)
  useEffect(() => {
    if (localRunningRun && localRunningRun.status === "completed" && externalRecentRuns && externalRecentRuns.length > 0) {
      // If the external list has a completed run with matching type and recent timestamp, clear local
      const hasMatchingRun = externalRecentRuns.some(
        (r) => r.status === "completed" && r.type === localRunningRun.type &&
          new Date(r.createdAt).getTime() > new Date(localRunningRun.createdAt).getTime() - 5000
      );
      if (hasMatchingRun) {
        setLocalRunningRun(null);
      }
    }
  }, [externalRecentRuns, localRunningRun]);

  // Resize preview panel via drag
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = previewWidth;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = startX - moveEvent.clientX;
      const newWidth = Math.min(800, Math.max(360, startWidth + delta));
      setPreviewWidth(newWidth);
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [previewWidth]);

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Connection status indicator */}
      <AnimatePresence>
        {connectionStatus === "reconnecting" && (
          <motion.div
            initial={{ y: -40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -40, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
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
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-red-600/90 px-4 py-2 text-xs text-white backdrop-blur-sm"
          >
            <WifiOff className="h-3 w-3" />
            Connection lost.
            <button onClick={onReconnect} className="ml-1 underline hover:no-underline">
              Reconnect
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Desktop Sidebar */}
      <motion.aside
        animate={{ width: sidebarOpen ? 280 : 56 }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
        className="hidden lg:block h-full overflow-hidden border-r flex-shrink-0"
        style={{ borderColor: "var(--theme-border)" }}
      >
        {sidebarOpen ? (
          <div className="w-[280px] h-full">
            <ErrorBoundary fallbackLabel="Sidebar">
              <Sidebar
                activeChatId={activeChatId ?? undefined}
                onSelectChat={(chatId) => { onSelectChat(chatId); }}
                onNewChat={(session) => { onNewChat(session); }}
                onDeleteChat={onDeleteChat}
                onLogout={onLogout}
                onCollapse={() => setSidebarOpen(false)}
                chatTitleUpdate={chatTitleUpdate}
                onOpenWorkflow={() => setMainView("home")}
                recentRuns={recentRuns}
                onSelectRun={handleSelectRun}
              />
            </ErrorBoundary>
          </div>
        ) : (
          <div className="w-[56px] h-full flex flex-col items-center backdrop-blur-sm py-3" style={{ backgroundColor: "var(--theme-sidebar-bg)" }}>
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex items-center justify-center rounded-lg p-2.5 text-grey/60 hover:text-white hover:bg-white/10 transition-all duration-200 mb-2"
              aria-label="Open sidebar"
              title="Open sidebar"
            >
              <PanelLeftOpen className="h-4.5 w-4.5" />
            </button>
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex items-center justify-center rounded-lg p-2.5 text-grey/60 hover:text-white hover:bg-white/10 transition-all duration-200 mb-1"
              aria-label="New project"
              title="New project"
            >
              <Plus className="h-4.5 w-4.5" />
            </button>
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex items-center justify-center rounded-lg p-2.5 text-grey/60 hover:text-white hover:bg-white/10 transition-all duration-200"
              aria-label="Search projects"
              title="Search projects"
            >
              <Search className="h-4.5 w-4.5" />
            </button>
            <div className="w-6 border-t border-grey/20 my-3" />
            <div className="flex-1" />
            <button
              onClick={onLogout}
              className="flex items-center justify-center rounded-lg p-2.5 text-red-400/60 hover:text-red-300 hover:bg-red-500/15 border border-transparent hover:border-red-500/20 transition-all duration-200 mb-2"
              aria-label="Log out"
              title="Log out"
            >
              <LogOut className="h-4.5 w-4.5" />
            </button>
          </div>
        )}
      </motion.aside>

      {/* Mobile sidebar overlay */}
      <AnimatePresence>
        {mobileSidebarOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 bg-black/70 backdrop-blur-sm"
              onClick={() => setMobileSidebarOpen(false)}
              aria-hidden="true"
            />
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="relative z-10 h-full w-[280px] border-r border-grey/20"
            >
              <ErrorBoundary fallbackLabel="Sidebar">
                <Sidebar
                  activeChatId={activeChatId ?? undefined}
                  onSelectChat={(chatId) => { onSelectChat(chatId); setMobileSidebarOpen(false); }}
                  onNewChat={(session) => { onNewChat(session); setMobileSidebarOpen(false); }}
                  onDeleteChat={onDeleteChat}
                  onLogout={onLogout}
                  onCollapse={() => setMobileSidebarOpen(false)}
                  chatTitleUpdate={chatTitleUpdate}
                  onOpenWorkflow={() => { setMainView("home"); setMobileSidebarOpen(false); }}
                  recentRuns={recentRuns}
                  onSelectRun={(run) => { handleSelectRun(run); setMobileSidebarOpen(false); }}
                />
              </ErrorBoundary>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 h-full flex flex-col relative">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b px-3 py-2 backdrop-blur-sm" style={{ backgroundColor: "var(--theme-bg)", opacity: 0.9, borderColor: "var(--theme-border)" }}>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="lg:hidden flex items-center justify-center rounded-md p-2 text-grey hover:text-white hover:bg-white/5 transition-all duration-200"
              aria-label="Open sidebar"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-1.5">
              <div
                className={`h-2 w-2 rounded-full ${
                  connectionStatus === "connected"
                    ? "bg-green-400"
                    : connectionStatus === "reconnecting"
                    ? "bg-yellow-400 animate-pulse"
                    : "bg-red-400"
                }`}
              />
              <span className="text-xs text-grey/70 hidden sm:inline">
                {connectionStatus === "connected"
                  ? "Connected"
                  : connectionStatus === "reconnecting"
                  ? "Reconnecting"
                  : "Disconnected"}
              </span>
            </div>
          </div>

          {/* Preview toggle */}
          {hasPreviewContent && !previewOpen && (
            <motion.button
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.2 }}
              onClick={handlePreviewOpen}
              className="hidden lg:flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-grey/80 hover:text-white bg-navy/40 hover:bg-navy/60 border border-grey/15 hover:border-grey/25 transition-all duration-200"
              aria-label="Open preview"
            >
              <Eye className="h-3.5 w-3.5" />
              View Results
            </motion.button>
          )}
        </div>

        {/* Main content — switches between Home, Workflow, and Results */}
        <div className="flex-1 min-h-0">
          <AnimatePresence mode="wait">
            {mainView === "home" && (
              <motion.div
                key="home"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="h-full"
              >
                <CreationHub
                  onSelectFeature={handleSelectFeature}
                />
              </motion.div>
            )}

            {mainView === "workflow" && (
              <motion.div
                key="workflow"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.25 }}
                className="h-full"
              >
                <WorkflowView
                  pipelineType={workflowType}
                  userMessage={workflowInput}
                  onClose={() => {
                    setMainView("home");
                    if (userStoryContent || pptContent || prototypeContent) {
                      setPreviewOpen(true);
                      setPreviewManualClose(false);
                    }
                  }}
                  websocketSend={websocketSend || (() => {})}
                  pipelineState={pipelineState}
                  onStartPipeline={(type, message, agentIds) => {
                    // Create local run tracking + trigger pipeline
                    const newRun: WorkflowRun = {
                      id: crypto.randomUUID(),
                      title: message.slice(0, 60),
                      type: type as WorkflowType,
                      status: "running",
                      input: message,
                      createdAt: new Date().toISOString(),
                      agentCount: agentIds?.length || (type === "ppt" ? 10 : 12),
                    };
                    setLocalRunningRun(newRun);
                    setWorkflowInput(message);
                    if (onStartPipeline) onStartPipeline(type, message, agentIds);
                  }}
                  onResetPipeline={onResetPipeline}
                  onViewResults={(pipelineType) => {
                    if (pipelineType === "user_stories") setWorkflowType("user_stories");
                    else if (pipelineType === "ppt") setWorkflowType("ppt");
                    else if (pipelineType === "prototype") setWorkflowType("prototype");
                    // Open the preview panel with results
                    setPreviewOpen(true);
                    setPreviewManualClose(false);
                    setPreviewInitialTab("preview");
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Preview Panel — resizable, auto-opens when content is generated */}
      <AnimatePresence>
        {previewOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: previewWidth, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="hidden lg:flex h-full overflow-hidden flex-shrink-0 relative"
            style={{ borderColor: "var(--theme-border)" }}
          >
            {/* Resize handle */}
            <div
              onMouseDown={handleResizeStart}
              className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-10 group flex items-center justify-center hover:bg-white/10 transition-colors"
              style={{ borderLeft: "1px solid var(--theme-border)" }}
              aria-label="Resize preview panel"
            >
              <div className="w-0.5 h-8 rounded-full bg-grey/30 group-hover:bg-grey/60 transition-colors" />
            </div>

            <div className="flex-1 h-full overflow-hidden pl-1.5" style={{ width: previewWidth }}>
              <ErrorBoundary fallbackLabel="PreviewPanel">
                <PreviewPanel
                  userStoryContent={userStoryContent || undefined}
                  pptContent={pptContent || undefined}
                  prototypeContent={prototypeContent || undefined}
                  isStreaming={isStreaming}
                  onCollapse={handlePreviewClose}
                  initialTab={previewInitialTab}
                  onTabSelect={(tab) => setPreviewInitialTab(tab)}
                  workflowType={workflowType}
                  agentOutputs={currentAgentOutputs}
                  liveAgents={pipelineState?.agents}
                  isPipelineRunning={pipelineState?.isRunning}
                  onFollowUp={(message) => {
                    const refinedInput = `${workflowInput}\n\n---\nRefinement: ${message}`;
                    setWorkflowInput(refinedInput);
                    if (onStartPipeline) onStartPipeline(workflowType, refinedInput);
                  }}
                />
              </ErrorBoundary>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}
