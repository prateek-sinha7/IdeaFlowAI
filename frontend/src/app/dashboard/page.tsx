"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, getChat, addMessage, logout, deleteChat, createChat, getWorkflows, getWorkflow, getMe, postGate, getRunEvents, getWorkflowDefinitions, getRunFamily } from "@/lib/api";
import type { WorkflowSummary } from "@/lib/api";
import type { ConnectionStatus } from "@/hooks/useHandoffSocket";
import type { RunConnectionPhase } from "@/hooks/useRunStream";
import { useWorkflow } from "@/hooks/useWorkflow";
// Phase 31 (CHATUI-01/02/03) — the chat-lane DATA layer + the nonce'd deep-link
// seam + the app-level SSE connection. useRunChat folds the Phase-29 chat frames
// into a transport-agnostic transcript; useTabDeepLink is the result-card →
// tab seam (borrow #6); useRunConnection supplies the SSE transport when the
// provider is mounted (inert default otherwise → the legacy WS path stays the
// active, byte-identical transport, LOCK-B additive).
import { useRunChat, type RunChatFrame } from "@/hooks/useRunChat";
import { useTabDeepLink } from "@/hooks/useTabDeepLink";
import { useRunConnection } from "@/providers/RunConnectionProvider";
import { shouldApplyEvent, resetReplayState, isForeignRunFrame, isAgentScopedFrame } from "@/lib/wsReplayState";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import type { ChatMessage, ChatSession, StreamMessage, ProcessStep, WorkflowRun, WorkflowStatus, WorkflowType, User, WaveGroup, GenericDeliverable, ReviewGateReadyData } from "@/types/index";
import { deriveDeliverableMimetype, resolveReopenMimetype } from "@/types/index";
import type { ChatMode } from "@/components/chat/ChatInput";
// IN-01 (16 review): SHARED failed-agent-id parser (single source of truth, no
// dual-impl). Consumed by both this live-reopen path and WorkflowHistory's
// history-reopen detail view so the two surfaces parse the persisted run `error`
// identically. See lib/parseFailedAgents.ts for the marker contract.
import { parseFailedAgentIds, buildAgentNameById } from "@/lib/parseFailedAgents";
// KAN-116 (title markers in submittedBrief): use the SAME single-source parser
// DashboardLayout already uses for notification titles (INV-12 — no dual impl).
import { parseRunInput } from "@/lib/runInput";
import { useRunStateStore } from "@/hooks/useRunStateStore";
import type { PerRunState } from "@/hooks/useRunStateStore";

/**
 * Map the SSE connection phase (RunConnectionPhase) onto the ConnectionStatus
 * shape (re-exported from useHandoffSocket) at the boundary, so the header /
 * reconnect UI reflects the SSE connection — the sole run transport (44-06).
 * `replaying`/`live` are "attached" → connected; `idle` (no active run) is
 * treated as connected so an idle SSE app never shows a false disconnect banner.
 */
function phaseToConnectionStatus(phase: RunConnectionPhase): ConnectionStatus {
  switch (phase) {
    case "connecting":
      return "connecting";
    case "reconnecting":
      return "reconnecting";
    case "failed":
      return "failed";
    case "disconnected":
      return "disconnected";
    case "replaying":
    case "live":
    case "idle":
    default:
      return "connected";
  }
}

// BUG-013: terminal run statuses for the reopen focus gate. A terminal run emits
// no further SSE events, so focusing it on reopen would only pin a dead-stream
// reconnect loop for the session; only NON-terminal reopens claim the sticky
// focus. Keyed on the generic server status string (SC-001), never a workflow name.
const REOPEN_TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "degraded"]);

/**
 * Dashboard page - the main authenticated view.
 * Manages WebSocket connection, workflow runs, and streaming content.
 * Workflow-first: the primary experience is running agent pipelines.
 */
export default function DashboardPage() {
  const router = useRouter();
  // Keep initial state false/null to match SSR — avoids hydration mismatch.
  // `mounted` flips to true after the first client render so we never show
  // the black loading screen; instead we show nothing until hydration is done.
  const [mounted, setMounted] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  // Run synchronously after DOM paint but before the browser repaints —
  // this is the earliest safe point to read localStorage on the client.
  useEffect(() => {
    setMounted(true);
  }, []);

  // Chat state (secondary — used for refinement)
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");

  // Preview content per section
  const [userStoryContent, setUserStoryContent] = useState<string>("");
  const [pptContent, setPptContent] = useState<string>("");
  const [prototypeContent, setPrototypeContent] = useState<string>("");
  // ISS-017 (16-04) — the persisted status of a history-reopened run. When a
  // failed/cancelled run is reopened it sets no content (unchanged), so this
  // server-persisted status is threaded into PreviewPanel to render the
  // terminal-empty degraded/failed affordance on the history path. Cleared
  // (undefined) for fresh/live runs and successful reopens.
  const [reopenedRunStatus, setReopenedRunStatus] = useState<WorkflowStatus | undefined>(undefined);
  // Phase 16 (IN-01): the failed-agent list for a history-reopened terminal run,
  // parsed from the persisted run detail. Threaded to PreviewPanel so the reopen
  // affordance lists the real failed agents (not an empty list). Cleared on every
  // reopen/new-run alongside reopenedRunStatus.
  const [reopenedFailedAgents, setReopenedFailedAgents] = useState<string[] | undefined>(undefined);
  // ISS-024 (16 review IN-02): id→name lookup for a history-reopened run's failed
  // agents, built from the reopened run detail's persisted agentOutputs
  // ({agent_id,name}). The live pipelineState reflects the new/idle run and so
  // can't name a reopened run's agents — this carries the names down to
  // PreviewPanel's DegradedRunAffordance. Cleared alongside reopenedFailedAgents.
  const [reopenedAgentNameById, setReopenedAgentNameById] = useState<Record<string, string> | undefined>(undefined);
  // ISS-021 (18-03) — generic deliverable channel. A pipeline_complete (live) or
  // history-reopen whose pipeline_type matched NONE of the known FE render
  // branches feeds this single channel: the declared/derived mimetype + filename
  // + content. PreviewPanel + FilesTab dispatch on the mimetype (text/html →
  // sandboxed iframe, text/markdown → MarkdownPreview, application/zip → bundle).
  // Structural fallback — NEVER keyed on a workflow name (SC-001). Cleared on
  // every new run / reopen alongside the other content state.
  const [genericDeliverable, setGenericDeliverable] = useState<GenericDeliverable | undefined>(undefined);
  const [currentMode, setCurrentMode] = useState<ChatMode>("default");
  const [chatTitleUpdate, setChatTitleUpdate] = useState<{ chat_session_id: string; title: string } | null>(null);
  const [processSteps, setProcessSteps] = useState<ProcessStep[]>([]);
  const processStepsRef = useRef<ProcessStep[]>([]);
  const activePreviewSectionRef = useRef<string | null>(null);
  const pptContentRef = useRef("");
  const prototypeContentRef = useRef("");
  const userStoryContentRef = useRef("");
  const handlePipelineMsgRef = useRef<((msg: { type: string; [key: string]: unknown }) => boolean) | null>(null);
  // Staged od_prototype run — written when authenticated, consumed when connected.
  // `gateAgentIds` (Phase 6, T5b) is present ONLY when the templates wizard's
  // Review-gates section was touched; absent ⇒ backend static gate default.
  const pendingOdProtoRef = useRef<{
    templateId: string; designSystemId: string; brief: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
    modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null>(null);

  // Staged od_ppt run — written when authenticated, consumed when connected.
  const pendingOdPptRef = useRef<{
    templateId: string; designSystemId: string | null; brief: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
    modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null>(null);

  // Phase 12 (§22 / RESUME-03) — wave/subagent tree state assembled from the
  // additive wave_*/subagent_* lifecycle events, fed (via the `waves` passthrough)
  // to AgentDetailPanel's inline construction/wave tree.
  const [waveGroups, setWaveGroups] = useState<WaveGroup[]>([]);
  // Per-run dedup substrate for the durable reconnect replay (RESUME-03 FE half):
  // every applied event_id is recorded so a replayed event is applied at most
  // once, and the max-seen seq is tracked so the reconnect can send after_seq.
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const lastSeqRef = useRef<number>(0);
  // BUG-005 — run-scope the pipeline_start reset. `trackedRunIdRef` holds the run
  // THIS tab is driving/viewing: the ONLY run whose pipeline_start may reset this
  // tab's clarify / active-run-id / seen-set. The SSE provider's non-run-scoped
  // fan-out forwards EVERY frame from EVERY attached run to the single subscriber,
  // so without this guard a CONCURRENT foreign run's pipeline_start wiped the
  // viewed run's clarify (activePipelineRunId → null → the lane fell clarify→
  // building). Synced below from activePipelineRunId ?? contentSourceRunId (NOT
  // pipelineState.pipelineRunId — useWorkflow adopts the foreign id into it).
  const trackedRunIdRef = useRef<string | null>(null);
  // KAN-125 — track ALL run ids launched from this tab so the isForeignFrame guard
  // (below) allows completions from ANY locally-launched run, not just the most
  // recently launched one. Without this, launching run B while run A is still
  // building would block run A's pipeline_complete (A's id ≠ trackedRunIdRef
  // which now holds B's id) → "Invalid presentation output".
  // KAN-125 MULTI-TAB FIX — session-scoped launched run ID set. Seeded from
  // sessionStorage on first render (survives same-tab reload; fresh per new tab).
  // Using a constant initializer function to avoid re-running the seed logic on
  // every render (useRef calls the function only once on mount).
  const TAB_LAUNCHED_KEY = "tab_launched_run_ids";
  const launchedRunIdsRef = useRef<Set<string>>((() => {
    // This IIFE executes only when useRef is first called (mount). React ignores
    // the argument on subsequent renders. Seeding from sessionStorage here means
    // same-tab page reloads see the previously-launched run IDs (so in-progress runs
    // remain locally-known), while new tabs start with an empty Set (fresh sessionStorage).
    try {
      const raw = sessionStorage.getItem("tab_launched_run_ids");
      if (raw) {
        const ids = JSON.parse(raw) as string[];
        if (Array.isArray(ids)) return new Set<string>(ids);
      }
    } catch { /* ignore storage errors — non-fatal */ }
    return new Set<string>();
  })());

  /** Persist the launched run IDs to sessionStorage after every mutation so
   *  a same-tab page reload restores the full allow-list. New tabs start with
   *  a fresh sessionStorage and see an empty set (correct isolation). */
  const persistLaunchedIds = () => {
    try {
      sessionStorage.setItem(TAB_LAUNCHED_KEY, JSON.stringify([...launchedRunIdsRef.current]));
    } catch { /* non-fatal */ }
  };

  // ─── Per-run state store (FIX-201 / KAN-168 concurrent-run isolation) ────────
  // Root cause of all cross-contamination: questionnaireData and reviewGateData
  // are SINGLE React state values shared by all concurrent runs. Every new
  // questionnaire_ready from any run overwrites them. Guards patch timing holes
  // but cannot eliminate all races across async operations.
  //
  // Solution: maintain a per-run state Map (not React state — a ref, so mutations
  // don't trigger renders). When a questionnaire_ready / review_gate_ready /
  // questionnaire_complete arrives for run X:
  //   • Always update the map[X] entry
  //   • Only project to React state when X === trackedRunIdRef.current (viewed run)
  //
  // On handleSwitchToLiveRun(newRunId): load map[newRunId] into React state
  // synchronously — no async gap, no race.
  //
  // This is the viewport pattern: each run has its own state; the viewport
  // (trackedRunIdRef) decides which run's state the UI sees.
  interface PerRunViewState {
    questionnaireData: {
      questions: {
        id: string; question: string; options: string[]; answerType?: string;
        recommendedAnswer?: string; recommendedReasoning?: string;
        recommendedDisplay?: string; ambiguityCategory?: string; impactLevel?: string;
      }[]
    } | null;
    reviewGateData: {
      gateKey: string; agentId: string; agentName: string; output: string;
      pipelineRunId: string; redoable?: boolean; updateSpecsEligible?: boolean;
      artifactKind?: string;
    } | null;
    activePipelineRunId: string | null;
  }
  const runStateMapRef = useRef<Map<string, PerRunViewState>>(new Map());

  /** Get or create the per-run state entry for a run id. */
  const getRunViewState = (runId: string): PerRunViewState => {
    if (!runStateMapRef.current.has(runId)) {
      runStateMapRef.current.set(runId, { questionnaireData: null, reviewGateData: null, activePipelineRunId: null });
    }
    return runStateMapRef.current.get(runId)!;
  };

  /** Update the per-run state map and optionally project to React state.
   *  Call with project=true only when runId === trackedRunIdRef.current. */
  const updateRunQuestionnaire = (
    runId: string,
    data: PerRunViewState["questionnaireData"],
  ) => {
    const entry = getRunViewState(runId);
    entry.questionnaireData = data;
    // Project to React state only when this is the currently viewed run
    if (runId === trackedRunIdRef.current || trackedRunIdRef.current === null) {
      setQuestionnaireData(data);
      if (data !== null && runId) setActivePipelineRunId(runId);
    }
  };

  const updateRunReviewGate = (
    runId: string,
    data: PerRunViewState["reviewGateData"],
  ) => {
    const entry = getRunViewState(runId);
    entry.reviewGateData = data;
    if (runId === trackedRunIdRef.current || trackedRunIdRef.current === null) {
      setReviewGateData(data);
    }
  };

  /** Load a run's persisted state into React state (called on run switch). */
  const projectRunStateToUI = (runId: string) => {
    const entry = runStateMapRef.current.get(runId);
    setQuestionnaireData(entry?.questionnaireData ?? null);
    setReviewGateData(entry?.reviewGateData ?? null);
    if (entry?.activePipelineRunId) {
      setActivePipelineRunId(entry.activePipelineRunId);
    }
  };

  // KAN-125 FIX — track the MOST-RECENTLY-LAUNCHED run id to gate the pipelineState
  // reducer. Unlike trackedRunIdRef (which gets overwritten by contentSourceRunId
  // from completed runs), this ref is ONLY updated when a new run is launched
  // (in the startPipeline .then() callback). This prevents a completing concurrent
  // run from re-pointing the reducer gate and blocking the currently-building run's
  // live agent progress from reaching the Steps / Audit tabs.
  const activelyBuildingRunIdRef = useRef<string | null>(null);
  // KAN-125 LAUNCH-ORDER FIX — a monotonically-increasing counter that bumps on
  // every launch CLICK (not on POST resolution). The .then() callback only updates
  // activelyBuildingRunIdRef when its launch counter matches the current value,
  // preventing a slow-responding first-launched run's .then() from overwriting
  // the second-launched run's ID (HTTP responses can arrive out of click order).
  const launchCounterRef = useRef<number>(0);
  // FIX-201 (KAN-168): launch-window sentinel. Set to true in onStartPipeline
  // !isRevision block, cleared in the POST .then(). While true, all pipeline-scoped
  // frames from runs other than the one being launched are blocked from reaching
  // pipelineState — prevents PPT/prototype agent frames from contaminating the
  // next User Stories pipelineState during the async POST gap.
  const launchPendingRef = useRef<boolean>(false);
  // BUG-015 — the provider's detachRun, reached through a ref so the empty-deps
  // handleWebSocketMessage (a useCallback([])) can release a completed run's focus
  // WITHOUT closing over `runConnection` (declared later, which would break the
  // stale-closure design). Synced from runConnection.detachRun in a useEffect below.
  const detachRunRef = useRef<((runId: string) => void) | null>(null);
  // FIX-172: a ref to appendRunChatFrames (from useRunChat) so the empty-deps
  // handleWebSocketMessage can fold completion narrator cards without closing over
  // the live hook value. Synced after useRunChat is called below.
  const appendRunChatFramesRef = useRef<((frames: import("@/hooks/useRunChat").RunChatFrame[]) => void) | null>(null);

  // Workflow runs state (primary)
  const [recentRuns, setRecentRuns] = useState<WorkflowRun[]>([]);
  // Pre-fetched user-launchable workflow definitions for the home card grid.
  // Fetched once on auth alongside recentRuns so HomeLaunchGrid never needs to
  // fire its own getWorkflowDefinitions — the cards appear immediately.
  const [homeWorkflows, setHomeWorkflows] = useState<WorkflowSummary[]>([]);
  // Revision Families (B1 / D1-D7): the reliable "run id that produced the
  // on-screen content". Set on pipeline_complete (live) + reopen; cleared on a
  // fresh (non-revision) run. Threaded to DashboardLayout so every revision
  // launch path sources parent linkage from it (replaces the old fragile
  // currentWorkflowRunId heuristic).
  const [contentSourceRunId, setContentSourceRunId] = useState<string | null>(null);
  // FIX-203: the most-recently completed background (non-viewed) concurrent run id.
  // Set in the pipeline_complete handler for foreign completions so DashboardLayout
  // can mark the matching notification as completed (pipelineState only reflects
  // the viewed run, so the standard completion effect never fires for background runs).
  const [backgroundCompletedRunId, setBackgroundCompletedRunId] = useState<string | null>(null);
  // FIX-205: the run id of a background concurrent run whose pipeline_start just
  // arrived. DashboardLayout uses this to stamp workflowRunId onto that run's
  // notification (created at launch time before the run id was known).
  const [backgroundStartedRunId, setBackgroundStartedRunId] = useState<string | null>(null);
  // BUG-012: the durable viewed-run-type — the REAL type of the run that produced
  // the on-screen content (fullRun.type), threaded to DashboardLayout so the
  // PreviewPanel render dispatch keys on the viewed run's type even for runs
  // OUTSIDE the recents window. Set on reopen; cleared on a fresh (non-revision)
  // launch. Gated on !isPipelineRunning downstream so live launch->watch is byte-identical.
  const [contentSourceRunType, setContentSourceRunType] = useState<WorkflowType | null>(null);
  const [questionnaireData, setQuestionnaireData] = useState<{
    questions: {
      id: string; question: string; options: string[]; answerType?: string;
      recommendedAnswer?: string; recommendedReasoning?: string;
      recommendedDisplay?: string; ambiguityCategory?: string; impactLevel?: string;
    }[]
  } | null>(null);
  // Phase 2 — pipeline_run_id of the run currently paused at the clarify gate,
  // used to address submit_questionnaire back to the correct paused run.
  const [activePipelineRunId, setActivePipelineRunId] = useState<string | null>(null);
  // KAN-120 — the run id of the most-recently cancelled or stopped run. Unlike
  // activePipelineRunId (cleared on cancel), this is NEVER cleared so handleResumeRun
  // in DashboardLayout can still find the run id after pipeline_cancelled fires.
  const [lastCancelledRunId, setLastCancelledRunId] = useState<string | null>(null);
  // KAN-101 — spec revision cycle counter. Incremented each time an agent that
  // was already "done" re-starts during an active pipeline run — the generic
  // signal that update_specs fired and the specify→plan→analyze sub-pipeline is
  // re-running. Reset to 0 on every pipeline_start (fresh or resumed run).
  // SC-001/INV-1: keyed on generic "was already done" status, never an agent/
  // workflow-name literal. INV-3: frontend-only, no backend event emitted.
  const [specRevisionCount, setSpecRevisionCount] = useState(0);

  // Review gate state — set when review_gate_ready fires
  const [reviewGateData, setReviewGateData] = useState<{
    gateKey: string;
    agentId: string;
    agentName: string;
    output: string;
    pipelineRunId: string;
    // REDO-GATE (F-fe3): generic server-set flag — the panel shows Redo iff true.
    redoable?: boolean;
    // SC-001 (plan 04 → 06/08): name-free, structurally-derived server flags.
    // The single FE parse point for KAN-101's "Update the Specs" affordance —
    // plan 06 maps it into laneGate, plan 08 into the Steps inline gate. Parsed
    // defensively (undefined when the backend omits them).
    updateSpecsEligible?: boolean;
    artifactKind?: string;
  } | null>(null);
  // Pending od_prototype params — set when questionnaire is triggered, consumed by DashboardLayout.
  // `gateAgentIds` (Phase 6, T5b) flows into DashboardLayout's `gate_agent_ids`
  // extraParam; it is set ONLY when the wizard's Review-gates section was touched.
  const [pendingOdProtoParams, setPendingOdProtoParams] = useState<{
    brief: string; templateId: string; designSystemId: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
    modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null>(null);
  // Pending od_ppt params
  const [pendingOdPptParams, setPendingOdPptParams] = useState<{
    brief: string; templateId: string; designSystemId: string | null; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
    modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
    images?: { name: string; mime_type: string; data: string }[];
    agentIds?: string[];
  } | null>(null);

  // Auth check on mount — redirect if no token, otherwise fetch user profile.
  useEffect(() => {
    const storedToken = getToken();
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    setIsAuthenticated(true);
    // Fetch user profile (includes tier)
    getMe(storedToken)
      .then((u) => setUser(u))
      .catch(() => {
        // Non-fatal — tier defaults to "basic" if fetch fails
      });
  }, [router]);

  // Stage an od_prototype run into a ref as soon as we're authenticated.
  // NOTE: We do NOT remove od_prototype.pending here — we remove it only
  // when the WebSocket connects and we actually fire the questionnaire.
  useEffect(() => {
    if (!isAuthenticated) return;
    const pending = sessionStorage.getItem("od_prototype.pending");
    if (!pending) return;
    try {
      const draft = JSON.parse(sessionStorage.getItem("prototype.draft") ?? "{}") as {
        templateId?: string; designSystemId?: string; brief?: string; customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
        modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
        images?: { name: string; mime_type: string; data: string }[];
        agentIds?: string[];
      };
      const discovery = JSON.parse(sessionStorage.getItem("prototype.discovery") ?? "null");
      // KAN-87: templateId is now optional (no-template mode). Only require designSystemId.
      // FIX-216c: allow empty brief when chaining (wizard canContinue already validated it).
      if (!draft.designSystemId) return;
      pendingOdProtoRef.current = {
        templateId: draft.templateId ?? "",  // empty string = no template
        designSystemId: draft.designSystemId,
        brief: draft.brief,
        discovery,
        customDsBody: draft.customDsBody,
        customTemplateBody: draft.customTemplateBody,
        sourceRunId: draft.sourceRunId,
        // Present only when the wizard's Review-gates section was touched.
        gateAgentIds: draft.gateAgentIds,
        modelOverrides: draft.modelOverrides,
        selections: draft.selections,
        images: draft.images,
        agentIds: draft.agentIds,
      };
    } catch { /* ignore malformed session data */ }
  }, [isAuthenticated]);

  // Stage an od_ppt run into a ref as soon as we're authenticated.
  // NOTE: We do NOT remove od_ppt.pending here — we remove it only when
  // the WebSocket connects and we actually fire the questionnaire. This
  // makes the flow resilient to backend restarts between auth and connect.
  useEffect(() => {
    if (!isAuthenticated) return;
    const pending = sessionStorage.getItem("od_ppt.pending");
    if (!pending) return;
    try {
      const draft = JSON.parse(sessionStorage.getItem("ppt.draft") ?? "{}") as {
        templateId?: string; designSystemId?: string | null; brief?: string;
        customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
        modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
        images?: { name: string; mime_type: string; data: string }[];
        agentIds?: string[];
      };
      // FIX-216c: allow empty brief when chaining (the chain context block IS the
      // brief; wizard canContinue guard already validated it). Only require templateId.
      if (!draft.templateId) return;
      pendingOdPptRef.current = {
        templateId: draft.templateId,
        designSystemId: draft.designSystemId ?? null,
        brief: draft.brief,
        discovery: null,
        customDsBody: draft.customDsBody,
        customTemplateBody: draft.customTemplateBody,
        sourceRunId: draft.sourceRunId,
        // Present only when the wizard's Review-gates section was touched.
        gateAgentIds: draft.gateAgentIds,
        modelOverrides: draft.modelOverrides,
        selections: draft.selections,
        images: draft.images,
        agentIds: draft.agentIds,
      };
    } catch { /* ignore malformed session data */ }
  }, [isAuthenticated]);
  useEffect(() => {
    if (!isAuthenticated) return;
    const currentToken = getToken();
    if (!currentToken) return;

    getWorkflows(currentToken, { limit: 50 })
      .then(({ runs }) => setRecentRuns(runs))
      .catch(() => {
        // Silently fail — workflows will load when backend is available
        // This prevents the error from showing on the UI
      });

    // Pre-fetch the user-launchable workflow catalog so HomeLaunchGrid can seed
    // its card grid instantly from state instead of making its own fetch.
    getWorkflowDefinitions(currentToken)
      .then((rows) => setHomeWorkflows(rows.filter((w) => w.user_launchable)))
      .catch(() => { /* non-fatal — HomeLaunchGrid falls back to its own fetch */ });
  }, [isAuthenticated]);

  // Handle incoming WebSocket messages.
  // `frameRunId` is the run the frame arrived ON (stamped by the SSE transport,
  // or passed explicitly by the durable-replay caller) — used to run-scope the
  // agent-state frames below.
  const handleWebSocketMessage = useCallback((msg: StreamMessage, frameRunId?: string) => {
    // ── Run-scope the per-agent frames (foreign-run bleed) ────────────────────
    // The SSE provider attaches ONE stream per live run and fans EVERY frame out
    // to this single subscriber. The agent-scoped payloads carry no
    // `pipeline_run_id`, and agent ids are NOT unique across runs (two prototype
    // runs both stream `prototype-build` / `prototype-validate`), so a
    // concurrently running run's frames were applied to the VIEWED run's agents:
    // after the viewed run finished (`pipeline_complete` → all agents "done",
    // completion notification fired) the other run's build/validate frames flipped
    // those same agents back to "running" and kept them cycling through its task
    // loop — the "workflow says done but build + validate are still looping"
    // symptom, with no second notification possible (the notif id was consumed).
    //
    // Dropped BEFORE the dedup/cursor bookkeeping so a foreign run's `seq` can no
    // longer advance this tab's reconnect cursor either. Generic — keyed only on
    // the run id (SC-001/INV-1, no workflow or agent name). Lifecycle frames
    // (pipeline_*/planner_*/clarify/wave_*/chat_*) are untouched: they carry their
    // own run id and drive cross-run behaviour (revision, chaining, reopen).
    if (
      isAgentScopedFrame(msg.type as string) &&
      isForeignRunFrame(frameRunId, trackedRunIdRef.current)
    ) {
      return;
    }

    // Phase 12 (RESUME-03 FE half) — track the last-received seq per run so the
    // reconnect can send it as after_seq (durable replay, 12-03). Every backend
    // event has carried seq/event_id since Phase 5. The max-seen seq is the
    // resume offset; the seen-event_id set dedupes replayed events so a durable
    // reconnect replay applies each event at most once (idempotent).
    const evData = (msg.data as Record<string, unknown> | undefined) ?? undefined;

    // CR-05 — dedup by event_id at the TOP of the handler, BEFORE routing to any
    // handler (wave AND non-wave: agent_chunk, tool_call, task_progress). The FE
    // now always sends after_seq on reconnect, so the backend replay branch is
    // always entered and persisted-but-not-yet-drained events can be delivered
    // twice (replay loop + re-attached drainer). The single dedup site here makes
    // every event type idempotent — a replayed agent_chunk applies at most once
    // (no duplicated streamed text). Legacy/unstamped events (no event_id) fall
    // through undeduped, as before.
    const topEventId =
      evData && typeof evData.event_id === "string"
        ? (evData.event_id as string)
        : undefined;
    if (!shouldApplyEvent(seenEventIdsRef.current, topEventId)) {
      return; // duplicate — drop before any routing or cursor advance
    }

    // Advance the max-seen seq cursor ONLY after the dedup check passes, so a
    // duplicate event does not re-advance the after_seq offset.
    const evSeq = evData && typeof evData.seq === "number" ? (evData.seq as number) : undefined;
    if (typeof evSeq === "number" && evSeq > lastSeqRef.current) {
      lastSeqRef.current = evSeq;
    }

    // Phase 31 (CHATUI-03) — the Phase-29 chat frames feed the transcript, not
    // the pipeline reducer. The chat transcript subscribes to the SSE fan-out
    // directly (chatSubscribe → useRunChat); here we simply early-return so these
    // frame types don't fall through into the pipeline switch below.
    // `msg.type` is the StreamMessage union which does not enumerate the chat
    // frame names; widen to string for the membership test.
    const frameType = msg.type as string;
    if (
      frameType === "chat_message" ||
      frameType === "chat_reply" ||
      frameType === "stream_attached"
    ) {
      return;
    }

    // Phase 12 (§22) — wave/subagent lifecycle events route into the wave-tree
    // state (statuses only, D-14). Dedup already happened at the TOP of the
    // handler (CR-05), so here we just fold the event into the wave groups, then
    // return (these events do not flow to the pipeline handler or the legacy
    // switch below).
    const WAVE_EVENT_TYPES = [
      "wave_started", "wave_completed", "wave_failed",
      "subagent_spawned", "subagent_result",
    ];
    if (WAVE_EVENT_TYPES.includes(msg.type)) {
      const data = evData ?? {};

      // KAN-125 FIX: only process wave events for the actively-building run.
      // Use _sourceRunId (injected per SSE stream) as the primary signal — this
      // covers events that might not carry pipeline_run_id in their data.
      const waveSourceRunId =
        (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined
        ?? (typeof data.pipeline_run_id === "string" ? data.pipeline_run_id : undefined);
      if (
        waveSourceRunId &&
        activelyBuildingRunIdRef.current &&
        waveSourceRunId !== activelyBuildingRunIdRef.current
      ) {
        return; // foreign concurrent run's wave event — skip
      }

      // 12-06 emit contract (flat on `data`): `wave_index` (number),
      // `step` (string), `worker` (number). Consume these EXACT keys — a rename
      // or nesting mismatch silently drops every subagent event again.
      const waveIndex =
        typeof data.wave_index === "number" ? (data.wave_index as number) : undefined;
      if (waveIndex === undefined) return;
      // IN-06 — key wave groups by (step, waveIndex), not waveIndex alone, so two
      // wave_scheduler steps in one run don't merge their wave-index-0 groups.
      const step = typeof data.step === "string" ? (data.step as string) : undefined;

      setWaveGroups((prev) => {
        const next = prev.map((w) => ({ ...w, workers: [...w.workers] }));
        let group = next.find(
          (w) => w.waveIndex === waveIndex && w.step === step,
        );
        if (!group) {
          group = { waveIndex, step, taskIds: [], status: "pending", workers: [] };
          next.push(group);
        }

        if (msg.type === "wave_started") {
          const taskIds = Array.isArray(data.task_ids)
            ? (data.task_ids as unknown[]).map((t) => String(t))
            : group.taskIds;
          group.taskIds = taskIds;
          group.status = "running";
        } else if (msg.type === "wave_completed") {
          group.status = "completed";
        } else if (msg.type === "wave_failed") {
          group.status = "failed";
        } else if (msg.type === "subagent_spawned" || msg.type === "subagent_result") {
          const agent =
            typeof data.agent === "string"
              ? (data.agent as string)
              : typeof data.agent_id === "string"
              ? (data.agent_id as string)
              : "worker";
          const status =
            typeof data.status === "string"
              ? (data.status as string)
              : msg.type === "subagent_spawned"
              ? "running"
              : "completed";
          // CR-06 FE half — key the worker leaf by the `worker` INDEX, not the
          // agent name, so N parallel workers of the SAME agent (the sample_wave
          // self×N shape) render as N distinct leaves instead of collapsing into
          // one flapping leaf. Fall back to the agent name when no worker index
          // is present (legacy/unstamped events).
          const workerIndex =
            typeof data.worker === "number" ? (data.worker as number) : undefined;
          const existing = group.workers.find((wk) =>
            workerIndex !== undefined
              ? wk.worker === workerIndex
              : wk.worker === undefined && wk.agent === agent,
          );
          if (existing) {
            existing.status = status;
            existing.agent = agent;
          } else {
            group.workers.push({ agent, status, worker: workerIndex });
          }
        }

        return next;
      });
      return;
    }

    // Route pipeline messages to the workflow handler.
    // pipeline_cancelled was omitted previously, which left
    // `pipelineState.isRunning` stuck true after Stop — the BE cancelled
    // and emitted the event, but the FE never transitioned out of the
    // running state.
    // Phase 2 (Universal Engine): planner_*/gate_status/clarification events
    // are also routed to the workflow handler so the planning stage is visible.
    const pipelineTypes = [
      "pipeline_start", "agent_start", "agent_thinking", "agent_chunk",
      "agent_complete", "agent_error", "pipeline_complete", "pipeline_failed",
      "pipeline_cancelled",
      "planner_start", "planner_complete", "planner_timeout", "planner_error",
      "gate_status", "clarification_limit_reached",
      // Phase 3 (T043/T044) — Thinking tab: agent_input carries inputPrompt +
      // contextSources; tool_call/tool_result carry tool execution data;
      // workflow_validated carries DAG edges for the dependency graph.
      "agent_input", "tool_call", "tool_result", "workflow_validated",
      // task_progress — prototype build agent reports per-task completion
      "task_progress",
      // task_loop_progress — engine-level build loop iteration counter
      "task_loop_progress",
      // pipeline_reconnected — backend confirmed reconnection to running pipeline
      "pipeline_reconnected",
      // Note: review_gate_ready and review_gate_approved are NOT here —
      // they go through the switch statement below to update reviewGateData state.
    ];
    if (pipelineTypes.includes(msg.type)) {
      // WR-03 — a new run starts: reset the per-run FE replay/dedup/wave state so
      // a stale after_seq cursor, a poisoned seen-set, or the previous run's wave
      // panel never bleed into the new run's reconnect. Run 2's events then
      // advance lastSeqRef from 0, so a mid-run reconnect during run 2 sends the
      // correct after_seq (run 1 left it at e.g. 500). NOTE: the just-deduped
      // pipeline_start event_id is re-recorded after the reset so a replay of
      // pipeline_start itself stays idempotent within the new run.
      //
      // BUG-005 — RUN-SCOPE the reset: the SSE provider's non-run-scoped fan-out
      // forwards a CONCURRENT foreign run's pipeline_start to this single
      // subscriber too. Running the reset for a foreign frame nulls the VIEWED
      // run's activePipelineRunId/questionnaireData + poisons the shared seen-set,
      // collapsing the viewed run's clarify to "0/0 BUILDING". So SKIP the reset
      // when the incoming pipeline_run_id belongs to a DIFFERENT run than the one
      // this tab tracks. When there is no tracked id yet, or the ids match, the
      // reset runs exactly as before (launch / same-tab-new-run flow unregressed).
      // CRITICAL: gate on `trackedRunIdRef.current` (a ref), NOT the
      // activePipelineRunId/contentSourceRunId STATE — handleWebSocketMessage is a
      // useCallback([]) whose closure captures the INITIAL (null) state, so a
      // direct state read would treat every pipeline_start as foreign and break the
      // launch reset (the DEF-44-12-4 stale-closure class).
      if (msg.type === "pipeline_start") {
        const incomingRunId =
          // _sourceRunId is injected per SSE stream — more reliable than data parsing
          (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined
          ?? (msg.data as Record<string, unknown> | undefined)?.pipeline_run_id as string | undefined;
        const isForeignRun =
          !!incomingRunId && (
            // KAN-125 MULTI-TAB: if this tab has never launched anything (empty set),
            // any incoming run is foreign — prevents new-tab from having its state reset
            // by a background run auto-attached by refreshLiveRuns.
            launchedRunIdsRef.current.size === 0 ||
            // Same-tab concurrent: if we're tracking a specific run, a different run's
            // pipeline_start must not reset the tracked run's clarify/seen-set.
            (!!trackedRunIdRef.current && incomingRunId !== trackedRunIdRef.current) ||
            // FIX-201 (KAN-168): launch window — launchPendingRef=true means a new run
            // was started but its id is not yet known. Any pipeline_start for a run
            // already in launchedRunIdsRef (a PREVIOUS run's concurrent SSE) is foreign.
            // Only pipeline_start for the NEW run (not yet in the set) should reset.
            // We can't know the new run's id yet, so block ALL pipeline_starts for
            // known-launched runs during the pending window.
            (launchPendingRef.current && launchedRunIdsRef.current.has(incomingRunId))
          );
        if (isForeignRun) {
          // Foreign concurrent run — forward the frame to the reducer (below) but
          // do NOT reset THIS tab's clarify / seen-set / review-gate.
          // FIX-205: stamp the run id onto the notification created for this run
          // at launch time (before the run id was known), so backgroundCompletedRunId
          // can find it on completion.
          if (incomingRunId) {
            setBackgroundStartedRunId(incomingRunId);
          }
        } else {
          // FIX-201 (KAN-168): when launchPendingRef=true, this pipeline_start is
          // for the new run being launched (not yet in launchedRunIdsRef). Register
          // it immediately so the isForeignFrame check below passes for subsequent
          // frames (agent_start, agent_chunk, etc.) that arrive before .then() adds
          // the run to launchedRunIdsRef. Without this, all frames during the POST
          // window are treated as foreign and dropped from the store.
          // Also switch the store viewport to this run immediately so frames project.
          if (launchPendingRef.current && incomingRunId && !launchedRunIdsRef.current.has(incomingRunId)) {
            launchedRunIdsRef.current.add(incomingRunId);
            persistLaunchedIds();
            // Check clarify state of the PREVIOUS viewed run BEFORE overwriting refs.
            // If the user is answering clarify questions for run A and run B's
            // pipeline_start arrives, switching the viewport would replace A's agent
            // list with B's agents below the clarify form (cross-run contamination).
            const prevTrackedId = trackedRunIdRef.current;
            const prevViewedHasClarify =
              !!prevTrackedId &&
              (runStore.get(prevTrackedId)?.questionnaireData != null);
            // Point all tracking refs at the new run immediately — same as .then()
            trackedRunIdRef.current = incomingRunId;
            activelyBuildingRunIdRef.current = incomingRunId;
            // Switch the store viewport so frames project to the UI immediately —
            // BUT only when the previous viewport was NOT parked on a clarify-paused
            // run. The .then() callback will handle the viewport switch once the
            // clarify is done; for now accumulate the new run's frames silently.
            if (!prevViewedHasClarify) {
              runStoreSwitchViewToRef.current(incomingRunId);
            }
          }
          resetReplayState({
            seen: seenEventIdsRef.current,
            setLastSeq: (n) => {
              lastSeqRef.current = n;
            },
            setWaveGroups,
          });
          if (topEventId) seenEventIdsRef.current.add(topEventId);
          // KAN-89: clear any stale reviewGateData from a previous run so the
          // ReviewGatePanel never blocks the new pipeline's preview area.
          // reviewGateData lives separately from pipelineState and is not cleared
          // by onResetPipeline() — this is the canonical place to clear it since
          // pipeline_start is the definitive "new run has begun" signal.
          setReviewGateData(null);
          // Clear stale questionnaire state from a previous run that may have
          // been cancelled/failed while the clarify gate was open (questionnaire_complete
          // never fired). Without this, the old questionnaire panel can flash or
          // persist into the next run's preview area.
          setQuestionnaireData(null);
          setActivePipelineRunId(null);
          // KAN-120: clear the lastCancelledRunId so the resumed run's pipeline_start
          // removes the "Cancelled" state from history and the chat lane.
          setLastCancelledRunId(null);
          // KAN-101: reset the spec revision cycle counter on every new run start.
          setSpecRevisionCount(0);
          // KAN-101: disarm the cycle detector on new run start.
          revisionCycleArmedRef.current = false;
        }
      }

      // KAN-125 — RUN-SCOPE the pipelineState reducer: the SSE provider's
      // non-run-scoped fan-out forwards frames from EVERY concurrent run to
      // this single subscriber. For events other than pipeline_start (whose
      // reset side-effect is already guarded by BUG-005 above), we must also
      // prevent foreign-run agent_start / agent_chunk / agent_complete /
      // pipeline_complete etc. from overwriting the VIEWED run's shared
      // pipelineState. Both concurrent user_stories runs use identical
      // agent_ids (domain-analyst, epic-architect, …) — without this guard
      // whichever run's frame arrives last overwrites the same state slot.
      //
      // KAN-125 FIX: The reducer guard uses TWO layers:
      //
      //   Layer 1 (launchedRunIdsRef) — "is this from a run this tab owns?"
      //     A frame is "foreign" ONLY when it carries a pipeline_run_id that is
      //     NOT in the set of runs launched by this tab. This blocks truly
      //     external runs (e.g. a concurrent run in another browser tab).
      //
      //   Layer 2 (activelyBuildingRunIdRef) — "is this from the run the user
      //     is currently BUILDING/VIEWING?" Even for tab-local runs, only the
      //     most-recently-launched (actively building) run's frames should go to
      //     the shared pipelineState reducer. A second tab-local run's
      //     pipeline_start would otherwise RESET the reducer (wipe agent list),
      //     showing "nothing in Steps" for the first run. The second run's final
      //     output is still captured in the pipeline_complete handler below (which
      //     intentionally saves content for ALL tab-local completions) and is
      //     accessible via the recents list.
      //
      // CRITICAL: both checks must use refs (not state) because this is a
      // useCallback([]) — all state reads see stale initial values.
      //
      // KAN-125 FIX (FIX-135): use `_sourceRunId` (injected by RunConnectionProvider
      // per attached run, keyed on the SSE stream id) as the primary run-identity
      // signal. This covers ALL event types — including agent_start / agent_chunk /
      // agent_complete / agent_input / tool_call / task_progress etc. — which do NOT
      // carry pipeline_run_id in their `data`. Previously these events bypassed the
      // `isForActiveRun` guard (via the `!frameRunId` pass-through), allowing them
      // from ALL concurrent runs to reach the shared pipelineState reducer.
      const frameRunId =
        // Prefer _sourceRunId (injected per SSE stream — covers all event types)
        (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined
        // Fallback to pipeline_run_id in data (only events that explicitly carry it)
        ?? (msg.data as Record<string, unknown> | undefined)?.pipeline_run_id as string | undefined;

      // Layer 1: is this from a run this tab ever launched?
      // KAN-125 MULTI-TAB FIX: when launchedRunIdsRef is empty (brand-new tab that
      // has never launched anything AND has no sessionStorage-restored launches),
      // treat ALL frames as foreign so server-discovered background runs never
      // pollute this tab's pipelineState. The isForActiveRun guard (Layer 2) already
      // blocks frames when activelyBuildingRunIdRef is null, but an explicit Layer-1
      // block here also prevents any frames from reaching the pipeline reducer for
      // runs this tab did not start.
      // Exception: frameRunId absent (infra events, Concierge) → always pass through.
      const isForeignFrame =
        !!frameRunId &&
        (
          // Tab never launched anything → every frame with a run id is foreign
          launchedRunIdsRef.current.size === 0 ||
          // Tab launched some runs but this frame is from a run we don't own
          !launchedRunIdsRef.current.has(frameRunId)
        );

      // Layer 2: is this from the run the user is currently VIEWING/BUILDING?
      // Only the actively-building run's frames update pipelineState (the Steps /
      // Audit / progress tabs). Other tab-local runs' content is captured at
      // pipeline_complete below but does not interfere with live agent progress.
      // CRITICAL: use activelyBuildingRunIdRef (only set on launch), NOT
      // trackedRunIdRef (which gets re-pointed by contentSourceRunId of completed
      // runs). Using trackedRunIdRef here would cause a completing concurrent run
      // to re-point the gate and block the still-building run's live progress.
      // FIX-201 (KAN-168): also block during launchPendingRef window (between
      // onStartPipeline click and POST .then() registering the new run id).
      // During this window, activelyBuildingRunIdRef still points to the PREVIOUS
      // run, so its live SSE frames would pass isForActiveRun and contaminate the
      // new run's pipelineState. launchPendingRef=true blocks all run-scoped frames
      // until the new run id is known.
      const isForActiveRun =
        !frameRunId || // no run id on frame → infra event (Concierge /messages), always pass through
        // During launch window: block frames ONLY for runs we don't know yet.
        // Once a run is registered (via pipeline_start early-registration or .then()),
        // its frames must flow through even if launchPendingRef is still true.
        // The old "block all frames during launchPendingRef" caused agent_start/agent_chunk
        // frames for already-registered runs to be dropped from useWorkflow.pipelineState.
        (
          !activelyBuildingRunIdRef.current || // no run launched yet → first launch, pass through
          frameRunId === activelyBuildingRunIdRef.current // frame is for the actively-building run
        );

      // FIX-201 (KAN-168): route ALL tab-local pipeline frames to the per-run store.
      // runStore.handleFrame stores pipeline state per run and projects to the UI
      // only for the viewed run — no cross-contamination between concurrent runs.
      // This runs BEFORE the isForActiveRun check so background runs accumulate
      // their state correctly while the user watches a different run.
      if (!isForeignFrame && frameRunId) {
        runStoreHandleFrameRef.current(frameRunId, msg as unknown as { type: string; [key: string]: unknown });
      }

      if (!isForeignFrame && isForActiveRun) {
        // KAN-101 — detect a spec revision cycle
        if (msg.type === "agent_start") {
          const agentId = (msg.data as Record<string, unknown> | undefined)?.agent_id as string | undefined
            ?? (msg as unknown as Record<string, unknown>).agent_id as string | undefined;
          if (agentId && revisionCycleArmedRef.current) {
            const prevAgent = pipelineAgentsRef.current.find((a) => a.id === agentId);
            if (prevAgent && prevAgent.status === "done") {
              revisionCycleArmedRef.current = false;
              setSpecRevisionCountRef.current((c) => c + 1);
            }
          }
        }

        handlePipelineMsgRef.current?.({
          type: msg.type,
          ...(msg.data as Record<string, unknown> || {}),
        });
      }

      // When pipeline completes, route final output to preview panel
      if (msg.type === "pipeline_complete" && msg.data) {
        const data = msg.data as Record<string, unknown>;
        // Revision Families (B1): the live completion source — the engine emits
        // pipeline_run_id in the pipeline_complete data (engine.py:2267). This is
        // the run a subsequent inline revise must link as its parent.
        // BUG-011: run-scope the set so a FOREIGN concurrent run's completion can
        // no longer re-point the VIEWED content-source. Mirrors the BUG-005
        // pipeline_start `isForeignRun` shape (gate on the trackedRunIdRef, not the
        // stale-closure state). When the completing run IS the tracked/launched run
        // (launch->watch) OR there is no tracked id yet, it is NOT foreign — so the
        // set runs byte-identically to before; only a genuine foreign concurrent
        // completion is skipped.
        const completingRunId = data.pipeline_run_id as string | undefined;
        const completingPipelineType = data.pipeline_type as string | undefined;
        const isForeignCompletion =
          !!completingRunId &&
          !!trackedRunIdRef.current &&
          completingRunId !== trackedRunIdRef.current;
        // KAN-116 (Issue 2): a *_revision pipeline is intentionally dispatched
        // FROM the currently-tracked run. When it completes, contentSourceRunId
        // must advance to the revision run so DashboardLayout's family useEffect
        // re-fires and fetches the updated family (showing v1/v2/... chips).
        // Without this, the revision completes but isForeignCompletion is true
        // (revision_run_id ≠ trackedRunIdRef which holds the parent run id) and
        // the family is never re-fetched, leaving the version dropdown at v1.
        // SC-001/INV-1: keyed on generic endsWith("_revision") suffix, no literal.
        const isRevisionCompletion = typeof completingPipelineType === "string" && completingPipelineType.endsWith("_revision");

        // FIX-203: for foreign completions (background concurrent runs), signal
        // DashboardLayout to mark the matching notification as completed.
        // pipelineState only reflects the viewed run, so DashboardLayout's standard
        // completion effect never fires for background runs. Exclude revision
        // completions (they are not "foreign" in the notification sense — the user
        // intentionally launched them and they are tracked via the viewed run).
        if (completingRunId && isForeignCompletion && !isRevisionCompletion) {
          setBackgroundCompletedRunId(completingRunId);
        }

        if (completingRunId && (!isForeignCompletion || isRevisionCompletion)) {
          setContentSourceRunId(completingRunId);
          // BUG-015 — release the tracked completing run's sticky focus so its
          // terminal SSE stream unmounts (no reconnect, no ~14k re-replay). Reached
          // via a ref (this handler is a useCallback([]) — never a direct
          // runConnection reference). The rendered preview/content is already in
          // state, so unmounting the connection does not remove it.
          detachRunRef.current?.(completingRunId);
          // FIX-172: the narrator's "Delivered" chat_reply card is yielded by
          // execute() AFTER pipeline_complete. Both go into the SSE queue, but
          // detachRun above unmounts the RunStreamConnection before the chat_reply
          // arrives — causing a race where the card is persisted to the DB but
          // never reaches the transcript via SSE. Fix: after detach, fetch the
          // completing run's durable events from the DB and fold any new chat_reply
          // frames into the transcript via appendRunChatFrames (no reset, idempotent
          // by event_id via useRunChat's seenRef dedup).
          // FIX-173: capture the current contentSourceRunId BEFORE the async gap
          // so we can guard against stale completions: with concurrent revisions
          // a superseded run's pipeline_complete can arrive AFTER a newer revision
          // has already set a different contentSourceRunId — without the guard its
          // "Delivered" card would be appended to the NEW run's transcript,
          // producing a duplicate. Re-read contentSourceRunIdRef inside the async
          // body (it's set synchronously two lines above).
          const _completingRunId = completingRunId;
          void (async () => {
            try {
              const tok = getToken();
              if (!tok || !_completingRunId) return;
              // Brief yield so the narrator's DB commit lands before we read.
              await new Promise<void>((res) => setTimeout(res, 400));
              // FIX-173: if contentSourceRunId has been superseded by a newer
              // revision, skip — the new run's completion will handle its own card.
              // We read from contentSourceRunId state via trackedRunIdRef (the
              // closest stable ref pointing at the viewed run); if it has moved on,
              // the frames are irrelevant to the current transcript.
              if (trackedRunIdRef.current !== _completingRunId) return;
              // FIX-176: fetch ONLY events after the last seq the chat hook has
              // seen — not from seq 0. This prevents already-delivered chat_reply
              // cards (e.g. "Revision started", "Run started") from being
              // re-added as duplicates. FIX-172's purpose is ONLY to recover the
              // "Delivered" card that raced with detachRun; the last event in a
              // run is pipeline_complete and its chat_reply, both of which arrive
              // after all other chat events and therefore after lastSeq.
              const afterSeq = getRunChatLastSeqRef.current?.() ?? 0;
              const frames = await getRunEvents(tok, _completingRunId, afterSeq);
              // Only forward chat frames — pipeline/agent frames for a completed
              // run must not re-trigger the reducer (they'd re-fire agent state).
              const chatFrames = frames.filter(
                (f) => f.type === "chat_message" || f.type === "chat_reply",
              );
              if (chatFrames.length > 0) {
                appendRunChatFramesRef.current?.(chatFrames);
              }
            } catch {
              // Non-fatal: if the fetch fails the card is absent until reopen
            }
          })();
        }
        const finalOutput = data.final_output as string;
        const pipelineType = data.pipeline_type as string;

        if (finalOutput && pipelineType) {
          if (pipelineType === "user_stories" || pipelineType === "user_stories_revision" || pipelineType === "app_builder" || pipelineType === "app_builder_revision") {
            setUserStoryContent(finalOutput);
          } else if (pipelineType === "ppt" || pipelineType === "ppt_revision" || pipelineType === "od_ppt" || pipelineType === "od_ppt_revision") {
            setPptContent(finalOutput);
          } else if (pipelineType === "prototype" || pipelineType === "prototype_revision" || pipelineType === "od_prototype") {
            setPrototypeContent(finalOutput);
          } else {
            // ISS-021 (18-03) + CR-01 (18 review fix): any pipeline_type matching
            // none of the known branches — INCLUDING the live agent-composer's
            // `custom` — feeds the generic deliverable channel. `custom` was
            // previously a KNOWN branch routed into setUserStoryContent →
            // MarkdownPreview (escaped HTML); that contradicted the reopen surface
            // (which already treats `custom` structurally) and was the exact
            // root-cause bug this phase eliminates. The mimetype is the DECLARED
            // `deliverable_mimetype` from the pipeline_complete event (18-01 emits
            // it from ectx.deliverable, authoritative on the live path), with the
            // SHARED deriveDeliverableMimetype helper as a defensive fallback for
            // older runs / forward-compat where the key is absent — the IDENTICAL
            // heuristic the reopen surfaces apply, so live and reopen agree. Never
            // routed into the user_story/markdown branch (REJECTED — escapes HTML)
            // and never keyed on the workflow name (SC-001). This is the structural
            // "no known branch matched" else.
            setGenericDeliverable({
              mimetype: (data.deliverable_mimetype as string | undefined)
                || deriveDeliverableMimetype(finalOutput),
              filename: (data.deliverable_filename as string | undefined) || undefined,
              content: finalOutput,
            });
          }
        }

        // IN-03 (13 review fix): a degraded completion (WR-05) is not a full
        // success — surface a warning through the chat (mirrors the
        // pipeline_failed pattern below) naming the agents that errored and
        // never completed. The deliverable above still routes to the preview.
        if (data.status === "degraded") {
          const degradedAgents = (data.agents_failed as string[]) || [];
          const degradedMsg: ChatMessage = {
            id: crypto.randomUUID(),
            chatSessionId: "",
            role: "assistant",
            content:
              `Warning: run completed degraded — the deliverable was produced, but ` +
              (degradedAgents.length
                ? `these agents failed: ${degradedAgents.join(", ")}.`
                : `some agents failed.`) +
              ` [code:pipeline_degraded] [recoverable:false]`,
            createdAt: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, degradedMsg]);
        }

        // Refresh workflow runs from backend after pipeline completes
        const currentToken = getToken();
        if (currentToken) {
          // KAN-125 / FIX-136: when a CONCURRENT run's pipeline_complete triggers this
          // refetch, the DB may already show the user_stories (or other still-building)
          // run as "completed" because the backend writes the status synchronously before
          // the SSE delivers the frame to the FE. Naively replacing recentRuns would show
          // "Done" in history for a run the FE still knows is building (launchedRunIdsRef).
          // Fix: preserve "running" for any run the FE knows is still being driven by this
          // tab. A run leaves launchedRunIdsRef implicitly when pipeline_complete/cancelled
          // for that specific run arrives and `detachRunRef.current(completingRunId)` fires.
          // CRITICAL: read launchedRunIdsRef.current inside the .then() callback (asynchronous
          // — the Set is always current because it's a ref). completingRunId captures the
          // run that just completed via closure, so we exclude ONLY that run from protection.
          const completedRunIdForThisEvent = completingRunId;
          getWorkflows(currentToken, { limit: 50 })
            .then(({ runs }) => setRecentRuns((prev) => {
              return runs.map((r) => {
                // Preserve "running" for any locally-launched run that hasn't completed yet
                // (its pipeline_complete hasn't been processed by this tab's handler yet).
                // Exception: the run that just triggered this refetch — its status IS correct.
                if (
                  r.id !== completedRunIdForThisEvent &&
                  launchedRunIdsRef.current.has(r.id) &&
                  r.status === "completed"
                ) {
                  // This run is tracked by this tab and the DB says completed, but the FE
                  // hasn't received its pipeline_complete yet — keep previous status to avoid
                  // the "running but shows Done" flash.
                  const prevRun = prev.find((p) => p.id === r.id);
                  if (prevRun && prevRun.status === "running") {
                    return { ...r, status: prevRun.status };
                  }
                }
                return r;
              });
            }))
            .catch(() => {});
          // KAN-120: do a second delayed refetch so the history reflects the
          // reconciled status (completed) after _reconcile_terminal_status
          // finishes writing it — the first fetch races against it.
          // KAN-125: the same protection applies to the delayed refetch.
          setTimeout(() => {
            const t = getToken();
            if (t) getWorkflows(t, { limit: 50 }).then(({ runs }) => setRecentRuns((prev) => {
              return runs.map((r) => {
                if (
                  r.id !== completedRunIdForThisEvent &&
                  launchedRunIdsRef.current.has(r.id) &&
                  r.status === "completed"
                ) {
                  const prevRun = prev.find((p) => p.id === r.id);
                  if (prevRun && prevRun.status === "running") {
                    return { ...r, status: prevRun.status };
                  }
                }
                return r;
              });
            })).catch(() => {});
          }, 2000);
        }
      }

      // F3 (13-06): terminal failure — every agent hard-failed. No deliverable
      // extraction (there is none); surface the failure through the same chat
      // error surface "error" events use, and refresh the runs list so the run
      // shows its failed status.
      // KAN-125: only show the error message for the tracked run — foreign run
      // failures should not inject error bubbles into this tab's chat.
      if (msg.type === "pipeline_failed" && msg.data && !isForeignFrame) {
        const data = msg.data as Record<string, unknown>;
        const failedAgents = (data.agents_failed as string[]) || [];
        const errorText = (data.error as string) || "Pipeline failed";
        const failureMsg: ChatMessage = {
          id: crypto.randomUUID(),
          chatSessionId: "",
          role: "assistant",
          content:
            `Error: ${errorText}` +
            (failedAgents.length ? ` (agents failed: ${failedAgents.join(", ")})` : "") +
            ` [code:pipeline_failed] [recoverable:false]`,
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, failureMsg]);

        const currentToken = getToken();
        if (currentToken) {
          // KAN-125 / FIX-136: same protection as pipeline_complete handler —
          // a failed run's refetch must not show other still-running tab-launched
          // runs as completed in history.
          const failedRunId = (msg.data as Record<string, unknown>)?.pipeline_run_id as string | undefined;
          getWorkflows(currentToken, { limit: 50 })
            .then(({ runs }) => setRecentRuns((prev) => {
              return runs.map((r) => {
                if (
                  r.id !== failedRunId &&
                  launchedRunIdsRef.current.has(r.id) &&
                  r.status === "completed"
                ) {
                  const prevRun = prev.find((p) => p.id === r.id);
                  if (prevRun && prevRun.status === "running") {
                    return { ...r, status: prevRun.status };
                  }
                }
                return r;
              });
            }))
            .catch(() => {});
        }
      }

      // KAN-115: clear stale questionnaire state on cancel/fail so laneClarifyOpen
      // goes false and runLaneState resolves to "terminal" not "clarify".
      // Must be HERE (inside the pipelineTypes block, before return) — pipeline_cancelled
      // and pipeline_failed are in pipelineTypes and never reach the switch below.
      // KAN-125: run-scope this — a FOREIGN concurrent run cancelling/failing must
      // not clear THIS tab's questionnaire/reviewGate/activePipelineRunId.
      if (msg.type === "pipeline_cancelled" || msg.type === "pipeline_failed") {
        if (!isForeignFrame) {
          setReviewGateData(null);
          setQuestionnaireData(null);
          setActivePipelineRunId(null);
        }
      }

      return;
    }

    switch (msg.type) {
      case "stream": {
        setIsStreaming(true);
        const chunk = msg.chunk || "";

        // Route content to the appropriate preview section
        if (msg.section === "user_stories") {
          setUserStoryContent((prev) => prev + chunk);
          setStreamingContent((prev) => prev + chunk);
          userStoryContentRef.current += chunk;
          activePreviewSectionRef.current = "user_stories";
        } else if (msg.section === "ppt") {
          // PPT content comes from pipeline_complete, not streaming
          // Only accumulate in ref for legacy chat mode
          pptContentRef.current += chunk;
          activePreviewSectionRef.current = "ppt";
        } else if (msg.section === "prototype") {
          // Prototype content comes from pipeline_complete, not streaming
          prototypeContentRef.current += chunk;
          activePreviewSectionRef.current = "prototype";
        } else {
          setStreamingContent((prev) => prev + chunk);
        }
        break;
      }

      case "phase_start": {
        break;
      }

      case "phase_end": {
        break;
      }

      case "complete": {
        setIsStreaming(false);
        const stepsSnapshot = [...(processStepsRef.current || [])];
        processStepsRef.current = [];
        const previewSection = activePreviewSectionRef.current;
        activePreviewSectionRef.current = null;

        setStreamingContent((prev) => {
          let chatContent = prev;

          if (!chatContent && previewSection) {
            if (previewSection === "ppt") {
              chatContent = "✅ **Presentation generated!** Check the Preview panel → PPT tab to see your slides.";
            } else if (previewSection === "prototype") {
              chatContent = "✅ **Prototype generated!** Check the Preview panel → Prototype tab to see the UI definition.";
            }
          }

          if (chatContent) {
            let artifact: { type: "user-stories" | "ppt" | "prototype"; filename: string; content: string; summary: string } | undefined;

            if (previewSection === "ppt" && pptContentRef.current) {
              artifact = {
                type: "ppt",
                filename: "presentation.pptx",
                content: pptContentRef.current,
                summary: "Slide deck with charts, tables, and comparisons",
              };
            } else if (previewSection === "prototype" && prototypeContentRef.current) {
              artifact = {
                type: "prototype",
                filename: "prototype.json",
                content: prototypeContentRef.current,
                summary: "Interactive prototype with component hierarchy and navigation",
              };
            } else if (previewSection === "user_stories" && userStoryContentRef.current) {
              artifact = {
                type: "user-stories",
                filename: "user-stories.md",
                content: userStoryContentRef.current,
                summary: "Structured backlog with epics, stories, and acceptance criteria",
              };
            }

            setMessages((msgs) => {
              const lastMsg = msgs[msgs.length - 1];
              if (lastMsg && lastMsg.role === "assistant") {
                return msgs;
              }
              return [...msgs, {
                id: crypto.randomUUID(),
                chatSessionId: "",
                role: "assistant" as const,
                content: chatContent,
                createdAt: new Date().toISOString(),
                steps: stepsSnapshot.length > 0 ? stepsSnapshot : undefined,
                artifact,
              }];
            });
          }
          return "";
        });

        setProcessSteps([]);

        if (msg.data && "user_stories" in msg.data) {
          const finalOutput = msg.data;
          if (finalOutput.user_stories) {
            setUserStoryContent(JSON.stringify(finalOutput.user_stories));
          }
          if (finalOutput.ppt) {
            setPptContent(JSON.stringify(finalOutput.ppt));
          }
          if (finalOutput.prototype) {
            setPrototypeContent(JSON.stringify(finalOutput.prototype));
          }
        }
        break;
      }

      case "error": {
        setIsStreaming(false);

        let errorMessage = "An error occurred during processing.";
        let errorCode: string | undefined;
        let recoverable = true;

        if (msg.data && "error" in msg.data) {
          const errorData = msg.data as { error?: string; code?: string; recoverable?: boolean };
          errorMessage = errorData.error || errorMessage;
          errorCode = errorData.code;
          recoverable = errorData.recoverable !== false;
        } else if (msg.chunk) {
          errorMessage = msg.chunk;
        }

        let content = `Error: ${errorMessage}`;
        if (errorCode) {
          content += ` [code:${errorCode}]`;
        }
        content += ` [recoverable:${recoverable}]`;

        const errorMsg: ChatMessage = {
          id: crypto.randomUUID(),
          chatSessionId: "",
          role: "assistant",
          content,
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMsg]);
        setStreamingContent("");
        break;
      }

      case "title_update": {
        if (msg.data && "title" in msg.data && "chat_session_id" in msg.data) {
          const titleData = msg.data as { chat_session_id: string; title: string };
          setChatTitleUpdate(titleData);
        }
        break;
      }

      case "workflow_title_update": {
        // Claude generated a clean title for the workflow run — update the list
        if (msg.data && "workflow_id" in msg.data && "title" in msg.data) {
          const { workflow_id, title } = msg.data as { workflow_id: string; title: string };
          setRecentRuns((prev) =>
            prev.map((r) => r.id === workflow_id ? { ...r, title } : r)
          );
        }
        break;
      }

      case "questionnaire": {
        if (msg.data && "questions" in msg.data) {
          // Per-run map (FIX-201 / KAN-168): store questionnaire by run id, project only when viewed.
          const qSrcRunId = (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined
            ?? frameRunId;
          const qData = msg.data as { questions: { id: string; question: string; options: string[] }[] };
          if (qSrcRunId) {
            getRunViewState(qSrcRunId).questionnaireData = qData;
            if (qSrcRunId === trackedRunIdRef.current) setQuestionnaireData(qData);
          } else if (!trackedRunIdRef.current) {
            setQuestionnaireData(qData);
          }
        }
        break;
      }

      case "questionnaire_ready": {
        if (msg.data && "questions" in msg.data) {
          const data = msg.data as {
            pipeline_run_id?: string;
            questions: Array<{
              question_id: string; question_text: string; options?: string[] | null;
              answer_type?: string; recommended_answer?: string; recommended_reasoning?: string;
              recommended_display?: string; ambiguity_category?: string; impact_level?: string;
            }>;
          };
          // Resolve which run this questionnaire belongs to (priority order).
          const qRunId = data.pipeline_run_id
            ?? (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined
            ?? frameRunId;

          const mapped = (data.questions || []).map((q) => ({
            id: q.question_id, question: q.question_text, options: q.options || [],
            answerType: q.answer_type || "single_choice",
            recommendedAnswer: q.recommended_answer || "",
            recommendedReasoning: q.recommended_reasoning || "",
            recommendedDisplay: q.recommended_display || q.recommended_answer || "",
            ambiguityCategory: q.ambiguity_category || "",
            impactLevel: q.impact_level || "medium",
          }));

          if (qRunId) {
            // Store for this run; runStore.update projects to UI only if viewed.
            runStore.update(qRunId, {
              questionnaireData: { questions: mapped },
              activePipelineRunId: qRunId,
            });
            // Also keep the legacy React state in sync for the viewed run
            // (DashboardLayout reads questionnaireData and activePipelineRunId as props).
            if (qRunId === trackedRunIdRef.current) {
              setQuestionnaireData({ questions: mapped });
              setActivePipelineRunId(qRunId);
            }
            // Refresh recentRuns so the header badge shows the correct "WAITING FOR YOU"
            // status instead of the stale "planning"/"clarifying" status snapshot.
            // When questionnaire_ready fires, the backend has already transitioned the
            // run to waiting_for_user — recentRuns needs to reflect this for the badge.
            const refreshToken = getToken();
            if (refreshToken) {
              getWorkflows(refreshToken, { limit: 50 })
                .then(({ runs }) => setRecentRuns(runs))
                .catch(() => { /* non-fatal — badge will show stale status */ });
            }
          } else if (!trackedRunIdRef.current) {
            setQuestionnaireData({ questions: mapped });
            if (data.pipeline_run_id) setActivePipelineRunId(data.pipeline_run_id);
          }
        }
        break;
      }

      case "questionnaire_complete": {
        // Per-run store: clear this run's questionnaire.
        const qcSrcRunId = (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined
          ?? frameRunId;
        if (qcSrcRunId) {
          runStore.update(qcSrcRunId, { questionnaireData: null });
          if (qcSrcRunId === trackedRunIdRef.current) setQuestionnaireData(null);
        } else {
          setQuestionnaireData(null);
        }
        // Refresh recentRuns so the badge reflects the resumed status.
        const qcToken = getToken();
        if (qcToken) {
          getWorkflows(qcToken, { limit: 50 })
            .then(({ runs }) => setRecentRuns(runs))
            .catch(() => { /* non-fatal */ });
        }
        break;
      }

      case "review_gate_ready": {
        // Per-run store: store gate data, project only when viewed.
        if (msg.data) {
          const data = msg.data as unknown as ReviewGateReadyData;
          const gateRunId = data.pipeline_run_id
            ?? (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined
            ?? frameRunId;

          const gateData = {
            gateKey: data.gate_key, agentId: data.agent_id, agentName: data.agent_name,
            output: data.output, pipelineRunId: data.pipeline_run_id,
            redoable: data.redoable ?? false,
            updateSpecsEligible: data.update_specs_eligible ?? false,
            artifactKind: data.artifact_kind,
          };

          if (gateRunId) {
            runStore.update(gateRunId, { reviewGateData: gateData });
            if (gateRunId === trackedRunIdRef.current) setReviewGateData(gateData);
          } else {
            setReviewGateData(gateData);
          }
          // Refresh recentRuns so the badge shows "WAITING FOR YOU" when gate fires.
          const gateToken = getToken();
          if (gateToken) {
            getWorkflows(gateToken, { limit: 50 })
              .then(({ runs }) => setRecentRuns(runs))
              .catch(() => { /* non-fatal */ });
          }
        }
        break;
      }

      case "review_gate_approved": {
        // User approved — clear the review gate UI and continue.
        // KAN-98: if the user approved with edits, apply the editedContent to the
        // agent's output in pipelineState so the Thinking tab shows the edited version.
        if (pendingGateEditRef.current) {
          const { agentId, editedContent } = pendingGateEditRef.current;
          pendingGateEditRef.current = null;
          retainAgentEdit(agentId, editedContent);
        }
        // Clear in the store too
        const approvedSrcRunId = (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined ?? frameRunId;
        if (approvedSrcRunId) {
          runStore.update(approvedSrcRunId, { reviewGateData: null });
        }
        setReviewGateData(null);
        // Refresh recentRuns so badge shows resumed status after gate approval.
        const approveToken = getToken();
        if (approveToken) {
          getWorkflows(approveToken, { limit: 50 })
            .then(({ runs }) => setRecentRuns(runs))
            .catch(() => { /* non-fatal */ });
        }
        break;
      }

      case "pipeline_cancelled":
      case "pipeline_failed": {
        // Per-run store: clear this run's gate/questionnaire state.
        const termSrcRunId = (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined ?? frameRunId;
        if (termSrcRunId) {
          runStore.update(termSrcRunId, { reviewGateData: null, questionnaireData: null });
        }
        setReviewGateData(null);
        // KAN-115: also clear stale questionnaire state — if the pipeline was
        // cancelled/failed while the clarify gate was open, questionnaire_complete
        // never fires, so questionnaireData stays populated. This keeps
        // laneClarifyOpen=true in DashboardLayout, which forces runLaneState to
        // "clarify" instead of "terminal" and leaves the AwaitingCard visible.
        // Mirrors the identical pipeline_start clear (lines above).
        setQuestionnaireData(null);
        // KAN-120: preserve the run id so Run Again can resume it even when
        // activePipelineRunId is about to be cleared.
        if (msg.type === "pipeline_cancelled") {
          const cancelledId = ((msg.data as Record<string, unknown>)?.pipeline_run_id as string | undefined)
            ?? activePipelineRunId
            ?? trackedRunIdRef.current;
          if (cancelledId) setLastCancelledRunId(cancelledId);
          // BUG-015 mirror for cancellation: release the sticky SSE focus so the
          // RunStreamConnection unmounts when the server closes the stream after
          // pipeline_cancelled. Without this, the stream close triggers
          // scheduleReconnect() (sawNonLiveAttachRef = false for a live run),
          // showing a yellow "Reconnecting…" banner after every Stop click.
          // Mirrors the identical call in the pipeline_complete case above
          // (~line 597). Safe: the durable run_events are already persisted and
          // the chat transcript is already in state — unmounting the connection
          // does not remove any rendered content.
          if (cancelledId) detachRunRef.current?.(cancelledId);
        }
        setActivePipelineRunId(null);
        break;
      }

      case "step": {
        if (msg.data && "id" in msg.data && "status" in msg.data) {
          const stepData = msg.data as ProcessStep;
          setProcessSteps((prev) => {
            const existing = prev.findIndex((s) => s.id === stepData.id);
            let updated: ProcessStep[];
            if (existing >= 0) {
              updated = [...prev];
              updated[existing] = stepData;
            } else {
              updated = [...prev, stepData];
            }
            processStepsRef.current = updated;
            return updated;
          });
        }
        break;
      }
    }
  }, []);

  // ─── Phase 31/44 — the app-level SSE run connection (sole transport) ─────────
  // The pipeline / questionnaire / review down-channel is sourced from
  // runConnection.subscribe (below) and the chat transcript from chatSubscribe.
  // SSE + REST is the only transport (44-06 hard cutoff) — no WebSocket client.
  const runConnection = useRunConnection();

  // BUG-015 — keep the ref pointed at the live detachRun so the empty-deps
  // handleWebSocketMessage can release a completed run's focus without closing
  // over runConnection (mirrors the handlePipelineMsgRef / trackedRunIdRef idiom).
  useEffect(() => {
    detachRunRef.current = runConnection.detachRun;
  }, [runConnection.detachRun]);

  // The status/reconnect the header UI reflects, sourced from the SSE connection
  // phase; reconnect routes through the provider's server-derived reattach.
  const effectiveConnectionStatus: ConnectionStatus = phaseToConnectionStatus(
    runConnection.phase,
  );
  const effectiveReconnect = runConnection.reattach;

  // Workflow pipeline state
  const { pipelineState, startPipeline, resetPipeline, isRunning: isPipelineRunning, handleMessage: handlePipelineMsg, submitQuestionnaire, retainClarifyRound, retainAgentEdit } = useWorkflow();
  // KAN-98: store pending gate edits so review_gate_approved can apply them to
  // the live agent state (planAgent.output etc.) for the Thinking tab display.
  const pendingGateEditRef = useRef<{ agentId: string; editedContent: string } | null>(null);
  // Workstream C1 (POR §1 gap-2): retain the launched brief on the LIVE path
  // (previously dropped). Reopen/history use fullRun.input / selectedRun.input.
  const [submittedBrief, setSubmittedBrief] = useState<string>("");

  // ─── Per-run state store (FIX-201 / KAN-168 — concurrent run isolation) ──────
  // The store holds a PerRunState entry per run id. SSE handlers write to
  // store.update(sourceRunId, ...) — background runs store silently, the viewed
  // run also triggers React re-renders. store.switchViewTo(runId) atomically
  // projects the new run's state to the UI — no async gap, no race.
  const runStore = useRunStateStore();
  // Convenience: the viewed run's state (what the UI actually renders).
  // Non-contamination-prone fields (pipelineState, waveGroups) still go through
  // the existing useWorkflow / waveGroups path which is already gated by
  // isForeignFrame + isForActiveRun guards. The store covers the fields that were
  // not properly guarded: questionnaireData, reviewGateData, content, submittedBrief.
  const viewedRun = runStore.viewed;

  // FIX-201: stable ref to runStore.handleFrame so the zero-deps handleWebSocketMessage
  // useCallback can call it without closing over a stale runStore object.
  const runStoreHandleFrameRef = useRef(runStore.handleFrame);
  useEffect(() => {
    runStoreHandleFrameRef.current = runStore.handleFrame;
  }, [runStore.handleFrame]);

  const runStoreSwitchViewToRef = useRef(runStore.switchViewTo);
  useEffect(() => {
    runStoreSwitchViewToRef.current = runStore.switchViewTo;
  }, [runStore.switchViewTo]);

  // Keep pipeline handler ref in sync
  useEffect(() => {
    handlePipelineMsgRef.current = handlePipelineMsg;
  }, [handlePipelineMsg]);

  // KAN-101 — keep refs to the live agents list and the spec revision counter setter
  // so handleWebSocketMessage (a useCallback([])) can detect re-runs of already-done
  // agents and increment the counter without closing over stale state.
  const pipelineAgentsRef = useRef<import("@/types/index").AgentRunState[]>([]);
  useEffect(() => {
    pipelineAgentsRef.current = runStore.viewed.pipelineState.agents;
    const agents = runStore.viewed.pipelineState.agents;
    if (
      runStore.viewed.pipelineState.isRunning &&
      agents.length > 0 &&
      agents.every((a) => a.status === "done")
    ) {
      revisionCycleArmedRef.current = true;
    }
  }, [runStore.viewed.pipelineState.agents, runStore.viewed.pipelineState.isRunning]);
  const setSpecRevisionCountRef = useRef(setSpecRevisionCount);
  // Armed = true once all agents are "done" mid-run (ready to detect next cycle).
  // Flips to false when the first re-starting agent is detected → increments once.
  const revisionCycleArmedRef = useRef(false);

  // BUG-005 — keep `trackedRunIdRef` pointed at the run this tab is driving/viewing
  // so the pipeline_start reset (handleWebSocketMessage) can run-scope itself. Sync
  // from activePipelineRunId (clarify-paused run) ?? contentSourceRunId (viewed/
  // reopened run); keep the last id when BOTH go null (the building phase clears
  // both but the tab is still driving that run). DELIBERATELY excludes
  // pipelineState.pipelineRunId — useWorkflow.ts:243 adopts a foreign frame's
  // pipeline_run_id into it, so tracking it would hijack the id to the foreign run.
  useEffect(() => {
    trackedRunIdRef.current = activePipelineRunId ?? contentSourceRunId ?? trackedRunIdRef.current;
  }, [activePipelineRunId, contentSourceRunId]);

  // FIX-201: sync useWorkflow.pipelineState → store for the currently-viewed run.
  // This is the BRIDGE between useWorkflow (reliable React setState, always fires for
  // agent frames) and the store (projection layer for the UI).
  // ISOLATION: only sync when pipelineState.pipelineRunId EXACTLY matches:
  //   1. runStore.viewedRunId — the run on screen
  //   2. activelyBuildingRunIdRef — the run this tab is actively building
  // If either doesn't match (different run's state leaked into useWorkflow, or
  // user is watching a different run than is building), skip the sync.
  useEffect(() => {
    const runId = pipelineState.pipelineRunId;
    if (!runId) return;
    // Both guards: pipelineState must belong to exactly the run being viewed AND built
    if (runId !== activelyBuildingRunIdRef.current) return;
    if (runId !== runStore.viewedRunId) return;
    // Push into store — project fires automatically since runId === viewedRunIdRef
    runStore.updatePipelineState(runId, () => pipelineState);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineState]);

  // ─── Phase 31 (CHATUI-01/02/03) — live chat transcript + deep-link seam ──────

  // SSE is the LIVE pipeline down-channel. Feed the SAME handleWebSocketMessage
  // router (pipeline / wave / questionnaire / review-gate switch, which
  // dispatches to handlePipelineMsgRef) from the per-run SSE fan-out. The reducer
  // is idempotent by event_id. `runConnection.subscribe` is a stable provider
  // callback → no resubscribe churn.
  const runSubscribe = runConnection.subscribe;
  useEffect(() => {
    const unsubscribe = runSubscribe((m) =>
      // Forward the transport's source-run stamp so the router can run-scope the
      // per-agent frames (foreign-run bleed guard at the top of the handler).
      handleWebSocketMessage(
        { type: m.type, data: m.data } as unknown as StreamMessage,
        m._sourceRunId,
      ),
    );
    return unsubscribe;
  }, [runSubscribe, handleWebSocketMessage]);

  // The chat transcript frame subscription — the SSE per-run fan-out.
  // FIX-201 (KAN-168): filter frames by _sourceRunId so only frames from the
  // currently-viewed run (trackedRunIdRef) reach useRunChat. Without this filter,
  // chat_message/chat_reply frames from all concurrently-running SSE streams
  // (e.g. 4 active pipelines) get mixed into the transcript after a badge switch.
  // _sourceRunId is injected per-stream by RunConnectionProvider (onMessage prop).
  // Frames with no _sourceRunId (infra events, Concierge /messages) always pass through.
  const chatSubscribe = useCallback(
    (fn: (f: RunChatFrame) => void) => {
      return runConnection.subscribe((m) => {
        const srcRunId = (m as unknown as Record<string, unknown>)._sourceRunId as string | undefined;
        // If the frame carries a source run id and it does NOT match the currently
        // tracked/viewed run, discard it — it belongs to a different concurrent run.
        // trackedRunIdRef follows every run-switch path (handleSwitchToLiveRun,
        // handleSelectWorkflowRun, onStartPipeline), so it always holds the correct
        // viewed run id. Frames without _sourceRunId (e.g. Concierge /messages reply
        // streaming via sendCommand) are always allowed through.
        if (srcRunId && trackedRunIdRef.current && srcRunId !== trackedRunIdRef.current) {
          return;
        }
        fn({ type: m.type, data: (m.data as Record<string, unknown>) ?? {} });
      });
    },
    [runConnection],
  );

  const { messages: runChatMessages, sendMessage: sendRunChatMessage, addOptimisticMessage: addRunChatOptimisticMessage, replyStreaming: runChatReplyStreaming, seedTranscript: seedRunChatTranscript, appendFrames: appendRunChatFrames, getLastSeq: getRunChatLastSeq, proposals: runChatProposals, dismissProposal: dismissRunChatProposal } = useRunChat({
    // ISS-036: target the LIVE building run (pipelineRunId) so the REST command
    // path hits the in-flight run instead of null-then-fresh-POST; fall back to
    // the clarify-only activePipelineRunId when the build id is not yet set.
    // DEF-44-12-1: then fall back to the currently-VIEWED run (contentSourceRunId,
    // set on history/recents reopen) so a Concierge/steering/revision turn on an
    // opened terminal run posts to POST /{id}/messages — NOT the null->/api/runs
    // launch branch (which 422'd pre-fix). A live pipeline still wins the precedence.
    // FIX-201 (KAN-168): use store's viewed pipelineState.pipelineRunId so the
    // chat hook targets the correct run after a badge switch.
    runId: runStore.viewed.pipelineState.pipelineRunId ?? activePipelineRunId ?? contentSourceRunId,
    subscribe: chatSubscribe,
    // W1 (44-01): sendCommand resolves to the launched run_id (for
    // launch->attach); the chat up-channel ignores that value, so adapt it to the
    // Promise<void>-returning shape useRunChat expects.
    // BUG-017: AWAIT (not void) the POST so the hook's `await sendCommand(...)`
    // blocks until the reply is persisted — the DEF-44-12-2 re-fetch then lands
    // after chat_reply exists and the Concierge reply renders on a completed run.
    sendCommand: async (runId, payload) => {
      return runConnection.sendCommand(runId, payload);
    },
    // SSE + REST is the sole transport (44-06) — the up-channel is sendCommand;
    // there is no legacy WS send.
    legacyWsSend: undefined,
    // DEF-44-12-2 — after a send resolves, re-fetch the run's durable events so
    // the Concierge reply (persisted durable-only, never queued → the live SSE
    // tail never carries it) renders on an opened terminal/live run. The hook
    // folds the returned frames through handleFrame (idempotent by event_id).
    fetchEvents: (runId, afterSeq) =>
      getRunEvents(getToken() ?? "", runId ?? "", afterSeq),
  });

  // FIX-172: sync appendRunChatFramesRef after useRunChat so the empty-deps
  // handleWebSocketMessage can fold completion narrator cards without closing
  // over the live hook value. Must be AFTER the useRunChat call above.
  useEffect(() => {
    appendRunChatFramesRef.current = appendRunChatFrames;
  }, [appendRunChatFrames]);

  // FIX-176: sync getRunChatLastSeqRef so FIX-172 can fetch only new events.
  const getRunChatLastSeqRef = useRef<(() => number) | null>(null);
  useEffect(() => {
    getRunChatLastSeqRef.current = getRunChatLastSeq;
  }, [getRunChatLastSeq]);

  // The nonce'd deep-link seam (borrow #6): the lane's result cards call
  // requestOpenTab; PreviewPanel consumes the pending {tab, nonce} (all tabs).
  const runTabDeepLink = useTabDeepLink();

  // Fire a staged od_prototype run once the SSE connection is ready (idle maps
  // to "connected" — an idle app with no live run is still ready to launch over
  // REST). Re-reads from sessionStorage so a staged run survives a reload.
  useEffect(() => {
    if (effectiveConnectionStatus !== "connected") return;

    let pending = pendingOdProtoRef.current;
    if (!pending) {
      const flag = sessionStorage.getItem("od_prototype.pending");
      if (!flag) return;
      try {
        const draft = JSON.parse(sessionStorage.getItem("prototype.draft") ?? "{}") as {
          templateId?: string; designSystemId?: string; brief?: string;
          customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
          modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
          images?: { name: string; mime_type: string; data: string }[];
          agentIds?: string[];
        };
        const discovery = JSON.parse(sessionStorage.getItem("prototype.discovery") ?? "null");
        // KAN-87: templateId is now optional (no-template mode). Only require designSystemId + brief.
        if (!draft.designSystemId || !draft.brief) return;
        pending = {
          templateId: draft.templateId ?? "",  // empty string = no template
          designSystemId: draft.designSystemId,
          brief: draft.brief,
          discovery,
          customDsBody: draft.customDsBody,
          customTemplateBody: draft.customTemplateBody,
          sourceRunId: draft.sourceRunId,
          gateAgentIds: draft.gateAgentIds,
          modelOverrides: draft.modelOverrides,
          selections: draft.selections,
          images: draft.images,
          agentIds: draft.agentIds,
        };
      } catch { return; }
    }

    pendingOdProtoRef.current = null;
    sessionStorage.removeItem("od_prototype.pending");
    sessionStorage.removeItem("prototype.draft");    // FIX-005: clear stale draft so next fresh wizard open starts empty

    setUserStoryContent("");
    setPptContent("");
    setPrototypeContent("");
    pptContentRef.current = "";
    prototypeContentRef.current = "";
    userStoryContentRef.current = "";
    // Phase 2 (Universal Engine): skip the legacy generate_questions pre-flight.
    // The backend no longer handles that message type. The pipeline starts
    // immediately via run_pipeline; the Deep_Planner_Agent will emit
    // questionnaire_ready mid-run if clarification is needed.
    setPendingOdProtoParams({
      brief: pending.brief,
      templateId: pending.templateId,
      designSystemId: pending.designSystemId,
      discovery: pending.discovery,
      customDsBody: pending.customDsBody,
      customTemplateBody: pending.customTemplateBody,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pending.sourceRunId ? { sourceRunId: pending.sourceRunId } : {}),
      // Phase 6 (T5b): per-run gate selection.
      ...(pending.gateAgentIds !== undefined ? { gateAgentIds: pending.gateAgentIds } : {}),
      // Advanced agent config from wizard AgentsPopup
      ...(pending.modelOverrides && Object.keys(pending.modelOverrides).length > 0 ? { modelOverrides: pending.modelOverrides } : {}),
      ...(pending.selections && Object.keys(pending.selections).length > 0 ? { selections: pending.selections } : {}),
      ...(pending.agentIds && pending.agentIds.length > 0 ? { agentIds: pending.agentIds } : {}),
      ...(pending.images && pending.images.length > 0 ? { images: pending.images } : {}),
    });
  // effectiveConnectionStatus drives the re-run.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveConnectionStatus]);

  // Fire a staged od_ppt run once the SSE connection is ready (idle → connected).
  // Re-reads from sessionStorage so a staged run survives a reload.
  useEffect(() => {
    if (effectiveConnectionStatus !== "connected") return;

    // Try ref first, then fall back to sessionStorage (handles reconnects)
    let pending = pendingOdPptRef.current;
    if (!pending) {
      const flag = sessionStorage.getItem("od_ppt.pending");
      if (!flag) return;
      try {
        const draft = JSON.parse(sessionStorage.getItem("ppt.draft") ?? "{}") as {
          templateId?: string; designSystemId?: string | null; brief?: string;
          customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
          modelOverrides?: Record<string, string>; selections?: Record<string, Record<string, unknown>>;
          images?: { name: string; mime_type: string; data: string }[];
          agentIds?: string[];
        };
        if (!draft.templateId || !draft.brief) return;
        pending = {
          templateId: draft.templateId,
          designSystemId: draft.designSystemId ?? null,
          brief: draft.brief,
          discovery: null,
          customDsBody: draft.customDsBody,
          customTemplateBody: draft.customTemplateBody,
          sourceRunId: draft.sourceRunId,
          gateAgentIds: draft.gateAgentIds,
          modelOverrides: draft.modelOverrides,
          selections: draft.selections,
          images: draft.images,
          agentIds: draft.agentIds,
        };
      } catch { return; }
    }

    // Consume — clear both ref and sessionStorage key
    pendingOdPptRef.current = null;
    sessionStorage.removeItem("od_ppt.pending");
    sessionStorage.removeItem("ppt.draft");          // FIX-005: clear stale draft so next fresh wizard open starts empty

    setUserStoryContent("");
    setPptContent("");
    setPrototypeContent("");
    pptContentRef.current = "";
    prototypeContentRef.current = "";
    userStoryContentRef.current = "";
    // Phase 2 (Universal Engine): skip the legacy generate_questions pre-flight.
    // The backend no longer handles that message type. The pipeline starts
    // immediately via run_pipeline; the Deep_Planner_Agent will emit
    // questionnaire_ready mid-run if clarification is needed.
    setPendingOdPptParams({
      brief: pending.brief,
      templateId: pending.templateId,
      designSystemId: pending.designSystemId,
      discovery: pending.discovery,
      customDsBody: pending.customDsBody,
      customTemplateBody: pending.customTemplateBody,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pending.sourceRunId ? { sourceRunId: pending.sourceRunId } : {}),
      // Phase 6 (T5b): per-run gate selection.
      ...(pending.gateAgentIds !== undefined ? { gateAgentIds: pending.gateAgentIds } : {}),
      // Advanced agent config from wizard AgentsPopup
      ...(pending.modelOverrides && Object.keys(pending.modelOverrides).length > 0 ? { modelOverrides: pending.modelOverrides } : {}),
      ...(pending.selections && Object.keys(pending.selections).length > 0 ? { selections: pending.selections } : {}),
      ...(pending.agentIds && pending.agentIds.length > 0 ? { agentIds: pending.agentIds } : {}),
      ...(pending.images && pending.images.length > 0 ? { images: pending.images } : {}),
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveConnectionStatus]);

  // Select a chat session and load its messages
  const handleSelectChat = useCallback(
    async (chatId: string) => {
      setActiveChatId(chatId);
      setStreamingContent("");
      setIsStreaming(false);
      setProcessSteps([]);

      const currentToken = getToken();
      if (!currentToken) return;

      try {
        const chatDetail = await getChat(currentToken, chatId);
        const loadedMessages: ChatMessage[] = chatDetail.messages.map((m) => {
          let content = m.content;
          let steps: ProcessStep[] | undefined;

          const stepsMatch = content.match(/^<!--steps:(.*?)-->/);
          if (stepsMatch) {
            try {
              steps = JSON.parse(stepsMatch[1]);
            } catch { /* ignore parse errors */ }
            content = content.replace(/^<!--steps:.*?-->/, "");
          }

          return {
            id: m.id,
            chatSessionId: m.chat_session_id,
            role: m.role as "user" | "assistant" | "system",
            content,
            createdAt: m.created_at,
            steps,
          };
        });
        setMessages(loadedMessages);

        if (chatDetail.final_output) {
          try {
            const finalOutput = JSON.parse(chatDetail.final_output);
            if (finalOutput.user_stories) {
              setUserStoryContent(JSON.stringify(finalOutput.user_stories));
            }
            if (finalOutput.ppt) {
              setPptContent(JSON.stringify(finalOutput.ppt));
            }
            if (finalOutput.prototype) {
              setPrototypeContent(JSON.stringify(finalOutput.prototype));
            }
          } catch {
            // Ignore parse errors
          }
        } else {
          setUserStoryContent("");
          setPptContent("");
          setPrototypeContent("");
          setGenericDeliverable(undefined);
        }
      } catch (err) {
        console.error("Failed to load chat:", err);
      }
    },
    []
  );

  // FIX-149 (Bug 2 — KAN-132): switch to a LIVE running run WITHOUT resetting
  // pipeline state externally. This is used when the user clicks a running
  // badge/notification in the header — the run is live and must NOT call
  // handleSelectWorkflowRun which is a history-reopen that calls resetPipeline()
  // and wipes live Step traces / gate state / questionnaire state.
  //
  // Performs all operations needed to switch which run is "viewed":
  // - Registers in launchedRunIdsRef so isForeignFrame guard accepts replay frames.
  // - Updates trackedRunIdRef + activelyBuildingRunIdRef so pipeline reducer gates.
  // - Updates activePipelineRunId so useRunChat.runId targets the run immediately.
  // - Updates submittedBrief so Steps "Starting point" shows the correct brief.
  // - Clears questionnaireData so the old run's clarify UI disappears immediately
  //   (the durable replay pipeline_start will also clear it, but doing it here gives
  //   instant feedback before the async fetch resolves).
  // - Attaches the SSE stream for the run.
  // - Updates contentSourceRunId / contentSourceRunType so DashboardLayout routes.
  // - Replays all durable frames through handleWebSocketMessage (same as
  //   handleSelectWorkflowRun at page.tsx:1947) so questionnaire_ready / agent_*
  //   frames rebuild pipelineState and questionnaireData correctly (FIX-201).
  //   Using seedRunChatTranscript alone was wrong — it only handles chat frames,
  //   leaving questionnaire_ready and agent frames unprocessed.
  // - Seeds the chat transcript separately from the replayed chat frames so the
  //   left panel shows the correct conversation (FIX-201 / KAN-168).
  //
  // Does NOT call resetPipeline() or resetReplayState() externally — the durable
  // replay's pipeline_start fires the correct in-handler reset. (FIX-149)
  const handleSwitchToLiveRun = useCallback(
    async (runId: string) => {
      // Find the run's type and brief from recentRuns so we know the correct renderer.
      const run = recentRuns.find((r) => r.id === runId);

      // FIX-195 Fix-B — register in launchedRunIdsRef BEFORE attachRun so the
      // isForeignFrame guard lets this run's durable replay frames through to pipelineState.
      launchedRunIdsRef.current.add(runId);
      persistLaunchedIds();

      // Point tracking refs at the selected run.
      trackedRunIdRef.current = runId;
      activelyBuildingRunIdRef.current = runId;

      // FIX-201 (KAN-168): set activePipelineRunId synchronously so useRunChat.runId
      // targets the newly-switched run immediately (beats the stale pipelineState.pipelineRunId).
      setActivePipelineRunId(runId);

      // FIX-201 (KAN-168): update submittedBrief to the new run's brief so the
      // Steps panel "Starting point" card shows the correct brief immediately.
      // Mirrors handleSelectWorkflowRun at page.tsx:1884.
      if (run?.input) {
        const _switchParsed = parseRunInput(run.input);
        const _switchBrief = (_switchParsed.revisionInstruction ?? _switchParsed.brief ?? "").split("\n")[0].trim();
        setSubmittedBrief(_switchBrief || run.title || "");
      } else if (run?.title) {
        setSubmittedBrief(run.title);
      }

      // FIX-201 (KAN-168): switch the store viewport to the new run so it projects
      // the correct pipelineState (agents, waveGroups) to the UI immediately.
      // This is the key call that isolates concurrent run state.
      runStore.switchViewTo(runId);
      // The DashboardLayout now reads questionnaireData/reviewGateData from
      // runStore.viewed directly (not legacy React state), so no separate
      // setQuestionnaireData/setReviewGateData calls needed here.

      // Make the selected run the sticky SSE focus.
      runConnection.attachRun(runId);

      // Update the content-source so DashboardLayout and PreviewPanel use the
      // correct renderer (effectiveReviseType derives from contentSourceRunType).
      setContentSourceRunId(runId);
      if (run) setContentSourceRunType(run.type ?? null);

      // FIX-201 (KAN-168): fetch durable events and replay them through
      // handleWebSocketMessage — the same path handleSelectWorkflowRun uses
      // at page.tsx:1947. This is critical: seedRunChatTranscript alone only
      // handles chat frames (chat_message/chat_reply), leaving questionnaire_ready,
      // pipeline_start, and agent_* frames unprocessed. Without this, the Steps
      // panel shows "Run complete" (stale pipelineState) and no clarify questions
      // appear. With this replay, pipeline_start resets the reducer, questionnaire_ready
      // restores the clarify gate, and agent frames rebuild the agent list.
      const switchToken = getToken();
      if (switchToken) {
        try {
          const durableFrames = await getRunEvents(switchToken, runId);
          // Replay each frame through the full page router so questionnaire_ready,
          // pipeline_start, and agent_* update pipelineState and the per-run map.
          for (const frame of durableFrames) {
            handleWebSocketMessage(
              {
                type: frame.type,
                data: frame.data,
              } as unknown as StreamMessage,
              runId,
            );
          }
          // FIX-201: after durable replay, directly replay all pipeline frames
          // through the store (bypassing seenEventIdsRef dedup) so the store
          // gets the LATEST agent state. The durable replay via handleWebSocketMessage
          // above may have dropped agent_start/complete frames (already in
          // seenEventIdsRef from live SSE). The final switchViewTo below projects
          // the correct current state.
          // Skip pipeline_start in this pass if the store already has running agents
          // (live SSE already set them — pipeline_start would reset to idle).
          const existingEntry = runStore.get(runId);
          const hasLiveAgents = existingEntry?.pipelineState?.agents?.some(
            (a) => a.status !== "idle"
          ) ?? false;
          for (const frame of durableFrames) {
            if (frame.type === "pipeline_start" && hasLiveAgents) continue;
            runStoreHandleFrameRef.current(runId, { type: frame.type, ...(frame.data as Record<string, unknown> || {}) });
          }
          // Seed the chat transcript from the same frames so the left panel shows
          // the correct conversation (chat_message/chat_reply frames only).
          // seedRunChatTranscript resets the seen-set + messages then folds frames.
          seedRunChatTranscript(durableFrames, false);
          // After replay, the per-run store has the correct state. Project it to UI
          // (the store already projected during replay via runStore.update calls,
          // but we call switchViewTo again to ensure a clean final projection).
          runStore.switchViewTo(runId);
        } catch {
          // Non-fatal: pipelineState and transcript will populate via live SSE frames.
        }
      }
    },
    [recentRuns, runConnection, seedRunChatTranscript, handleWebSocketMessage],
  );

  // FIX-170: called by DashboardLayout's postRevision path when the REST revision
  // launch resolves to a run_id. Updates the 3 page-level routing refs that gate
  // ALL incoming SSE pipeline events so the revision run's frames are accepted
  // instead of discarded as "foreign". Also adds the run to launchedRunIdsRef
  // so the full isForeignFrame allow-list is consistent with a normal launch.
  // Mirrors the .then() block in the onStartPipeline handler exactly.
  const handleRevisionLaunched = useCallback(
    (runId: string) => {
      launchedRunIdsRef.current.add(runId);
      persistLaunchedIds();
      launchCounterRef.current += 1;
      trackedRunIdRef.current = runId;
      activelyBuildingRunIdRef.current = runId;
      // FIX-211: attach the SSE stream for the new child run so its pipeline_start
      // / agent frames arrive. Also switch the store viewport immediately so the UI
      // shows the new run rather than the parent. Without attachRun the child SSE
      // stream is never connected; without switchViewTo the UI stays on the old run.
      runStoreSwitchViewToRef.current(runId);
      runConnection.attachRun(runId);
    },
    // runConnection is stable (memo'd in RunConnectionProvider). All others are refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [runConnection],
  );

  // Handle selecting a workflow run from sidebar/hub
  const handleSelectWorkflowRun = useCallback(
    async (run: WorkflowRun) => {
      // FIX-201 (KAN-168): switch the store viewport to the selected run IMMEDIATELY
      // (synchronous, before any async work). This eliminates the 1-second flash
      // where the previous live run's agents were visible during the async gap
      // between click and durable replay completion. getOrCreate creates an empty
      // initial entry if the run hasn't been seen before — the empty state
      // (no agents, no questions) is better than showing a different run's data.
      runStoreSwitchViewToRef.current(run.id);

      // FIX-201 (KAN-168): set activelyBuildingRunIdRef SYNCHRONOUSLY so that
      // displayedPipelineState selects useWorkflow.pipelineState for this run
      // (condition: pipelineState.pipelineRunId === runStore.viewedRunId).
      // Without this, another run's live SSE frames could update useWorkflow's
      // pipelineState before the durable replay sets it, causing the condition
      // to fail and falling back to an empty store entry.
      activelyBuildingRunIdRef.current = run.id;
      trackedRunIdRef.current = run.id;

      // Clear existing content
      setUserStoryContent("");
      setPptContent("");
      setPrototypeContent("");
      setGenericDeliverable(undefined);
      // ISS-017 (16-04): reset the reopened-run failure signal until the run
      // detail loads — avoids a stale affordance leaking across reopens.
      setReopenedRunStatus(undefined);
      setReopenedFailedAgents(undefined);
      setReopenedAgentNameById(undefined);

      // Load the workflow output from backend
      const currentToken = getToken();
      if (!currentToken) return;

      try {
        const fullRun = await getWorkflow(currentToken, run.id);
        // Revision Families (B1): the history-reopen source — the reopened run is
        // now the on-screen content, so an inline revise from here links it as
        // parent.
        setContentSourceRunId(fullRun.id);
        // Claim the reopened run as the run THIS tab tracks, synchronously. The
        // `trackedRunIdRef` sync effect keys on the contentSourceRunId STATE, which
        // has not committed yet inside this callback — so without this the durable
        // replay below (and the reopened run's live tail) would still be measured
        // against the PREVIOUS run's id and its per-agent frames dropped as foreign.
        // Mirrors the launch path, which sets the ref synchronously too.
        trackedRunIdRef.current = fullRun.id;
        // BUG-013: make the VIEWED run the single sticky SSE focus so a parked /
        // building run streams live (multi-round clarify + resume→build) without
        // waiting on the next refreshLiveRuns poll. GATED on non-terminal — a
        // terminal run emits nothing, so focusing it would only pin a dead-stream
        // reconnect loop. A new focus replaces the prior (no stream accumulation).
        if (!REOPEN_TERMINAL_STATUSES.has(fullRun.status)) { runConnection.attachRun(fullRun.id); }
        // BUG-012: capture the viewed run's REAL type so the PreviewPanel render
        // dispatch keys on it (durable, independent of the recents window).
        setContentSourceRunType(fullRun.type ?? null);

        // DEF-44-12-4 (Piece 1) — bind the run-screen LIVE state (the Steps
        // pipeline trace) to the run being VIEWED, not only the run launched
        // in-session. `handleSelectWorkflowRun` sets contentSourceRunId (drives
        // Preview/Files) but never seeded the pipeline reducer, so a history-
        // opened run showed the empty "Start a pipeline…" placeholder. Seed it
        // from the durable run_events — but ONLY when the opened run differs from
        // the live launched run: re-seeding the launched run would replay-from-0
        // over live progress and wipe gate/questionnaire state (page.tsx pipeline_start
        // reset side effects). The same fetched frames feed Piece 3's transcript seed.
        // FIX-201 (KAN-168): always replay for store population. The old condition
        // skipped replay when fullRun.id === runStore.viewed.pipelineState.pipelineRunId
        // (same run was previously opened). This left the store with stale state from
        // the previous visit instead of fresh durable events. Use pipelineState
        // (useWorkflow's actively-building run) as the comparison to skip only when
        // this is TRULY the current live build (not just a cached store entry).
        if (fullRun.id !== pipelineState.pipelineRunId) {
          // Wire the VIEWED run's brief into the Steps surface (runInput=submittedBrief
          // via DashboardLayout) so AgentThinkingTab's hasAnyData gate + header reflect
          // the opened run, not a stale launched brief.
          // FIX-130: parse the raw input to extract the clean brief — never store
          // the full marker-laden input as the displayed title.
          const _reopenParsed = parseRunInput(fullRun.input ?? "");
          const _reopenBrief = (_reopenParsed.revisionInstruction ?? _reopenParsed.brief ?? "").split("\n")[0].trim();
          setSubmittedBrief(_reopenBrief || fullRun.title || "");
          try {
            // Reset the per-run FE replay state (seen-set / seq cursor / wave groups)
            // and the reducer's agents[] so the prior run's state does not poison the
            // new view (mirrors the launch path's pipeline_start reset + startPipeline).
            resetReplayState({
              seen: seenEventIdsRef.current,
              setLastSeq: (n) => {
                lastSeqRef.current = n;
              },
              setWaveGroups,
            });
            resetPipeline();
            // KAN-125: register this reopened run as locally-known so the
            // isForeignFrame guard (in handleWebSocketMessage) lets its durable
            // events pass through to pipelineState. Without this, a run opened
            // from history that was NOT launched in this session would be blocked
            // because launchedRunIdsRef doesn't contain its id.
            launchedRunIdsRef.current.add(fullRun.id);
            // KAN-125 MULTI-TAB FIX — persist to sessionStorage so the set
            // survives a same-tab page refresh.
            persistLaunchedIds();
            // Also set trackedRunIdRef so the questionnaire/review gate guards
            // correctly scope to the viewed run.
            trackedRunIdRef.current = fullRun.id;
            // KAN-125 FIX — also update activelyBuildingRunIdRef so the reducer
            // gate in handleWebSocketMessage routes the durable frames (and any
            // subsequent live frames for a non-terminal run) to pipelineState.
            activelyBuildingRunIdRef.current = fullRun.id;
            // Fetch the durable events and replay each through the PAGE ROUTER
            // (handleWebSocketMessage), NOT the bare reducer — so each event_id lands
            // in seenEventIdsRef and the subsequently-attached live SSE tail is deduped
            // (idempotent, no double-count). pipeline_start rebuilds agents[]; the
            // agent_* frames then fill it. Works for a live-opened run (durable seed +
            // live tail continues) and a terminal-opened run (seed is the whole trace).
            const durableFrames = await getRunEvents(currentToken, fullRun.id);
            for (const frame of durableFrames) {
              // These frames all belong to the run being REOPENED — pass its id so
              // the foreign-run guard adopts them (trackedRunIdRef was already
              // pointed at fullRun.id synchronously above; the contentSourceRunId
              // state sync only lands after this callback returns).
              handleWebSocketMessage(
                {
                  type: frame.type,
                  data: frame.data,
                } as unknown as StreamMessage,
                fullRun.id,
              );
            }
            // KAN-154 (Gap 1): family-aware chat seed — also fetch chat_reply rows
            // from the run's revision family so the transcript shows the full history
            // of all versions, not just the selected run. getRunFamily returns members
            // ordered by created_at (root first); we fetch each PRIOR member's events
            // and seed only the chat frames. Best-effort: any per-member fetch failure
            // is tolerated so the primary run's seed is never blocked.
            // DEF-44-12-4 (Piece 3) — seed the prior chat turns. For the PRIMARY run
            // we reuse the already-fetched durableFrames (no second fetch). Family
            // members are fetched cheaply in parallel; their events are merged
            // chronologically by family order before seeding so the transcript reads
            // in the correct run-creation order.
            let familyChatFrames = [...durableFrames];
            try {
              const family = await getRunFamily(currentToken, fullRun.id);
              // family.members is ordered by created_at ASC (root first, then
              // revisions in chronological order). fullRun.id is already covered
              // by durableFrames — fetch the OTHER members only.
              const otherMembers = (family?.members ?? []).filter(
                (m: { id: string }) => m.id !== fullRun.id,
              );
              if (otherMembers.length > 0) {
                const memberFrameArrays = await Promise.allSettled(
                  otherMembers.map((m: { id: string }) =>
                    getRunEvents(currentToken, m.id),
                  ),
                );
                // FIX-174: build an ordered map: family member id → its chat frames.
                // family.members is created_at ASC so we can reconstruct the correct
                // chronological order across runs. We MUST NOT sort by raw `seq`
                // values here because seq is per-run-scoped (each run starts at 1),
                // so a revision run's seq 1 would sort before the parent run's
                // seq 200, placing "Revision started" at the top of the transcript.
                const memberFramesByMemberId = new Map<string, (typeof durableFrames)>();
                otherMembers.forEach((m, i) => {
                  const result = memberFrameArrays[i];
                  if (result.status === "fulfilled") {
                    // Keep only chat frames — pipeline reducer frames for other members
                    // are intentionally excluded (they'd overwrite pipelineState which
                    // should reflect the OPENED run, not every family member's agents).
                    memberFramesByMemberId.set(
                      m.id,
                      result.value.filter(
                        (f) => f.type === "chat_message" || f.type === "chat_reply",
                      ),
                    );
                  }
                });

                // Build the ordered transcript: interleave runs in the family's
                // chronological order (family.members is created_at ASC). For each
                // family member that is NOT the currently-opened run, append its chat
                // frames in their own within-run seq order. The opened run's frames
                // (durableFrames) are included as non-chat + chat — they anchor the
                // pipeline state seed. We place each member's frames relative to the
                // opened run by family position.
                //
                // Strategy: determine where fullRun.id sits in the ordered members
                // list; prepend earlier members' frames and append later members'
                // frames around the primary run's frames.
                const allMemberIds = (family?.members ?? []).map(
                  (m: { id: string }) => m.id,
                );
                const openedRunIndex = allMemberIds.indexOf(fullRun.id);

                // Frames from members BEFORE the opened run (earlier in time) go first
                const priorChatFrames: (typeof durableFrames) = [];
                for (let i = 0; i < openedRunIndex; i++) {
                  const mid = allMemberIds[i];
                  const mFrames = memberFramesByMemberId.get(mid);
                  if (mFrames) priorChatFrames.push(...mFrames);
                }
                // Frames from members AFTER the opened run (later in time) go last
                const laterChatFrames: (typeof durableFrames) = [];
                for (let i = openedRunIndex + 1; i < allMemberIds.length; i++) {
                  const mid = allMemberIds[i];
                  const mFrames = memberFramesByMemberId.get(mid);
                  if (mFrames) laterChatFrames.push(...mFrames);
                }

                // Final order: earlier-run chats → opened run's full frames (pipeline
                // seed + chat) → later-run chats. This preserves chronological order
                // across the family without mixing per-run seq numbers.
                familyChatFrames = [
                  ...priorChatFrames,
                  ...durableFrames,
                  ...laterChatFrames,
                ];
              }
            } catch {
              // Family fetch failed — fall back to single-run transcript (no crash).
              familyChatFrames = [...durableFrames];
            }
            // seedTranscript resets the hook's seen-set + seq cursor so the
            // re-fetch-after-send (DEF-44-12-2) pulls only newer events.
            // Pass isTerminalRun=true for completed/failed/cancelled/degraded runs so
            // gate chat_reply cards are auto-resolved (no pending review box).
            seedRunChatTranscript(familyChatFrames, REOPEN_TERMINAL_STATUSES.has(fullRun.status));
            // FIX-201 (KAN-168): switch the store viewport to the reopened run so
            // its pipelineState (agents, progress) renders correctly. Without this,
            // the store still projects whichever live run was previously viewed —
            // Jump Back In / Run History selections always showed the live run's agents.
            runStoreSwitchViewToRef.current(fullRun.id);
          } catch (seedErr) {
            // Log-and-continue: a seed fetch failure must not break the reopen
            // content path already set above.
            console.error("Failed to seed run trace on open:", seedErr);
          }
        }

        // WR-01 (16 review): "degraded" is a terminal status ISS-016 now persists
        // for partially-failed runs — it carries a real (partial) deliverable. Treat
        // it like "completed" for content so the partial deliverable still renders on
        // the history-reopen path (it previously fell through to the neutral empty
        // state). Keyed on the generic server status field, never a workflow name.
        const isContentTerminal =
          fullRun.status === "completed" || fullRun.status === "degraded";
        if (fullRun.output && isContentTerminal) {
          if (fullRun.type === "user_stories" || fullRun.type === "user_stories_revision") {
            setUserStoryContent(fullRun.output);
          } else if (fullRun.type === "ppt" || fullRun.type === "ppt_revision" || fullRun.type === "od_ppt" || fullRun.type === "od_ppt_revision") {
            setPptContent(fullRun.output);
          } else if (fullRun.type === "prototype" || fullRun.type === "prototype_revision" || fullRun.type === "od_prototype") {
            setPrototypeContent(fullRun.output);
          } else {
            // ISS-021 (18-03) / UXFIX-02 (22-03) — generic reopen fallback.
            // Prefer the PERSISTED deliverable_mimetype on the run row (22-03
            // backend) so a binary deliverable (e.g. application/zip) re-renders
            // faithfully; fall back to the SHARED deriveDeliverableMimetype text
            // heuristic ONLY for legacy NULL rows — the IDENTICAL resolution
            // WorkflowHistory.tsx applies (resolveReopenMimetype), so the two
            // reopen surfaces cannot diverge. Structural "no known branch" else;
            // never a workflow-name check (SC-001).
            setGenericDeliverable({
              mimetype: resolveReopenMimetype(
                fullRun.deliverableMimetype,
                fullRun.output,
              ),
              filename: fullRun.deliverableFilename,
              content: fullRun.output,
            });
          }
        }

        // ISS-017 (16-04) + WR-01 (16 review): a reopened run that ended
        // failed/cancelled/degraded WITH no content sets no content (unchanged
        // above) — thread its persisted server status down so PreviewPanel shows the
        // terminal-empty degraded/failed affordance on the history path. This keys on
        // the SERVER status, not a client empty guess. "degraded" is included so a
        // degraded run with NO partial deliverable still surfaces the affordance
        // rather than the neutral empty-state (CONTEXT A2: affordance on BOTH the live
        // and history paths). A completed (success) reopen clears the signal.
        setReopenedRunStatus(
          fullRun.status === "failed" ||
            fullRun.status === "cancelled" ||
            fullRun.status === "degraded"
            ? fullRun.status
            : undefined,
        );

        // IN-01 (16 review): wire the reopened run's failed-agent list so the
        // affordance lists the real agents (not an empty list). The backend persists
        // it into wr.error as "...agent(s) failed: <id1>, <id2>" for a degraded run
        // (websocket.py); parse those ids when present so the history-reopen
        // affordance matches the live path. Server-keyed; no client guess.
        setReopenedFailedAgents(parseFailedAgentIds(fullRun.error));
        // ISS-024 (16 review IN-02): build the id→name lookup for those failed
        // agents from the reopened run detail's persisted agentOutputs
        // ({agent_id,name}) so PreviewPanel's affordance shows human names. Unknown
        // ids fall back to the raw id inside DegradedRunAffordance (never blank).
        setReopenedAgentNameById(
          buildAgentNameById(
            (fullRun.agentOutputs || []).map((a) => ({ id: a.agent_id, name: a.name })),
          ),
        );
      } catch (err) {
        console.error("Failed to load workflow output:", err);
      }
    },
    // DEF-44-12-4 — the closure now reads pipelineState.pipelineRunId and calls
    // resetPipeline/setWaveGroups/handleWebSocketMessage/setSubmittedBrief, so
    // they MUST be deps (refs seenEventIdsRef/lastSeqRef are stable, omitted).
    // BUG-013: handleSelectWorkflowRun now calls runConnection.attachRun on reopen.
    [runStore.viewed.pipelineState.pipelineRunId, resetPipeline, setWaveGroups, handleWebSocketMessage, setSubmittedBrief, seedRunChatTranscript, runConnection]
  );

  // Handle new chat creation from sidebar
  const handleNewChat = useCallback((chatSession: ChatSession) => {
    setActiveChatId(chatSession.id);
    setMessages([]);
    setStreamingContent("");
    setIsStreaming(false);
    setUserStoryContent("");
    setPptContent("");
    setPrototypeContent("");
    setGenericDeliverable(undefined);
  }, []);

  // Handle deleting a chat session
  const handleDeleteChat = useCallback(
    async (chatId: string) => {
      const currentToken = getToken();
      if (!currentToken) return;

      try {
        await deleteChat(currentToken, chatId);
      } catch (err) {
        console.error("Failed to delete chat:", err);
      }

      if (chatId === activeChatId) {
        setActiveChatId(null);
        setMessages([]);
        setStreamingContent("");
        setIsStreaming(false);
        setUserStoryContent("");
        setPptContent("");
        setPrototypeContent("");
        setGenericDeliverable(undefined);
      }
    },
    [activeChatId]
  );

  // Handle logout: revoke the JWT on the backend, then drop it locally and
  // redirect. We await the logout call so the token is reliably revoked
  // before navigation — fire-and-forget would be at the mercy of the page
  // unload aborting the request. logout() swallows network errors and always
  // clears the local token in its finally block, so navigation is safe even
  // if the backend is unreachable.
  const handleLogout = useCallback(async () => {
    await logout(getToken() ?? "");
    router.replace("/login");
  }, [router]);

  if (!mounted || !isAuthenticated) {
    // Return null (not a loading screen) until the client has hydrated and
    // confirmed auth. This avoids both the hydration mismatch (server renders
    // null, client renders null — they match) and the black flash.
    return null;
  }

  // FIX-201 (KAN-168): use runStore.viewed.pipelineState as the single source of truth.
  // The store's handleFrame always populates map[runId].pipelineState correctly for
  // every SSE frame. switchViewTo(runId) projects the correct run's state to the UI.
  // For live progress: pipeline_start early-registration calls switchViewTo immediately
  // so all subsequent agent frames project to the viewed state in real-time.
  const displayedPipelineState = runStore.viewed.pipelineState;

  // Build a per-run agents-completed map from the run store so AppHeader can show
  // live progress for ALL concurrent background runs (not just the viewed one).
  // The store receives agent_complete SSE frames for every attached run via
  // runStore.handleFrame, so completedCount is accurate for all of them.
  // SC-001: keyed on run ids (generic), never workflow-name literals.
  const runAgentsCompletedMap: Record<string, number> = {};
  for (const run of recentRuns) {
    const entry = runStore.get(run.id);
    if (entry) {
      runAgentsCompletedMap[run.id] = entry.pipelineState.completedCount;
    }
  }

  return (
    <DashboardLayout
      activeChatId={activeChatId}
      messages={messages}
      isStreaming={isStreaming}
      streamingContent={streamingContent}
      userStoryContent={userStoryContent}
      pptContent={pptContent}
      prototypeContent={prototypeContent}
      genericDeliverable={genericDeliverable}
      connectionStatus={effectiveConnectionStatus}
      onSelectChat={handleSelectChat}
      onNewChat={handleNewChat}
      onDeleteChat={handleDeleteChat}
      onLogout={handleLogout}
      onReconnect={effectiveReconnect}
      messageMode={currentMode}
      chatTitleUpdate={chatTitleUpdate}
      processSteps={processSteps}
      // FIX-201 (KAN-168): use the correct pipelineState for the viewed run.
      // - activelyBuildingRunIdRef = the run this tab is currently building/watching
      // - pipelineState (useWorkflow) = updated by React setState, always correct for the active run
      // - runStore.viewed.pipelineState = populated from durable replay for history/reopened runs
      // Pick useWorkflow when the viewed run IS the active run; store when it's a history run.
      pipelineState={displayedPipelineState}
      reopenedRunStatus={reopenedRunStatus}
      reopenedFailedAgents={reopenedFailedAgents}
      reopenedAgentNameById={reopenedAgentNameById}
      submittedBrief={submittedBrief}
      // KAN-101 — spec revision cycle counter, incremented when update_specs fires
      // and the specify→plan→analyze sub-pipeline re-runs. Reset per new run.
      specRevisionCount={specRevisionCount}
      // Phase 31 (CHATUI-01/02/03) — the family-anchored transcript + the
      // transport-agnostic send, plus the nonce'd deep-link seam. The lane
      // (mounted in DashboardLayout) consumes messages/send/requestOpenTab;
      // PreviewPanel consumes the pending deep-link target for all tabs.
      runChatMessages={runChatMessages}
      runChatReplyStreaming={runChatReplyStreaming}
      runChatProposals={runChatProposals}
      onDismissRunChatProposal={dismissRunChatProposal}
      onRunChatSend={sendRunChatMessage}
      addOptimisticMessage={addRunChatOptimisticMessage}
      onRevisionLaunched={handleRevisionLaunched}
      onRequestOpenTab={runTabDeepLink.requestOpenTab}
      deepLinkTarget={runTabDeepLink.pending}
      onStartPipeline={(type, message, agentIds, attachedSkills, attachedHooks, extraParams) => {
        const isRevision = type.endsWith("_revision");
        // Workstream C1 (POR §1 gap-2): capture the run's input on every launch
        // (revision or fresh — it is the run's input either way), reset per run.
        // KAN-116 (Bug 3): prefer the explicit _display_title from extraParams (set
        // by DashboardLayout chain/revision handlers with the already-clean brief),
        // fall back to parseRunInput for other callers. This avoids re-parsing
        // complex nested context blocks that can defeat the regex.
        const _displayTitle = extraParams?._display_title as string | undefined;
        let _cleanBrief: string;
        if (_displayTitle && _displayTitle.trim()) {
          _cleanBrief = _displayTitle.trim();
        } else {
          const _parsed = parseRunInput(message);
          // FIX-130: if the message is dominated by context/marker blocks (brief=""),
          // pull "Original Brief:" from inside the context block rather than
          // falling back to the raw message (which would show the full blob).
          const _rawBrief = (_parsed.revisionInstruction ?? _parsed.brief ?? "").trim();
          if (_rawBrief) {
            _cleanBrief = _rawBrief;
          } else if (_parsed.chainContext) {
            // The whole message was a context block — extract the Original Brief line
            const _origBriefMatch = _parsed.chainContext.match(/Original Brief:\s*(.+)/);
            _cleanBrief = _origBriefMatch ? _origBriefMatch[1].split("\n")[0].trim() : "";
          } else {
            _cleanBrief = "";
          }
        }
        // Never store the raw message as the displayed title — it may be a full
        // context blob. Fall back to "Untitled" rather than polluting the title.
        setSubmittedBrief(_cleanBrief || "");
        // ISS-017 (16-04): any new run clears the history-reopen failure signal
        // so a prior failed reopen never bleeds the affordance into a live run.
        setReopenedRunStatus(undefined);
        setReopenedFailedAgents(undefined);
        setReopenedAgentNameById(undefined);
        if (!isRevision) {
          // Fresh run — clear previous preview content
          setUserStoryContent("");
          setPptContent("");
          setPrototypeContent("");
          setGenericDeliverable(undefined);
          pptContentRef.current = "";
          prototypeContentRef.current = "";
          userStoryContentRef.current = "";
          // Revision Families (B1): a fresh run has no source until it completes —
          // clear so a stale source can't be sent as a revise parent.
          setContentSourceRunId(null);
          // BUG-012: a fresh run has no viewed type yet — clear so a stale
          // reopened type can't misroute the fresh run's live deliverable.
          setContentSourceRunType(null);
          // BUG-021: a fresh run starts a NEW conversation — clear the last-viewed
          // run's transcript so its turns don't bleed into the new run's chat lane
          // (the new run's frames fold into the empty transcript via handleFrame as
          // they stream). Reuses the seedTranscript reset primitive with []; the
          // history-open seed at :1336 (durableFrames) is untouched.
          seedRunChatTranscript([]);
          // FIX-201 (KAN-168): mark the launch window. While launchPendingRef=true,
          // the isForActiveRun guard blocks all frames whose _sourceRunId does NOT
          // match the previous tracked run (stale) OR the new run (not yet known).
          // The .then() block clears this flag once the new run id is registered.
          launchPendingRef.current = true;
        }
        // For revisions, keep existing content visible until new output arrives.
        // W1 (44-01) launch->attach (R4): the SSE launch (POST /api/runs) resolves
        // to the created run_id; attach its SSE stream immediately so a run
        // launched after boot streams live without waiting for the next
        // refreshLiveRuns poll. The WS path returns null synchronously (attachRun
        // no-op) — Promise.resolve normalizes both shapes.
        //
        // KAN-125 LAUNCH-ORDER FIX — capture the launch counter BEFORE the async
        // POST fires so that if two runs are launched in quick succession, the
        // .then() that resolves LATER (out of click order) does NOT overwrite
        // activelyBuildingRunIdRef with the earlier-clicked run's ID.
        launchCounterRef.current += 1;
        const thisLaunchSeq = launchCounterRef.current;
        void Promise.resolve(
          startPipeline(type, message, agentIds, attachedSkills, attachedHooks, extraParams),
        ).then((launchedRunId) => {
          if (launchedRunId) {
            runConnection.attachRun(launchedRunId);
            // KAN-125 — register this run as locally-launched so isForeignFrame
            // allows events from ALL runs started in this tab, not just the most
            // recent one. Prevents blocking pipeline_start / agent_complete events
            // from a run launched while another run was still setting up.
            launchedRunIdsRef.current.add(launchedRunId);
            // KAN-125 MULTI-TAB FIX — persist to sessionStorage so the set survives
            // a same-tab page refresh. New browser tabs start with an empty set
            // (fresh sessionStorage) so they don't treat background runs as local.
            persistLaunchedIds();
            // KAN-125 LAUNCH-ORDER FIX — only update the critical routing refs if
            // this is STILL the most recently clicked launch (launchCounterRef
            // advances on each new click, so an out-of-order .then() that fires
            // after a newer launch was already registered is safely ignored).
            // BUG-005: trackedRunIdRef must point to the LATEST launched run so
            // pipeline_start from that run doesn't get treated as foreign.
            // KAN-125: activelyBuildingRunIdRef gates the pipelineState reducer to
            // only the latest run's frames.
            if (thisLaunchSeq === launchCounterRef.current) {
              trackedRunIdRef.current = launchedRunId;
              activelyBuildingRunIdRef.current = launchedRunId;
              // FIX-201: switch the store viewport to the new run so it starts
              // receiving agent/pipeline frames as the viewed run.
              runStoreSwitchViewToRef.current(launchedRunId);
            }
            // FIX-201 (KAN-168): clear the launch-pending sentinel so the
            // isForActiveRun guard resumes normal per-run filtering.
            launchPendingRef.current = false;
            // FIX-195 Fix-A — ISS-061: refresh recentRuns so the newly-launched run
            // appears in the header badge/dropdown immediately. Without this refresh
            // the snapshot stays stale until a run finishes (pipeline_complete) and
            // the badge lists only runs that were already live at page load.
            const freshToken = getToken();
            if (freshToken) {
              getWorkflows(freshToken, { limit: 50 })
                .then(({ runs }) => setRecentRuns(runs))
                .catch(() => {/* best-effort — stale list is recoverable on next terminal event */});
            }
          }
          // Always clear launchPendingRef regardless of whether we got a run id
          // (failure case — launch failed or returned no id).
          else { launchPendingRef.current = false; }
        });
      }}
      onResetPipeline={resetPipeline}
      recentRuns={recentRuns}
      homeWorkflows={homeWorkflows}
      runAgentsCompletedMap={runAgentsCompletedMap}
      contentSourceRunId={contentSourceRunId}
      backgroundCompletedRunId={backgroundCompletedRunId}
      backgroundStartedRunId={backgroundStartedRunId}
      contentSourceRunType={contentSourceRunType}
      onSelectWorkflowRun={handleSelectWorkflowRun}
      onSwitchToLiveRun={handleSwitchToLiveRun}
      // FIX-201 (KAN-168): read questionnaireData and reviewGateData from the
      // per-run store (runStore.viewed) instead of the legacy shared React state.
      // This ensures Jump Back In / Run History open the correct run's clarify
      // questions and review gates — the store is keyed per-run and switched
      // atomically by switchViewTo(). The legacy state was shared across all
      // concurrent runs and only updated after the async durable replay.
      questionnaireData={runStore.viewed.questionnaireData}
      activePipelineRunId={runStore.viewed.activePipelineRunId ?? activePipelineRunId}
      lastCancelledRunId={lastCancelledRunId}
      onSubmitQuestionnaire={submitQuestionnaire}
      onRetainClarifyRound={retainClarifyRound}
      reviewGateData={runStore.viewed.reviewGateData}
      onApproveReview={(gateKey, editedContent) => {
        // Use store's viewed reviewGateData so gate actions target the correct run
        // regardless of which run was last active (FIX-201 / KAN-168).
        const activeGate = runStore.viewed.reviewGateData;
        if (editedContent && activeGate) {
          pendingGateEditRef.current = { agentId: activeGate.agentId, editedContent };
        }
        void postGate(getToken() ?? "", activeGate?.pipelineRunId ?? "", {
          gate_key: gateKey,
          action: "approve",
          approved: true,
          edited_content: editedContent ?? null,
        }).catch((e) => console.error("postGate approve failed", e));
        setReviewGateData(null);
        if (activeGate?.pipelineRunId) runStore.update(activeGate.pipelineRunId, { reviewGateData: null });
      }}
      onRejectReview={(gateKey) => {
        const activeGate = runStore.viewed.reviewGateData;
        void postGate(getToken() ?? "", activeGate?.pipelineRunId ?? "", {
          gate_key: gateKey,
          action: "reject",
          approved: false,
        }).catch((e) => console.error("postGate reject failed", e));
        setReviewGateData(null);
        if (activeGate?.pipelineRunId) runStore.update(activeGate.pipelineRunId, { reviewGateData: null });
      }}
      onRedoReview={(gateKey, instructions) => {
        const activeGate = runStore.viewed.reviewGateData;
        void postGate(getToken() ?? "", activeGate?.pipelineRunId ?? "", {
          gate_key: gateKey,
          action: "redo",
          instructions,
        }).catch((e) => console.error("postGate redo failed", e));
        setReviewGateData(null);
        if (activeGate?.pipelineRunId) runStore.update(activeGate.pipelineRunId, { reviewGateData: null });
      }}
      onUpdateSpecsReview={(gateKey, analysisReport) => {
        const activeGate = runStore.viewed.reviewGateData;
        void postGate(getToken() ?? "", activeGate?.pipelineRunId ?? "", {
          gate_key: gateKey,
          action: "update_specs",
          analysis_report: analysisReport,
        }).catch((e) => console.error("postGate update_specs failed", e));
        setReviewGateData(null);
        if (activeGate?.pipelineRunId) runStore.update(activeGate.pipelineRunId, { reviewGateData: null });
      }}
      pendingOdProtoParams={pendingOdProtoParams}
      onClearPendingOdProto={() => setPendingOdProtoParams(null)}
      pendingOdPptParams={pendingOdPptParams}
      onClearPendingOdPpt={() => setPendingOdPptParams(null)}
      userTier={user?.tier ?? "basic"}
      userEmail={user?.email}
      waves={runStore.viewed.waveGroups}
    />
  );
}
