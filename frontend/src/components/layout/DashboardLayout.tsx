"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  PanelLeftOpen,
  PanelRightOpen,
  Plus,
  Search,
  LogOut,
  WifiOff,
  RefreshCw,
  Eye,
} from "lucide-react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import type { ChatMessage, ChatSession, ProcessStep } from "@/types/index";
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
}

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
}: DashboardLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [previewOpen, setPreviewOpen] = useState(false); // Hidden by default — like Claude
  const [previewManualClose, setPreviewManualClose] = useState(false); // Track if user manually closed
  const [previewInitialTab, setPreviewInitialTab] = useState<string | undefined>(undefined);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const prevContentRef = useRef({ userStory: "", ppt: "", prototype: "" });

  // Check if any preview content exists
  const hasPreviewContent = !!(userStoryContent || pptContent || prototypeContent);

  // Auto-open preview when NEW content arrives (like Claude artifacts)
  useEffect(() => {
    const prev = prevContentRef.current;
    const hasNewUserStory = userStoryContent && !prev.userStory;
    const hasNewPpt = pptContent && !prev.ppt;
    const hasNewPrototype = prototypeContent && !prev.prototype;

    // Auto-open if new content appeared and user hasn't manually closed
    if ((hasNewUserStory || hasNewPpt || hasNewPrototype) && !previewManualClose) {
      setPreviewOpen(true);

      // Auto-select the tab that has new content
      if (hasNewUserStory) setPreviewInitialTab("user-stories");
      else if (hasNewPpt) setPreviewInitialTab("ppt");
      else if (hasNewPrototype) setPreviewInitialTab("prototype");
    }

    prevContentRef.current = {
      userStory: userStoryContent,
      ppt: pptContent,
      prototype: prototypeContent,
    };
  }, [userStoryContent, pptContent, prototypeContent, previewManualClose]);

  // Reset manual close flag when a new chat is selected or created
  useEffect(() => {
    setPreviewManualClose(false);
  }, [activeChatId]);

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

  const handleRegenerateMessage = useCallback(
    (messageId: string) => {
      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex === -1) return;
      for (let i = msgIndex - 1; i >= 0; i--) {
        if (messages[i].role === "user") {
          onSendMessage(messages[i].content);
          break;
        }
      }
    },
    [messages, onSendMessage]
  );

  const handleEditMessage = useCallback(
    (_messageId: string, newContent: string) => {
      onSendMessage(newContent);
    },
    [onSendMessage]
  );

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ backgroundColor: 'var(--theme-bg)' }}>
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

      {/* Desktop Sidebar — toggles between full (280px) and mini rail (56px) */}
      <motion.aside
        animate={{ width: sidebarOpen ? 280 : 56 }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
        className="hidden lg:block h-full overflow-hidden border-r flex-shrink-0"
        style={{ borderColor: 'var(--theme-border)' }}
      >
        {sidebarOpen ? (
          <div className="w-[280px] h-full">
            <ErrorBoundary fallbackLabel="Sidebar">
              <Sidebar
                activeChatId={activeChatId ?? undefined}
                onSelectChat={onSelectChat}
                onNewChat={onNewChat}
                onDeleteChat={onDeleteChat}
                onLogout={onLogout}
                onCollapse={() => setSidebarOpen(false)}
                chatTitleUpdate={chatTitleUpdate}
              />
            </ErrorBoundary>
          </div>
        ) : (
          <div className="w-[56px] h-full flex flex-col items-center backdrop-blur-sm py-3" style={{ backgroundColor: 'var(--theme-sidebar-bg)' }}>
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
              aria-label="New chat"
              title="New chat"
            >
              <Plus className="h-4.5 w-4.5" />
            </button>
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex items-center justify-center rounded-lg p-2.5 text-grey/60 hover:text-white hover:bg-white/10 transition-all duration-200"
              aria-label="Search chats"
              title="Search chats"
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
                />
              </ErrorBoundary>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      {/* Chat Panel */}
      <main className="flex-1 min-w-0 h-full flex flex-col relative">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b px-3 py-2 backdrop-blur-sm" style={{ backgroundColor: 'var(--theme-bg)', opacity: 0.9, borderColor: 'var(--theme-border)' }}>
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

          {/* Preview toggle — only show when there's content and panel is closed */}
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
              Preview
            </motion.button>
          )}
        </div>

        <div className="flex-1 min-h-0">
          <ErrorBoundary fallbackLabel="ChatPanel">
            <ChatPanel
              messages={messages}
              isStreaming={isStreaming}
              streamingContent={streamingContent}
              onSendMessage={onSendMessage}
              onSendMessageWithMode={onSendMessageWithMode}
              onRegenerateMessage={handleRegenerateMessage}
              onEditMessage={handleEditMessage}
              messageMode={messageMode}
              processSteps={processSteps}
            />
          </ErrorBoundary>
        </div>
      </main>

      {/* Preview Panel — hidden by default, auto-opens when content arrives (like Claude artifacts) */}
      <AnimatePresence>
        {previewOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 420, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="hidden lg:block h-full overflow-hidden border-l flex-shrink-0"
            style={{ borderColor: 'var(--theme-border)' }}
          >
            <div className="w-[420px] h-full">
              <ErrorBoundary fallbackLabel="PreviewPanel">
                <PreviewPanel
                  userStoryContent={userStoryContent || undefined}
                  pptContent={pptContent || undefined}
                  prototypeContent={prototypeContent || undefined}
                  isStreaming={isStreaming}
                  onCollapse={handlePreviewClose}
                  initialTab={previewInitialTab}
                  onTabSelect={(tab) => setPreviewInitialTab(tab)}
                />
              </ErrorBoundary>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}
