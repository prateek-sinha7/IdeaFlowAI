"use client";

import { useState, useCallback } from "react";

interface ChatInputProps {
  onSendMessage: (content: string) => void;
  isStreaming: boolean;
}

/**
 * Chat input bar with a text input and send button.
 * Supports Enter-to-send (Shift+Enter for newline).
 * Disabled while streaming is in progress.
 */
export function ChatInput({ onSendMessage, isStreaming }: ChatInputProps) {
  const [value, setValue] = useState("");

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (trimmed && !isStreaming) {
      onSendMessage(trimmed);
      setValue("");
    }
  }, [value, isStreaming, onSendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-grey/30 p-4">
      <div className="flex gap-2 items-end">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message..."
          disabled={isStreaming}
          rows={1}
          className="flex-1 resize-none rounded border border-grey/30 bg-navy px-3 py-2 text-white text-sm placeholder-grey/50 focus:border-white focus:outline-none focus:ring-1 focus:ring-white disabled:opacity-50 max-h-32 overflow-y-auto"
          aria-label="Chat message input"
        />
        <button
          onClick={handleSend}
          disabled={isStreaming || !value.trim()}
          className="rounded bg-white px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-85 disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Send message"
        >
          Send
        </button>
      </div>
    </div>
  );
}
