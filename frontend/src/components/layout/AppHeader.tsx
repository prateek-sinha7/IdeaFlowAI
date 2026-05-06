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

export function AppHeader({ currentPage, onNavigate, onLogout, userEmail }: AppHeaderProps) {
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
    <header className="flex items-center justify-between px-3 sm:px-6 py-2.5 sm:py-3 border-b border-[#e8e6dc] bg-white/80 backdrop-blur-md z-40 relative">
      {/* Left — Logo */}
      <div className="flex items-center gap-2 sm:gap-3">
        <div className="flex h-7 w-7 sm:h-8 sm:w-8 items-center justify-center rounded-xl bg-gradient-to-br from-[#c96442] to-[#d97757] shadow-sm">
          <Sparkles className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-white" />
        </div>
        <span className="text-xs sm:text-sm font-bold text-[#141413] tracking-tight">
          IdeaFlow <span className="text-[#87867f] font-medium hidden sm:inline">AI</span>
        </span>
      </div>

      {/* Center — Navigation */}
      <nav className="flex items-center gap-0.5 sm:gap-1 rounded-lg sm:rounded-xl bg-[#f0eee6] border border-[#e8e6dc] p-0.5 sm:p-1">
        <button
          onClick={() => onNavigate("home")}
          className={`flex items-center gap-1 sm:gap-2 rounded-md sm:rounded-lg px-2.5 sm:px-4 py-1.5 sm:py-2 text-[10px] sm:text-xs font-medium transition-all ${
            currentPage === "home"
              ? "bg-white text-[#141413] shadow-sm border border-[#e8e6dc]"
              : "text-[#5e5d59] hover:text-[#141413] hover:bg-white/50 border border-transparent"
          }`}
        >
          <Home className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
          <span className="hidden sm:inline">Home</span>
        </button>
        <button
          onClick={() => onNavigate("library")}
          className={`flex items-center gap-1 sm:gap-2 rounded-md sm:rounded-lg px-2.5 sm:px-4 py-1.5 sm:py-2 text-[10px] sm:text-xs font-medium transition-all ${
            currentPage === "library"
              ? "bg-white text-[#141413] shadow-sm border border-[#e8e6dc]"
              : "text-[#5e5d59] hover:text-[#141413] hover:bg-white/50 border border-transparent"
          }`}
        >
          <BookOpen className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
          <span className="hidden sm:inline">Library</span>
        </button>
      </nav>

      {/* Right — Profile */}
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setProfileOpen(!profileOpen)}
          className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-[#5e5d59] hover:text-[#141413] hover:bg-[#f0eee6] border border-transparent hover:border-[#e8e6dc] transition-all"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[#c96442] to-[#d97757]">
            <User className="h-3.5 w-3.5 text-white" />
          </div>
          <ChevronDown className={`h-3 w-3 transition-transform ${profileOpen ? "rotate-180" : ""}`} />
        </button>

        <AnimatePresence>
          {profileOpen && (
            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.95 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-[#e8e6dc] bg-white shadow-lg shadow-black/8 overflow-hidden z-50"
            >
              {userEmail && (
                <div className="px-4 py-3 border-b border-[#e8e6dc]">
                  <p className="text-[11px] text-[#141413] font-medium truncate">{userEmail}</p>
                  <p className="text-[10px] text-[#87867f] mt-0.5">Free Plan</p>
                </div>
              )}
              <div className="py-1.5">
                <button className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-[#5e5d59] hover:text-[#141413] hover:bg-[#f5f4ed] transition-all">
                  <Settings className="h-3.5 w-3.5" />
                  Account Settings
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-2.5 text-[11px] text-[#5e5d59] hover:text-[#141413] hover:bg-[#f5f4ed] transition-all">
                  <History className="h-3.5 w-3.5" />
                  Workflow History
                </button>
              </div>
              <div className="border-t border-[#e8e6dc] py-1.5">
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
    </header>
  );
}
