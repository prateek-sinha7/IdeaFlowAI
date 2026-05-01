"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChatSession } from "@/types/index";
import { getToken, getChats, createChat } from "@/lib/api";
import { ChatSessionItem } from "./ChatSessionItem";

interface SidebarProps {
  activeChatId?: string;
  onSelectChat?: (chatId: string) => void;
  onNewChat?: (chatSession: ChatSession) => void;
}

/**
 * Sidebar component with chat session management.
 * Fetches chat sessions on mount, displays them ordered by lastActivity descending,
 * and provides a "New Chat" button to create new sessions.
 */
export function Sidebar({ activeChatId, onSelectChat, onNewChat }: SidebarProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch chat sessions on mount
  useEffect(() => {
    async function fetchSessions() {
      const token = getToken();
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const chats = await getChats(token);
        // Sort by lastActivity descending (most recent first)
        const sorted = [...chats].sort(
          (a, b) =>
            new Date(b.lastActivity).getTime() -
            new Date(a.lastActivity).getTime()
        );
        setSessions(sorted);
        setError(null);
      } catch (err) {
        setError("Failed to load chats");
        console.error("Failed to fetch chat sessions:", err);
      } finally {
        setLoading(false);
      }
    }

    fetchSessions();
  }, []);

  // Handle creating a new chat session
  const handleNewChat = useCallback(async () => {
    const token = getToken();
    if (!token || creating) return;

    setCreating(true);
    try {
      const newSession = await createChat(token);
      // Prepend new session to the list
      setSessions((prev) => [newSession, ...prev]);
      setError(null);
      onNewChat?.(newSession);
    } catch (err) {
      setError("Failed to create chat");
      console.error("Failed to create chat session:", err);
    } finally {
      setCreating(false);
    }
  }, [creating, onNewChat]);

  // Handle selecting a chat session
  const handleSelectChat = useCallback(
    (chatId: string) => {
      onSelectChat?.(chatId);
    },
    [onSelectChat]
  );

  return (
    <div className="flex h-full flex-col bg-navy p-4">
      {/* New Chat button */}
      <button
        onClick={handleNewChat}
        disabled={creating}
        className="mb-4 w-full rounded-md bg-white px-4 py-2.5 text-sm font-medium text-black transition-opacity hover:opacity-85 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {creating ? "Creating..." : "+ New Chat"}
      </button>

      {/* Chat session list */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="text-sm text-grey animate-pulse">Loading chats...</div>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-md bg-red-900/20 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        {!loading && !error && sessions.length === 0 && (
          <p className="text-sm text-grey py-4 text-center">
            No chat sessions yet.
          </p>
        )}

        {!loading &&
          sessions.map((session) => (
            <ChatSessionItem
              key={session.id}
              session={session}
              isActive={session.id === activeChatId}
              onClick={() => handleSelectChat(session.id)}
            />
          ))}
      </div>
    </div>
  );
}
