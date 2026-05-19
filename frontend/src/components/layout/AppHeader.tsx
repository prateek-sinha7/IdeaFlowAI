"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Zap,
  Home,
  BookOpen,
  User,
  Settings,
  History,
  LogOut,
  ChevronDown,
} from "lucide-react";
import { NotificationPanel } from "@/components/ui/NotificationPanel";
import type { PipelineNotification } from "@/hooks/useNotifications";
import { getWorkflowLabel } from "@/hooks/useNotifications";

interface AppHeaderProps {
  currentPage: "home" | "library" | "workflow" | "execution" | "history";
  onNavigate: (page: "home" | "library" | "history" | "settings") => void;
  onLogout: () => void;
  userEmail?: string;
  disabled?: boolean;
  // Pipeline running indicator
  isPipelineRunning?: boolean;
  pipelineType?: string;
  pipelineAgentsCompleted?: number;
  pipelineAgentsTotal?: number;
  onGoToPipeline?: () => void;
  // Notifications
  notifications?: PipelineNotification[];
  unreadCount?: number;
  onMarkAllRead?: () => void;
  onClearNotifications?: () => void;
  onViewResults?: (n: PipelineNotification) => void;
}

export function AppHeader({
  currentPage,
  onNavigate,
  onLogout,
  userEmail,
  disabled,
  isPipelineRunning,
  pipelineType,
  pipelineAgentsCompleted = 0,
  pipelineAgentsTotal = 0,
  onGoToPipeline,
  notifications = [],
  unreadCount = 0,
  onMarkAllRead,
  onClearNotifications,
  onViewResults,
}: AppHeaderProps) {
  const [profileOpen, setProfileOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    if (profileOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [profileOpen]);

  return (
    <header className="flex items-center justify-between px-3 sm:px-6 py-2.5 sm:py-3 bg-[#111827] border-b border-[#1f2937] z-40 relative">
      {/* Left — Logo */}
      <div className="flex items-center gap-2 sm:gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600">
          <Zap className="h-3.5 w-3.5 text-white" />
        </div>
        <span className="text-sm sm:text-base font-normal italic text-white tracking-tight font-serif">
          VelocityAI
        </span>
      </div>

      {/* Center — Navigation */}
      <nav className="flex items-center gap-0.5 sm:gap-1 bg-[#1f2937] rounded-lg p-0.5 sm:p-1">
        <button
          onClick={() => onNavigate("home")}
          className={`flex items-center gap-1 sm:gap-1.5 rounded-md px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium transition-all ${
            currentPage === "home"
              ? "bg-white text-gray-900"
              : "text-gray-400 hover:text-white border border-transparent"
          }`}
        >
          <Home className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
          <span className="hidden sm:inline">Home</span>
        </button>
        <button
          onClick={() => onNavigate("library")}
          className={`flex items-center gap-1 sm:gap-1.5 rounded-md px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium transition-all ${
            currentPage === "library"
              ? "bg-white text-gray-900"
              : "text-gray-400 hover:text-white border border-transparent"
          }`}
        >
          <BookOpen className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
          <span className="hidden sm:inline">Library</span>
        </button>
      </nav>

      {/* Right — Running badge + Notifications + Profile */}
      <div className="flex items-center gap-2">

        {/* Running pipeline badge — only when pipeline is active */}
        <AnimatePresence>
          {isPipelineRunning && pipelineType && (
            <motion.button
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.2 }}
              onClick={onGoToPipeline}
              className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1B2A4A]/80 border border-[#1B2A4A] text-[11px] font-medium text-white hover:bg-[#1B2A4A] transition-colors"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse flex-shrink-0" />
              <span className="max-w-[120px] truncate">{getWorkflowLabel(pipelineType)}</span>
              {pipelineAgentsTotal > 0 && (
                <span className="text-white/60 flex-shrink-0">
                  {pipelineAgentsCompleted}/{pipelineAgentsTotal}
                </span>
              )}            </motion.button>
          )}
        </AnimatePresence>

        {/* Notification bell */}
        <NotificationPanel
          notifications={notifications}
          unreadCount={unreadCount}
          onMarkAllRead={onMarkAllRead ?? (() => {})}
          onClearAll={onClearNotifications ?? (() => {})}
          onGoToPipeline={onGoToPipeline ?? (() => {})}
          onViewResults={onViewResults ?? (() => {})}
        />

        {/* Profile dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => !disabled && setProfileOpen(!profileOpen)}
            disabled={disabled}
            className={`flex items-center gap-2 rounded-lg px-2 sm:px-2.5 py-1.5 transition-all ${
              disabled ? "opacity-40 cursor-not-allowed" : "text-gray-400 hover:text-white hover:bg-[#1f2937]"
            }`}
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600">
              <User className="h-3.5 w-3.5 text-white" />
            </div>
            <ChevronDown className={`h-3 w-3 transition-transform hidden sm:block ${profileOpen ? "rotate-180" : ""}`} />
          </button>

          <AnimatePresence>
            {profileOpen && (
              <motion.div
                initial={{ opacity: 0, y: 8, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className="absolute right-0 top-full mt-2 w-56 rounded-lg border border-gray-200 bg-white shadow-lg shadow-black/8 overflow-hidden z-50"
              >
                {userEmail && (
                  <div className="px-4 py-3 border-b border-gray-100">
                    <p className="text-[11px] text-gray-900 font-medium truncate">{userEmail}</p>
                    <p className="text-[10px] text-gray-500 mt-0.5">Free Plan</p>
                  </div>
                )}
                <div className="py-1.5">
                  <button
                    onClick={() => { setProfileOpen(false); onNavigate("settings"); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-gray-600 hover:text-gray-900 hover:bg-gray-50 transition-all"
                  >
                    <Settings className="h-3.5 w-3.5" />
                    Account Settings
                  </button>
                  <button
                    onClick={() => { setProfileOpen(false); onNavigate("history"); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-gray-600 hover:text-gray-900 hover:bg-gray-50 transition-all"
                  >
                    <History className="h-3.5 w-3.5" />
                    Workflow History
                  </button>
                </div>
                <div className="border-t border-gray-100 py-1.5">
                  <button
                    onClick={() => { setProfileOpen(false); onLogout(); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-red-600 hover:bg-red-50 transition-all"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    Log out
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
}
