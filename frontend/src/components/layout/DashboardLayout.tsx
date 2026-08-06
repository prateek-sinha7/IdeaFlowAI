"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import { WifiOff, RefreshCw, Loader2 } from "lucide-react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { AppHeader } from "./AppHeader";
import { HomeLaunchGrid } from "@/components/catalog/HomeLaunchGrid";
import { LibraryPage } from "@/components/library/LibraryPage";
import { WorkflowHistory } from "@/components/history/WorkflowHistory";
import { AccountSettings } from "@/components/settings/AccountSettings";
import { AnalyticsPage } from "@/components/analytics/AnalyticsPage";
import { SavedWorkflowsPage } from "@/components/savedworkflows/SavedWorkflowsPage";
import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import { ComposerPage } from "@/components/workflow/composer/ComposerPage";
// INV-3 (plan 06): the AgentProgressPanel run-lane mount was removed here — its
// Stop/revise/suggestions controls are fully absorbed by RunChatLane. The
// component itself is retained (its own suite + the plan-08 Steps relocation);
// DashboardLayout no longer imports or mounts it.
// Phase 31 (CHATUI-01/02/03) — the run-screen chat lane composition root. Mounted
// as the execution-surface left column; it ABSORBS the AgentProgressPanel
// Stop/revise/suggestions controls (D-12 composer-per-state, SC-001 generic).
import { RunChatLane, type RunLaneState, type GateContext, type LaneSuggestion, type LaneProposal } from "@/components/chat/RunChatLane";
import type { ReplyStreamingState, SendMessageOptions } from "@/hooks/useRunChat";
import type { ClarifyResponse } from "@/components/chat/InlineClarifyActions";
import { PreviewPanel } from "@/components/preview/PreviewPanel";
import { CompletionToast } from "@/components/ui/CompletionToast";
import type { ToastItem } from "@/components/ui/CompletionToast";
import { useNotifications } from "@/hooks/useNotifications";
import type { ChatMessage, ChatSession, ProcessStep, PipelineRunState, WaveGroup, WorkflowRun, WorkflowType, GenericDeliverable, RunFamily } from "@/types/index";
import { canChainFrom, CHAIN_OPTIONS, CHAIN_BRIEF_KEY, CHAIN_FROM_KEY, CHAIN_SOURCE_RUN_ID_KEY, baseWorkflowType } from "@/lib/workflowChaining";
import { parseRunInput } from "@/lib/runInput";
import { getToken, getChainContext, getRunFamily, postCancel, postRevision, postResume } from "@/lib/api";
import type { UserWorkflowSummary, WorkflowSummary } from "@/lib/api";
import type { ConnectionStatus } from "@/hooks/useHandoffSocket";
import type { ChatMode } from "@/components/chat/ChatInput";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import { useRunConnection } from "@/providers/RunConnectionProvider";
// KAN-128 (FIX-141): content-derived filename for the left chat panel deliverable card
import { deriveDeliverableFilename } from "@/components/results/FilesTab";

export interface DashboardLayoutProps {
  activeChatId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  userStoryContent: string;
  pptContent: string;
  prototypeContent: string;
  // ISS-021 (18-03) — generic deliverable channel for any pipeline_type that
  // matched no known FE render branch (live pipeline_complete + history-reopen).
  // Threaded straight down to PreviewPanel/FilesTab; the mimetype drives the
  // generic fallback renderer (SC-001 — never a workflow-name branch).
  genericDeliverable?: GenericDeliverable;
  connectionStatus: ConnectionStatus;
  // Legacy chat-sidebar send seam — the run chat lane rides onRunChatSend (REST);
  // this remains as an optional fallback for the settled-run ASK path.
  onSendMessage?: (content: string) => void;
  onSendMessageWithMode?: (content: string, mode: ChatMode) => void;
  onSelectChat: (chatId: string) => void;
  onNewChat: (chatSession: ChatSession) => void;
  onDeleteChat: (chatId: string) => void;
  onLogout: () => void;
  onReconnect: () => void;
  messageMode?: ChatMode;
  chatTitleUpdate?: { chat_session_id: string; title: string } | null;
  processSteps?: ProcessStep[];
  pipelineState?: PipelineRunState;
  onStartPipeline?: (type: string, message: string, agentIds?: string[], attachedSkills?: import("@/types/index").AttachedSkill[], attachedHooks?: import("@/types/index").AttachedHook[], extraParams?: Record<string, unknown>) => void;
  onResetPipeline?: () => void;
  recentRuns?: WorkflowRun[];
  /** Pre-fetched user-launchable workflow definitions from page.tsx. When supplied,
   *  HomeLaunchGrid uses them as initial state and skips its own getWorkflowDefinitions
   *  fetch, so the card grid appears instantly alongside the recents strip. */
  homeWorkflows?: WorkflowSummary[];
  // Revision Families (B1 / D1-D7): the reliable "run id that produced the
  // on-screen content", owned by page.tsx (pipeline_complete + reopen). Every
  // revision launch path sources parent linkage from this — replaces the fragile
  // currentWorkflowRunId heuristic (which mis-matched on double-revision types).
  contentSourceRunId?: string | null;
  // BUG-012: the durable REAL type of the viewed run (page.tsx fullRun.type),
  // preferred over the recents lookup so the PreviewPanel render dispatch keys on
  // the viewed run's type even when it is outside the recents window.
  contentSourceRunType?: WorkflowType | null;
  onSelectWorkflowRun?: (run: WorkflowRun) => void;
  /**
   * FIX-149 (Bug 2): switch the active live run view WITHOUT resetting pipeline
   * state or fetching from the DB. Used when the user clicks a RUNNING pipeline
   * notification — the run is live, so we must NOT call handleSelectWorkflowRun
   * (which resets/reseeds as if it were a history reopen). Instead we just attach
   * the SSE stream and update the content-source so the execution view reflects
   * the selected running run.
   */
  onSwitchToLiveRun?: (runId: string) => void;
  // Phase 16 (ISS-017) — the persisted status of a history-reopened run. When a
  // failed/cancelled run is reopened it carries no content, so the run's
  // server-persisted status is threaded down to PreviewPanel to render the
  // terminal-empty degraded/failed affordance on the history path. Undefined for
  // fresh/live runs and successful reopens.
  reopenedRunStatus?: import("@/types/index").WorkflowStatus;
  // Phase 16 (IN-01) — the failed-agent ids of a history-reopened terminal run,
  // parsed from the persisted run detail. Threaded to PreviewPanel so the reopen
  // affordance lists the real failed agents instead of an empty list.
  reopenedFailedAgents?: string[];
  // ISS-024 (16 review IN-02) — id→name lookup for a history-reopened run's
  // failed agents (the live pipelineState can't name them). Threaded straight to
  // PreviewPanel's DegradedRunAffordance; unknown ids fall back to the raw id.
  reopenedAgentNameById?: Record<string, string>;
  questionnaireData?: {
    questions: {
      id: string; question: string; options: string[]; answerType?: string;
      recommendedAnswer?: string; recommendedReasoning?: string;
      recommendedDisplay?: string; ambiguityCategory?: string; impactLevel?: string;
    }[]
  } | null;
  // Phase 2 (Universal Engine) — clarify gate resume wiring.
  activePipelineRunId?: string | null;
  // KAN-120 — the run id of the most-recently cancelled/stopped run. Preserved
  // across pipeline_cancelled so Run Again can resume a clarify-cancelled run
  // whose activePipelineRunId was already cleared.
  lastCancelledRunId?: string | null;
  onSubmitQuestionnaire?: (pipelineRunId: string, responses: Array<{ question_id: string; answer: string }>, skipClarification?: boolean) => void;
  // Workstream C1 (POR §6.5) — fold an answered clarify round into run-scoped
  // state before the questionnaire panel clears (consumed by C2's ClarificationsCard).
  onRetainClarifyRound?: (round: import("@/types/index").ClarifyRound) => void;
  // Review gate — shown when an agent with gate: Human_Gate completes
  reviewGateData?: {
    gateKey: string;
    agentId: string;
    agentName: string;
    output: string;
    pipelineRunId: string;
    // REDO-GATE (F-fe2): generic server-set flag threaded into the panel so the
    // Redo control renders only on redoable (inline) gates.
    redoable?: boolean;
    // SC-001 (plan 04→06, KAN-101): name-free server flags parsed in page.tsx —
    // the lane maps updateSpecsEligible into the InlineGateActions "Update the
    // Specs" affordance and artifactKind into the approve relabel. Additive.
    updateSpecsEligible?: boolean;
    artifactKind?: string;
  } | null;
  onApproveReview?: (gateKey: string, editedContent?: string) => void;
  onRejectReview?: (gateKey: string) => void;
  // REDO-GATE (F-fe2): pass-through redo callback to the ReviewGatePanel.
  onRedoReview?: (gateKey: string, instructions: string) => void;
  // KAN-101: pass-through update-specs callback to the ReviewGatePanel.
  onUpdateSpecsReview?: (gateKey: string, analysisReport: string) => void;
  pendingOdProtoParams?: {
    brief: string; templateId: string; designSystemId: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string;
    gateAgentIds?: string[];
    modelOverrides?: Record<string, string>;
    selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null;
  onClearPendingOdProto?: () => void;
  pendingOdPptParams?: {
    brief: string; templateId: string; designSystemId: string | null; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string;
    gateAgentIds?: string[];
    modelOverrides?: Record<string, string>;
    selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null;
  onClearPendingOdPpt?: () => void;
  userTier?: "basic" | "pro" | "enterprise";
  userEmail?: string;
  // Phase 12 (WAVE-03) — wave groups assembled from the live `wave_*` /
  // `subagent_*` WS events by dashboard/page.tsx. Optional + defaulted to []
  // so existing callers/tests that omit it are unaffected; a non-wave run
  // feeds an empty list and AgentDetailPanel's inline construction/wave tree
  // renders its own empty state.
  waves?: WaveGroup[];
  // Workstream C2 (POR §5 D3 / §6.2) — the live run's captured input (submittedBrief
  // in page.tsx, set in onStartPipeline). Threaded as PreviewPanel.runInput so the
  // StartingPointCard + Files "Run input" section render on the LIVE mount. Optional
  // and default-undefined → non-live callers/tests render unchanged.
  submittedBrief?: string;
  // KAN-101 — spec revision cycle counter from page.tsx. Threaded to
  // AgentThinkingTab to show a violet "Spec Revision Cycle N" banner and version
  // chips during an active update_specs re-run. Optional + defaulted to 0 so
  // existing callers/tests render unchanged.
  specRevisionCount?: number;
  // ─── Phase 31 (CHATUI-01/02/03) — run chat lane wiring ──────────────────────
  // The family-anchored transcript + the transport-agnostic send from page.tsx's
  // `useRunChat` (fed by the active transport — SSE flag ON or legacy WS OFF).
  // Consumed by the RunChatLane mounted in the execution left column. Optional /
  // default-undefined → non-live callers and existing test renders unchanged.
  runChatMessages?: ChatMessage[];
  // quick-260719-rqo (Issue 2 part 2) — the active streaming-reply hint from
  // page.tsx's useRunChat. Threaded to RunChatLane so the lane can show the
  // "reading run data…" indicator during the Concierge reply's read-tool freeze.
  runChatReplyStreaming?: ReplyStreamingState | null;
  /**
   * ISS-054 / KAN-160: live Concierge-held consequential proposals for the
   * currently viewed run, sourced from page.tsx's useRunChat.proposals (durable
   * concierge_proposal run_events, delivered via DEF-44-12-2 post-send re-fetch).
   * Optional/default-undefined → non-live callers/tests render unchanged.
   */
  runChatProposals?: LaneProposal[];
  onDismissRunChatProposal?: (id: string) => void;
  onRunChatSend?: (
    text: string,
    attachments?: import("@/types/index").ChatAttachment[],
    options?: SendMessageOptions,
  ) => void;
  /**
   * FIX-170: Called by the postRevision path (od_ppt/od_prototype REST launch)
   * when the created revision run_id is known. Updates page.tsx's routing refs
   * (trackedRunIdRef, activelyBuildingRunIdRef, launchedRunIdsRef) so the new
   * revision run's SSE events are not blocked by isForeignRunFrame. Without this,
   * the revision starts but pipeline_start/agent events are all discarded as
   * foreign — the UI stays frozen showing the completed parent run's state until
   * the user refreshes.
   */
  onRevisionLaunched?: (runId: string) => void;
  /**
   * FIX-119: Optimistically add a user bubble to the transcript without posting
   * to the backend. Passed from page.tsx's `useRunChat.addOptimisticMessage` to
   * the `RunChatLane` so `handleFreeText` can echo the user's text immediately
   * before the classify-intent LLM round-trip (for all runState === "complete"
   * workflows). Without this, only the "ask" path showed a user bubble (via
   * sendMessage); "revise" and "chain" paths showed nothing.
   */
  addOptimisticMessage?: (
    text: string,
    attachments?: import("@/types/index").ChatAttachment[],
  ) => string;
  // The nonce'd deep-link seam (borrow #6): the lane's result cards call
  // onRequestOpenTab; PreviewPanel consumes deepLinkTarget for all tabs.
  onRequestOpenTab?: (tab: string) => void;
  deepLinkTarget?: import("@/hooks/useTabDeepLink").TabDeepLinkTarget | null;
}

type MainView = "home" | "library" | "history" | "settings" | "analytics" | "input" | "execution" | "catalog" | "saved-workflows" | "composer";

// ISS-054 / KAN-160: stable empty fallback for non-live callers and existing tests
// (preserves referential identity across renders). Live proposals now come from
// page.tsx's useRunChat via runChatProposals prop; this constant is the ?? fallback.
const RUN_CONCIERGE_PROPOSALS: LaneProposal[] = [];

export function DashboardLayout({
  activeChatId,
  messages,
  isStreaming,
  streamingContent,
  userStoryContent,
  pptContent,
  prototypeContent,
  genericDeliverable,
  connectionStatus,
  onSendMessage,
  onSendMessageWithMode,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onLogout,
  onReconnect,
  messageMode,
  chatTitleUpdate,
  processSteps,
  pipelineState,
  reopenedRunStatus,
  reopenedFailedAgents,
  reopenedAgentNameById,
  onStartPipeline,
  onResetPipeline,
  recentRuns,
  homeWorkflows,
  contentSourceRunId,
  contentSourceRunType,
  onSelectWorkflowRun,
  onSwitchToLiveRun,
  questionnaireData,
  activePipelineRunId,
  lastCancelledRunId,
  onSubmitQuestionnaire,
  onRetainClarifyRound,
  reviewGateData,
  onApproveReview,
  onRejectReview,
  onRedoReview,
  onUpdateSpecsReview,
  pendingOdProtoParams,
  onClearPendingOdProto,
  pendingOdPptParams,
  onClearPendingOdPpt,
  userTier = "basic",
  userEmail,
  waves = [],
  submittedBrief,
  specRevisionCount = 0,
  runChatMessages,
  runChatReplyStreaming,
  runChatProposals,
  onDismissRunChatProposal,
  onRunChatSend,
  addOptimisticMessage,
  onRevisionLaunched,
  onRequestOpenTab,
  deepLinkTarget,
}: DashboardLayoutProps) {
  const router = useRouter();
  // The app-level SSE connection — the sole run transport (44-06). Commands ride
  // its REST up-channel; useRunStream owns Last-Event-ID replay.
  const runConnection = useRunConnection();
  const [mainView, setMainView] = useState<MainView>(() => {
    // If an od_prototype or od_ppt run is staged (user came from the wizard),
    // start directly in execution view — avoids the home screen flash while
    // waiting for the WebSocket to connect and fire the pipeline.
    if (typeof window !== "undefined" && (
      sessionStorage.getItem("od_prototype.pending") ||
      sessionStorage.getItem("od_ppt.pending")
    )) {
      return "execution";
    }
    return "home";
  });
  const [workflowType, setWorkflowType] = useState<WorkflowType>(() => {
    if (typeof window !== "undefined") {
      if (sessionStorage.getItem("od_prototype.pending")) return "prototype";
      if (sessionStorage.getItem("od_ppt.pending")) return "ppt";
    }
    return "user_stories";
  });
  const [workflowInput, setWorkflowInput] = useState("");
  // Tracks completed pipeline types (fed by the WS completion handlers). The
  // run-lane chaining suggestions derive from canChainFrom(workflowType); this
  // state is retained for the completion bookkeeping its setters perform.
  const [completedPipelineTypes, setCompletedPipelineTypes] = useState<WorkflowType[]>([]);
  const [lastPipelineOutput, setLastPipelineOutput] = useState<string>("");
  // KAN-120 BUG-4: inline error message shown in the terminal lane when a
  // resume attempt fails (instead of silently navigating home). Cleared on the
  // next pipeline_start (the run actually resumes) or when a new run is started.
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [questionnaireQuestions, setQuestionnaireQuestions] = useState<{
    id: string; question: string; options: string[]; answerType?: string;
    recommendedAnswer?: string; recommendedReasoning?: string;
    recommendedDisplay?: string; ambiguityCategory?: string; impactLevel?: string;
  }[]>([]);
  const [questionnaireLoading, setQuestionnaireLoading] = useState(false);
  const [pendingPipelineRun, setPendingPipelineRun] = useState<{
    type: WorkflowType;
    message: string;
    agentIds?: string[];
    extraParams?: {
      template_id?: string;
      design_system_id?: string;
      custom_ds_body?: string;
      custom_template_body?: string;
      discovery?: unknown;
    };
  } | null>(null);

  // Read attached skills/hooks from global context — set by user in AgentsPopup
  const { attachedSkills, attachedHooks } = useSkillsHooks();

  // ── Notifications + toasts ──────────────────────────────────────────────
  const {
    notifications,
    unreadCount,
    addRunningNotification,
    updateProgress,
    updateAgentsTotal,
    markCompleted,
    markFailed,
    markCancelled,
    markGatePaused,
    markGateResumed,
    setNotifWorkflowRunId,
    markAllRead,
    clearAll,
  } = useNotifications();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  // FIX-155: track notif id per pipeline run (keyed by backend run id or a
  // local placeholder) so concurrent runs (user_stories + prototype + ppt) each
  // maintain their OWN notification entry without overwriting each other.
  // currentPipelineNotifId tracks the CURRENTLY VIEWED run's notif for
  // progress/gate/completion updates.
  const currentPipelineNotifId = useRef<string | null>(null);
  // Map: local notifId → was-this-created-by-the-explicit-handler (true) or by
  // the reactive odProtoNotifCreated effect (false). Used to prevent the reactive
  // effect from creating a duplicate after the explicit handler already fired.
  // keyed on pipeline type ("prototype" | "ppt") to deduplicate per concurrent run.
  const odProtoNotifId = useRef<string | null>(null);
  const odPptNotifId = useRef<string | null>(null);
  // KAN-90: when user explicitly cancels from the clarification step, block
  // the auto-redirect-to-execution effect for one render cycle so the home
  // navigation isn't immediately overridden by pipelineState.isRunning=true.
  const cancelNavigatingHomeRef = useRef(false);

  // ─── B3 (POR §5 D5) — revision family for the on-screen content ──────────────
  // Fetched here (the minimal seam — DashboardLayout already receives
  // contentSourceRunId AND mounts PreviewPanel) keyed on contentSourceRunId, and
  // threaded into PreviewPanel as an optional prop. The .catch guarantees it
  // never throws even if the endpoint is unavailable.
  const [runFamily, setRunFamily] = useState<RunFamily | null>(null);
  useEffect(() => {
    if (!contentSourceRunId) { setRunFamily(null); return; }
    getRunFamily(getToken() || "", contentSourceRunId)
      .then(setRunFamily)
      .catch(() => setRunFamily(null));
  }, [contentSourceRunId]);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Detect when pipeline starts running → switch to execution view.
  // Also sync workflowType from the pipeline's declared type so PreviewPanel
  // renders the right output component. Without this, od_prototype (which is
  // triggered programmatically, not via handleSelectFeature) would leave
  // workflowType at its "user_stories" default, causing PreviewPanel to render
  // UserStoryPreview instead of PrototypePreview.
  useEffect(() => {
    if (pipelineState?.isRunning) {
      // KAN-90: if user just cancelled from the clarification step, don't
      // force the execution view — they want to stay on home/dashboard.
      if (cancelNavigatingHomeRef.current) {
        cancelNavigatingHomeRef.current = false; // consume the flag
        return;
      }
      if (mainView !== "execution") {
        setMainView("execution");
      }
      const pt = pipelineState.pipeline_type as WorkflowType | "od_prototype" | "od_ppt";
      // Normalise od_prototype → prototype, od_ppt → ppt
      const normalised: WorkflowType = pt === "od_prototype" ? "prototype" : pt === "od_ppt" ? "ppt" : (pt as WorkflowType);
      if (normalised && normalised !== workflowType) {
        setWorkflowType(normalised);
      }
      // KAN-88 stale label fix: if currentPipelineNotifId still holds an old
      // run's id when a new pipeline starts (the previous completion effect may
      // not have run yet), clear it so subsequent notifications are created fresh.
      // FIX-155: only reset if odProtoNotifCreated hasn't fired yet for the new
      // run (avoids clearing a freshly-created od_prototype notification).
      const incomingRunId = pipelineState.pipelineRunId;
      if (incomingRunId && currentPipelineNotifId.current) {
        if (!odProtoNotifCreated.current) {
          currentPipelineNotifId.current = null;
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineState?.isRunning, pipelineState?.pipeline_type]);

  // Capture output when pipeline completes (for chaining)
  useEffect(() => {
    if (pipelineState && !pipelineState.isRunning && pipelineState.agents.length > 0) {
      // The completion notification/toast fires only once EVERY agent reached a
      // terminal status (done/error) — an agent left `running`/`thinking`/`idle`
      // (e.g. the build + validate pair still cycling) keeps the announcement
      // pending. The effect re-runs on every pipelineState change and fires once
      // they settle, because `currentPipelineNotifId` is consumed only when it
      // actually fires. Keyed on agent status only, never on an agent or workflow
      // name (SC-001/INV-1).
      const allDone = pipelineState.agents.every((a) => a.status === "done" || a.status === "error");
      if (allDone && pipelineState.agents.some((a) => a.status === "done")) {
        setCompletedPipelineTypes((prev) => {
          if (prev.includes(workflowType)) return prev;
          return [...prev, workflowType];
        });
        const output = pptContent || userStoryContent || prototypeContent;
        if (output) setLastPipelineOutput(output);

        // Fire completion notification + toast
        if (currentPipelineNotifId.current) {
          const notifId = currentPipelineNotifId.current;
          currentPipelineNotifId.current = null;  // reset so next run gets a fresh notification
          markCompleted(notifId);
          setToasts(prev => [...prev, {
            id: notifId + "-toast",
            workflowType,
            title: workflowType,
            status: "completed",
          }]);
        }
      }

      // Terminal failure / cancellation — fire the matching notification off the
      // GENERIC plan-05 pipelineState markers (failed / cancelled), NEVER a
      // workflow name (SC-001/INV-1). The completed branch above already reset
      // currentPipelineNotifId on success, so this only fires for a non-completed
      // terminal run that still owns a notification id.
      if (currentPipelineNotifId.current) {
        if (pipelineState.failed) {
          const notifId = currentPipelineNotifId.current;
          currentPipelineNotifId.current = null;
          markFailed(notifId);
        } else if (pipelineState.cancelled) {
          const notifId = currentPipelineNotifId.current;
          currentPipelineNotifId.current = null;
          markCancelled(notifId);
        }
      }
    }
  }, [pipelineState, workflowType, pptContent, userStoryContent, prototypeContent]);

  // Gate pause/resume — a review gate OPENING pauses the notification and its
  // RESOLVING resumes it, both off the GENERIC markers (reviewGateData +
  // running), the SAME condition that drives runLaneState==="gate" (:1311) —
  // never a workflow name (SC-001/INV-1). markGateResumed no-ops unless the
  // notification is actually paused, so it never clobbers a terminal mark.
  useEffect(() => {
    if (!currentPipelineNotifId.current || !pipelineState?.isRunning) return;
    if (reviewGateData) {
      markGatePaused(currentPipelineNotifId.current);
    } else {
      markGateResumed(currentPipelineNotifId.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewGateData, pipelineState?.isRunning]);

  // Update notification progress as agents complete
  useEffect(() => {
    if (pipelineState?.isRunning && currentPipelineNotifId.current) {
      updateProgress(currentPipelineNotifId.current, pipelineState.completedCount);
    }
  }, [pipelineState?.completedCount, pipelineState?.isRunning]);

  // Detect when od_prototype/od_ppt starts (fired from dashboard/page.tsx directly,
  // not through handleQuestionnaireSubmit) and create a notification for it.
  const odProtoNotifCreated = useRef(false);
  useEffect(() => {
    if (
      pipelineState?.isRunning &&
      (pipelineState.pipeline_type === "od_prototype" || pipelineState.pipeline_type === "prototype" ||
       pipelineState.pipeline_type === "od_ppt")
    ) {
      if (odProtoNotifCreated.current) return;
      odProtoNotifCreated.current = true;
      // Use the stable pipelineRunId as the notification id so a second firing
      // of this effect for the SAME run is a no-op (addRunningNotification
      // deduplicates by id). Falls back to Date.now() only when pipelineRunId
      // is not yet available (edge case on the very first render).
      const notifId = pipelineState.pipelineRunId
        ? `pipeline-${pipelineState.pipelineRunId}`
        : `pipeline-${Date.now()}`;
      // Use correct workflowType for od_ppt vs prototype
      const wfType: WorkflowType = (pipelineState.pipeline_type === "od_ppt") ? "ppt" : "prototype";
      // FIX-155: track od_prototype and od_ppt in their own refs so concurrent
      // user_stories runs don't interfere. The currentPipelineNotifId ref still
      // tracks the VIEWED run for progress/completion updates.
      if (pipelineState.pipeline_type === "od_ppt") {
        // Only create via this reactive path if the explicit handler didn't already.
        if (!odPptNotifId.current) {
          odPptNotifId.current = notifId;
          currentPipelineNotifId.current = notifId;
          // FIX-149 (Bug 1): use the user's actual brief as the title so the header
          // dropdown shows "My interactive shopping cart" not "Prototype · Prototype".
          const label = submittedBrief
            ? submittedBrief.split("\n")[0].trim().slice(0, 80)
            : "Presentation";
          addRunningNotification(notifId, wfType, label, 0);
        }
      } else {
        // od_prototype / prototype
        if (!odProtoNotifId.current) {
          odProtoNotifId.current = notifId;
          currentPipelineNotifId.current = notifId;
          const label = submittedBrief
            ? submittedBrief.split("\n")[0].trim().slice(0, 80)
            : "Prototype";
          addRunningNotification(notifId, wfType, label, 0);
        }
      }
    }
    if (!pipelineState?.isRunning) {
      odProtoNotifCreated.current = false;
      odProtoNotifId.current = null;
      odPptNotifId.current = null;
    }
  }, [pipelineState?.isRunning, pipelineState?.pipeline_type, pipelineState?.pipelineRunId]);

  // Update agentsTotal when pipeline_start arrives with the real agent list
  useEffect(() => {
    const agentCount = pipelineState?.agents?.length ?? 0;
    if (agentCount > 0 && currentPipelineNotifId.current) {
      updateAgentsTotal(currentPipelineNotifId.current, agentCount);
    }
  }, [pipelineState?.agents?.length]);

  // Update notification title when backend generates a clean title
  useEffect(() => {
    const latestRun = recentRuns?.[0];
    if (latestRun?.title && latestRun.title !== "Untitled" && currentPipelineNotifId.current) {
      const rawDbTitle = latestRun.title;
      // FIX-130: never use a title that starts with "===" (polluted marker text).
      // Fall back to existing notification title by not calling updateAgentsTotal.
      if (rawDbTitle.trimStart().startsWith("===")) return;
      let cleanDbTitle = rawDbTitle;
      if (rawDbTitle.includes("===")) {
        const parsed = parseRunInput(rawDbTitle);
        cleanDbTitle = (parsed.revisionInstruction ?? parsed.brief ?? "").split("\n")[0].trim() || "";
        if (!cleanDbTitle) return; // still polluted — skip update
      }
      updateAgentsTotal(currentPipelineNotifId.current, pipelineState?.agents?.length ?? 0, cleanDbTitle);
    }
  }, [recentRuns?.[0]?.title]);

  // Check if pipeline is running (blocks navigation)
  const isPipelineRunning = pipelineState?.isRunning || false;

  // KAN-120 BUG-4: clear the inline resume-error banner once the pipeline
  // actually starts (confirms the resume was accepted by the backend).
  // Keyed on isPipelineRunning transitioning to true — the pipeline_start
  // event fires successfully. Direction is one-way (handleResumeRun sets it;
  // only this effect clears it). The empty deps-array on the outer useCallback
  // is safe because this effect runs on each isPipelineRunning change.
  useEffect(() => {
    if (isPipelineRunning) setResumeError(null);
  }, [isPipelineRunning]);

  // Extract Agent 3's (ppt-code-generator) output for early PPTX download
  const pptxCode = pipelineState?.agents.find(a => a.id === "ppt-code-generator" && a.status === "done")?.output || undefined;

  // Revision Families (B1 / D1-D7): the fragile currentWorkflowRunId heuristic is
  // GONE — it guessed the parent by matching recentRuns on the current workflow
  // type (with a double-revision-suffix branch that could never match) and
  // orphaned every history-launched revision. Parent linkage now comes from the
  // contentSourceRunId prop (page.tsx tracks the actual on-screen run).

  // Handle PPT revision — Phase 3: launch the revision over REST (POST
  // /{id}/revisions) when a completed run exists; fall back to the legacy
  // text-injection pattern for backward compat with pre-Phase3 runs.
  const handleRevisePpt = useCallback((instruction: string) => {
    // BUG-003: do NOT let the empty-content guard block the self-sufficient REST
    // path below. On a reopened od_ppt run both pptxCode (no ppt-code-generator
    // agent → always undefined) and pptContent (empty when fullRun.output is empty
    // — LV-02) are empty, so the old content-only early-return fired nothing.
    // When a parent run id (contentSourceRunId) exists the handler
    // proceeds to postRevision (:504), which reseeds the parent deck server-side
    // and needs no local content. The legacy text-injection fallback (:519-536) is
    // reached only when contentSourceRunId is falsy and still reads the content.
    if (!contentSourceRunId && !pptxCode && !pptContent) return;

    // FIX-117: "ppt" runs produce HTML via the OD template flow (no pptxCode).
    // If we have pptContent (HTML) but no pptxCode (JavaScript), it's an HTML
    // deck regardless of the "ppt" vs "od_ppt" pipeline_type label → use
    // od_ppt_revision (HTML-capable). The legacy ppt_revision path (PptxGenJS)
    // only applies when pptxCode is present.
    const isOdPpt = workflowType === "od_ppt" || workflowType === "od_ppt_revision"
      || (!!pptContent && !pptxCode);

    // W3b (44-05): launch the revision when we have a completed parent run id.
    // POST /{id}/revisions (Strategy A — the byte-twin of engine._handle_revision:
    // server-side artifact seed + planning-context prepend + exact-kind
    // derived_from lineage), then attach the returned run so it streams over SSE
    // (W1). REST is the sole up-channel (44-06). contentSourceRunId is the
    // explicit parent (bug (b): no orphaned run — source_workflow_run_id is
    // written server-side from it).
    if (contentSourceRunId) {
      const targetType = isOdPpt ? "od_ppt_output" : "ppt_output";
      // FIX-173: switch to the execution view IMMEDIATELY so the user sees the
      // revision progress screen rather than the old completed run's content
      // until the first pipeline_start event arrives (the same pattern the
      // onStartPipeline path and the wizard launch path already follow).
      setMainView("execution");
      void postRevision(getToken() ?? "", contentSourceRunId, {
        target_artifact_type: targetType,
        instruction,
      })
        .then(({ run_id }) => {
          if (run_id) {
            runConnection.attachRun(run_id);
            // FIX-170: update page.tsx's routing refs so the new revision run's
            // SSE events (pipeline_start, agent_*) are NOT blocked by
            // isForeignRunFrame. Without this, trackedRunIdRef still points to
            // the old completed run → all revision events discarded → UI frozen.
            onRevisionLaunched?.(run_id);
          }
        })
        .catch((e) => console.error("postRevision failed", e));
      setWorkflowType((isOdPpt ? "od_ppt_revision" : "ppt_revision") as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      return;
    }

    // Legacy fallback
    if (isOdPpt) {
      const existingHtml = pptContent || "";
      const revisionMessage = `=== EXISTING HTML DECK ===\n${existingHtml.slice(0, 60000)}\n=== END EXISTING DECK ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
      setWorkflowType("od_ppt_revision" as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      if (onStartPipeline) {
        onStartPipeline("od_ppt_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
      }
    } else {
      const existingCode = pptxCode || "";
      const revisionMessage = `=== EXISTING PRESENTATION CODE ===\n${existingCode}\n=== END EXISTING CODE ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
      setWorkflowType("ppt_revision" as WorkflowType);
      if (onResetPipeline) onResetPipeline();
      if (onStartPipeline) {
        onStartPipeline("ppt_revision", revisionMessage, undefined, attachedSkills, attachedHooks);
      }
    }
  }, [workflowType, pptxCode, pptContent, contentSourceRunId, runConnection, onStartPipeline, onResetPipeline, onRevisionLaunched, attachedSkills, attachedHooks]);

  // Handle User Story revision — re-run pipeline with existing backlog + change instruction
  const handleReviseUserStory = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING PRODUCT BACKLOG ===\n${userStoryContent}\n=== END EXISTING BACKLOG ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("user_stories_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      // Revision Families (B1): link the parent so the backend assembles the family.
      onStartPipeline("user_stories_revision", revisionMessage, undefined, attachedSkills, attachedHooks, { source_workflow_run_id: contentSourceRunId || undefined, _display_title: instruction.slice(0, 60) });
    }
  }, [userStoryContent, contentSourceRunId, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle Prototype revision — surgical diff approach
  // Instead of asking the agent to reproduce the full HTML (which exceeds
  // model output token limits), we pass the full HTML but instruct the agent
  // to output ONLY the changed sections in a structured diff format.
  // The engine then merges the diff back into the original HTML.
  const handleRevisePrototype = useCallback((instruction: string) => {
    if (!prototypeContent) return;
    // Pass the full prototype HTML — no slice. The agent will output only the
    // changed sections, not the full document.
    const revisionMessage = `=== EXISTING PROTOTYPE HTML ===\n${prototypeContent}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("prototype_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      // Phase 5: send source_workflow_run_id so the backend can seed the
      // original run's spec/design into the revision sandbox. B1: sourced from the
      // contentSourceRunId prop (the actual on-screen run) — undefined when none.
      onStartPipeline("prototype_revision", revisionMessage, undefined, attachedSkills, attachedHooks, { ...(contentSourceRunId ? { source_workflow_run_id: contentSourceRunId } : {}), _display_title: instruction.slice(0, 60) });
    }
  }, [prototypeContent, contentSourceRunId, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle App Builder revision — re-run pipeline with existing blueprint + change instruction
  const handleReviseAppBuilder = useCallback((instruction: string) => {
    if (!userStoryContent) return;
    const revisionMessage = `=== EXISTING APP BLUEPRINT ===\n${userStoryContent.slice(0, 40000)}\n=== END EXISTING BLUEPRINT ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
    setWorkflowType("app_builder_revision" as WorkflowType);
    if (onResetPipeline) onResetPipeline();
    if (onStartPipeline) {
      // Revision Families (B1): link the parent so the backend assembles the family.
      onStartPipeline("app_builder_revision", revisionMessage, undefined, attachedSkills, attachedHooks, { source_workflow_run_id: contentSourceRunId || undefined, _display_title: instruction.slice(0, 60) });
    }
  }, [userStoryContent, contentSourceRunId, onStartPipeline, onResetPipeline, attachedSkills, attachedHooks]);

  // Handle incoming questionnaire data from WebSocket
  useEffect(() => {
    if (questionnaireData && questionnaireData.questions) {
      setQuestionnaireQuestions(questionnaireData.questions);
      setQuestionnaireLoading(false);
    }
  }, [questionnaireData]);

  // If the WebSocket reconnects while a pipeline run is in-flight (i.e. the
  // user submitted the questionnaire but the connection dropped before the
  // run_pipeline message was delivered), re-send it on the new connection.
  const pendingPipelineRunRef = useRef<typeof pendingPipelineRun>(null);
  useEffect(() => {
    pendingPipelineRunRef.current = pendingPipelineRun;
  }, [pendingPipelineRun]);

  // Ref to store a pipeline start that needs to be fired once connected.
  // Used to survive WebSocket reconnects that happen between questionnaire
  // submit and pipeline_start arriving (e.g. hot-reload in dev, network blip).
  const pendingStartOnConnectRef = useRef<{
    type: string; message: string; agentIds?: string[];
    extraParams?: Record<string, unknown>;
  } | null>(null);

  // BUG-007: object-identity latches for the launch-consumer effects. The only
  // guard below is `if (!pendingOdProtoParams) return;` + an ASYNC clear, so
  // React StrictMode's dev double mount-effect invoke passes it twice before the
  // clear lands and mints two runs for one launch. A synchronous ref compare
  // makes the SAME param object mint once while a NEW launch (new object) still
  // mints — the ref persists across the same-instance double invoke.
  const launchedProtoParamsRef = useRef<object | null>(null);
  const launchedPptParamsRef = useRef<object | null>(null);

  // Fire any pending pipeline start as soon as the WebSocket is connected.
  useEffect(() => {
    if (connectionStatus !== "connected") return;
    const pending = pendingStartOnConnectRef.current;
    if (!pending) return;
    pendingStartOnConnectRef.current = null;
    if (onStartPipeline) {
      onStartPipeline(pending.type, pending.message, pending.agentIds, attachedSkills, attachedHooks, pending.extraParams);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionStatus]);

  // Reconnection is owned by the SSE transport (useRunStream) — it reconnects
  // natively and replays from Last-Event-ID, so there is no client-side
  // re-attach frame to send (44-06 hard cutoff).

  // When pendingOdProtoParams arrives (set by dashboard/page.tsx after the
  // When pendingOdProtoParams arrives, immediately start the od_prototype pipeline.
  // Phase 2 (Universal Engine): the legacy generate_questions pre-flight is
  // retired. We fire run_pipeline straight away; the Deep_Planner_Agent will
  // emit questionnaire_ready mid-run if it needs clarification (CLARIFY_REQUIRED).
  useEffect(() => {
    if (!pendingOdProtoParams) return;
    // BUG-007: latch on object identity BEFORE any side effect so the second
    // StrictMode mount-invoke early-returns without a second mint.
    if (launchedProtoParamsRef.current === pendingOdProtoParams) return;
    launchedProtoParamsRef.current = pendingOdProtoParams;
    setMainView("execution");
    setWorkflowType("prototype");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    if (onClearPendingOdProto) onClearPendingOdProto();

    const extraParams = {
      template_id: pendingOdProtoParams.templateId,
      design_system_id: pendingOdProtoParams.designSystemId,
      ...(pendingOdProtoParams.customDsBody ? { custom_ds_body: pendingOdProtoParams.customDsBody } : {}),
      ...(pendingOdProtoParams.customTemplateBody ? { custom_template_body: pendingOdProtoParams.customTemplateBody } : {}),
      discovery: pendingOdProtoParams.discovery,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pendingOdProtoParams.sourceRunId ? { source_workflow_run_id: pendingOdProtoParams.sourceRunId } : {}),
      // Phase 6: per-run gate selection. Only when explicitly provided (touched);
      // an empty array is a valid "no gates" choice, so guard on presence (!== undefined),
      // NOT truthiness. Absent ⇒ omitted ⇒ backend static default (byte-identical).
      ...(pendingOdProtoParams.gateAgentIds !== undefined ? { gate_agent_ids: pendingOdProtoParams.gateAgentIds } : {}),
      // Advanced agent config from wizard AgentsPopup
      ...(pendingOdProtoParams.modelOverrides && Object.keys(pendingOdProtoParams.modelOverrides).length > 0 ? { model_overrides: pendingOdProtoParams.modelOverrides } : {}),
      ...(pendingOdProtoParams.selections && Object.keys(pendingOdProtoParams.selections).length > 0 ? { selections: pendingOdProtoParams.selections } : {}),
      ...(pendingOdProtoParams.images && pendingOdProtoParams.images.length > 0 ? { images: pendingOdProtoParams.images } : {}),
    };

    if (onStartPipeline) {
      // FIX-155: always create a SEPARATE notification for the od_prototype run
      // so it doesn't collide with a concurrently-running user_stories notification.
      // The odProtoNotifCreated reactive effect may fire later (after pipelineState
      // reflects the new run) — we pre-empt it by setting odProtoNotifId now so
      // the reactive path skips the addRunningNotification call.
      const notifId = `pipeline-${Date.now()}`;
      odProtoNotifId.current = notifId;
      currentPipelineNotifId.current = notifId;
      addRunningNotification(notifId, "prototype", pendingOdProtoParams.brief.slice(0, 60), 0);
      const agentIds = pendingOdProtoParams.agentIds ?? [];
      if (connectionStatus === "connected") {
        onStartPipeline("od_prototype" as WorkflowType, pendingOdProtoParams.brief, agentIds, attachedSkills, attachedHooks, extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: "od_prototype" as WorkflowType,
          message: pendingOdProtoParams.brief,
          agentIds,
          extraParams,
        };
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOdProtoParams]);

  // When pendingOdPptParams arrives, immediately start the od_ppt pipeline.
  // Phase 2 (Universal Engine): the legacy generate_questions pre-flight is
  // retired. We fire run_pipeline straight away; the Deep_Planner_Agent will
  // emit questionnaire_ready mid-run if it needs clarification (CLARIFY_REQUIRED).
  useEffect(() => {
    if (!pendingOdPptParams) return;
    // BUG-007: latch on object identity BEFORE any side effect so the second
    // StrictMode mount-invoke early-returns without a second mint.
    if (launchedPptParamsRef.current === pendingOdPptParams) return;
    launchedPptParamsRef.current = pendingOdPptParams;
    setMainView("execution");
    setWorkflowType("ppt");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    if (onClearPendingOdPpt) onClearPendingOdPpt();

    const extraParams = {
      template_id: pendingOdPptParams.templateId,
      ...(pendingOdPptParams.designSystemId ? { design_system_id: pendingOdPptParams.designSystemId } : {}),
      ...(pendingOdPptParams.customDsBody ? { custom_ds_body: pendingOdPptParams.customDsBody } : {}),
      ...(pendingOdPptParams.customTemplateBody ? { custom_template_body: pendingOdPptParams.customTemplateBody } : {}),
      discovery: pendingOdPptParams.discovery,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pendingOdPptParams.sourceRunId ? { source_workflow_run_id: pendingOdPptParams.sourceRunId } : {}),
      // Phase 6: per-run gate selection. Only when explicitly provided (touched);
      // empty array = valid "no gates" → guard on presence, not truthiness.
      ...(pendingOdPptParams.gateAgentIds !== undefined ? { gate_agent_ids: pendingOdPptParams.gateAgentIds } : {}),
      // Advanced agent config from wizard AgentsPopup
      ...(pendingOdPptParams.modelOverrides && Object.keys(pendingOdPptParams.modelOverrides).length > 0 ? { model_overrides: pendingOdPptParams.modelOverrides } : {}),
      ...(pendingOdPptParams.selections && Object.keys(pendingOdPptParams.selections).length > 0 ? { selections: pendingOdPptParams.selections } : {}),
      ...(pendingOdPptParams.images && pendingOdPptParams.images.length > 0 ? { images: pendingOdPptParams.images } : {}),
    };

    if (onStartPipeline) {
      // FIX-155: always create a SEPARATE notification for the od_ppt run so it
      // doesn't collide with concurrently-running user_stories / od_prototype
      // notifications. Pre-empts the odProtoNotifCreated reactive path.
      const notifId = `pipeline-${Date.now()}`;
      odPptNotifId.current = notifId;
      currentPipelineNotifId.current = notifId;
      addRunningNotification(notifId, "ppt", pendingOdPptParams.brief.slice(0, 60), 0);
      const agentIds = pendingOdPptParams.agentIds ?? [];
      if (connectionStatus === "connected") {
        onStartPipeline("od_ppt" as WorkflowType, pendingOdPptParams.brief, agentIds, attachedSkills, attachedHooks, extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: "od_ppt" as WorkflowType,
          message: pendingOdPptParams.brief,
          agentIds,
          extraParams,
        };
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOdPptParams]);

  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — a saved workflow carries a persisted
  // composition (`agent_ids` + `model_overrides`) that `onSelectFeature` (a bare
  // WorkflowType) cannot express. We stash it here and thread it into IdeaInputPage
  // as the launch-preload seeds. Cleared on a normal select so a non-saved launch
  // starts from the empty filter (no stale seed bleed — T-21-12).
  const [savedComposition, setSavedComposition] = useState<{
    agentIds: string[];
    modelOverrides: Record<string, string>;
    selections: Record<string, Record<string, unknown>>;
    brief?: string;
    gateAgentIds?: string[];
    // 41-04 — edit-from-My-Workflows carries the saved name/description into the
    // full-page Composer (mainView='composer') so it mounts PRE-LOADED.
    name?: string;
    description?: string;
  } | null>(null);

  // Fused Home (SHELL-02 SC-1) — the launcher-brief captured on the home landing,
  // and the pending brief handed to the input view for the generic launch path.
  const [homeBrief, setHomeBrief] = useState("");
  const [pendingHomeBrief, setPendingHomeBrief] = useState<string | undefined>(undefined);

  // Navigate from Home to Input page — EXCEPT the custom-compose entry, which
  // (41-04, D-CMP-ENTRY) opens the full-page Composer surface (mainView='composer')
  // fresh instead of the brief/input view. All other deliverable types keep the
  // existing home→input seam unchanged.
  const handleSelectFeature = useCallback((type: WorkflowType) => {
    setSavedComposition(null);
    setWorkflowType(type);
    setMainView(type === ("custom" as WorkflowType) ? "composer" : "input");
  }, []);

  // Fused Home launcher: carry the typed brief into the input view, then reuse the
  // existing home→input seam. Wizard-routed types (prototype/ppt/requiresWizard) are
  // intercepted INSIDE HomeLaunchGrid before this runs, so they keep their own brief
  // entry. SC-001: keyed on the generic WorkflowType, never a workflow-name branch.
  const handleHomeSelectFeature = useCallback((type: WorkflowType) => {
    setPendingHomeBrief(homeBrief.trim() || undefined);
    handleSelectFeature(type);
  }, [homeBrief, handleSelectFeature]);

  // Launch a saved workflow — mirrors handleSelectFeature but carries the saved
  // composition into state so IdeaInputPage mounts PRE-LOADED. Run then flows
  // UNCHANGED through handleRunPipeline → useWorkflow.startPipeline (which already
  // sends agent_ids + merges model_overrides) → re-validated server-side at launch
  // (SC-001: pure-data replay, no engine/run-path edit, no `if saved` fork).
  const handleLaunchSaved = useCallback((saved: UserWorkflowSummary) => {
    // Fused Home: a saved-workflow launch owns its own preload (initialInput via
    // savedComposition.brief); clear any stale home-launcher brief so it can't leak.
    setPendingHomeBrief(undefined);
    // WR-01: carry the persisted Advanced-lever selections so the launched saved
    // workflow re-loads AND re-sends them (previously selections never reached launch).

    // For PPT and Prototype saved workflows, extract _wizard config and route
    // directly to the wizard page (restoring templateId, designSystemId, brief, etc.)
    if (saved.base_pipeline_type === "od_ppt" || saved.base_pipeline_type === "ppt") {
      const wizard = (saved.selections?._wizard ?? {}) as Record<string, unknown>;
      const draft: Record<string, unknown> = {
        templateId: wizard.templateId ?? null,
        designSystemId: wizard.designSystemId ?? null,
        brief: wizard.brief ?? "",
        ...(wizard.customDsBody ? { customDsBody: wizard.customDsBody } : {}),
        ...(wizard.customTemplateBody ? { customTemplateBody: wizard.customTemplateBody } : {}),
        ...(wizard.gateAgentIds !== undefined ? { gateAgentIds: wizard.gateAgentIds } : {}),
        ...(saved.model_overrides && Object.keys(saved.model_overrides).length > 0 ? { modelOverrides: saved.model_overrides } : {}),
        // Pass selections (without _wizard key) so AgentsPopup can restore them
        ...(saved.selections && Object.keys(saved.selections).filter(k => k !== "_wizard").length > 0
          ? { selections: Object.fromEntries(Object.entries(saved.selections).filter(([k]) => k !== "_wizard")) }
          : {}),
        agentIds: saved.agent_ids,
      };
      sessionStorage.setItem("ppt.draft", JSON.stringify(draft));
      router.push("/workflow/create?mode=ppt");
      return;
    }

    if (saved.base_pipeline_type === "od_prototype" || saved.base_pipeline_type === "prototype") {
      const wizard = (saved.selections?._wizard ?? {}) as Record<string, unknown>;
      const draft: Record<string, unknown> = {
        templateId: wizard.templateId ?? null,
        designSystemId: wizard.designSystemId ?? null,
        brief: wizard.brief ?? "",
        ...(wizard.customDsBody ? { customDsBody: wizard.customDsBody } : {}),
        ...(wizard.customTemplateBody ? { customTemplateBody: wizard.customTemplateBody } : {}),
        ...(wizard.gateAgentIds !== undefined ? { gateAgentIds: wizard.gateAgentIds } : {}),
        ...(saved.model_overrides && Object.keys(saved.model_overrides).length > 0 ? { modelOverrides: saved.model_overrides } : {}),
        // Pass selections (without _wizard key) so AgentsPopup can restore them
        ...(saved.selections && Object.keys(saved.selections).filter(k => k !== "_wizard").length > 0
          ? { selections: Object.fromEntries(Object.entries(saved.selections).filter(([k]) => k !== "_wizard")) }
          : {}),
        agentIds: saved.agent_ids,
      };
      sessionStorage.setItem("prototype.draft", JSON.stringify(draft));
      router.push("/workflow/create?mode=prototype");
      return;
    }

    setSavedComposition({
      agentIds: saved.agent_ids,
      modelOverrides: saved.model_overrides ?? {},
      selections: saved.selections ?? {},
      brief: typeof saved.selections?._wizard?.brief === "string"
        ? (saved.selections._wizard.brief as string)
        : undefined,
      gateAgentIds: Array.isArray(saved.selections?._wizard?.gateAgentIds)
        ? (saved.selections!._wizard!.gateAgentIds as string[])
        : undefined,
      name: saved.name,
      description: saved.description ?? undefined,
    });
    setWorkflowType(saved.base_pipeline_type as WorkflowType);
    // 41-04 — edit-from-My-Workflows opens the full-page Composer PRE-LOADED with
    // the saved agents + selections (D-CMP-ENTRY). The composer's per-run Run wiring
    // lands in 41-06; until then this is the authoring/edit entry for saved workflows.
    setMainView("composer");
  }, [router]);

  // Run the pipeline from Input page — triggers questionnaire first
  // `resolvedType` is the concrete pipeline the backend will dispatch. For
  // most workflows it matches the parent state; for the `migration` meta
  // type the IdeaInputPage resolves it to a real sub-pipeline (Mulesoft→
  // Spring Boot or .NET→Azure) before invoking us. We sync `workflowType`
  // here so downstream effects (chaining, sidebar labels, completion
  // tracking) see the real pipeline.
  const handleRunPipeline = useCallback((message: string, agentIds: string[], resolvedType: WorkflowType, extraParams?: Record<string, unknown>) => {
    setWorkflowInput(message);
    setMainView("execution");
    setWorkflowType(resolvedType);

    // Reset previous pipeline state so left panel clears
    if (onResetPipeline) onResetPipeline();

    // Phase 2 (Universal Engine): start the pipeline directly. The Deep_Planner_Agent
    // runs first and gates execution; the clarify questionnaire now appears mid-run
    // ONLY when the planner issues CLARIFY_REQUIRED (via the `questionnaire_ready`
    // event). The legacy `generate_questions` pre-step and its 15s timeout are retired.
    //
    // `extraParams` (Phase 6) carries the per-run Human-review gate selection as
    // `{ gate_agent_ids: string[] }` — but ONLY when the user touched the
    // Review-gates section in IdeaInputPage. When undefined we pass nothing, so
    // the run_pipeline payload is byte-identical to before this feature.
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // Strip injected context/revision markers before using as notification title
      // so the panel never shows raw "=== EXISTING PROTOTYPE HTML ===" text.
      const parsedMsg = parseRunInput(message);
      let notifTitle = (parsedMsg.revisionInstruction ?? parsedMsg.brief ?? "").trim();
      // FIX-130: if message is dominated by a context block, pull Original Brief from it
      if (!notifTitle && parsedMsg.chainContext) {
        const origBriefMatch = parsedMsg.chainContext.match(/Original Brief:\s*(.+)/);
        notifTitle = origBriefMatch ? origBriefMatch[1].split("\n")[0].trim() : "";
      }
      const cleanNotifTitle = (notifTitle || message).slice(0, 60);
      addRunningNotification(notifId, resolvedType, cleanNotifTitle, 0);
      // FIX-130: inject _display_title so page.tsx onStartPipeline can set a
      // clean submittedBrief even when extraParams has no _display_title yet
      // (IdeaInputPage/LaunchWizard path never sets it directly).
      const enrichedExtraParams = notifTitle
        ? { ...(extraParams || {}), _display_title: notifTitle.slice(0, 60) }
        : extraParams;
      if (connectionStatus === "connected") {
        onStartPipeline(resolvedType, message, agentIds, attachedSkills, attachedHooks, enrichedExtraParams);
      } else {
        pendingStartOnConnectRef.current = { type: resolvedType, message, agentIds, extraParams: enrichedExtraParams };
      }
    }
  }, [onStartPipeline, onResetPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Go back to home
  const handleGoHome = useCallback(() => {
    setMainView("home");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (!isPipelineRunning && onResetPipeline) onResetPipeline();
  }, [onResetPipeline, isPipelineRunning]);

  // "Edit brief & run again" — navigate to the input view so the user can
  // modify their brief and start a fresh run (does NOT resume from checkpoint).
  // Pre-fills the brief from submittedBrief when available so the user can edit
  // rather than retype from scratch. Resets pipeline state so the input page
  // starts clean (no stale failed-run overlay).
  const handleEditBrief = useCallback(() => {
    if (!isPipelineRunning && onResetPipeline) onResetPipeline();
    setResumeError(null);
    setQuestionnaireQuestions([]);
    setMainView("input");
  }, [isPipelineRunning, onResetPipeline]);

  // Chain to another pipeline using previous output as context
  const handleChainPipeline = useCallback(async (nextType: WorkflowType) => {
    // Check if this chain target requires a wizard (prototype, ppt)
    const option = CHAIN_OPTIONS.find((o) => o.type === nextType);

    // Find the source run ID for context fetching.
    // FIX-139: always prefer contentSourceRunId (the explicit "run currently on
    // screen") over a recentRuns type-scan. The type-scan is unreliable when
    // multiple completed runs of the same type exist — it returns whichever
    // matches first (which can be an older run). contentSourceRunId is set by
    // page.tsx on pipeline_complete and on history-reopen, so it always points
    // at the run the user is CURRENTLY viewing. Fall back to the type-scan only
    // when contentSourceRunId is absent (e.g. initial state).
    const sourceRunId: string | undefined =
      contentSourceRunId ??
      recentRuns?.find(
        r => baseWorkflowType(r.type as WorkflowType) === baseWorkflowType(workflowType) && r.status === "completed"
      )?.id;

    if (option?.requiresWizard && option.wizardPath) {
      // Store the current brief so the wizard can pre-fill it
      const cleanBrief = workflowInput.split("\n\n===")[0].trim();
      sessionStorage.setItem(CHAIN_BRIEF_KEY, cleanBrief);
      sessionStorage.setItem(CHAIN_FROM_KEY, workflowType);
      if (sourceRunId) {
        sessionStorage.setItem(CHAIN_SOURCE_RUN_ID_KEY, sourceRunId);
        // Also store the structured context so the wizard can pass it
        // as part of the brief when the pipeline fires
        try {
          const token = getToken();
          if (token) {
            const ctx = await getChainContext(token, sourceRunId);
            if (ctx.context_block) {
              sessionStorage.setItem("chain.context_block", ctx.context_block);
            }
          }
        } catch { /* non-fatal */ }
      } else {
        sessionStorage.removeItem(CHAIN_SOURCE_RUN_ID_KEY);
        sessionStorage.removeItem("chain.context_block");
      }
      router.push(option.wizardPath);
      return;
    }

    setWorkflowType(nextType);

    // Fetch structured context from the source run
    let contextBlock = "";
    if (sourceRunId) {
      try {
        const token = getToken();
        if (token) {
          const ctx = await getChainContext(token, sourceRunId);
          contextBlock = ctx.context_block;
        }
      } catch {
        // Fallback: use the old approach
        const isHtmlOutput = workflowType === "od_ppt" || workflowType === "od_ppt_revision" ||
          workflowType === "od_prototype" || workflowType === "prototype" || workflowType === "prototype_revision";
        contextBlock = isHtmlOutput
          ? `=== CONTEXT FROM PREVIOUS PIPELINE (${workflowType}) ===\n[${workflowType} output — HTML file]\n=== END PREVIOUS CONTEXT ===`
          : `=== CONTEXT FROM PREVIOUS PIPELINE (${workflowType}) ===\n${lastPipelineOutput.slice(0, 4000)}\n=== END PREVIOUS CONTEXT ===`;
      }
    }

    // Workstream C1 (INV-12): the single parser owns marker extraction. For a
    // plain brief -> its clean brief; for a revision blob (starts with ===) ->
    // the revision instruction (parseRunInput returns brief='' for a pure blob,
    // so the empty-string fallback is subsumed).
    const parsedChain = parseRunInput(workflowInput);
    const chainBrief = parsedChain.revisionInstruction ?? parsedChain.brief;
    const enrichedInput = contextBlock
      ? `${chainBrief}\n\n${contextBlock}`.trim()
      : chainBrief;

    if (onResetPipeline) onResetPipeline();
    setWorkflowInput(enrichedInput);

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // chainBrief is the stripped user brief (no markers); use it as the
      // notification title so the panel never shows raw context block text.
      const chainNotifTitle = (chainBrief || enrichedInput).slice(0, 60);
      addRunningNotification(notifId, nextType, chainNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(nextType, enrichedInput, [], attachedSkills, attachedHooks, { _display_title: chainBrief });
      } else {
        pendingStartOnConnectRef.current = { type: nextType, message: enrichedInput, agentIds: [], extraParams: { _display_title: chainBrief } };
      }
    }
  }, [workflowType, workflowInput, lastPipelineOutput, recentRuns, contentSourceRunId, onStartPipeline, onResetPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Chain to another pipeline starting from a historical run. The user is
  // viewing a past WorkflowRun in the history view; they pick a next
  // pipeline. We must use the historical run's input/output for the
  // enrichment (NOT the current dashboard state, which is stale for the
  // run they just opened from history). After dispatching we switch to
  // the execution view so the new pipeline shows the agent progress.
  const handleChainFromHistory = useCallback(async (run: WorkflowRun, nextType: WorkflowType) => {
    const option = CHAIN_OPTIONS.find((o) => o.type === nextType);
    if (option?.requiresWizard && option.wizardPath) {
      const cleanBrief = (run.input || "").split("\n\n===")[0].trim();
      sessionStorage.setItem(CHAIN_BRIEF_KEY, cleanBrief);
      sessionStorage.setItem(CHAIN_FROM_KEY, run.type);
      if (run.id) {
        sessionStorage.setItem(CHAIN_SOURCE_RUN_ID_KEY, run.id);
        try {
          const token = getToken();
          if (token) {
            const ctx = await getChainContext(token, run.id);
            if (ctx.context_block) {
              sessionStorage.setItem("chain.context_block", ctx.context_block);
            }
          }
        } catch { /* non-fatal */ }
      } else {
        sessionStorage.removeItem(CHAIN_SOURCE_RUN_ID_KEY);
        sessionStorage.removeItem("chain.context_block");
      }
      router.push(option.wizardPath);
      return;
    }

    // Fetch structured context from the source run
    let contextBlock = "";
    try {
      const token = getToken();
      if (token && run.id) {
        const ctx = await getChainContext(token, run.id);
        contextBlock = ctx.context_block;
      }
    } catch {
      // Fallback
      const isHtmlOutput = run.type === "od_ppt" || run.type === "od_ppt_revision" ||
        run.type === "od_prototype" || run.type === "prototype" || run.type === "prototype_revision";
      const baseOutput = isHtmlOutput
        ? `[${run.title || run.type} output — HTML file]`
        : (run.output || "").slice(0, 4000);
      if (baseOutput) {
        contextBlock = `=== CONTEXT FROM PREVIOUS PIPELINE (${run.type}) ===\n${baseOutput}\n=== END PREVIOUS CONTEXT ===`;
      }
    }

    // Workstream C1 (INV-12): same single-parser rewire as handleChainPipeline.
    const parsedHistory = parseRunInput(run.input || "");
    const historyBrief = parsedHistory.revisionInstruction ?? parsedHistory.brief;
    const enrichedInput = contextBlock ? `${historyBrief}\n\n${contextBlock}`.trim() : historyBrief;

    setWorkflowType(nextType);
    setWorkflowInput(enrichedInput);
    setLastPipelineOutput(run.output || "");
    setCompletedPipelineTypes((prev) =>
      prev.includes(run.type as WorkflowType) ? prev : [...prev, run.type as WorkflowType],
    );
    setMainView("execution");
    if (onResetPipeline) onResetPipeline();

    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      // historyBrief is the stripped user brief (no markers); use it so the
      // panel never shows raw context block text for history-chained runs.
      const historyNotifTitle = (historyBrief || enrichedInput).slice(0, 60);
      addRunningNotification(notifId, nextType, historyNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(nextType, enrichedInput, [], attachedSkills, attachedHooks, { _display_title: historyBrief });
      } else {
        pendingStartOnConnectRef.current = { type: nextType, message: enrichedInput, agentIds: [], extraParams: { _display_title: historyBrief } };
      }
    }
  }, [onStartPipeline, onResetPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Handle questionnaire answers.
  //
  // Phase 2 (Universal Engine): when the questionnaire was raised mid-run by the
  // Clarify_Engine (CLARIFY_REQUIRED gate), `activePipelineRunId` is set — we send
  // `submit_questionnaire` to resume the paused run from the gate (no restart).
  //
  // Legacy path (no active run id): build an enriched message and start the
  // pipeline — retained for any flow still pre-questioning.
  const handleQuestionnaireSubmit = useCallback((answers: Record<string, string[]>, freeformInput: string) => {
    // ── New flow: resume a paused run ────────────────────────────────────
    if (activePipelineRunId && onSubmitQuestionnaire) {
      const responses: Array<{ question_id: string; answer: string }> = [];
      questionnaireQuestions.forEach((q) => {
        const selected = answers[q.id];
        if (selected && selected.length > 0) {
          responses.push({ question_id: q.id, answer: selected.join(", ") });
        }
      });
      if (freeformInput) {
        responses.push({ question_id: "freeform", answer: freeformInput });
      }
      // Workstream C1 (POR §6.5): fold the answered Q&A into run-scoped state
      // BEFORE clearing the panel — order matters, else the round is lost.
      if (onRetainClarifyRound) {
        const round = {
          round: (pipelineState?.clarifications?.length ?? 0) + 1,
          qa: questionnaireQuestions.map((q) => {
            const selected = answers[q.id];
            return {
              question_id: q.id,
              question_text: q.question,
              impact_level: q.impactLevel ?? "",
              answer: selected && selected.length > 0 ? selected.join(", ") : null,
            };
          }),
        };
        onRetainClarifyRound(round);
      }
      setQuestionnaireQuestions([]);
      setQuestionnaireLoading(false);
      onSubmitQuestionnaire(activePipelineRunId, responses);
      return;
    }

    // ── Legacy flow: enrich message + start pipeline ─────────────────────
    if (!pendingPipelineRun) return;

    let enrichedMessage = pendingPipelineRun.message;
    const answerLines: string[] = [];
    questionnaireQuestions.forEach((q) => {
      const selected = answers[q.id];
      if (selected && selected.length > 0) {
        answerLines.push(`- ${q.question}: ${selected.join(", ")}`);
      }
    });
    if (freeformInput) {
      answerLines.push(`- Additional notes: ${freeformInput}`);
    }
    if (answerLines.length > 0) {
      enrichedMessage = `${pendingPipelineRun.message}\n\n=== USER PREFERENCES ===\n${answerLines.join("\n")}\n=== END PREFERENCES ===`;
    }

    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      const parsedPending = parseRunInput(pendingPipelineRun.message);
      const pendingNotifTitle = (parsedPending.revisionInstruction ?? parsedPending.brief ?? pendingPipelineRun.message).slice(0, 60);
      addRunningNotification(notifId, pendingPipelineRun.type, pendingNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(pendingPipelineRun.type, enrichedMessage, pendingPipelineRun.agentIds, attachedSkills, attachedHooks, pendingPipelineRun.extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: pendingPipelineRun.type,
          message: enrichedMessage,
          agentIds: pendingPipelineRun.agentIds,
          extraParams: pendingPipelineRun.extraParams,
        };
      }
    }
  }, [activePipelineRunId, onSubmitQuestionnaire, onRetainClarifyRound, pipelineState, pendingPipelineRun, questionnaireQuestions, onStartPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Skip questionnaire.
  // New flow (ISS-027): submit empty answers WITH skip_clarification=true so the
  // backend ClarifyEngine force-proceeds immediately and runs with best-available
  // context — instead of re-asking the same questions for up to 3 rounds (which
  // an empty submit alone triggered, contradicting the "run directly" label).
  // Legacy flow: start the pipeline with the un-enriched message.
  const handleQuestionnaireSkip = useCallback(() => {
    if (activePipelineRunId && onSubmitQuestionnaire) {
      setQuestionnaireQuestions([]);
      setQuestionnaireLoading(false);
      onSubmitQuestionnaire(activePipelineRunId, [], true);
      return;
    }

    if (!pendingPipelineRun) return;
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onStartPipeline) {
      const notifId = `pipeline-${Date.now()}`;
      currentPipelineNotifId.current = notifId;
      const parsedSkip = parseRunInput(pendingPipelineRun.message);
      const skipNotifTitle = (parsedSkip.revisionInstruction ?? parsedSkip.brief ?? pendingPipelineRun.message).slice(0, 60);
      addRunningNotification(notifId, pendingPipelineRun.type, skipNotifTitle, 0);
      if (connectionStatus === "connected") {
        onStartPipeline(pendingPipelineRun.type, pendingPipelineRun.message, pendingPipelineRun.agentIds, attachedSkills, attachedHooks, pendingPipelineRun.extraParams);
      } else {
        pendingStartOnConnectRef.current = {
          type: pendingPipelineRun.type,
          message: pendingPipelineRun.message,
          agentIds: pendingPipelineRun.agentIds,
          extraParams: pendingPipelineRun.extraParams,
        };
      }
    }
  }, [activePipelineRunId, onSubmitQuestionnaire, pendingPipelineRun, onStartPipeline, connectionStatus, attachedSkills, attachedHooks, addRunningNotification]);

  // Cancel the active pipeline from the clarification step and navigate to dashboard.
  // Two-step sequence: submit_questionnaire(skip=true) unblocks the gate, then a
  // REST cancel terminates the now-running pipeline. All state resets to initial.
  // KAN-90: "Cancel Workflow" button in QuestionnairePanel confirmation dialog.
  const handleCancelWorkflow = useCallback(() => {
    // Set the flag BEFORE navigating so the isRunning effect doesn't fight us
    cancelNavigatingHomeRef.current = true;
    // Navigate home and reset state IMMEDIATELY — before any async work
    setMainView("home");
    setQuestionnaireQuestions([]);
    setQuestionnaireLoading(false);
    setPendingPipelineRun(null);
    if (onResetPipeline) onResetPipeline();

    if (activePipelineRunId && onSubmitQuestionnaire) {
      // Step 1: unblock the clarify gate (fire and forget)
      onSubmitQuestionnaire(activePipelineRunId, [], true);
      // Step 2: cancel the now-unblocked pipeline after a short delay.
      // W2 (44-04): POST /{id}/cancel with the run id threaded — REST is the sole
      // up-channel (44-06).
      setTimeout(() => {
        void postCancel(getToken() ?? "", activePipelineRunId).catch((e) =>
          console.error("postCancel (cancel workflow) failed", e),
        );
      }, 200);
    }
  }, [activePipelineRunId, onSubmitQuestionnaire, onResetPipeline]);

  // Handle "Reject & cancel pipeline" from the ReviewGatePanel.
  // KAN-95: the raw onRejectReview prop (from page.tsx) only sends the WS message
  // and clears reviewGateData — it does not navigate. This wrapper sets
  // cancelNavigatingHomeRef first (so the pipelineState.isRunning effect doesn't
  // snap the view back to "execution"), resets pipeline state, and navigates home
  // before delegating to the prop for the actual WS send.
  const handleRejectReview = useCallback((gateKey: string) => {
    // Set the guard BEFORE any state changes so the isRunning effect can't fight us
    cancelNavigatingHomeRef.current = true;
    // Navigate home and reset state immediately
    setMainView("home");
    if (onResetPipeline) onResetPipeline();
    // Delegate to page.tsx for the WS send + reviewGateData clear
    if (onRejectReview) onRejectReview(gateKey);
  }, [onRejectReview, onResetPipeline]);

  // Header navigation — free navigation even while pipeline runs
  const handleNavigate = useCallback((page: "home" | "library" | "history" | "settings" | "analytics" | "catalog" | "saved-workflows") => {
    setMainView(page as MainView);
  }, []);

  // ─── Phase 31 (CHATUI-01/02/03) — run chat lane derivations ──────────────────
  // The revise handler selected by the run TYPE (the SAME expression the
  // left-column AgentProgressPanel used before the lane absorbed it). Undefined
  // when the current output type has no revise path.
  //
  // BUG-003: on a COMPLETED reopen the `workflowType` sync effect (:330) is
  // isRunning-gated and never fires, leaving workflowType stale (likely
  // "user_stories") → the selector picked the wrong handler (a no-op) for a
  // reopened od_ppt run. Bind the selection to the VIEWED run's type when not
  // running (mirrors BUG-001); fall back to workflowType while running/launching
  // (viewedRunType undefined → byte-identical, no regression). SC-001-safe (keys
  // on run.type, no workflow-name literal added to a guarded component).
  // BUG-012: prefer the DURABLE threaded type (page.tsx fullRun.type); fall back
  // to the recents lookup (identical value for in-recents runs; defined for
  // out-of-recents runs where recents returns undefined).
  // BUG-012 follow-up: prefer the durable reopened type REGARDLESS of running
  // state (a reopened clarify/build run leaves isPipelineRunning true, so gating
  // the whole expression on !isPipelineRunning wrongly dropped the viewed type on
  // a non-terminal reopen). Only the recents fallback stays !isPipelineRunning-
  // gated — contentSourceRunType is null on a fresh launch, so viewedRunType stays
  // undefined there and launch->watch is byte-identical.
  const viewedRunType =
    contentSourceRunType ??
    (!isPipelineRunning && contentSourceRunId != null
      ? recentRuns?.find((r) => r.id === contentSourceRunId)?.type
      : undefined);
  const effectiveReviseType = viewedRunType ?? workflowType;
  const activeReviseHandler =
    (effectiveReviseType === "ppt" || effectiveReviseType === "ppt_revision" || effectiveReviseType === "od_ppt" || effectiveReviseType === "od_ppt_revision") ? handleRevisePpt :
    (effectiveReviseType === "user_stories" || effectiveReviseType === "user_stories_revision") ? handleReviseUserStory :
    (effectiveReviseType === "prototype" || effectiveReviseType === "prototype_revision" || effectiveReviseType === "od_prototype" || !!prototypeContent) ? handleRevisePrototype :
    (effectiveReviseType === "app_builder" || effectiveReviseType === "app_builder_revision") ? handleReviseAppBuilder :
    undefined;

  // ─── 43-02 (A.1 CRUX) — Concierge send seam + confirm round-trip ─────────────
  // The lane's send seam: the options-capable `onRunChatSend` (POST /messages)
  // when supplied, else the legacy `onSendMessage`. A settled-run ASK folds
  // `{ concierge: true }` here; a confirm chip folds the held proposal's
  // `{ concierge: true, confirm_proposal: { channel, params } }`. Per LOCK-B the
  // WS transport does not deliver the concierge fields to the Concierge until the
  // Part-C SSE cutover — this wires the DECISION + payload shape, not a live flip.
  const runChatSend = useCallback(
    (
      text: string,
      attachments?: import("@/types/index").ChatAttachment[],
      options?: SendMessageOptions,
    ) => {
      if (onRunChatSend) onRunChatSend(text, attachments, options);
      else onSendMessage?.(text);
    },
    [onRunChatSend, onSendMessage],
  );

  // Confirm a held consequential Concierge proposal: replay the confirm turn
  // through the SAME send seam, carrying the durable proposal's channel + params
  // verbatim (the backend H1 fence — 43-01 — locates its durable pending row and
  // disposes from THAT, never from this client body). Reject simply dismisses.
  const handleConfirmProposal = useCallback(
    (p: LaneProposal) => {
      runChatSend("", [], {
        concierge: true,
        confirm_proposal: { channel: p.channel, params: p.params },
      });
    },
    [runChatSend],
  );

  // ISS-054 / KAN-160: replace the permanently-empty frozen constant with the
  // live proposals from useRunChat. Falls back to RUN_CONCIERGE_PROPOSALS (still
  // an empty stable array) so non-live callers/tests render byte-identically.
  const runConciergeProposals = runChatProposals ?? RUN_CONCIERGE_PROPOSALS;

  // Reject dismisses a held proposal client-side (T-33-04-01). Now wired to
  // onDismissRunChatProposal from page.tsx's useRunChat.dismissProposal.
  const handleRejectProposal = useCallback((_id: string) => {
    onDismissRunChatProposal?.(_id);
  }, [onDismissRunChatProposal]);

  // Compaction has no backend trigger wired yet; the FE only ever SIGNALS (it
  // never compresses, D-08). A no-op-safe handler until the Part-C trigger lands
  // — deliberately NOT an invented backend call.
  const handleCompact = useCallback(() => {
    /* no-op: compaction trigger arrives with the Part-C transport (43-06) */
  }, []);

  // Stop (absorbed) — the SAME cooperative cancel the AgentProgressPanel fired.
  // The pipeline_cancelled event drives the state reset (no eager onReset).
  const handleStopPipeline = useCallback(() => {
    // W2 (44-04): REST cancel (run id threaded) — the sole up-channel (44-06).
    const runId = pipelineState?.pipelineRunId ?? activePipelineRunId;
    if (runId) {
      void postCancel(getToken() ?? "", runId).catch((e) =>
        console.error("postCancel (stop) failed", e),
      );
    }
  }, [pipelineState, activePipelineRunId]);

  // Resume a cancelled or failed run from where it stopped (KAN-120 / RESUME-18).
  // Captures the run id BEFORE any state mutation, POSTs to /api/runs/{id}/resume,
  // then attaches the SSE stream — the same pattern as handleRevisePpt/postRevision.
  // The SSE stream drives the state machine forward naturally (no onResetPipeline
  // needed before the call — calling it would wipe pipelineRunId and make the UI
  // snap back to idle before the resume fires).
  // Falls back to handleGoHome when no run id is available (safe no-op).
  const handleResumeRun = useCallback(() => {
    // Guard: if a pipeline is already running, don't try to resume (the live run
    // is in "generating" state → backend returns 409 run_not_resumable).
    if (pipelineState?.isRunning) return;
    // Priority: lastCancelledRunId (set on pipeline_cancelled, never cleared) >
    // pipelineState?.pipelineRunId (set on pipeline_start, survives cancel) >
    // contentSourceRunId (set on pipeline_complete / reopen) >
    // activePipelineRunId (clarify gate id, cleared on cancel — lowest priority).
    const runId = lastCancelledRunId ?? pipelineState?.pipelineRunId ?? contentSourceRunId ?? activePipelineRunId;
    if (!runId) {
      handleGoHome();
      return;
    }
    // Clear any prior inline resume error before attempting.
    setResumeError(null);

    const doResume = (token: string, id: string): Promise<void> =>
      postResume(token, id).then(({ run_id }) => {
        if (run_id) runConnection.attachRun(run_id);
      });

    const token = getToken() ?? "";
    void doResume(token, runId).catch((e) => {
      // KAN-120 BUG-1/BUG-4: the backend DB commit of wr.status="cancelled" is
      // async — it happens after _drive_launch_to_queue fully drains its queue
      // (~1-5s AFTER pipeline_cancelled fires on the FE). A fast click in that
      // window sees the DB with "generating" status → 409 run_not_resumable.
      // Retry once after 2.5 s so the DB commit has time to land. This covers
      // the common case (user stops build, immediately clicks Reopen) without
      // adding UI complexity. Any error other than "generating" (e.g. pipeline_already_running)
      // surfaces as an inline message — never silent home navigation.
      const detail = e?.detail ?? {};
      const code =
        (typeof detail === "object" && detail !== null && "code" in detail)
          ? (detail as Record<string, unknown>).code
          : undefined;
      if (code === "run_not_resumable" && typeof e?.message === "string" && e.message.includes("generating")) {
        // Timing race — the DB hasn't committed "cancelled" yet. Retry once after 2.5s.
        setTimeout(() => {
          void doResume(token, runId).catch((retryErr) => {
            console.error("postResume retry failed", retryErr);
            setResumeError("Could not resume the run — please try again.");
          });
        }, 2500);
        return;
      }
      // Any other error: show inline message instead of silently navigating home.
      console.error("postResume failed", e);
      if (code === "pipeline_already_running") {
        // The run is live in another tab or session — just attach this SSE stream.
        runConnection.attachRun(runId);
        return;
      }
      setResumeError("Could not resume the run — please try again.");
    });
  }, [lastCancelledRunId, pipelineState, contentSourceRunId, activePipelineRunId, runConnection, handleGoHome]);

  // GENERIC live-run state that drives the D-12 composer mode (SC-001 — never a
  // workflow name). Priority: gate > clarify > building > terminal-failure >
  // complete (has deliverable) > idle.
  const laneHasDeliverable = !!(userStoryContent || pptContent || prototypeContent || genericDeliverable?.content);
  const laneClarifyOpen = questionnaireQuestions.length > 0 && (!!pendingPipelineRun || !!activePipelineRunId);
  // Terminal keys off the GENERIC plan-05 markers (cancelled / failed /
  // degraded) — never a workflow name (SC-001, LIVE-STATE-CONTRACT §1).
  const runLaneState: RunLaneState =
    reviewGateData && isPipelineRunning ? "gate" :
    laneClarifyOpen ? "clarify" :
    isPipelineRunning ? "building" :
    (pipelineState?.failed || pipelineState?.cancelled || pipelineState?.degraded) ? "terminal" :
    laneHasDeliverable ? "complete" :
    "idle";

  // KAN-128 (FIX-143): content-derived deliverable filename for the left chat
  // panel "Run summary" DeliverableCard. Uses deriveDeliverableFilename (FIX-140,
  // FilesTab.tsx) so the chat card always agrees with the Files tab and Preview
  // URL bar. The active content slot is selected by effectiveReviseType (the same
  // value PreviewPanel uses for workflowType) — NOT the local workflowType state,
  // which is stale on history-reopened runs (it stays "user_stories" by default
  // until a wizard runs, while effectiveReviseType correctly reflects
  // contentSourceRunType e.g. "od_ppt" or "od_prototype").
  const laneActiveContent =
    effectiveReviseType === "ppt" || effectiveReviseType === "ppt_revision" ||
    effectiveReviseType === "od_ppt" || effectiveReviseType === "od_ppt_revision"
      ? pptContent
      : effectiveReviseType === "prototype" || effectiveReviseType === "prototype_revision" ||
        effectiveReviseType === "od_prototype"
        ? prototypeContent
        : userStoryContent; // user_stories, custom, app_builder, and revision variants
  const laneDerivedFilename = deriveDeliverableFilename(
    effectiveReviseType || workflowType || "user_stories",
    laneActiveContent || undefined,
    pipelineState?.deliverableFilename,
  );

  // Phase 39 (RUNUI-06) — the live run title for the lane header. BUG-001: bind
  // it to the VIEWED run (contentSourceRunId), not recentRuns[0] (the most-recent
  // run). On a fresh launch contentSourceRunId is null → recentRuns[0] = the
  // just-launched run (byte-identical to the old primary flow). On a complete /
  // history-reopen, contentSourceRunId = the viewed run → its own clean title. If
  // the viewed run is outside the recents window (find → undefined) the ternary
  // falls back to submittedBrief (the viewed run's own input on reopen), never a
  // foreign run's title. SC-001-safe (keys on run.id). The lane falls back further
  // to the first user turn.
  const viewedRun =
    contentSourceRunId != null
      ? recentRuns?.find((r) => r.id === contentSourceRunId)
      : undefined;
  const latestRunTitle = viewedRun?.title;
  // FIX-130: strip any === marker text from the DB title before displaying.
  // DB titles may be polluted (truncated at 60 chars so closing markers are missing,
  // defeating parseRunInput's regex). Use a simple line-scan: if the first non-empty
  // line starts with "===", the title is polluted — fall through to submittedBrief.
  const cleanLatestTitle = (() => {
    if (!latestRunTitle || latestRunTitle === "Untitled") return undefined;
    // If the title starts with "===" it's a raw marker line — discard entirely.
    if (latestRunTitle.trimStart().startsWith("===")) return undefined;
    // Strip "Title: " prefix from cascading context pollution
    const stripped = latestRunTitle.startsWith("Title: ")
      ? latestRunTitle.slice("Title: ".length).trim()
      : latestRunTitle;
    // If it contains "===" anywhere, run it through parseRunInput as a safety net.
    if (stripped.includes("===")) {
      const _p = parseRunInput(stripped);
      const _clean = (_p.revisionInstruction ?? _p.brief ?? "").split("\n")[0].trim();
      return _clean || undefined;
    }
    return stripped || undefined;
  })();
  const runHeaderTitle = cleanLatestTitle ?? submittedBrief;

  // The gate the lane surfaces (mirrors the Steps ReviewGatePanel props). The
  // KAN-101 spec-loop affordance + approve relabel are mapped off the declared
  // reviewGateData flags (SC-001) — mirrors the redoable mapping, no literal.
  // KAN-146: when the clarify questionnaire is open (laneClarifyOpen), suppress
  // the gate so the two panels are never shown simultaneously. The gate is still
  // armed on the backend; it will re-surface after the questionnaire resolves.
  const laneGate: GateContext | undefined = reviewGateData && !laneClarifyOpen
    ? {
        agentId: reviewGateData.agentId,
        agentName: reviewGateData.agentName,
        output: reviewGateData.output,
        gateKey: reviewGateData.gateKey,
        redoable: reviewGateData.redoable,
        updateSpecsEligible: reviewGateData.updateSpecsEligible,
        // Pass the backend's artifact_kind so discriminateArtifact() can render
        // the correct preview for agents whose output has no XML wrapper tags
        // (e.g. user_stories domain-analyst produces plain markdown, kind="summary").
        artifactKind: reviewGateData.artifactKind,
        // KAN-101: the analyze gate (artifactKind="summary") is the final human
        // decision before the build agents fire — label it clearly. Generic
        // fallback for other gate kinds (spec, task_list). SC-001: keyed on the
        // server-provided artifactKind string, never a workflow/agent-name literal.
        approveLabel: reviewGateData.artifactKind === "summary"
          ? "Accept & continue to build"
          : reviewGateData.artifactKind
          ? `Approve the ${reviewGateData.artifactKind.replace(/_/g, " ")}`
          : undefined,
      }
    : undefined;

  // Clarify quick-actions → the SAME resume path the QuestionnairePanel uses.
  // Maps the lane's ClarifyResponse[] onto the (answers, freeform) submit.
  const handleLaneSubmitAnswers = useCallback(
    (responses: ClarifyResponse[]) => {
      const answers: Record<string, string[]> = {};
      let freeform = "";
      for (const r of responses) {
        if (r.question_id === "freeform") {
          freeform = r.answer;
          continue;
        }
        answers[r.question_id] = r.answer ? [r.answer] : [];
      }
      handleQuestionnaireSubmit(answers, freeform);
    },
    [handleQuestionnaireSubmit],
  );

  // Suggested next steps (absorbed) — the chainable workflows as generic chips.
  // Use effectiveReviseType (the type of the run currently on screen) so the filter
  // correctly excludes the VIEWED pipeline type, not the last-launched type.
  const chainFromType = (effectiveReviseType ?? workflowType) as WorkflowType;
  const laneSuggestions: LaneSuggestion[] = canChainFrom(chainFromType)
    ? CHAIN_OPTIONS
        .filter((o) => baseWorkflowType(o.type) !== baseWorkflowType(chainFromType))
        .map((o) => ({ id: o.type, label: o.label }))
    : [];
  const handleLaneSuggestion = useCallback(
    (id: string) => { handleChainPipeline(id as WorkflowType); },
    [handleChainPipeline],
  );

  // Map mainView to header page type
  const headerPage = mainView === "library" ? "library" :
    mainView === "catalog" ? "catalog" :
    mainView === "history" ? "history" :
    mainView === "settings" ? "history" :
    mainView === "saved-workflows" ? "saved-workflows" :
    mainView === "input" ? "workflow" :
    mainView === "execution" ? "execution" : "home";

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden bg-surface-paper">
      {/* Connection status banner */}
      <AnimatePresence>
        {connectionStatus === "reconnecting" && (
          <motion.div
            initial={{ y: -40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -40, opacity: 0 }}
            className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-yellow-600/90 px-4 py-2 text-xs text-white backdrop-blur-sm"
          >
            <RefreshCw className="h-3 w-3 animate-spin" />
            Reconnecting...
          </motion.div>
        )}
        {connectionStatus === "failed" && (
          <motion.div
            initial={{ y: -40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -40, opacity: 0 }}
            className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-red-600/90 px-4 py-2 text-xs text-white backdrop-blur-sm"
          >
            <WifiOff className="h-3 w-3" />
            Connection lost.
            <button onClick={onReconnect} className="ml-1 underline hover:no-underline">Reconnect</button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Global Header — visible on all pages */}
      <AppHeader
        currentPage={headerPage}
        onNavigate={handleNavigate}
        onLogout={onLogout}
        userTier={userTier}
        userEmail={userEmail}
        isPipelineRunning={isPipelineRunning}
        pipelineType={effectiveReviseType}
        pipelineAgentsCompleted={pipelineState?.completedCount ?? 0}
        pipelineAgentsTotal={pipelineState?.agents?.length ?? 0}
        activePipelineRunId={pipelineState?.pipelineRunId ?? null}
        onGoToPipeline={() => setMainView("execution")}
        recentRuns={recentRuns}
        onSwitchToLiveRun={onSwitchToLiveRun}
        onSelectWorkflowRun={(run) => {
          onSelectWorkflowRun?.(run);
          setMainView("execution");
        }}
        notifications={notifications}
        unreadCount={unreadCount}
        onMarkAllRead={markAllRead}
        onClearNotifications={clearAll}
        onViewResults={(n) => {
          if (n.status === "running" || n.status === "gate") {
            // FIX-149 (Bug 2): for RUNNING/GATE pipelines, switch to the live
            // run view WITHOUT resetting pipeline state (calling onSelectWorkflowRun
            // is wrong — it triggers handleSelectWorkflowRun which is a history-reopen
            // function that calls resetPipeline(), getWorkflow() fetch, resetReplayState(),
            // and wipes the live Steps trace). Instead use onSwitchToLiveRun which
            // only updates the content-source and attaches the SSE stream.
            // FIX-157: expand the recentRuns status filter from === "running" to any
            // live status (planning, generating, clarifying, etc.) so runs in any
            // in-flight state are correctly located — not just those with status="running".
            const LIVE_RUN_STATUSES = new Set(["running", "revising", "planning", "generating", "waiting_for_user", "clarifying", "analyzing"]);
            const targetRunId = n.workflowRunId ?? recentRuns?.find(
              (r) =>
                LIVE_RUN_STATUSES.has(r.status) &&
                (r.type === n.workflowType ||
                  (n.workflowType === "ppt" && (r.type === "od_ppt" || r.type === "ppt")) ||
                  (n.workflowType === "prototype" && (r.type === "od_prototype" || r.type === "prototype"))),
            )?.id;
            if (targetRunId && onSwitchToLiveRun) {
              onSwitchToLiveRun(targetRunId);
            }
            setMainView("execution");
          } else if (n.status === "completed") {
            setMainView("execution");
          } else {
            setMainView("history");
          }
        }}
      />

      {/* Main Content */}
      <div className="flex-1 min-h-0">
        <AnimatePresence mode="sync">
          {/* HOME — the data-driven HomeLaunchGrid is the DEFAULT landing
              (UXFIX-03 / D-20). The hardcoded `CreationHub.WORKFLOWS` array no
              longer drives the default home — the catalog sources its rows from
              `GET /api/workflows`, so a brand-new launchable manifest appears
              with zero FE edit (SC-001). This is a re-route, not a new visual:
              the same launch/select wiring (`handleSelectFeature` +
              `handleLaunchSaved`, P21) is preserved. */}
          {mainView === "home" && (
            <motion.div
              key="home"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              {/* FUSED HOME (SHELL-02 SC-1, restyled 40-02) — one landing owned by
                  HomeLaunchGrid: the mock's prompt UNDER the h1 (Attach + Build,
                  no Voice — ND-X), the SC-001 data-driven deliverable card grid,
                  and the live "Jump back in" recents. The prompt state stays here
                  (homeBrief) so it can ride into the launch via pendingHomeBrief;
                  it is threaded down as controlled props. Build carries the brief
                  down the existing launch fork (handleHomeSelectFeature). Wizard-
                  routed types (prototype/ppt) still router.push inside
                  HomeLaunchGrid — the fork is preserved. The `input` view is
                  UNCHANGED and still reachable for the saved-workflow preload path
                  (handleLaunchSaved). Recents deep-link via onSelectWorkflowRun →
                  the execution view. Page-keys stay generic (SC-001/INV-1). */}
              <div className="flex h-full flex-col bg-surface-paper">
                <HomeLaunchGrid
                  onSelectFeature={handleHomeSelectFeature}
                  onLaunchSaved={handleLaunchSaved}
                  userTier={userTier}
                  brief={homeBrief}
                  onBriefChange={setHomeBrief}
                  onBuild={() => handleHomeSelectFeature("custom" as WorkflowType)}
                  onOpenRun={(run) => { onSelectWorkflowRun?.(run); setMainView("execution"); }}
                  recentRuns={recentRuns}
                  homeWorkflows={homeWorkflows}
                />
              </div>
            </motion.div>
          )}


          {/* LIBRARY — Agent catalog */}
          {mainView === "library" && (
            <motion.div
              key="library"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <LibraryPage />
            </motion.div>
          )}

          {/* HISTORY — Workflow history */}
          {mainView === "history" && (
            <motion.div
              key="history"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <WorkflowHistory onBack={handleGoHome} onChainPipeline={handleChainFromHistory}
            activeRunId={pipelineState?.pipelineRunId ?? null}
            onViewRunningPipeline={() => setMainView("execution")}
            onOpenRun={(run) => { onSelectWorkflowRun?.(run); setMainView("execution"); }}
            onReviseUserStory={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("user_stories_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PRODUCT BACKLOG ===\n${content}\n=== END EXISTING BACKLOG ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                // Revision Families (B1): history revisions previously sent NO
                // parent → orphan runs. Thread selectedRun.id so the backend links it.
                onStartPipeline("user_stories_revision", msg, undefined, attachedSkills, attachedHooks, sourceRunId ? { source_workflow_run_id: sourceRunId } : undefined);
              }
            }}
            onRevisePpt={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("ppt_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PRESENTATION CODE ===\n${content}\n=== END EXISTING CODE ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("ppt_revision", msg, undefined, attachedSkills, attachedHooks, { ...(sourceRunId ? { source_workflow_run_id: sourceRunId } : {}), _display_title: instruction.slice(0, 60) });
              }
            }}
            onRevisePrototype={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("prototype_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING PROTOTYPE HTML ===\n${content}\n=== END EXISTING HTML ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("prototype_revision", msg, undefined, attachedSkills, attachedHooks, { ...(sourceRunId ? { source_workflow_run_id: sourceRunId } : {}), _display_title: instruction.slice(0, 60) });
              }
            }}
            onReviseAppBuilder={(instruction, content, sourceRunId) => {
              setMainView("execution");
              setWorkflowType("app_builder_revision");
              if (onResetPipeline) onResetPipeline();
              if (onStartPipeline) {
                const msg = `=== EXISTING APP BLUEPRINT ===\n${content.slice(0, 40000)}\n=== END EXISTING BLUEPRINT ===\n\n=== REVISION REQUEST ===\n${instruction}\n=== END REQUEST ===`;
                onStartPipeline("app_builder_revision", msg, undefined, attachedSkills, attachedHooks, { ...(sourceRunId ? { source_workflow_run_id: sourceRunId } : {}), _display_title: instruction.slice(0, 60) });
              }
            }}
          />
            </motion.div>
          )}

          {/* SETTINGS — Account settings */}
          {mainView === "settings" && (
            <motion.div
              key="settings"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <AccountSettings onBack={handleGoHome} />
            </motion.div>
          )}

          {/* ANALYTICS */}
          {mainView === "analytics" && (
            <motion.div
              key="analytics"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <AnalyticsPage onBack={handleGoHome} />
            </motion.div>
          )}

          {/* SAVED WORKFLOWS — user's saved custom workflows */}
          {mainView === "saved-workflows" && (
            <motion.div
              key="saved-workflows"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <SavedWorkflowsPage onLaunchSaved={handleLaunchSaved} />
            </motion.div>
          )}

          {/* INPUT — Idea input page */}
          {mainView === "input" && (
            <motion.div
              key="input"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
              className="h-full"
            >
              <IdeaInputPage
                workflowType={workflowType}
                onBack={handleGoHome}
                onRun={handleRunPipeline}
                initialAgentIds={savedComposition?.agentIds}
                initialModelOverrides={savedComposition?.modelOverrides}
                initialSelections={savedComposition?.selections}
                initialInput={savedComposition?.brief ?? pendingHomeBrief}
                initialGateIds={savedComposition?.gateAgentIds}
                // SURF-03 — the backend workflow id whose compiled per-step
                // capabilities the composer surfaces. For a built-in launchable
                // workflow opened from the catalog, `workflowType` IS the workflow id
                // (HomeLaunchGrid launches via `row.id as WorkflowType`); for a saved
                // workflow it is the persisted `base_pipeline_type` (set in
                // handleLaunchSaved). Unknown ids (e.g. `custom`/`migration` meta) 404
                // server-side and the strip simply does not render.
                workflowId={workflowType}
              />
            </motion.div>
          )}

          {/* COMPOSER — full-page custom-workflow authoring surface (41-04).
              ADDITIVE: reached from Home's "Compose a custom workflow" card and
              edit-from-My-Workflows (pre-loaded). Reuses the AgentsPopup shared
              data model + exported sub-components; the modal wrapper is retained
              for the wizard/input inline-edit flow (INV-3). */}
          {mainView === "composer" && (
            <motion.div
              key="composer"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
              className="h-full"
            >
              <ComposerPage
                workflowType={workflowType}
                onBack={handleGoHome}
                // 41-06 (D-05 / D-CMP-RUN) — Run-once launches the composed workflow
                // through the EXISTING onStartPipeline → startPipeline seam, mirroring
                // the revision launch sites (reset → onStartPipeline with the SAME arg
                // convention). `type` is the composer's fixed-at-entry base_pipeline_type
                // ("custom" for the compose entry, ND-AH) — the SAME value Save persists.
                // startPipeline flips pipelineState.isRunning → the surface auto-transitions
                // to mainView='execution'. No new contract / endpoint / fabricated cost (ND-AG).
                onRun={(type, brief, agentIds, extraParams) => {
                  if (onResetPipeline) onResetPipeline();
                  if (onStartPipeline) {
                    onStartPipeline(type, brief, agentIds, attachedSkills, attachedHooks, extraParams);
                  }
                }}
                initialAgentIds={savedComposition?.agentIds}
                initialSelections={
                  savedComposition?.selections
                    ? (Object.fromEntries(
                        Object.entries(savedComposition.selections).filter(
                          ([k]) => k !== "_wizard",
                        ),
                      ) as import("@/components/workflow/AgentsPopup").SelectionsMap)
                    : undefined
                }
                initialName={savedComposition?.name}
                initialDescription={savedComposition?.description}
              />
            </motion.div>
          )}

          {/* EXECUTION — 2-panel layout */}
          {mainView === "execution" && (
            <motion.div
              key="execution"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full flex flex-col md:flex-row"
              style={{ background: "var(--surface-paper)" }}
            >
              {/* Left Panel — Phase 31/32 (CHATUI/SC-4): the RunChatLane is the
                  primary left-column surface. It FULLY ABSORBS the AgentProgressPanel
                  Stop / revise / suggestions controls (D-12 composer-per-state,
                  SC-001 generic) and mounts the plan-05 gate/clarify quick-actions.
                  INV-3 (plan 06): the duplicate AgentProgressPanel run-lane mount is
                  REMOVED — the lane is now the SOLE stop/revise implementation. The
                  AgentProgressPanel component is retained for the plan-08 Steps
                  relocation (its per-agent detail also lives in the Thinking tab).
                  ISS-019: the column is a height-owning flex parent — the lane
                  flexes to remaining space and owns its own scroll; the wave panel
                  is a non-shrinking capped bottom region. */}
              <div className="w-full md:w-[340px] lg:w-[360px] flex-shrink-0 h-[45vh] md:h-full border-b md:border-b-0 md:border-r border-gray-200 flex flex-col overflow-hidden bg-white">
                {/* The run chat lane — primary conversational surface. */}
                <div data-testid="execution-chat-lane" className="flex-1 min-h-0 overflow-hidden">
                  <ErrorBoundary fallbackLabel="RunChatLane">
                    <RunChatLane
                      messages={runChatMessages ?? messages}
                      runState={runLaneState}
                      // 43-02 (A.1 CRUX): the options-capable send seam so a
                      // settled-run ASK can fold { concierge: true } onto the
                      // payload (Concierge answer vs. onRevise revision).
                      sendMessage={runChatSend}
                      // FIX-119: optimistic-message echo for all runState=complete
                      // workflows so the user's text is always visible in the chat
                      // before the classify-intent LLM round-trip resolves.
                      addOptimisticMessage={addOptimisticMessage}
                      isStreaming={isStreaming}
                      streamingContent={streamingContent}
                      // quick-260719-rqo (Issue 2 part 2): the streaming-reply hint
                      // that drives the mid-reply "reading run data…" indicator.
                      replyStreaming={runChatReplyStreaming}
                      pipelineState={pipelineState}
                      onRequestOpenTab={onRequestOpenTab}
                      // Phase 39 (RUNUI-06) — wire the lane run header's 39-01
                      // slots with the real DashboardLayout data: Back-to-history
                      // navigation, the live run title (clean backend title, else
                      // the submitted brief), and the generic run type (SC-001 —
                      // the pipeline_type string, never a workflow-name branch).
                      onBackToHistory={() => setMainView("history")}
                      runTitle={runHeaderTitle}
                      runType={effectiveReviseType || pipelineState?.pipeline_type}
                      // KAN-128 (FIX-141): pass the content-derived filename so the
                      // left chat panel "Run summary" DeliverableCard shows the same
                      // name as the Files tab and Preview URL bar (not the static
                      // manifest name from pipelineState.deliverableFilename).
                      deliverableFilename={laneDerivedFilename || undefined}
                      // Absorbed AgentProgressPanel controls (Stop / revise / suggestions).
                      onStop={handleStopPipeline}
                      onRevise={activeReviseHandler}
                      onRelaunch={handleResumeRun}
                      onEditBrief={handleEditBrief}
                      relaunchError={resumeError}
                      suggestions={laneSuggestions}
                      onSuggestion={handleLaneSuggestion}
                      // 43-02 (A.1 CRUX) — Concierge props wired at the mount.
                      // `proposals` is the held-proposal surface: empty until the
                      // Part-C SSE transport (43-06) delivers concierge_proposal
                      // holds, then the SAME confirm chip fires handleConfirmProposal
                      // (POST { concierge:true, confirm_proposal:{channel,params} }).
                      // Reject dismisses without executing; compaction has no
                      // backend trigger yet (no invented call) — a no-op-safe
                      // onCompact + no explicit availability signal (LOCK-B).
                      proposals={runConciergeProposals}
                      onConfirmProposal={handleConfirmProposal}
                      onRejectProposal={handleRejectProposal}
                      compactAvailable={false}
                      onCompact={handleCompact}
                      // Plan-05 gate quick-actions (KAN-100/101 fences owned by the component).
                      gate={laneGate}
                      onApprove={onApproveReview}
                      onReject={handleRejectReview}
                      onRedo={onRedoReview}
                      onUpdateSpecs={onUpdateSpecsReview}
                      // Plan-05 clarify quick-actions.
                      clarifyQuestions={questionnaireQuestions}
                      onSubmitAnswers={handleLaneSubmitAnswers}
                      onSkipClarify={handleQuestionnaireSkip}
                      // Phase 42-02 (§A2 re-home) — Cancel-Workflow on the inline
                      // clarify, bound to the existing owner-scoped handler (guarded
                      // by an active run, matching the old QuestionnairePanel wiring).
                      onCancelWorkflow={activePipelineRunId ? handleCancelWorkflow : undefined}
                    />
                  </ErrorBoundary>
                </div>
                {/* INV-3 (plan 06): the demoted per-agent AgentProgressPanel mount
                    was REMOVED here — its Stop/revise/suggestions controls are fully
                    absorbed by the RunChatLane composer above, leaving ONE stop/revise
                    implementation. Per-agent detail relocates into Steps in plan 08. */}
                {/* Phase 32 (plan 08 / ISS-019) + Phase 39/42-04: the separate
                    below-the-fold wave-tree panel is gone. The live wave/subagent
                    tree renders inside AgentDetailPanel's inline construction block
                    (Steps drill-down) via the `waves` passthrough to PreviewPanel
                    below. INV-12 — one wave-tree implementation. */}
              </div>

              {/* Right Panel — always PreviewPanel */}
              <div className="flex-1 h-[55vh] md:h-full min-w-0 bg-white rounded-none md:rounded-l-none">
                <ErrorBoundary fallbackLabel="Preview">
                  {/* Phase 42-02 (§A1/§A2/§A3): the three legacy full-screen takeover
                      branches (planning overlay / review-gate / questionnaire panels)
                      were removed from this cascade so PreviewPanel — the sole host of
                      the mock-matching inline Steps clarify/gate/planning surfaces —
                      mounts during those very states. Gate/clarify still flow inline via
                      the laneGate / clarifyQuestions passthrough below. */}
                  <PreviewPanel
                      userStoryContent={userStoryContent || undefined}
                      pptContent={pptContent || undefined}
                      prototypeContent={prototypeContent || undefined}
                      genericDeliverable={genericDeliverable}
                      isStreaming={isStreaming}
                      workflowType={effectiveReviseType}
                      rawPipelineType={pipelineState?.pipeline_type || workflowType}
                      pptxCode={pptxCode}
                      onRevisePpt={undefined}
                      onReviseUserStory={undefined}
                      onRevisePrototype={undefined}
                      onReviseAppBuilder={undefined}
                      agentOutputs={
                        pipelineState && pipelineState.agents.length > 0
                          ? pipelineState.agents
                              .filter((a) => a.status === "done" && a.output && a.output.trim().length > 0)
                              .map((a) => ({ name: a.name, role: a.role, output: a.output, agentId: a.id }))
                          : undefined
                      }
                      agents={pipelineState?.agents}
                      pipelineState={pipelineState}
                      reopenedRunStatus={reopenedRunStatus}
                      reopenedFailedAgents={reopenedFailedAgents}
                      reopenedAgentNameById={reopenedAgentNameById}
                      runFamily={runFamily}
                      liveRunId={contentSourceRunId ?? null}
                      runInput={submittedBrief}
                      deepLinkTarget={deepLinkTarget}
                      // Phase 32 (plan 06 → 07/08) — additive gate/clarify passthrough
                      // so a future Steps surface can host the SAME inline gate/clarify
                      // affordances the lane uses. Mirrors the RunChatLane wiring;
                      // pinned to the shared GateContext/clarify shapes (SC-001).
                      laneGate={laneGate}
                      onApproveGate={onApproveReview}
                      onRejectGate={handleRejectReview}
                      onRedoGate={onRedoReview}
                      onUpdateSpecsGate={onUpdateSpecsReview}
                      clarifyQuestions={questionnaireQuestions}
                      onSubmitClarify={handleLaneSubmitAnswers}
                      onSkipClarify={handleQuestionnaireSkip}
                      // Phase 42-02 (§A2 re-home) — Cancel-Workflow on the Steps
                      // inline clarify, bound to the existing owner-scoped handler.
                      onCancelWorkflow={activePipelineRunId ? handleCancelWorkflow : undefined}
                      // Phase 32 (plan 08 / ISS-019) — the live wave/subagent tree
                      // now mounts INSIDE the Steps drill-down (relocated from the
                      // below-the-fold left slot). Forward the assembled groups.
                      waves={waves}
                      // KAN-101 — spec revision cycle counter for the Steps banner.
                      specRevisionCount={specRevisionCount}
                    />
                </ErrorBoundary>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Completion toasts — bottom-right, non-blocking */}
      <CompletionToast
        toasts={toasts}
        onDismiss={dismissToast}
        onViewResults={(toast) => {
          dismissToast(toast.id);
          setMainView("execution");
        }}
      />
    </div>
  );
}
