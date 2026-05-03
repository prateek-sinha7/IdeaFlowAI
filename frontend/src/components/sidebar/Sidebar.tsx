"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import { Plus, Search, Sparkles, LogOut, PanelLeftClose } from "lucide-react";
import type { ChatSession } from "@/types/index";
import { getToken, getChats, createChat } from "@/lib/api";
import { ChatSessionItem } from "./ChatSessionItem";
import { ThemePicker } from "@/components/ui/ThemePicker";

interface SidebarProps {
  activeChatId?: string;
  onSelectChat?: (chatId: string) => void;
  onNewChat?: (chatSession: ChatSession) => void;
  onDeleteChat?: (chatId: string) => void;
  onLogout?: () => void;
  onCollapse?: () => void;
  chatTitleUpdate?: { chat_session_id: string; title: string } | null;
}

/**
 * Sidebar component with chat session management.
 * Features IdeaFlow AI branding, search filter, animated chat list,
 * delete chat support, and a logout button.
 */
export function Sidebar({ activeChatId, onSelectChat, onNewChat, onDeleteChat, onLogout, onCollapse, chatTitleUpdate }: SidebarProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

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

  // React to title updates from WebSocket
  useEffect(() => {
    if (chatTitleUpdate) {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === chatTitleUpdate.chat_session_id
            ? { ...s, title: chatTitleUpdate.title }
            : s
        )
      );
    }
  }, [chatTitleUpdate]);

  // Handle creating a new chat session
  const handleNewChat = useCallback(async () => {
    const token = getToken();
    if (!token || creating) return;

    setCreating(true);
    try {
      const newSession = await createChat(token);
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

  // Handle deleting a chat session
  const handleDeleteChat = useCallback(
    (chatId: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== chatId));
      onDeleteChat?.(chatId);
    },
    [onDeleteChat]
  );

  // Filter sessions by search query
  const filteredSessions = sessions.filter((session) =>
    (session.title || "Untitled Chat")
      .toLowerCase()
      .includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-full flex-col backdrop-blur-sm" style={{ backgroundColor: 'var(--theme-sidebar-bg)' }}>
      {/* Header with branding */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/10 border border-white/10">
              <Sparkles className="h-3.5 w-3.5 text-white" />
            </div>
            <h1 className="text-sm font-semibold tracking-tight" style={{ color: 'var(--theme-fg)' }}>
              IdeaFlow AI
            </h1>
          </div>
          {onCollapse && (
            <button
              onClick={onCollapse}
              className="flex items-center justify-center rounded-md p-1 text-grey/60 hover:text-white hover:bg-white/5 transition-all duration-200"
              aria-label="Close sidebar"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* New Chat button */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleNewChat}
          disabled={creating}
          className="w-full flex items-center justify-center gap-1.5 rounded-md bg-white/10 border border-white/10 px-2 py-1.5 text-[11px] font-medium text-white transition-all duration-200 hover:bg-white/15 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="h-3 w-3" />
          {creating ? "Creating..." : "New Chat"}
        </motion.button>
      </div>

      {/* Divider */}
      <div className="mx-5 border-t border-grey/15" />

      {/* Search input */}
      <div className="px-5 py-2.5">
        <div className="flex items-center gap-1.5 rounded-md border border-grey/15 px-2.5 py-1.5" style={{ backgroundColor: 'var(--theme-input-bg)' }}>
          <Search className="h-3 w-3 text-grey/50" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search chats..."
            className="flex-1 bg-transparent text-[11px] text-white placeholder-grey/40 focus:outline-none"
          />
        </div>
      </div>

      {/* Chat session list */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-1">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="text-sm text-grey animate-pulse">Loading chats...</div>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-lg bg-red-900/20 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        {!loading && !error && filteredSessions.length === 0 && (
          <p className="text-xs text-grey/60 py-4 text-center">
            {searchQuery ? "No matching chats" : "No chat sessions yet"}
          </p>
        )}

        {!loading &&
          filteredSessions.map((session) => (
            <ChatSessionItem
              key={session.id}
              session={session}
              isActive={session.id === activeChatId}
              onClick={() => handleSelectChat(session.id)}
              onDelete={handleDeleteChat}
            />
          ))}
      </div>

      {/* Theme picker */}
      <div className="border-t border-grey/15 px-5 pt-2 pb-1.5">
        <ThemePicker />
      </div>

      {/* User section with logout */}
      {onLogout && (
        <div className="border-t border-grey/15 px-5 py-2 mb-1">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onLogout}
            className="w-full flex items-center justify-center gap-1.5 rounded-md border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-[11px] font-medium text-red-300 hover:bg-red-500/20 hover:text-red-200 hover:border-red-500/30 transition-all duration-200"
          >
            <LogOut className="h-3 w-3" />
            Log out
          </motion.button>
        </div>
      )}
    </div>
  );
}
