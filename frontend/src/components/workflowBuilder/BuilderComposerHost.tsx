"use client";

/**
 * BuilderComposerHost: the AI Workflow Builder's seam into the Composer
 * (design 3.10.1 to 3.10.7).
 *
 * It owns the panel reducer, the Session_Stream hook and the REST calls, and
 * renders `ComposerPage` with every prop it was given plus `builder` and
 * `builderPanel`. The Composer opens no stream; it receives drafts, the
 * running-turn flag and the AI button through the binding, and only places the
 * panel element this host renders (under its header, left of the canvas).
 *
 * The AI button opens and closes the panel; there is no popup. With no
 * conversation yet the panel shows its empty state (examples, recent
 * conversations), and the first message creates the session: in edit mode on
 * `/workflows/{id}/edit`, so the open workflow stays on the canvas.
 *
 * Availability (Req 1.1, 1.2, 2.1 to 2.3): the controls exist only when
 * `canRunPipeline(tier, "custom")` is true and `GET /models` answered 200. In
 * every other case the binding and the panel are absent and the tree is
 * `ComposerPage` alone, inside two `display: contents` wrappers that add no box.
 * The wrappers are always there so the Composer keeps its place in the tree, and
 * its state, when the profile or the model list arrives after the first render.
 *
 * `useSearchParams` is read in a tiny child inside `<Suspense>`, as the Next.js
 * docs require for a prerendered route, so a missing search-params value can
 * never suspend the Composer itself.
 */

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ComponentProps,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ComposerPage } from "@/components/workflow/composer/ComposerPage";
import { useBuilderModelPicker } from "@/hooks/useBuilderModelPicker";
import { useBuilderSessionList } from "@/hooks/useBuilderSessionList";
import { useBuilderSessionStream } from "@/hooks/useBuilderSessionStream";
import { ApiError, getToken, getUserWorkflows } from "@/lib/api";
import { canRunPipeline, type Tier } from "@/lib/entitlements";
import { markShallowNavTo } from "@/lib/shallowNavGuard";
import {
  cancelTurn,
  createSession,
  getSession,
  linkSession,
  newClientMessageId,
  retryTurn,
  sendMessage,
  undoLastChange,
} from "@/lib/workflowBuilderApi";
import type { WorkflowManifest } from "@/types/index";
import type {
  BuilderEvent,
  ComposerBuilderBinding,
  CreateSessionRequest,
  SessionDetail,
} from "@/types/workflowBuilder";

import { BuilderEmptyState } from "./BuilderEmptyState";
import { BuilderInput } from "./BuilderInput";
import { BuilderLiveRegion } from "./BuilderLiveRegion";
import { BuilderModelPicker } from "./BuilderModelPicker";
import { BUILDER_PANEL_ID, BuilderPanel } from "./BuilderPanel";
import { BuilderTranscript } from "./BuilderTranscript";
import {
  clearNewConversationPending,
  isNewConversationPending,
  markNewConversationPending,
  recallPickerChoice,
  rememberPickerChoice,
  stashFirstMessage,
  takeFirstMessage,
} from "./builderHandoff";
import {
  decideDraft,
  isBuilderRoute,
  linkedBaseIsCustom,
  manifestFingerprint,
  parseEditWorkflowId,
  retryTurnId,
  searchWithAi,
  sessionIdOf,
  sessionRoutePath,
} from "./builderHostLogic";
import {
  INITIAL_BUILDER_STATE,
  builderReducer,
  type BuilderState,
  type CanvasDraft,
} from "./builderReducer";
import { useFollowScroll } from "./useFollowScroll";

// --- Props ---------------------------------------------------------------------------

type ComposerPageProps = ComponentProps<typeof ComposerPage>;

export type BuilderComposerHostProps = Omit<ComposerPageProps, "builder" | "builderPanel"> & {
  /** The user's plan; `null` until the profile loads. Decides the Custom_Entitlement. */
  tier: Tier | null;
  /**
   * `base_pipeline_type` of the saved row the route names, when the caller has it.
   * Without it the host looks the row up itself on `/workflows/{id}/edit`.
   */
  linkedBasePipelineType?: string | null;
};

// --- Small pieces --------------------------------------------------------------------

/** Reports the `ai` search parameter. Lives in its own Suspense boundary. */
function AiParamReader({ onChange }: { onChange: (ai: string | null) => void }) {
  const params = useSearchParams();
  const ai = params.get("ai");
  useEffect(() => {
    onChange(ai);
  }, [ai, onChange]);
  return null;
}

type Prompt =
  | { kind: "load_draft" }
  | { kind: "undo" }
  | { kind: "new_conversation" }
  | { kind: "open_session"; sessionId: string; workflowId: string | null };

const PROMPT_TEXT: Record<
  Prompt["kind"],
  { title: string; description: string; confirm: string; cancel: string }
> = {
  load_draft: {
    title: "Load the builder's update?",
    description:
      "The builder changed this workflow in another tab, and this canvas has unsaved changes. Loading the update replaces them.",
    confirm: "Load update",
    cancel: "Keep my changes",
  },
  undo: {
    title: "Discard your edits?",
    description:
      "You edited the canvas after the last AI change. Undoing restores the canvas from before that change and discards your edits.",
    confirm: "Undo and discard",
    cancel: "Cancel",
  },
  new_conversation: {
    title: "Discard unsaved work?",
    description:
      "This workflow has unsaved changes. Starting a new conversation clears the canvas.",
    confirm: "Start new conversation",
    cancel: "Cancel",
  },
  open_session: {
    title: "Discard unsaved work?",
    description: "This workflow has unsaved changes. Opening another conversation replaces the canvas.",
    confirm: "Open conversation",
    cancel: "Cancel",
  },
};

function ConfirmDialog({
  prompt,
  onConfirm,
  onCancel,
}: {
  prompt: Prompt;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const text = PROMPT_TEXT[prompt.kind];
  return (
    <Modal title={text.title} description={text.description} onClose={onCancel}>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          {text.cancel}
        </Button>
        <Button onClick={onConfirm}>{text.confirm}</Button>
      </div>
    </Modal>
  );
}

function PanelNotice({
  state,
  onDismiss,
}: {
  state: BuilderState;
  onDismiss: () => void;
}) {
  let text: string | null = null;
  switch (state.notice.kind) {
    case "reply_in_progress_elsewhere":
      text = "A reply is being written. Your message is still in the box. Send it when the reply finishes.";
      break;
    case "deleted_elsewhere":
      text = "This conversation was deleted in another tab.";
      break;
    case "linked_row_changed":
      text =
        "The saved workflow changed after the builder's last draft. The canvas shows the saved version.";
      break;
    default:
      return null;
  }
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-[var(--radius-node)] border border-status-amber-border bg-status-amber-fill px-3 py-2 text-[12px] text-ink-800"
    >
      <p className="min-w-0 flex-1 break-words">{text}</p>
      <Button variant="secondary" size="sm" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  );
}

// --- Helpers -------------------------------------------------------------------------

function initialBuilderState(): BuilderState {
  return isNewConversationPending()
    ? { ...INITIAL_BUILDER_STATE, panelOpen: true }
    : INITIAL_BUILDER_STATE;
}

/**
 * Move the address bar without a navigation. A change of path is marked first, so
 * `app/[...view]/page.tsx` skips its edit cold-mount fetch and the Composer is not
 * remounted (design 3.10.6, D-08).
 */
function replaceBuilderUrl(path: string, sessionId: string | null): void {
  const samePath = path === window.location.pathname;
  const search = searchWithAi(samePath ? window.location.search : "", sessionId);
  if (!samePath) markShallowNavTo(path);
  window.history.replaceState(window.history.state, "", `${path}${search}`);
}

interface SendChoice {
  modelId: string;
  effort: string | null;
}

/** The first message of a conversation that does not exist yet. */
interface StartRequest extends SendChoice {
  text: string;
}

// --- Component -----------------------------------------------------------------------

export function BuilderComposerHost({
  tier,
  linkedBasePipelineType,
  ...composerProps
}: BuilderComposerHostProps) {
  const entitled = tier !== null && canRunPipeline(tier, "custom");
  const pathname = usePathname();
  const router = useRouter();

  const [state, dispatch] = useReducer(builderReducer, undefined, initialBuilderState);
  /** True when this instance opened its panel for a "New conversation" or entry hand-off. */
  const [openedByHandoff] = useState(isNewConversationPending);
  const [urlAi, setUrlAi] = useState<string | null | undefined>(undefined);
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  /**
   * The first message of a conversation being created, shown as the user's
   * message at once and kept until its send settles; `null` otherwise. While it
   * is set, Send and New conversation are held, so one click makes one session.
   */
  const [startingText, setStartingText] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [startError, setStartError] = useState<string | null>(null);
  const [composerKey, setComposerKey] = useState(0);
  const [shownDraft, setShownDraft] = useState<ComposerBuilderBinding["draft"]>(null);
  const [fetchedBase, setFetchedBase] = useState<{ id: string; base: string } | null>(null);
  const [recalledChoice] = useState(recallPickerChoice);

  const session = state.load.kind === "ready" ? state.load.session : null;
  const sessionId = sessionIdOf(state.load);

  const picker = useBuilderModelPicker({
    enabled: entitled,
    stored: session
      ? { modelId: session.model_id, effort: session.effort }
      : recalledChoice,
  });
  const available = entitled && picker.state.status === "ready";
  const sessionList = useBuilderSessionList();
  const refreshSessions = sessionList.refresh;

  // --- Refs: the latest values for callbacks that must stay stable --------------------

  const stateRef = useRef(state);
  const canvasApiRef = useRef<{ getManifest: () => WorkflowManifest; isDirty: () => boolean } | null>(
    null,
  );
  /** The session this tab follows. Set before the reducer shows it. */
  const targetSessionRef = useRef<string | null>(null);
  const linkedIdRef = useRef<string | null>(null);
  const prevUrlAiRef = useRef<string | null | undefined>(undefined);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  /** Highest draft revision acted on (applied, skipped or declined). */
  const handledRevisionRef = useRef(0);
  /** Drafts up to this revision belong to the saved row, which the canvas shows instead. */
  const skipRevisionRef = useRef(0);
  /** Revisions this tab asked for itself, so they apply without a prompt. */
  const silentRevisionsRef = useRef<Set<number>>(new Set());
  const undoInFlightRef = useRef(false);
  const thisTabTurnRef = useRef<string | null>(null);
  const confirmedOpenRef = useRef<string | null>(null);
  /** Host-side counter handed to the Composer, so equal revision numbers of two sessions both apply. */
  const applyCounterRef = useRef(0);
  /** Bumped when this tab moves to another conversation, so a slow create is not adopted. */
  const startGenerationRef = useRef(0);
  /** Whether this instance is done with the hand-off flag it opened its panel for. */
  const handoffSettledRef = useRef(!openedByHandoff);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const {
    scrollRef: transcriptScrollRef,
    contentRef: transcriptContentRef,
    onScroll: onTranscriptScroll,
    scrollToEnd: scrollTranscriptToEnd,
  } = useFollowScroll();

  useEffect(() => {
    stateRef.current = state;
  });

  // The hand-off flag was read by the state initialisers. It is cleared once, when this
  // instance first stands on a builder route. The Saved Workflows entry sets the flag and
  // then navigates: an instance that mounts before the URL changes (still on
  // `/workflows`) leaves the flag for the instance the navigation mounts, or clears it
  // itself when the route arrives without a remount.
  useEffect(() => {
    if (handoffSettledRef.current || !isBuilderRoute(pathname)) return;
    handoffSettledRef.current = true;
    clearNewConversationPending();
  }, [pathname]);

  // --- Draft tracking -----------------------------------------------------------------

  const resetDraftTracking = useCallback((skipUpToRevision: number) => {
    handledRevisionRef.current = 0;
    skipRevisionRef.current = skipUpToRevision;
    silentRevisionsRef.current.clear();
    thisTabTurnRef.current = null;
    setShownDraft(null);
    setPrompt(null);
  }, []);

  const applyDraftToCanvas = useCallback((draft: Extract<CanvasDraft, { kind: "applied" }>) => {
    applyCounterRef.current += 1;
    handledRevisionRef.current = draft.revision;
    setShownDraft({
      revision: applyCounterRef.current,
      manifest: draft.manifest,
      targetTrust: draft.targetTrust,
    });
  }, []);

  // A new draft in the reducer reaches the canvas here: at once when this tab asked for it
  // or has no unsaved work, after a prompt otherwise (Req 7.2, 17.11).
  useEffect(() => {
    const draft = state.draft;
    if (draft.kind !== "applied" || draft.revision <= handledRevisionRef.current) return;
    const decision = decideDraft({
      revision: draft.revision,
      skipUpToRevision: skipRevisionRef.current,
      silent: silentRevisionsRef.current.has(draft.revision) || undoInFlightRef.current,
      dirty: canvasApiRef.current?.isDirty() ?? false,
    });
    if (decision === "skip") {
      handledRevisionRef.current = draft.revision;
    } else if (decision === "apply") {
      applyDraftToCanvas(draft);
    } else {
      setPrompt((current) => current ?? { kind: "load_draft" });
    }
  }, [state.draft, applyDraftToCanvas]);

  // --- Session lifecycle --------------------------------------------------------------

  /** End the hold on a first message: it was sent, refused, failed or abandoned. */
  const endStarting = useCallback(() => {
    setStartingText(null);
  }, []);

  const clearSession = useCallback(() => {
    targetSessionRef.current = null;
    linkedIdRef.current = null;
    startGenerationRef.current += 1;
    endStarting();
    resetDraftTracking(0);
    dispatch({ type: "session_cleared" });
  }, [resetDraftTracking, endStarting]);

  const loadSession = useCallback(
    async (id: string) => {
      const token = getToken();
      if (!token) return;
      startGenerationRef.current += 1;
      endStarting();
      resetDraftTracking(0);
      targetSessionRef.current = id;
      linkedIdRef.current = null;
      dispatch({ type: "session_loading", sessionId: id });
      dispatch({ type: "panel_set", open: true });
      try {
        const detail = await getSession(token, id);
        if (targetSessionRef.current !== id) return;
        linkedIdRef.current = detail.workflow_id;
        // A linked session shows the saved row, not its latest draft (Req 12.4).
        skipRevisionRef.current = detail.workflow_id !== null ? (detail.latest_draft?.revision ?? 0) : 0;
        if (confirmedOpenRef.current === id && detail.latest_draft) {
          silentRevisionsRef.current.add(detail.latest_draft.revision);
        }
        confirmedOpenRef.current = null;
        dispatch({ type: "session_loaded", session: detail });
      } catch {
        if (targetSessionRef.current === id) dispatch({ type: "session_not_found", sessionId: id });
      }
    },
    [resetDraftTracking, endStarting],
  );

  // The URL decides which session this tab follows (Req 3.7, 3.9, 3.10).
  useEffect(() => {
    const previous = prevUrlAiRef.current;
    prevUrlAiRef.current = urlAi;
    if (!available || urlAi === undefined) return;
    if (urlAi !== null) {
      if (urlAi !== targetSessionRef.current) void loadSession(urlAi);
      return;
    }
    // The parameter was removed from the address, for example by navigating away.
    if (previous !== undefined && previous !== null && targetSessionRef.current !== null) {
      clearSession();
    }
  }, [urlAi, available, loadSession, clearSession]);

  // Reload the stored session when the reducer asks: a turn ended, or the stream rejoined.
  useEffect(() => {
    if (!state.needsReload) return;
    const id = sessionIdOf(state.load);
    const token = getToken();
    dispatch({ type: "reload_acknowledged" });
    if (id === null || !token) return;
    getSession(token, id).then(
      (detail) => {
        if (targetSessionRef.current !== id) return;
        linkedIdRef.current = detail.workflow_id;
        dispatch({ type: "session_loaded", session: detail });
      },
      () => undefined,
    );
  }, [state.needsReload, state.load]);

  // --- Sending ------------------------------------------------------------------------

  const failSend = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 409) {
      dispatch({ type: "send_failed", reason: "conflict" });
      return;
    }
    dispatch({ type: "send_failed", reason: "other" });
    const id = targetSessionRef.current;
    if (error instanceof ApiError && error.status === 404 && id !== null) {
      dispatch({ type: "session_not_found", sessionId: id });
    }
  }, []);

  /** Send one message in a session. Resolves true when the server accepted it. */
  const sendInSession = useCallback(
    async (id: string, text: string, choice: SendChoice): Promise<boolean> => {
      const token = getToken();
      if (!token) return false;
      const clientMessageId = newClientMessageId();
      dispatch({ type: "send_started", clientMessageId, text });
      try {
        const canvas = canvasApiRef.current?.getManifest() ?? { steps: [] };
        const accepted = await sendMessage(
          token,
          id,
          {
            content: text,
            model_id: choice.modelId,
            effort: choice.effort,
            canvas_state: canvas as unknown as Record<string, unknown>,
          },
          clientMessageId,
        );
        dispatch({ type: "send_accepted", turnId: accepted.turn_id });
        return true;
      } catch (error) {
        failSend(error);
        return false;
      }
    },
    [failSend],
  );

  /**
   * Create a session and keep the first message until its stream opens (Req 1.7 to
   * 1.10). On `/workflows/{id}/edit` the session is seeded with that workflow and the
   * canvas keeps showing it; no navigation happens.
   */
  const startSession = useCallback(
    async (request: StartRequest) => {
      const token = getToken();
      if (!token) throw new Error("Not authenticated");
      const generation = startGenerationRef.current;
      const editId = parseEditWorkflowId(pathname);
      const body: CreateSessionRequest = editId
        ? { mode: "edit", workflow_id: editId, model_id: request.modelId, effort: request.effort }
        : { mode: "create", model_id: request.modelId, effort: request.effort };
      const detail: SessionDetail = await createSession(token, body);
      // The user opened another conversation meanwhile: leave this one unopened.
      if (startGenerationRef.current !== generation) return;

      stashFirstMessage(detail.id, {
        text: request.text,
        modelId: request.modelId,
        effort: request.effort,
      });
      resetDraftTracking(0);
      targetSessionRef.current = detail.id;
      linkedIdRef.current = detail.workflow_id;
      dispatch({ type: "session_loading", sessionId: detail.id });
      dispatch({ type: "session_loaded", session: detail });
      dispatch({ type: "panel_set", open: true });
      replaceBuilderUrl(editId ? sessionRoutePath(editId) : sessionRoutePath(null), detail.id);
    },
    [pathname, resetDraftTracking],
  );

  // --- Stream -------------------------------------------------------------------------

  const onStreamEvent = useCallback(
    (event: BuilderEvent) => {
      if (event.type === "turn_started") {
        const current = stateRef.current;
        if (current.turn.kind === "sending" || current.ownTurnIds.includes(event.turn_id)) {
          thisTabTurnRef.current = event.turn_id;
        }
      } else if (event.type === "draft_applied" && event.turn_id === thisTabTurnRef.current) {
        // This tab sent the message with its canvas, so the draft needs no prompt.
        silentRevisionsRef.current.add(event.revision);
      }
      dispatch({ type: "stream_event", event, now: Date.now() });

      if (event.type === "snapshot") {
        const id = targetSessionRef.current;
        const pending = id === null ? null : takeFirstMessage(id);
        if (id !== null && pending !== null) {
          // A refused first message goes back into the input so it is not lost (Req 13.10).
          void sendInSession(id, pending.text, {
            modelId: pending.modelId,
            effort: pending.effort,
          }).then((accepted) => {
            endStarting();
            if (!accepted) setInputText((current) => (current === "" ? pending.text : current));
          });
        }
      }
    },
    [sendInSession, endStarting],
  );

  const stream = useBuilderSessionStream({
    sessionId,
    enabled: available && sessionId !== null && state.load.kind !== "not_found",
    onEvent: onStreamEvent,
  });

  // A stream that closes for good before its first snapshot never sends the first
  // message: release the hold and put the text back in the box so it is not lost.
  // Adjusted during render when the phase changes, not in an effect.
  const streamClosed = stream.phase.startsWith("closed");
  const [streamWasClosed, setStreamWasClosed] = useState(streamClosed);
  if (streamWasClosed !== streamClosed) {
    setStreamWasClosed(streamClosed);
    if (streamClosed && startingText !== null) {
      setStartingText(null);
      setInputText((current) => (current === "" ? startingText : current));
    }
  }

  // --- Linked row ---------------------------------------------------------------------

  const editId = parseEditWorkflowId(pathname);
  useEffect(() => {
    if (!available || linkedBasePipelineType != null || editId === null) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    getUserWorkflows(token).then(
      (rows) => {
        const row = rows.find((candidate) => candidate.id === editId);
        if (!cancelled && row) setFetchedBase({ id: editId, base: row.base_pipeline_type });
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [available, linkedBasePipelineType, editId]);
  const linkedBase =
    linkedBasePipelineType ?? (fetchedBase !== null && fetchedBase.id === editId ? fetchedBase.base : null);

  // After a save: link the session to the row and move the URL (Req 10.7, 10.11, 3.8).
  const handleSaved = useCallback(({ id }: { id: string; baseIsCustom: boolean }) => {
    const sid = targetSessionRef.current;
    if (sid === null) return;
    const target = sessionRoutePath(id);
    const move = () => {
      if (window.location.pathname !== target) replaceBuilderUrl(target, sid);
    };
    const token = getToken();
    if (linkedIdRef.current === id || !token) {
      move();
      return;
    }
    linkSession(token, sid, { workflow_id: id }).then(
      () => {
        linkedIdRef.current = id;
        move();
      },
      () => move(),
    );
  }, []);

  // --- Remember the picker choice for the next host instance -------------------------

  const choiceModelId = picker.choice?.modelId ?? null;
  const choiceEffort = picker.choice?.effort ?? null;
  useEffect(() => {
    rememberPickerChoice(choiceModelId === null ? null : { modelId: choiceModelId, effort: choiceEffort });
  }, [choiceModelId, choiceEffort]);

  // --- Actions ------------------------------------------------------------------------

  const handleRegisterCanvasApi = useCallback(
    (api: { getManifest: () => WorkflowManifest; isDirty: () => boolean }) => {
      canvasApiRef.current = api;
    },
    [],
  );

  // The AI button opens and closes the panel (Req 1.3 to 1.5). It never opens a new
  // canvas: on a saved or half-built workflow the panel opens beside that canvas, and
  // the first message starts a conversation about it.
  const handleAiButton = useCallback(() => {
    if (stateRef.current.panelOpen) {
      dispatch({ type: "panel_set", open: false });
      return;
    }
    returnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dispatch({ type: "panel_set", open: true });
  }, []);

  // An empty panel lists the recent conversations: load the first page whenever it opens.
  const emptyPanelOpen = available && state.panelOpen && state.load.kind === "none";
  useEffect(() => {
    if (emptyPanelOpen) void refreshSessions();
  }, [emptyPanelOpen, refreshSessions]);

  const goToSession = useCallback(
    (id: string, workflowId: string | null) => {
      startGenerationRef.current += 1;
      router.push(`${sessionRoutePath(workflowId)}?ai=${encodeURIComponent(id)}`);
    },
    [router],
  );

  const requestOpenSession = (id: string) => {
    if (id === targetSessionRef.current) {
      dispatch({ type: "panel_set", open: true });
      return;
    }
    const workflowId = sessionList.items.find((item) => item.id === id)?.workflow_id ?? null;
    if (canvasApiRef.current?.isDirty()) {
      setPrompt({ kind: "open_session", sessionId: id, workflowId });
      return;
    }
    goToSession(id, workflowId);
  };

  const startNewConversation = () => {
    setPrompt(null);
    setInputText("");
    setStartError(null);
    clearSession();
    dispatch({ type: "panel_set", open: true });
    if (parseEditWorkflowId(pathname) !== null) {
      // A saved row is open: a fresh conversation starts on /workflows/new, and the
      // next host instance opens its panel with no session (Req 11.2).
      markNewConversationPending();
      router.push(sessionRoutePath(null));
      return;
    }
    replaceBuilderUrl(window.location.pathname, null);
    setComposerKey((key) => key + 1);
  };

  const handleNewConversation = () => {
    if (canvasApiRef.current?.isDirty()) {
      setPrompt({ kind: "new_conversation" });
      return;
    }
    startNewConversation();
  };

  const handleDeleteSession = (id: string) => {
    sessionList.remove(id).then(
      () => {
        if (id !== targetSessionRef.current) return;
        clearSession();
        replaceBuilderUrl(window.location.pathname, null);
      },
      () => undefined,
    );
  };

  const performUndo = async () => {
    const token = getToken();
    const id = targetSessionRef.current;
    const draft = stateRef.current.draft;
    if (!token || id === null || draft.kind !== "applied") return;
    undoInFlightRef.current = true;
    try {
      const restored = await undoLastChange(token, id, { expected_revision: draft.revision });
      silentRevisionsRef.current.add(restored.revision);
    } catch {
      /* a stale revision (409) or a failure: the reload below shows the truth */
    }
    try {
      const detail = await getSession(token, id);
      if (targetSessionRef.current === id) dispatch({ type: "session_loaded", session: detail });
    } catch {
      /* the stream's draft_restored event still carries the restored manifest */
    } finally {
      undoInFlightRef.current = false;
    }
  };

  const handleUndo = () => {
    const draft = state.draft;
    const api = canvasApiRef.current;
    if (draft.kind !== "applied") return;
    const edited = api !== null && manifestFingerprint(api.getManifest()) !== draft.fingerprint;
    if (edited) {
      setPrompt({ kind: "undo" });
      return;
    }
    void performUndo();
  };

  const handleRetry = async () => {
    const token = getToken();
    const id = targetSessionRef.current;
    const turnId = session ? retryTurnId(session.messages) : null;
    if (!token || id === null || turnId === null) return;
    scrollTranscriptToEnd();
    dispatch({ type: "send_started", clientMessageId: newClientMessageId(), text: "" });
    try {
      const accepted = await retryTurn(token, id, turnId);
      dispatch({ type: "send_accepted", turnId: accepted.turn_id });
    } catch (error) {
      failSend(error);
    }
  };

  const handleContinue = () => {
    const id = targetSessionRef.current;
    if (id === null || picker.choice === null) return;
    scrollTranscriptToEnd();
    void sendInSession(id, "continue", picker.choice);
  };

  const handleStop = () => {
    const token = getToken();
    const id = targetSessionRef.current;
    if (!token || id === null || state.turn.kind !== "running") return;
    cancelTurn(token, id, state.turn.turnId).catch(() => undefined);
  };

  const handleInputSend = async () => {
    const choice = picker.choice;
    if (choice === null) return;
    const text = inputText;
    setStartError(null);
    scrollTranscriptToEnd();
    if (state.load.kind === "ready" && sessionId !== null) {
      if (await sendInSession(sessionId, text, choice)) setInputText("");
      return;
    }
    // No session yet (a fresh panel, after "New conversation", or the old one is gone):
    // create one. One create at a time: the box empties and Send stays disabled until
    // the first message's send settles, so a second Enter cannot make a second session.
    // The text shows at once as the user's message while the session is created.
    if (startingText !== null) return;
    setStartingText(text);
    setInputText("");
    try {
      await startSession({ text, modelId: choice.modelId, effort: choice.effort });
    } catch {
      endStarting();
      setInputText((current) => (current === "" ? text : current));
      setStartError("Could not start the conversation. Your text is still here. Try again.");
    }
  };

  const confirmPrompt = () => {
    const current = prompt;
    setPrompt(null);
    if (current === null) return;
    switch (current.kind) {
      case "load_draft": {
        const draft = stateRef.current.draft;
        if (draft.kind === "applied") applyDraftToCanvas(draft);
        break;
      }
      case "undo":
        void performUndo();
        break;
      case "new_conversation":
        startNewConversation();
        break;
      case "open_session":
        confirmedOpenRef.current = current.sessionId;
        goToSession(current.sessionId, current.workflowId);
        break;
    }
  };

  const cancelPrompt = () => {
    if (prompt?.kind === "load_draft") {
      // Declined: keep the canvas, and ask again only for a newer revision.
      const draft = stateRef.current.draft;
      if (draft.kind === "applied") handledRevisionRef.current = draft.revision;
    }
    setPrompt(null);
  };

  // --- Composer binding ---------------------------------------------------------------

  const turnRunning = state.turn.kind === "running";
  const aiButtonVisible = available && isBuilderRoute(pathname);
  const baseIsCustom = linkedBaseIsCustom(linkedBase);

  const binding = useMemo<ComposerBuilderBinding | undefined>(() => {
    if (!available) return undefined;
    return {
      draft: shownDraft,
      turnRunning,
      panelOpen: state.panelOpen,
      panelId: BUILDER_PANEL_ID,
      aiButtonVisible,
      linkedBaseIsCustom: baseIsCustom,
      onAiButton: handleAiButton,
      registerCanvasApi: handleRegisterCanvasApi,
      onSaved: handleSaved,
    };
  }, [
    available,
    shownDraft,
    turnRunning,
    state.panelOpen,
    aiButtonVisible,
    baseIsCustom,
    handleAiButton,
    handleRegisterCanvasApi,
    handleSaved,
  ]);

  // --- Render -------------------------------------------------------------------------

  const turn = state.turn;
  const turnBusy = turn.kind === "sending" || turn.kind === "running";
  const draftRevision = state.draft.kind === "applied" ? state.draft.revision : 0;
  const revisions = session
    ? [session.latest_draft, session.latest_unproposed].filter(
        (revision): revision is NonNullable<typeof revision> => revision !== null,
      )
    : [];
  const notFound = state.load.kind === "not_found";
  const starting = startingText !== null;
  const showEmptyState = state.load.kind === "none" && !starting;

  /** An example fills the box and does not send [pending G-25]; the cursor goes to the box. */
  const pickExample = (text: string) => {
    setInputText(text);
    inputRef.current?.focus();
  };

  const panel = available ? (
    <BuilderPanel
      collapsed={!state.panelOpen}
      returnFocusRef={returnFocusRef}
      onCollapse={() => dispatch({ type: "panel_set", open: false })}
      onExpand={handleAiButton}
      header={{
        title: session?.title || undefined,
        sessions: sessionList.items,
        currentSessionId: sessionId,
        hasMoreSessions: sessionList.hasMore,
        onMenuOpen: () => void refreshSessions(),
        onShowMore: () => void sessionList.loadMore(),
        onSelectSession: requestOpenSession,
        onDeleteSession: handleDeleteSession,
        onNewConversation: handleNewConversation,
        newConversationDisabled: turnBusy || starting,
      }}
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div
          ref={transcriptScrollRef}
          onScroll={onTranscriptScroll}
          className="min-h-0 flex-1 overflow-y-auto px-[18px] py-4"
        >
          <div ref={transcriptContentRef} className="flex min-w-0 flex-col gap-4">
            {stream.phase === "reconnecting" ? (
              <p role="status" className="font-sans text-[11px] text-ink-500">
                Reconnecting…
              </p>
            ) : null}
            {state.load.kind === "loading" ? (
              <p role="status" className="font-sans text-[12px] text-ink-500">
                Loading conversation…
              </p>
            ) : notFound ? (
              <div className="flex flex-col items-start gap-2 rounded-[var(--radius-menu)] border border-line-border bg-surface-card px-[13px] py-[11px]">
                <p className="font-sans text-[12px] text-ink-700">
                  {state.notice.kind === "deleted_elsewhere"
                    ? "This conversation was deleted."
                    : "This conversation was not found."}
                </p>
                <Button variant="secondary" size="sm" onClick={handleNewConversation}>
                  New conversation
                </Button>
              </div>
            ) : showEmptyState ? (
              <BuilderEmptyState
                onPickExample={pickExample}
                recentSessions={sessionList.items}
                onSelectSession={requestOpenSession}
              />
            ) : (
              <BuilderTranscript
                messages={session?.messages ?? []}
                revisions={revisions}
                turn={turn}
                pendingUserText={state.pendingUser?.text ?? startingText}
                starting={starting}
                actionsDisabled={turnBusy}
                onRetry={() => void handleRetry()}
                onContinue={handleContinue}
                onUndo={handleUndo}
              />
            )}
            <PanelNotice state={state} onDismiss={() => dispatch({ type: "notice_dismissed" })} />
          </div>
        </div>

        <div className="flex-none border-t border-line-divider px-4 pb-2.5 pt-3">
          <BuilderInput
            value={inputText}
            onChange={setInputText}
            onSend={() => void handleInputSend()}
            onStop={handleStop}
            turn={turn}
            textareaRef={inputRef}
            placeholder={session === null ? "Describe the workflow you want to build" : undefined}
            sendDisabled={picker.choice === null || state.load.kind === "loading" || starting}
            toolbar={
              <BuilderModelPicker
                state={picker.state}
                choice={picker.choice}
                note={picker.note}
                onModelChange={picker.onModelChange}
                onEffortChange={picker.onEffortChange}
                onRetry={picker.onRetry}
                disabled={turnBusy || starting}
              />
            }
          />
          {startError ? (
            <p role="alert" className="mt-1 px-1 font-sans text-[12px] text-status-failed-strong">
              {startError}
            </p>
          ) : null}
        </div>
        <BuilderLiveRegion turn={turn} draftRevision={draftRevision} />
      </div>
    </BuilderPanel>
  ) : null;

  return (
    <div className="contents">
      <Suspense fallback={null}>
        <AiParamReader onChange={setUrlAi} />
      </Suspense>

      <div className="contents">
        <ComposerPage key={composerKey} {...composerProps} builder={binding} builderPanel={panel} />
      </div>

      {available && prompt !== null ? (
        <ConfirmDialog prompt={prompt} onConfirm={confirmPrompt} onCancel={cancelPrompt} />
      ) : null}
    </div>
  );
}

export default BuilderComposerHost;
