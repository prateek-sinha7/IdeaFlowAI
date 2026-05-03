"use client";

import { useCallback, useRef, useState } from "react";
import { motion } from "motion/react";
import { MessageSquare, Trash2 } from "lucide-react";
import type { ChatSession } from "@/types/index";

interface ChatSessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onClick: () => void;
  onDelete?: (chatId: string) => void;
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
 * Features motion hover animations, MessageSquare icon, active state accent,
 * and a delete button that appears on hover with confirmation.
 */
export function ChatSessionItem({
  session,
  isActive,
  onClick,
  onDelete,
}: ChatSessionItemProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const confirmTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleDeleteClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();

      if (confirmDelete) {
        // Second click within timeout — confirm deletion
        if (confirmTimeoutRef.current) {
          clearTimeout(confirmTimeoutRef.current);
          confirmTimeoutRef.current = null;
        }
        setConfirmDelete(false);
        onDelete?.(session.id);
      } else {
        // First click — enter confirmation state
        setConfirmDelete(true);
        confirmTimeoutRef.current = setTimeout(() => {
          setConfirmDelete(false);
          confirmTimeoutRef.current = null;
        }, 2000);
      }
    },
    [confirmDelete, onDelete, session.id]
  );

  return (
    <motion.div
      role="button"
      tabIndex={0}
      whileHover={{ x: 2 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }}
      className={`group w-full text-left rounded-md px-2.5 py-1.5 transition-all duration-200 relative cursor-pointer ${
        isActive
          ? "bg-white/10 text-white border-l-2 border-l-white"
          : "text-grey hover:bg-white/5 hover:text-white border-l-2 border-l-transparent"
      }`}
      aria-current={isActive ? "true" : undefined}
    >
      <div className="flex items-start gap-2">
        <MessageSquare className={`h-3 w-3 mt-0.5 flex-shrink-0 ${isActive ? "text-white" : "text-grey/60"}`} />
        <div className="flex-1 min-w-0">
          <div className="truncate text-[11px] font-medium leading-tight">
            {session.title || "Untitled Chat"}
          </div>
          <div className="mt-0.5 text-[10px] text-grey/50">
            {formatRelativeTime(session.lastActivity)}
          </div>
        </div>

        {/* Delete button - appears on hover */}
        {onDelete && (
          <button
            onClick={handleDeleteClick}
            className={`flex-shrink-0 rounded p-0.5 transition-all duration-200 ${
              confirmDelete
                ? "opacity-100 text-red-400 bg-red-400/10"
                : "opacity-0 group-hover:opacity-100 text-grey/60 hover:text-red-400 hover:bg-red-400/10"
            }`}
            aria-label={confirmDelete ? "Confirm delete" : "Delete chat"}
          >
            {confirmDelete ? (
              <span className="text-[9px] font-medium px-0.5">Delete?</span>
            ) : (
              <Trash2 className="h-3 w-3" />
            )}
          </button>
        )}
      </div>
    </motion.div>
  );
}
