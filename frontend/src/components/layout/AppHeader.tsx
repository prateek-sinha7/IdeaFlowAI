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
  BarChart2,
  CreditCard,
  LayoutGrid,
} from "lucide-react";
import { NotificationPanel } from "@/components/ui/NotificationPanel";
import type { PipelineNotification } from "@/hooks/useNotifications";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import type { Tier } from "@/lib/entitlements";
import { TIER_LABELS } from "@/lib/entitlements";

interface AppHeaderProps {
  currentPage: "home" | "library" | "workflow" | "execution" | "history" | "analytics" | "catalog" | "saved-workflows";
  onNavigate: (page: "home" | "library" | "history" | "settings" | "analytics" | "catalog" | "saved-workflows") => void;
  onLogout: () => void;
  userEmail?: string;
  userTier?: Tier;
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
  userTier = "basic",
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
  // a11y: Escape closes the profile menu and returns focus here (D-15 a11y).
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    if (profileOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [profileOpen]);

  // a11y: Escape closes the menu and refocuses the trigger. Bound on the wrapper
  // so it fires whether focus is on the trigger button or a menu item.
  const handleMenuKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" && profileOpen) {
      e.stopPropagation();
      setProfileOpen(false);
      triggerRef.current?.focus();
    }
  };

  // Nav shape is a GENERIC {key,label,icon} list keyed on page keys — never a
  // workflow name (SC-001/INV-1). The saved-workflows item is relabeled to
  // "My Workflows" (D-11) while its page key + routing stay UNCHANGED.
  const navItems: {
    key: "home" | "library" | "saved-workflows";
    label: string;
    Icon: typeof Home;
  }[] = [
    { key: "home", label: "Home", Icon: Home },
    { key: "library", label: "Library", Icon: BookOpen },
    { key: "saved-workflows", label: "My Workflows", Icon: LayoutGrid },
  ];

  return (
    <header className="flex items-center justify-between px-3 sm:px-6 py-2.5 sm:py-3 bg-surface-near-black border-b border-white/10 z-40 relative">
      {/* Left — Logo */}
      <div className="flex items-center gap-2 sm:gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand">
          <Zap className="h-3.5 w-3.5 text-white" />
        </div>
        <span className="text-sm sm:text-base font-semibold text-white tracking-tight font-sans">
          VelocityAI
        </span>
      </div>

      {/* Center — Navigation (purple-underline active, no pill fill) */}
      <nav className="flex items-center gap-3 sm:gap-5">
        {navItems.map(({ key, label, Icon }) => {
          const active = currentPage === key;
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-1 sm:gap-1.5 -mb-px border-b-2 px-1 pb-1 pt-0.5 text-[10px] sm:text-xs font-medium transition-colors ${
                active
                  ? "text-white border-brand"
                  : "text-white/60 border-transparent hover:text-white"
              }`}
            >
              <Icon className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          );
        })}
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
              className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-button)] bg-brand/80 border border-brand text-[11px] font-medium text-white hover:bg-brand transition-colors"
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
        <div className="relative" ref={dropdownRef} onKeyDown={handleMenuKeyDown}>
          <button
            ref={triggerRef}
            onClick={() => !disabled && setProfileOpen(!profileOpen)}
            disabled={disabled}
            aria-label="Account menu"
            aria-haspopup="menu"
            aria-expanded={profileOpen}
            className={`flex items-center gap-2 rounded-[var(--radius-button)] px-2 sm:px-2.5 py-1.5 transition-all ${
              disabled ? "opacity-40 cursor-not-allowed" : "text-white/60 hover:text-white hover:bg-white/10"
            }`}
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-button)] bg-brand">
              <User className="h-3.5 w-3.5 text-white" />
            </div>
            <ChevronDown className={`h-3 w-3 transition-transform hidden sm:block ${profileOpen ? "rotate-180" : ""}`} />
          </button>

          <AnimatePresence>
            {profileOpen && (
              <motion.div
                role="menu"
                initial={{ opacity: 0, y: 6, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 6, scale: 0.97 }}
                transition={{ duration: 0.12 }}
                className="absolute right-0 top-full mt-1.5 w-56 rounded-[var(--radius-menu)] border border-line-border bg-surface-card shadow-[var(--elevation-menu)] overflow-hidden z-50"
              >
                {/* Identity block — email + plan on one compact card */}
                <div className="px-3.5 py-3.5 border-b border-line-divider">
                  {userEmail ? (
                    <p className="text-[12px] font-medium text-ink-900 truncate leading-tight">{userEmail}</p>
                  ) : (
                    <p className="text-[12px] font-medium text-ink-400">Account</p>
                  )}
                  <div className="flex items-center justify-between mt-2.5">
                    <div className="flex items-center gap-1.5">
                      <CreditCard className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />
                      <span className="text-[12px] text-ink-500 leading-none">
                        Plan: <span className="text-ink-900 font-semibold">{TIER_LABELS[userTier]}</span>
                      </span>
                    </div>
                    {userTier === "basic" && (
                      <button
                        onClick={() => { setProfileOpen(false); onNavigate("settings"); }}
                        className="text-[11px] font-semibold text-brand hover:underline leading-none"
                      >
                        Upgrade
                      </button>
                    )}
                  </div>
                </div>

                {/* Menu items — compact, no excess padding */}
                <div className="py-0.5">
                  <button
                    role="menuitem"
                    onClick={() => { setProfileOpen(false); onNavigate("settings"); }}
                    className="w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-ink-700 hover:bg-surface-warm transition-colors text-left"
                  >
                    <Settings className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />
                    Account Settings
                  </button>
                  <button
                    role="menuitem"
                    onClick={() => { setProfileOpen(false); onNavigate("analytics"); }}
                    className="w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-ink-700 hover:bg-surface-warm transition-colors text-left"
                  >
                    <BarChart2 className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />
                    Analytics
                  </button>
                  <button
                    role="menuitem"
                    onClick={() => { setProfileOpen(false); onNavigate("history"); }}
                    className="w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-ink-700 hover:bg-surface-warm transition-colors text-left"
                  >
                    <History className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />
                    Workflow History
                  </button>
                </div>

                <div className="border-t border-line-divider py-0.5">
                  <button
                    role="menuitem"
                    onClick={() => { setProfileOpen(false); onLogout(); }}
                    className="w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-status-failed hover:bg-surface-warm transition-colors text-left"
                  >
                    <LogOut className="h-3.5 w-3.5 flex-shrink-0" />
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
