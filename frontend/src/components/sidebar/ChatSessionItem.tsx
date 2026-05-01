"use client";

import type { ChatSession } from "@/types/index";

interface ChatSessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onClick: () => void;
}

/**
 * Formats a timestamp into a relative time string (e.g., "2 hours ago").
 * Falls back to a short date for older timestamps.
 */
function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) {
    return "just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  }
  if (diffHours < 24) {
    return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  }
  if (diffDays < 7) {
    return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/**
 * ChatSessionItem displays a single chat session in the sidebar list.
 * Shows the chat title and a relative timestamp.
 * Highlights the active/selected session with a distinct background.
 */
export function ChatSessionItem({
  session,
  isActive,
  onClick,
}: ChatSessionItemProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-md px-3 py-2.5 transition-colors duration-200 ${
        isActive
          ? "bg-white/10 border border-grey/40 text-white"
          : "text-grey hover:bg-white/5 hover:text-white border border-transparent"
      }`}
      aria-current={isActive ? "true" : undefined}
    >
      <div className="truncate text-sm font-medium leading-tight">
        {session.title || "Untitled Chat"}
      </div>
      <div className="mt-1 text-xs text-grey/70">
        {formatRelativeTime(session.lastActivity)}
      </div>
    </button>
  );
}
