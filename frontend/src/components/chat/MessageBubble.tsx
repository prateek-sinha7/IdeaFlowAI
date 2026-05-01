"use client";

import { useState } from "react";
import type { ChatMessage } from "@/types/index";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
  streamingContent?: string;
  onRegenerate?: (messageId: string) => void;
  onEdit?: (messageId: string, newContent: string) => void;
}

/**
 * Renders a single chat message bubble.
 * User messages are right-aligned with a dark background.
 * AI messages are left-aligned with a lighter (navy) background.
 * Supports "Regenerate" action on AI messages and "Edit" action on user messages.
 */
export function MessageBubble({
  message,
  isStreaming = false,
  streamingContent,
  onRegenerate,
  onEdit,
}: MessageBubbleProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);

  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  const displayContent =
    isStreaming && streamingContent !== undefined
      ? streamingContent
      : message.content;

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

  return (
    <div
      className={`fade-in-up flex w-full mb-4 ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      <div
        className={`relative group max-w-[80%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-white/10 text-white"
            : "bg-navy text-white"
        }`}
      >
        {/* Message content */}
        {isEditing ? (
          <div className="flex flex-col gap-2">
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              onKeyDown={handleEditKeyDown}
              className="w-full min-h-[60px] resize-none rounded border border-grey/30 bg-black/50 px-3 py-2 text-white text-sm focus:border-white focus:outline-none"
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setEditContent(message.content);
                  setIsEditing(false);
                }}
                className="rounded px-3 py-1 text-xs text-grey hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleEditSubmit}
                className="rounded bg-white/10 px-3 py-1 text-xs text-white hover:bg-white/20 transition-colors"
              >
                Save & Send
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {displayContent}
          </p>
        )}

        {/* Action buttons - shown on hover for completed messages */}
        {!isEditing && !isStreaming && (
          <div className="absolute -bottom-6 right-0 hidden group-hover:flex gap-2">
            {isAssistant && onRegenerate && (
              <button
                onClick={() => onRegenerate(message.id)}
                className="rounded px-2 py-0.5 text-xs text-grey hover:text-white transition-colors"
                aria-label="Regenerate response"
              >
                Regenerate
              </button>
            )}
            {isUser && onEdit && (
              <button
                onClick={() => setIsEditing(true)}
                className="rounded px-2 py-0.5 text-xs text-grey hover:text-white transition-colors"
                aria-label="Edit message"
              >
                Edit
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
