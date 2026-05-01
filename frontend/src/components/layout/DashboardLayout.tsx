"use client";

import { useCallback, useState } from "react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import type { ChatMessage, ChatSession } from "@/types/index";
import type { ConnectionStatus } from "@/hooks/useWebSocket";

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
  onSelectChat: (chatId: string) => void;
  onNewChat: (chatSession: ChatSession) => void;
  onReconnect: () => void;
}

/**
 * DashboardLayout provides the three-panel flex layout:
 * - Sidebar (fixed 280px width)
 * - ChatPanel (flex-grow, takes remaining space)
 * - PreviewPanel (fixed 420px width)
 *
 * On screens <1024px, the Sidebar collapses to a toggleable overlay.
 * Receives all state and handlers from DashboardPage and wires them to child components.
 */
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
  onSelectChat,
  onNewChat,
  onReconnect,
}: DashboardLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleRegenerateMessage = useCallback(
    (messageId: string) => {
      // Find the last user message before this assistant message and re-send it
      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex === -1) return;

      // Look backwards for the preceding user message
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
    (messageId: string, newContent: string) => {
      // Re-send the edited content as a new message
      onSendMessage(newContent);
    },
    [onSendMessage]
  );

  return (
    <div className="flex h-screen w-full overflow-hidden bg-black">
      {/* Connection status indicator */}
      {connectionStatus === "reconnecting" && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-yellow-600/90 px-4 py-1 text-center text-xs text-white">
          Reconnecting...
        </div>
      )}
      {connectionStatus === "failed" && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-red-600/90 px-4 py-1 text-center text-xs text-white">
          Connection lost.{" "}
          <button
            onClick={onReconnect}
            className="underline hover:no-underline ml-1"
          >
            Reconnect
          </button>
        </div>
      )}

      {/* Sidebar - fixed width on desktop, overlay on mobile */}
      {/* Desktop sidebar */}
      <aside className="hidden lg:block w-[280px] min-w-[280px] h-full border-r border-grey/30">
        <ErrorBoundary fallbackLabel="Sidebar">
          <Sidebar
            activeChatId={activeChatId ?? undefined}
            onSelectChat={onSelectChat}
            onNewChat={onNewChat}
          />
        </ErrorBoundary>
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          {/* Sidebar panel */}
          <aside className="relative z-10 h-full w-[280px] border-r border-grey/30">
            <ErrorBoundary fallbackLabel="Sidebar">
              <Sidebar
                activeChatId={activeChatId ?? undefined}
                onSelectChat={(chatId) => {
                  onSelectChat(chatId);
                  setSidebarOpen(false);
                }}
                onNewChat={(session) => {
                  onNewChat(session);
                  setSidebarOpen(false);
                }}
              />
            </ErrorBoundary>
          </aside>
        </div>
      )}

      {/* Chat Panel - flex-grow */}
      <main className="flex-1 min-w-0 h-full flex flex-col">
        {/* Mobile sidebar toggle */}
        <div className="lg:hidden flex items-center border-b border-grey/30 px-4 py-2">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded p-2 text-grey hover:text-white hover:bg-navy transition-colors"
            aria-label="Open sidebar"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
        </div>

        <div className="flex-1 min-h-0">
          <ErrorBoundary fallbackLabel="ChatPanel">
            <ChatPanel
              messages={messages}
              isStreaming={isStreaming}
              streamingContent={streamingContent}
              onSendMessage={onSendMessage}
              onRegenerateMessage={handleRegenerateMessage}
              onEditMessage={handleEditMessage}
            />
          </ErrorBoundary>
        </div>
      </main>

      {/* Preview Panel - fixed width */}
      <aside className="hidden lg:block w-[420px] min-w-[420px] h-full border-l border-grey/30">
        <ErrorBoundary fallbackLabel="PreviewPanel">
          <PreviewPanel
            userStoryContent={userStoryContent || undefined}
            pptContent={pptContent || undefined}
            prototypeContent={prototypeContent || undefined}
          />
        </ErrorBoundary>
      </aside>
    </div>
  );
}
