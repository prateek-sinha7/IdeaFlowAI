"use client";

import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { Sparkles, Lightbulb, Code, FileText, Layers } from "lucide-react";
import type { ChatMessage, ProcessStep } from "@/types/index";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { ProcessSteps } from "./ProcessSteps";
import { ChatInput } from "./ChatInput";
import { ErrorMessage } from "./ErrorMessage";
import type { ChatMode } from "./ChatInput";

export interface ChatPanelProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  onSendMessage: (content: string) => void;
  onSendMessageWithMode?: (content: string, mode: ChatMode) => void;
  onRegenerateMessage?: (messageId: string) => void;
  onEditMessage?: (messageId: string, newContent: string) => void;
  messageMode?: ChatMode;
  processSteps?: ProcessStep[];
}

const SUGGESTION_CHIPS = [
  {
    icon: Lightbulb,
    label: "Brainstorm a product idea",
    description: "Generate creative concepts and validate them",
  },
  {
    icon: Code,
    label: "Design a technical architecture",
    description: "Plan scalable systems and infrastructure",
  },
  {
    icon: FileText,
    label: "Write user stories for my app",
    description: "Create detailed requirements and acceptance criteria",
  },
  {
    icon: Layers,
    label: "Create a presentation deck",
    description: "Build compelling slides for stakeholders",
  },
];

/**
 * Main chat panel with a scrollable message list and input bar.
 * Features Claude-style centered layout with empty state greeting and suggestion chips.
 */
export function ChatPanel({
  messages,
  isStreaming,
  streamingContent,
  onSendMessage,
  onSendMessageWithMode,
  onRegenerateMessage,
  onEditMessage,
  messageMode,
  processSteps,
}: ChatPanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom during streaming and when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, isStreaming]);

  const hasMessages = messages.length > 0 || isStreaming;

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: 'var(--theme-bg)' }}>
      {/* Scrollable message list */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-4 py-8 md:px-6 relative"
      >
        {/* Subtle dot grid pattern */}
        <div className="dot-grid absolute inset-0 pointer-events-none" />
        {!hasMessages ? (
          <div className="flex h-full flex-col items-center justify-center px-4 relative overflow-hidden">
            {/* Animated gradient orbs — floating ambient background */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
              <motion.div
                animate={{
                  x: [0, 80, -40, 60, 0],
                  y: [0, -60, 40, -30, 0],
                  scale: [1, 1.2, 0.9, 1.1, 1],
                }}
                transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
                className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full opacity-[0.07]"
                style={{ background: "radial-gradient(circle, var(--theme-accent), transparent 70%)", filter: "blur(60px)" }}
              />
              <motion.div
                animate={{
                  x: [0, -60, 50, -30, 0],
                  y: [0, 50, -40, 60, 0],
                  scale: [1, 0.9, 1.15, 0.95, 1],
                }}
                transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
                className="absolute bottom-1/4 right-1/4 w-80 h-80 rounded-full opacity-[0.05]"
                style={{ background: "radial-gradient(circle, #7c3aed, transparent 70%)", filter: "blur(70px)" }}
              />
              <motion.div
                animate={{
                  x: [0, 40, -60, 20, 0],
                  y: [0, -30, 50, -50, 0],
                  scale: [1, 1.1, 0.85, 1.05, 1],
                }}
                transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
                className="absolute top-1/2 right-1/3 w-64 h-64 rounded-full opacity-[0.04]"
                style={{ background: "radial-gradient(circle, #3b82f6, transparent 70%)", filter: "blur(50px)" }}
              />
            </div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: "easeOut" }}
              className="text-center max-w-2xl"
            >
              {/* Greeting icon with glow */}
              <motion.div
                initial={{ scale: 0.6, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.1, type: "spring", stiffness: 200 }}
                className="relative mx-auto mb-8"
              >
                {/* Glow ring */}
                <motion.div
                  animate={{ opacity: [0.3, 0.6, 0.3], scale: [1, 1.15, 1] }}
                  transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                  className="absolute inset-0 rounded-2xl"
                  style={{ background: "radial-gradient(circle, var(--theme-accent), transparent 70%)", filter: "blur(20px)", opacity: 0.4 }}
                />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-navy/40 border border-grey/10">
                  <Sparkles className="h-8 w-8 text-white/80" />
                </div>
              </motion.div>

              {/* Animated gradient greeting */}
              <motion.h1
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="gradient-text text-4xl font-semibold tracking-tight mb-3"
                style={{ color: 'var(--theme-fg)' }}
              >
                What can I help you with?
              </motion.h1>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.4 }}
                className="text-[15px] mb-10 leading-relaxed"
                style={{ color: 'var(--theme-muted)' }}
              >
                Describe your idea and I&apos;ll help you create user stories, presentations, and prototypes.
              </motion.p>

              {/* 2x2 Suggestion chips grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl mx-auto">
                {SUGGESTION_CHIPS.map((chip, index) => (
                  <motion.button
                    key={chip.label}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.5 + index * 0.08 }}
                    whileHover={{ scale: 1.02, backgroundColor: "rgba(0, 31, 63, 0.5)" }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => onSendMessage(chip.label)}
                    className="relative flex items-start gap-3 rounded-xl border border-grey/12 bg-navy/20 px-4 py-3.5 text-left transition-all duration-200 hover:border-grey/25 chip-shimmer overflow-hidden"
                  >
                    <div className="flex-shrink-0 mt-0.5">
                      <chip.icon className="h-4 w-4 text-grey/60" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm text-white/90 font-medium truncate">
                        {chip.label}
                      </div>
                      <div className="text-xs text-grey/50 mt-0.5 line-clamp-1">
                        {chip.description}
                      </div>
                    </div>
                  </motion.button>
                ))}
              </div>
            </motion.div>
          </div>
        ) : (
          <div className="mx-auto max-w-4xl">
            {messages.map((message, index) => {
              const isLastAssistant =
                isStreaming &&
                message.role === "assistant" &&
                index === messages.length - 1;

              // Detect error messages
              const isError =
                message.role === "assistant" &&
                (message.content.startsWith("Error:") ||
                  (message as ChatMessage & { isError?: boolean }).isError === true);

              if (isError) {
                // Parse error details from content
                const errorContent = message.content.startsWith("Error: ")
                  ? message.content.slice(7)
                  : message.content;

                // Try to extract code and recoverable from structured error
                let errorCode: string | undefined;
                let recoverable = true;

                if (errorContent.includes("[code:")) {
                  const codeMatch = errorContent.match(/\[code:(\w+)\]/);
                  const recoverableMatch = errorContent.match(/\[recoverable:(true|false)\]/);
                  if (codeMatch) errorCode = codeMatch[1];
                  if (recoverableMatch) recoverable = recoverableMatch[1] === "true";
                }

                const displayMessage = errorContent
                  .replace(/\[code:\w+\]/, "")
                  .replace(/\[recoverable:(true|false)\]/, "")
                  .trim();

                return (
                  <ErrorMessage
                    key={message.id}
                    message={displayMessage}
                    code={errorCode}
                    recoverable={recoverable}
                    onRetry={
                      recoverable
                        ? () => {
                            // Find the last user message and resend
                            for (let i = index - 1; i >= 0; i--) {
                              if (messages[i].role === "user") {
                                onSendMessage(messages[i].content);
                                break;
                              }
                            }
                          }
                        : undefined
                    }
                  />
                );
              }

              return (
                <MessageBubble
                  key={message.id}
                  message={message}
                  isStreaming={isLastAssistant}
                  streamingContent={
                    isLastAssistant ? streamingContent : undefined
                  }
                  mode={isLastAssistant ? messageMode : undefined}
                  onRegenerate={onRegenerateMessage}
                  onEdit={onEditMessage}
                />
              );
            })}

            {/* Process steps indicator — persists after streaming completes */}
            {processSteps && processSteps.length > 0 && (
              <div className="mx-auto max-w-4xl">
                <ProcessSteps steps={processSteps} />
              </div>
            )}

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
      <ChatInput onSendMessage={onSendMessage} onSendMessageWithMode={onSendMessageWithMode} isStreaming={isStreaming} />
    </div>
  );
}
