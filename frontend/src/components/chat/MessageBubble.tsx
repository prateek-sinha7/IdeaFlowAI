"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  RefreshCw,
  Pencil,
  Copy,
  Check,
  Volume2,
  VolumeX,
  ChevronDown,
  ChevronRight,
  FileText,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "@/types/index";
import { useTextToSpeech } from "@/hooks/useTextToSpeech";
import { useSmoothText } from "@/hooks/useSmoothText";
import { ProcessSteps } from "./ProcessSteps";
import { ArtifactCard } from "./ArtifactCard";
import type { ChatMode } from "./ChatInput";
import type { AgentEvent } from "./runtime/blocks.types";
import { buildBlocks } from "./runtime/buildBlocks";
import { renderToolBlock } from "./runtime/tool-renderers";
import { ThinkingBlock } from "./blocks/ThinkingBlock";
import { FileOpsSummary } from "./blocks/FileOpsSummary";
import { ResultCard } from "./ResultCard";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
  streamingContent?: string;
  mode?: ChatMode;
  onRegenerate?: (messageId: string) => void;
  onEdit?: (messageId: string, newContent: string) => void;
  /**
   * Plan-01 agent event stream for an assistant turn (Phase 31, CHATUI-01). When
   * present, the coalesced ChatBlock strip (thinking / tools / file-ops) renders
   * above the markdown prose so an agent turn shows reasoning + tools, not just
   * text. Absent for plain narrator/user turns.
   */
  events?: AgentEvent[];
  /** The nonce'd deep-link seam a narrator ResultCard fires (borrow #6). */
  onRequestOpenTab?: (tab: string) => void;
}

/**
 * Render the coalesced plan-01 ChatBlock strip for an assistant turn: thinking →
 * ThinkingBlock, tool → the plan-02 renderToolBlock registry, file_ops →
 * FileOpsSummary. Text/usage blocks are omitted here — the prose is the markdown
 * body below, and usage rides the lane's token widget. Every branch keys on the
 * generic block `kind` (SC-001).
 */
function AgentBlockStrip({ events }: { events: AgentEvent[] }) {
  const blocks = buildBlocks(events);
  if (blocks.length === 0) return null;
  return (
    <div className="mb-3">
      {blocks.map((block, i) => {
        switch (block.kind) {
          case "thinking":
            return <ThinkingBlock key={i} block={block} />;
          case "tool":
            return <div key={i}>{renderToolBlock(block)}</div>;
          case "file_ops":
            return <FileOpsSummary key={i} block={block} />;
          default:
            return null;
        }
      })}
    </div>
  );
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
  events,
  onRequestOpenTab,
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

  // Issue-2 (260719-rqo): smooth the reply's growth so the coarse ~70-180-char
  // Bedrock deltas render as a steady flow instead of jumps. Only assistant text
  // streams; a static (historical) message never grows, so this is a no-op there.
  const smoothedContent = useSmoothText(displayContent, isAssistant);

  // Parse thinking blocks for assistant messages
  const { thinking, mainContent } = useMemo(() => {
    if (isAssistant) {
      return parseThinkingBlocks(smoothedContent);
    }
    return { thinking: null, mainContent: smoothedContent };
  }, [smoothedContent, isAssistant]);

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

  // --- NARRATOR RESULT CARD ---
  // A chat_reply narrator turn (carries a GENERIC cardKind) renders a ResultCard
  // instead of a prose bubble. Keyed on the generic kind (SC-001); falls back to
  // a normal assistant bubble when no deep-link seam is threaded.
  if (message.cardKind && onRequestOpenTab) {
    return (
      <motion.div
        data-testid="chat-message"
        data-role="narrator"
        data-message-id={message.id}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="flex w-full mb-6"
      >
        <div className="mr-[9px] flex-shrink-0 pt-px">
          <div className="grid h-[22px] w-[22px] place-items-center rounded-[6px] bg-surface-near-black">
            <span className="h-[7px] w-[7px] rotate-45 rounded-[1px] bg-brand" />
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <ResultCard message={message} onRequestOpenTab={onRequestOpenTab} />
        </div>
      </motion.div>
    );
  }

  // --- USER MESSAGE ---
  if (isUser) {
    return (
      <motion.div
        data-testid="chat-message"
        data-role="user"
        data-message-id={message.id}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="flex w-full justify-end mb-8 group"
      >
        {/* Hover zone covers bubble + action bar so mouse movement between them
            doesn't dismiss the bar before the click lands. */}
        <div
          className="relative max-w-[86%] flex items-start gap-3"
          onMouseEnter={() => setShowActions(true)}
          onMouseLeave={() => setShowActions(false)}
        >
          {/* Message content */}
          <div className="flex-1 min-w-0">
            {/* User message container — file-only: no bubble wrapper, chips render bare.
                Text present (with or without files): brand-fill bubble wraps everything. */}
            {(() => {
              const fileAtts = (message.attachments ?? []).filter((a) => a.kind === "file");
              const fileOnly = fileAtts.length > 0 && !displayContent;

              const fileChips = fileAtts.length > 0 ? (
                <div className={`flex flex-col gap-[5px] ${!fileOnly ? "mb-[8px]" : ""}`}>
                  {fileAtts.map((a, i) => (
                    <div
                      key={`${a.name}-${i}`}
                      className="inline-flex items-center gap-[8px] rounded-[8px] border border-brand-border bg-brand-fill px-[10px] py-[7px]"
                    >
                      <span className="grid h-[24px] w-[24px] flex-none place-items-center rounded-[6px] bg-white/70">
                        <FileText className="h-[13px] w-[13px] text-brand" strokeWidth={1.7} />
                      </span>
                      <span className="font-sans text-[12px] font-semibold text-ink-900 break-all leading-[1.3]">
                        {a.name || "Attached file"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null;

              if (fileOnly) {
                // No bubble background — chips stand alone
                return isEditing ? null : fileChips;
              }

              return (
                <div className="rounded-[14px_14px_4px_14px] border border-brand-border bg-brand-fill px-[13px] py-[10px]">
                  {isEditing ? (
                    <div className="flex flex-col gap-2">
                      <textarea
                        aria-label="Edit message"
                        name="edit-message"
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        onKeyDown={handleEditKeyDown}
                        className="w-full min-h-[60px] resize-none rounded-lg border border-grey/20 bg-black/40 px-3 py-2 text-white text-[15px] focus:border-grey/40 focus:outline-none leading-relaxed"
                        autoFocus
                      />
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => { setEditContent(message.content); setIsEditing(false); }}
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
                    <>
                      {fileChips}
                      {displayContent && (
                        <p className="font-serif text-[13.5px] leading-[1.5] text-ink-800 whitespace-pre-wrap">
                          {displayContent}
                        </p>
                      )}
                    </>
                  )}
                </div>
              );
            })()}

            {/* Action bar — always mounted, fades in on hover via CSS opacity. */}
            {!isEditing && (
              <div className={`flex justify-end mt-1.5 transition-opacity duration-150 ${showActions || copied ? "opacity-100" : "opacity-0 pointer-events-none"}`}>
                <div className="flex items-center gap-0.5 rounded-full glass-action-bar px-2 py-1">
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/80 hover:text-grey/60 transition-colors"
                    aria-label="Copy message"
                  >
                    {copied
                      ? <Check className="h-3 w-3 text-green-400" />
                      : <Copy className="h-3 w-3" />
                    }
                  </button>
                  {onEdit && (
                    <button
                      onClick={() => setIsEditing(true)}
                      className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/80 hover:text-grey/60 transition-colors"
                      aria-label="Edit message"
                    >
                      <Pencil className="h-3 w-3" />
                    </button>
                  )}
                  <span className="text-[10px] text-grey/40 px-1">{formattedTime}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </motion.div>
    );
  }

  // --- ASSISTANT MESSAGE ---
  return (
    <motion.div
      data-testid="chat-message"
      data-role="assistant"
      data-message-id={message.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="flex w-full mb-8 group"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* AI Avatar — the mock's 22px near-black square with a rotated brand
          diamond (Phase 39, RUNUI-06). */}
      <div className="mr-[9px] flex-shrink-0 pt-px">
        <div className="grid h-[22px] w-[22px] place-items-center rounded-[6px] bg-surface-near-black">
          <span className="h-[7px] w-[7px] rotate-45 rounded-[1px] bg-brand" />
        </div>
      </div>

      <div className="relative flex-1 min-w-0 font-serif text-[13.5px] leading-[1.55] text-ink-700">
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

        {/* Agent block strip — plan-01 ChatBlocks (thinking / tools / file-ops)
            coalesced from the turn's event stream, above the prose. */}
        {events && events.length > 0 && <AgentBlockStrip events={events} />}

        {/* Message content — NO bubble, flows naturally like a document */}
        <div className={`markdown-content ${isStreaming ? "streaming-cursor" : ""}`}>
          <ReactMarkdown>{mainContent}</ReactMarkdown>
        </div>

        {/* Artifact card — inline card for generated content */}
        {message.artifact && (
          <div className="mt-3">
            <ArtifactCard
              type={message.artifact.type}
              filename={message.artifact.filename}
              content={message.artifact.content}
              summary={message.artifact.summary}
            />
          </div>
        )}

        {/* Floating action bar — always mounted, fades via CSS opacity on hover */}
        {!isStreaming && (
          <div className={`mt-3 inline-flex items-center gap-0.5 rounded-full glass-action-bar px-2 py-1 transition-opacity duration-150 ${showActions || copied ? "opacity-100" : "opacity-0 pointer-events-none"}`}>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/70 hover:text-grey/50 transition-colors"
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
                className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/70 hover:text-grey/50 transition-colors"
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
                className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-grey/70 hover:text-grey/50 transition-colors"
                aria-label="Regenerate response"
              >
                <RefreshCw className="h-3 w-3" />
              </button>
            )}

            <span className="text-[10px] text-grey/40 px-1">{formattedTime}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
