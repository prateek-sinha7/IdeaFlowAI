"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Sparkles,
  Home,
  BookOpen,
  User,
  Settings,
  History,
  LogOut,
  ChevronDown,
} from "lucide-react";

interface AppHeaderProps {
  currentPage: "home" | "library" | "workflow" | "execution";
  onNavigate: (page: "home" | "library") => void;
  onLogout: () => void;
  userEmail?: string;
}

/**
 * Global app header — visible across all pages.
 * Left: Logo + brand. Center: Navigation (Home, Library). Right: Profile dropdown.
 */
export function AppHeader({ currentPage, onNavigate, onLogout, userEmail }: AppHeaderProps) {
  const [profileOpen, setProfileOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
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
    <header className="flex items-center justify-between px-6 py-3 border-b border-white/8 backdrop-blur-md bg-[#060a12]/80 z-40 relative">
      {/* Left — Logo */}
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-white/10 shadow-lg shadow-blue-500/5">
          <Sparkles className="h-4 w-4 text-white" />
        </div>
        <span className="text-sm font-bold text-white tracking-tight">
          IdeaFlow <span className="text-white/50 font-normal">AI</span>
        </span>
      </div>

      {/* Center — Navigation */}
      <nav className="flex items-center gap-1 rounded-xl bg-white/[0.03] border border-white/8 p-1">
        <button
          onClick={() => onNavigate("home")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition-all ${
            currentPage === "home"
              ? "bg-white/10 text-white border border-white/10"
              : "text-white/50 hover:text-white hover:bg-white/5 border border-transparent"
          }`}
        >
          <Home className="h-3.5 w-3.5" />
          Home
        </button>
        <button
          onClick={() => onNavigate("library")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition-all ${
            currentPage === "library"
              ? "bg-white/10 text-white border border-white/10"
              : "text-white/50 hover:text-white hover:bg-white/5 border border-transparent"
          }`}
        >
          <BookOpen className="h-3.5 w-3.5" />
          Library
        </button>
      </nav>

      {/* Right — Profile */}
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setProfileOpen(!profileOpen)}
          className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-white/60 hover:text-white hover:bg-white/5 border border-transparent hover:border-white/10 transition-all"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-blue-500/30 to-purple-500/30 border border-white/15">
            <User className="h-3.5 w-3.5 text-white/80" />
          </div>
          <ChevronDown className={`h-3 w-3 transition-transform ${profileOpen ? "rotate-180" : ""}`} />
        </button>

        {/* Dropdown */}
        <AnimatePresence>
          {profileOpen && (
            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.95 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-white/10 bg-[#0c1220] shadow-2xl shadow-black/50 overflow-hidden z-50"
            >
              {/* User info */}
              {userEmail && (
                <div className="px-4 py-3 border-b border-white/8">
                  <p className="text-[11px] text-white/80 font-medium truncate">{userEmail}</p>
                  <p className="text-[10px] text-white/30 mt-0.5">Free Plan</p>
                </div>
              )}

              {/* Menu items */}
              <div className="py-1.5">
                <button
                  onClick={() => { setProfileOpen(false); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-white/60 hover:text-white hover:bg-white/5 transition-all"
                >
                  <Settings className="h-3.5 w-3.5" />
                  Account Settings
                </button>
                <button
                  onClick={() => { setProfileOpen(false); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-white/60 hover:text-white hover:bg-white/5 transition-all"
                >
                  <History className="h-3.5 w-3.5" />
                  Workflow History
                </button>
              </div>

              {/* Logout */}
              <div className="border-t border-white/8 py-1.5">
                <button
                  onClick={() => { setProfileOpen(false); onLogout(); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-red-400/80 hover:text-red-300 hover:bg-red-500/5 transition-all"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Log out
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </header>
  );
}
