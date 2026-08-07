"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
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
  Shield,
  ShieldCheck,
} from "lucide-react";
import { NotificationPanel } from "@/components/ui/NotificationPanel";
import type { PipelineNotification } from "@/hooks/useNotifications";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import type { Tier } from "@/lib/entitlements";
import { TIER_LABELS } from "@/lib/entitlements";
import type { WorkflowRun } from "@/types/index";

// Status label + dot colour map for live runs — mirrors HomeLaunchGrid's
// STATUS_TONE so the running dropdown shows the same labels as Jump Back In.
// SC-001: keyed on generic status strings, never a workflow-name literal.
const RUN_STATUS_TONE: Record<string, { label: string; dotClass: string }> = {
  running:          { label: "Running",         dotClass: "bg-brand animate-pulse" },
  revising:         { label: "Revising",        dotClass: "bg-brand animate-pulse" },
  planning:         { label: "Planning",        dotClass: "bg-status-amber animate-pulse" },
  generating:       { label: "Generating",      dotClass: "bg-brand animate-pulse" },
  waiting_for_user: { label: "Waiting for you", dotClass: "bg-status-amber" },
  clarifying:       { label: "Clarifying",      dotClass: "bg-status-amber animate-pulse" },
  gate:             { label: "Awaiting review", dotClass: "bg-status-amber" },
};

// Statuses that mean "the run is still in flight and needs your attention or
// is actively building". Used to filter recentRuns for the badge.
const LIVE_STATUSES = new Set([
  "running", "revising", "planning", "generating", "waiting_for_user", "clarifying",
]);

interface AppHeaderProps {
  currentPage: "home" | "library" | "workflow" | "execution" | "history" | "analytics" | "catalog" | "saved-workflows";
  onNavigate: (page: "home" | "library" | "history" | "settings" | "analytics" | "catalog" | "saved-workflows") => void;
  onLogout: () => void;
  userEmail?: string;
  userTier?: Tier;
  /** Shows the "Admin Dashboard" nav item only for authenticated admins. */
  isAdmin?: boolean;
  disabled?: boolean;
  // Pipeline running indicator (legacy scalar — kept as fallback)
  isPipelineRunning?: boolean;
  pipelineType?: string;
  pipelineAgentsCompleted?: number;
  pipelineAgentsTotal?: number;
  // The backend run-id of the currently tracked/building pipeline. When supplied,
  // it allows the running dropdown to show live agent progress (from the scalar
  // pipelineAgentsCompleted/Total) for the matching run entry.
  activePipelineRunId?: string | null;
  onGoToPipeline?: () => void;
  // Live runs from the server (recentRuns from page.tsx via DashboardLayout).
  // When provided, these are used to drive the "N Running" badge and dropdown
  // instead of the ephemeral notification state — giving the same ground-truth
  // data that powers the "Jump Back In" section on the home page.
  recentRuns?: WorkflowRun[];
  onSwitchToLiveRun?: (runId: string) => void;
  onSelectWorkflowRun?: (run: WorkflowRun) => void;
  // Notifications (for the bell panel — unchanged)
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
  isAdmin = false,
  disabled,
  isPipelineRunning,
  pipelineType,
  pipelineAgentsCompleted = 0,
  pipelineAgentsTotal = 0,
  activePipelineRunId,
  onGoToPipeline,
  recentRuns = [],
  onSwitchToLiveRun,
  onSelectWorkflowRun,
  notifications = [],
  unreadCount = 0,
  onMarkAllRead,
  onClearNotifications,
  onViewResults,
}: AppHeaderProps) {
  const router = useRouter();
  const [profileOpen, setProfileOpen] = useState(false);
  // KAN-132: dropdown state for the multi-pipeline running badge
  const [runningDropdownOpen, setRunningDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const runningDropdownRef = useRef<HTMLDivElement>(null);
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

  // KAN-132: close the running-pipelines dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (runningDropdownRef.current && !runningDropdownRef.current.contains(e.target as Node)) {
        setRunningDropdownOpen(false);
      }
    };
    if (runningDropdownOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [runningDropdownOpen]);

  // a11y: Escape closes the menu and refocuses the trigger. Bound on the wrapper
  // so it fires whether focus is on the trigger button or a menu item.
  const handleMenuKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" && profileOpen) {
      e.stopPropagation();
      setProfileOpen(false);
      triggerRef.current?.focus();
    }
  };

  // Derive running/in-flight runs from the server-sourced recentRuns (the same
  // ground-truth data that powers "Jump Back In" on the home page). Falls back
  // to the notification-based list only when recentRuns is not yet available
  // (e.g. initial render before the page.tsx fetch completes).
  // SC-001: keyed on generic status strings and run ids, never workflow-name literals.
  const liveRunsFromServer = recentRuns.filter((r) => LIVE_STATUSES.has(r.status));

  // KAN-132 compat: also check the ephemeral notifications for "gate" pipelines
  // that may not yet have a workflowRunId but ARE paused at a review gate.
  // When recentRuns has data, prefer it exclusively (server is the truth).
  const runningFromNotifs = notifications.filter(
    (n) => n.status === "running" || n.status === "gate"
  );

  // Use server runs when available; fall back to notification list.
  const hasServerData = recentRuns.length > 0;
  const liveRuns = hasServerData ? liveRunsFromServer : null;

  // runningPipelines: the unified list driving the header badge and dropdown.
  // When server data is available, map WorkflowRun→PipelineNotification shape
  // so the JSX can use a single concrete type. Falls back to the ephemeral
  // notification list on the very first render before recentRuns resolves.
  // SC-001: all fields are generic (status, type, id) — no workflow-name branch.
  const runningPipelines: PipelineNotification[] = liveRuns !== null
    ? liveRuns.map((r): PipelineNotification => {
        // For the currently-tracked/building run, use the live agent progress
        // from pipelineAgentsCompleted/Total so the dropdown shows real progress
        // (e.g. "2/6") instead of a hardcoded "0/N" from the list endpoint.
        const isActive = activePipelineRunId != null && r.id === activePipelineRunId;
        return {
          id: r.id,
          workflowRunId: r.id,
          workflowType: r.type,
          title: r.title,
          // Map extended live statuses to the PipelineNotification status union.
          // "waiting_for_user"/"gate" both mean the run is paused at a review gate.
          status: (r.status === "waiting_for_user" ? "gate"
            : (r.status === "running" || r.status === "planning" || r.status === "generating"
                || r.status === "clarifying" || r.status === "analyzing" || r.status === "revising")
              ? "running"
              : r.status) as PipelineNotification["status"],
          agentsCompleted: isActive ? pipelineAgentsCompleted : 0,
          agentsTotal: isActive ? (pipelineAgentsTotal || r.agentCount) : (r.agentCount ?? 0),
          createdAt: new Date(r.createdAt),
          read: true,
        };
      })
    : runningFromNotifs;

  // Handle clicking a live run in the dropdown — same logic as "Jump Back In":
  // live/building runs → onSwitchToLiveRun (no reset); terminal → onSelectWorkflowRun.
  // IMPORTANT: always call onGoToPipeline (→ setMainView("execution")) after routing
  // so the user actually sees the execution view. Without this, switching the run
  // source happens but the user stays on the home/history screen.
  const handleRunClick = (run: WorkflowRun) => {
    setRunningDropdownOpen(false);
    if (LIVE_STATUSES.has(run.status)) {
      if (onSwitchToLiveRun) {
        onSwitchToLiveRun(run.id);
      }
      // Always navigate to execution view — onSwitchToLiveRun only attaches the
      // SSE stream; it cannot call setMainView (that lives in DashboardLayout).
      onGoToPipeline?.();
    } else {
      if (onSelectWorkflowRun) {
        onSelectWorkflowRun(run);
      } else {
        onGoToPipeline?.();
      }
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
      {/* Left — Hexaware Logo + VelocityAI wordmark */}
      <div className="flex items-center gap-2 sm:gap-2.5">
        <img
          src="/hexaware-logo.png"
          alt="Hexaware"
          className="h-8 w-8 rounded-[6px] flex-shrink-0"
        />
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

        {/* Running pipeline badge(s) — only when at least one pipeline is active.
            KAN-132: single pipeline → existing badge; multiple → dropdown listing all.
            SC-001: label uses getWorkflowLabel (generic map), never a name branch.
            Dot colour: blue (animate-pulse) for running, amber for gate (paused). */}
        <AnimatePresence>
          {runningPipelines.length === 1 && (
            /* Single-pipeline: badge — clicking switches to that run AND navigates
               to execution. Mimics Jump Back In's onOpenRun behaviour. */
            <motion.button
              key="single-run-badge"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.2 }}
              onClick={() => {
                const serverRun = recentRuns.find(r => r.id === runningPipelines[0].workflowRunId);
                if (serverRun) {
                  handleRunClick(serverRun);
                } else {
                  onGoToPipeline?.();
                }
              }}
              className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-button)] bg-brand/80 border border-brand text-[11px] font-medium text-white hover:bg-brand transition-colors"
            >
              {(() => {
                const serverRun = recentRuns.find(r => r.id === runningPipelines[0].workflowRunId);
                const rawStatus = serverRun?.status ?? runningPipelines[0].status;
                const isGate = rawStatus === "waiting_for_user" || rawStatus === "gate";
                const isPlanning = rawStatus === "planning" || rawStatus === "clarifying";
                return (
                  <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${
                    isGate ? "bg-amber-300" : isPlanning ? "bg-amber-300 animate-pulse" : "bg-white animate-pulse"
                  }`} />
                );
              })()}
              <span className="max-w-[120px] truncate">{getWorkflowLabel(runningPipelines[0].workflowType)}</span>
              {(runningPipelines[0].agentsTotal ?? 0) > 0 && (
                <span className="text-white/60 flex-shrink-0">
                  {runningPipelines[0].agentsCompleted ?? 0}/{runningPipelines[0].agentsTotal}
                </span>
              )}
            </motion.button>
          )}

          {runningPipelines.length > 1 && (
            /* Multi-pipeline: dropdown button showing count + expanded list */
            <motion.div
              key="multi-run-badge"
              ref={runningDropdownRef}
              className="relative hidden sm:block"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.2 }}
            >
              <button
                onClick={() => setRunningDropdownOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={runningDropdownOpen}
                aria-label={`${runningPipelines.length} pipelines running — click to view`}
                className="flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-button)] bg-brand/80 border border-brand text-[11px] font-medium text-white hover:bg-brand transition-colors"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse flex-shrink-0" />
                <span>{runningPipelines.length} Running</span>
                <ChevronDown className={`h-3 w-3 transition-transform ${runningDropdownOpen ? "rotate-180" : ""}`} />
              </button>

              <AnimatePresence>
                {runningDropdownOpen && (
                  <motion.div
                    role="menu"
                    initial={{ opacity: 0, y: 6, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 6, scale: 0.97 }}
                    transition={{ duration: 0.12 }}
                    className="absolute right-0 top-full mt-1.5 w-64 rounded-[var(--radius-menu)] border border-line-border bg-surface-card shadow-[var(--elevation-menu)] overflow-hidden z-50"
                  >
                    <div className="px-3 py-2 border-b border-line-divider">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-400">
                        Active Pipelines
                      </p>
                    </div>
                    <div className="flex flex-col divide-y divide-line-divider">
                      {runningPipelines.map((pipeline) => (
                        <button
                          key={pipeline.id}
                          role="menuitem"
                          onClick={() => {
                            setRunningDropdownOpen(false);
                            // Use the same navigation logic as "Jump Back In":
                            // live runs → onSwitchToLiveRun; terminal → onSelectWorkflowRun.
                            const serverRun = recentRuns.find(r => r.id === pipeline.workflowRunId);
                            if (serverRun) {
                              handleRunClick(serverRun);
                            } else {
                              // Fallback: notification-based run (no server run yet)
                              onViewResults?.(pipeline);
                            }
                          }}
                          className="flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-surface-warm transition-colors w-full"
                        >
                          {(() => {
                            // Derive the real status from the server run (most accurate)
                            // or fall back to the mapped notification status.
                            const serverRun = recentRuns.find(r => r.id === pipeline.workflowRunId);
                            const rawStatus = serverRun?.status ?? pipeline.status;
                            const tone = RUN_STATUS_TONE[rawStatus] ?? RUN_STATUS_TONE["running"];
                            return (
                              <>
                                <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 mt-0.5 ${tone.dotClass}`} />
                                <div className="min-w-0 flex-1">
                                  <p className="text-[12px] font-semibold text-ink-900 truncate">
                                    {getWorkflowLabel(pipeline.workflowType)}
                                  </p>
                                  <div className="flex items-center gap-1.5 mt-0.5">
                                    <span className={`text-[10px] font-semibold uppercase tracking-[0.06em] ${
                                      rawStatus === "waiting_for_user" || rawStatus === "gate"
                                        ? "text-status-amber"
                                        : "text-status-running"
                                    }`}>{tone.label}</span>
                                    {pipeline.title && (
                                      <span className="text-[10px] text-ink-400 truncate">·&nbsp;{pipeline.title}</span>
                                    )}
                                  </div>
                                </div>
                                {(pipeline.agentsTotal ?? 0) > 0 && (
                                  <span className="text-[10px] text-ink-400 flex-shrink-0 font-mono">
                                    {pipeline.agentsCompleted ?? 0}/{pipeline.agentsTotal}
                                  </span>
                                )}
                              </>
                            );
                          })()}
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Legacy: fall back to old scalar props if notifications don't carry
              a running entry but pipelineState says running (edge case on first render) */}
          {runningPipelines.length === 0 && isPipelineRunning && pipelineType && (
            <motion.button
              key="legacy-run-badge"
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
              )}
            </motion.button>
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
          recentRuns={recentRuns}
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
                  {/* Routes directly rather than through onNavigate: security is
                      its own page, not one of the dashboard's in-app panels the
                      onNavigate union covers (mirrors Admin Dashboard below). */}
                  <button
                    role="menuitem"
                    onClick={() => { setProfileOpen(false); router.push("/settings/security"); }}
                    className="w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-ink-700 hover:bg-surface-warm transition-colors text-left"
                  >
                    <ShieldCheck className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />
                    Security
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
                    Run History
                  </button>
                  {isAdmin && (
                    <button
                      role="menuitem"
                      onClick={() => { setProfileOpen(false); router.push("/admin"); }}
                      className="w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-ink-700 hover:bg-surface-warm transition-colors text-left"
                    >
                      <Shield className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />
                      Admin Dashboard
                    </button>
                  )}
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
