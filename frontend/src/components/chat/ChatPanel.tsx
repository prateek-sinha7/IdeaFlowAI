"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/index";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { ChatInput } from "./ChatInput";

export interface ChatPanelProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  onSendMessage: (content: string) => void;
  onRegenerateMessage?: (messageId: string) => void;
  onEditMessage?: (messageId: string, newContent: string) => void;
}

/**
 * Main chat panel with a scrollable message list and input bar.
 * Supports streaming display with auto-scroll, regenerate, and edit actions.
 * Follows the Claude-style chat UI layout with enterprise-dark theme.
 */
export function ChatPanel({
  messages,
  isStreaming,
  streamingContent,
  onSendMessage,
  onRegenerateMessage,
  onEditMessage,
}: ChatPanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom during streaming and when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, isStreaming]);

  const hasMessages = messages.length > 0 || isStreaming;

  return (
    <div className="flex h-full flex-col bg-black">
      {/* Scrollable message list */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-4 py-6 md:px-6"
      >
        {!hasMessages ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-center text-grey text-sm">
              Start a conversation by typing a message below.
            </p>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl">
            {messages.map((message, index) => {
              // Determine if this is the last assistant message currently streaming
              const isLastAssistant =
                isStreaming &&
                message.role === "assistant" &&
                index === messages.length - 1;

              return (
                <MessageBubble
                  key={message.id}
                  message={message}
                  isStreaming={isLastAssistant}
                  streamingContent={
                    isLastAssistant ? streamingContent : undefined
                  }
                  onRegenerate={onRegenerateMessage}
                  onEdit={onEditMessage}
                />
              );
            })}

            {/* Typing indicator when streaming but no assistant message yet */}
            {isStreaming &&
              (messages.length === 0 ||
                messages[messages.length - 1].role !== "assistant") && (
                <TypingIndicator />
              )}

            {/* Scroll anchor */}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <ChatInput onSendMessage={onSendMessage} isStreaming={isStreaming} />
    </div>
  );
}
