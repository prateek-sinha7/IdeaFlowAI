"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  RefreshCw,
  Pencil,
  Sparkles,
  User,
  Copy,
  Check,
  Volume2,
  VolumeX,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "@/types/index";
import { useTextToSpeech } from "@/hooks/useTextToSpeech";
import { ProcessSteps } from "./ProcessSteps";
import type { ChatMode } from "./ChatInput";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
  streamingContent?: string;
  mode?: ChatMode;
  onRegenerate?: (messageId: string) => void;
  onEdit?: (messageId: string, newContent: string) => void;
}

const MODE_LABELS: Record<string, { emoji: string; label: string }> = {
  thinking: { emoji: "🧠", label: "Thinking" },
  deep_research: { emoji: "🔬", label: "Deep Research" },
  web_search: { emoji: "🌐", label: "Web Search" },
  quiz: { emoji: "📝", label: "Quiz" },
};

/**
 * Parses content to extract <thinking>...</thinking> blocks.
 */
function parseThinkingBlocks(content: string): {
  thinking: string | null;
  mainContent: string;
} {
  const thinkingRegex = /<thinking>([\s\S]*?)<\/thinking>/g;
  const matches: string[] = [];
  let match;

  while ((match = thinkingRegex.exec(content)) !== null) {
    matches.push(match[1].trim());
  }

  const mainContent = content.replace(thinkingRegex, "").trim();

  return {
    thinking: matches.length > 0 ? matches.join("\n\n") : null,
    mainContent,
  };
}

/**
 * Renders a single chat message with Claude/ChatGPT-style design.
 * AI messages: NO bubble — text flows naturally like a document with avatar on left.
 * User messages: Subtle rounded container, right-aligned.
 * Action bar: Floating glass-morphism pill below message on hover.
 * Thinking blocks: Gradient left border, collapsible with smooth animation.
 * Streaming: Blinking cursor at end of content.
 */
export function MessageBubble({
  message,
  isStreaming = false,
  streamingContent,
  mode,
  onRegenerate,
  onEdit,
}: MessageBubbleProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);
  const [showActions, setShowActions] = useState(false);
  const [copied, setCopied] = useState(false);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);

  const { isSpeaking, speak, stop, isSupported: ttsSupported } = useTextToSpeech();

  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  const displayContent =
    isStreaming && streamingContent !== undefined
      ? streamingContent
      : message.content;

  // Parse thinking blocks for assistant messages
  const { thinking, mainContent } = useMemo(() => {
    if (isAssistant) {
      return parseThinkingBlocks(displayContent);
    }
    return { thinking: null, mainContent: displayContent };
  }, [displayContent, isAssistant]);

  const handleEditSubmit = () => {
    if (editContent.trim() && editContent !== message.content) {
      onEdit?.(message.id, editContent.trim());
    }
    setIsEditing(false);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleEditSubmit();
    }
    if (e.key === "Escape") {
      setEditContent(message.content);
      setIsEditing(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(displayContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleTTS = () => {
    if (isSpeaking) {
      stop();
    } else {
      speak(mainContent);
    }
  };

  const formattedTime = new Date(message.createdAt).toLocaleTimeString(
    undefined,
    { hour: "2-digit", minute: "2-digit" }
  );

  // --- USER MESSAGE ---
  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="flex w-full justify-end mb-8 group"
        onMouseEnter={() => setShowActions(true)}
        onMouseLeave={() => setShowActions(false)}
      >
        <div className="relative max-w-[80%] flex items-start gap-3">
          {/* Message content */}
          <div className="flex-1 min-w-0">
            {/* User message container */}
            <div
              className="rounded-2xl px-5 py-3.5 border"
              style={{
                backgroundColor: "var(--theme-accent)",
                borderColor: "var(--theme-border)",
                opacity: 0.85,
              }}
            >
              {isEditing ? (
                <div className="flex flex-col gap-2">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    onKeyDown={handleEditKeyDown}
                    className="w-full min-h-[60px] resize-none rounded-lg border border-grey/20 bg-black/40 px-3 py-2 text-white text-[15px] focus:border-grey/40 focus:outline-none leading-relaxed"
                    autoFocus
                  />
                  <div className="flex gap-2 justify-end">
                    <button
                      onClick={() => {
                        setEditContent(message.content);
                        setIsEditing(false);
                      }}
                      className="rounded-lg px-3 py-1.5 text-xs text-grey hover:text-white transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleEditSubmit}
                      className="rounded-lg bg-white/10 px-3 py-1.5 text-xs text-white hover:bg-white/15 transition-colors"
                    >
                      Save & Send
                    </button>
                  </div>
                </div>
              ) : (
                <p className="text-[15px] leading-relaxed text-white whitespace-pre-wrap">
                  {displayContent}
                </p>
              )}
            </div>

            {/* Action bar */}
            {!isEditing && (
              <AnimatePresence>
                {showActions && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.15 }}
                    className="flex justify-end mt-1.5"
                  >
                    <div className="flex items-center gap-0.5 rounded-full glass-action-bar px-2 py-1">
                      <button
                        onClick={handleCopy}
                        className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/80 hover:text-white transition-colors"
                        aria-label="Copy message"
                      >
                        {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                      </button>
                      {onEdit && (
                        <button
                          onClick={() => setIsEditing(true)}
                          className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/80 hover:text-white transition-colors"
                          aria-label="Edit message"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                      )}
                      <span className="text-[10px] text-grey/40 px-1">{formattedTime}</span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            )}
          </div>

          {/* User Avatar */}
          <div className="flex-shrink-0 pt-1">
            <div
              className="flex h-7 w-7 items-center justify-center rounded-full border"
              style={{ backgroundColor: "var(--theme-accent)", borderColor: "var(--theme-border)" }}
            >
              <User className="h-3.5 w-3.5 text-white" />
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  // --- ASSISTANT MESSAGE ---
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="flex w-full mb-8 group"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* AI Avatar */}
      <div className="mr-4 flex-shrink-0 pt-1">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-navy/60 border border-grey/15">
          <Sparkles className="h-3.5 w-3.5 text-white/80" />
        </div>
      </div>

      <div className="relative flex-1 min-w-0">
        {/* Mode badge */}
        {mode && mode !== "default" && MODE_LABELS[mode] && (
          <div className="mb-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-navy/30 border border-grey/10 px-2.5 py-0.5 text-[11px] text-grey/70">
              <span>{MODE_LABELS[mode].emoji}</span>
              <span>{MODE_LABELS[mode].label}</span>
            </span>
          </div>
        )}

        {/* Process steps — embedded in message history */}
        {message.steps && message.steps.length > 0 && (
          <div className="mb-3">
            <ProcessSteps steps={message.steps} />
          </div>
        )}

        {/* Thinking block — gradient left border, collapsible */}
        {thinking && (
          <div className="mb-4">
            <button
              onClick={() => setThinkingExpanded(!thinkingExpanded)}
              className="flex items-center gap-1.5 text-[12px] text-grey/60 hover:text-grey/90 transition-colors mb-2"
            >
              {thinkingExpanded ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
              <span className="font-medium">Thought process</span>
            </button>
            <AnimatePresence>
              {thinkingExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: "easeInOut" }}
                  className="overflow-hidden"
                >
                  <div className="relative pl-4 py-2 text-[13px] text-grey/60 leading-relaxed whitespace-pre-wrap">
                    {/* Gradient left border */}
                    <div className="absolute left-0 top-0 bottom-0 w-[2px] rounded-full bg-gradient-to-b from-blue-400/60 via-purple-400/40 to-transparent" />
                    {thinking}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Message content — NO bubble, flows naturally like a document */}
        <div className={`markdown-content ${isStreaming ? "streaming-cursor" : ""}`}>
          <ReactMarkdown>{mainContent}</ReactMarkdown>
        </div>

        {/* Floating action bar — glass morphism pill below message on hover */}
        {!isStreaming && (
          <AnimatePresence>
            {showActions && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.15 }}
                className="mt-3 inline-flex items-center gap-0.5 rounded-full glass-action-bar px-2 py-1"
              >
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/70 hover:text-white transition-colors"
                  aria-label="Copy message"
                >
                  {copied ? (
                    <Check className="h-3 w-3 text-green-400" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                </button>

                {ttsSupported && (
                  <button
                    onClick={handleTTS}
                    className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/70 hover:text-white transition-colors"
                    aria-label={isSpeaking ? "Stop reading" : "Read aloud"}
                  >
                    {isSpeaking ? (
                      <VolumeX className="h-3 w-3 text-red-400" />
                    ) : (
                      <Volume2 className="h-3 w-3" />
                    )}
                  </button>
                )}

                {onRegenerate && (
                  <button
                    onClick={() => onRegenerate(message.id)}
                    className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/70 hover:text-white transition-colors"
                    aria-label="Regenerate response"
                  >
                    <RefreshCw className="h-3 w-3" />
                  </button>
                )}

                <span className="text-[10px] text-grey/40 px-1">{formattedTime}</span>
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </div>
    </motion.div>
  );
}
