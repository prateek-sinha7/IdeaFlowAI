/**
 * Wire types of the AI Workflow Builder.
 *
 * Mirrors `backend/app/api/workflow_builder/schemas.py` (REST bodies) and
 * `backend/app/agents/workflow_builder/events.py` (Session_Stream events), per
 * design sections 3.2.2, 3.3.2 and 3.10.7. Datetimes are ISO-8601 strings on
 * the wire. A backend field typed `dict[str, Any]` is `Record<string, unknown>`
 * here, because a manifest from the wire is untrusted until it is validated.
 */

import type { CapabilityModelEntry } from "@/lib/api";
import type { WorkflowManifest } from "@/types/index";

// --- Status literals ----------------------------------------------------------------

export type TurnStatus =
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "interrupted";

export type StopReason =
  | "time"
  | "tool_calls"
  | "tokens"
  | "recursion"
  | "gate_rejections"
  | "cancelled"
  | "deleted"
  | "shutdown"
  | "restart"
  | "error";

export type Outcome = "draft" | "reply" | "unfinished";
export type RevisionKind = "seed" | "accepted" | "undo" | "unproposed";
export type TargetTrust = "user" | "db";
export type SessionMode = "create" | "edit";

/** The stages the server derives from the agent's actions (design 3.3.3). */
export type BuilderStage =
  | "starting"
  | "thinking"
  | "reading"
  | "looking_up"
  | "writing"
  | "checking"
  | "platform_check"
  | "applying"
  | "responding";

export type ToolKind = "read" | "write" | "script" | "lookup" | "propose";
export type ToolStatus = "running" | "ok" | "error" | "refused" | "timed_out" | "stopped";
export type ToolFinishStatus = Exclude<ToolStatus, "running">;
export type CheckSource = "skill_validator" | "platform_dry_run" | "server_gate";
export type CheckVerdict = "valid" | "invalid" | "unknown";
export type LimitKind = "time" | "tool_calls" | "tokens";
export type LaunchNeedKind = "uploads" | "design" | "connector" | "source_run";
export type FinalTurnStatus = Exclude<TurnStatus, "running">;

/** A manifest as it arrives from the server: untrusted until validated. */
export type WireManifest = Record<string, unknown>;

// --- Shared value models ------------------------------------------------------------

/** One tool call (`ToolActivity` / `ToolActivityOut` / `ActivityLine`). */
export interface ToolActivity {
  call_id: string;
  tool: string;
  kind: ToolKind;
  label: string;
  status: ToolStatus;
  duration_ms: number | null;
  /** Script calls only. */
  command: string | null;
  /** Script calls only. */
  exit_code: number | null;
  summary: string | null;
}

export interface CheckResult {
  source: CheckSource;
  verdict: CheckVerdict;
  errors: number;
  warnings: number;
  attempt: number | null;
  attempts_left: number | null;
}

export interface ChangeSummary {
  added: string[];
  removed: string[];
  reordered: boolean;
  gates_changed: string[];
  validators_changed: string[];
  models_changed: string[];
  prompts_changed: number;
}

export interface LaunchNeed {
  kind: LaunchNeedKind;
  /** For example a connector server name. */
  detail: string | null;
}

export interface RunningTurnSnapshot {
  turn_id: string;
  message_id: string;
  stage: BuilderStage;
  label: string;
  started_at: string;
  /** Drop turn events with `seq <= through_seq`: the snapshot already shows them. */
  through_seq: number;
  activity: ToolActivity[];
  checks: CheckResult[];
}

export interface UsageCounts {
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
}

export interface TokenUsage extends UsageCounts {
  summary: UsageCounts | null;
}

// --- REST requests ------------------------------------------------------------------

export type CreateSessionRequest =
  | { mode: "create"; workflow_id?: null; model_id: string; effort?: string | null }
  | { mode: "edit"; workflow_id: string; model_id: string; effort?: string | null };

export interface SendMessageRequest {
  /** 1..BUILDER_MAX_MESSAGE_CHARS code points, not whitespace-only. */
  content: string;
  model_id: string;
  effort: string | null;
  canvas_state: Record<string, unknown>;
  /** Matches `^[A-Za-z0-9_-]{8,64}$`; a `crypto.randomUUID()` value does. */
  client_message_id: string;
}

export interface UndoRequest {
  expected_revision: number;
}

export interface LinkRequest {
  workflow_id: string;
}

// --- REST responses -----------------------------------------------------------------

export interface TurnAccepted {
  turn_id: string;
  message_id: string;
  replayed: boolean;
}

/** A stored turn error. Generic text only. */
export interface ErrorOut {
  code: string;
  message: string;
  retryable: boolean;
}

export interface ActivitySummary {
  actions: number;
  checks: number;
  duration_ms: number;
}

export interface DraftRevisionOut {
  revision: number;
  kind: RevisionKind;
  manifest: WireManifest;
  target_trust: TargetTrust | null;
  change_summary: ChangeSummary | null;
  launch_needs: LaunchNeed[];
  source_turn_id: string | null;
  created_at: string;
}

/**
 * One stored step of a finished turn, in the order it happened. A tools step names
 * the turn's `activity` entries by `call_id`. Reply text is not a step: it is the
 * message `content`.
 */
export type StoredStep =
  | { kind: "thinking"; text: string }
  | { kind: "tools"; call_ids: string[] }
  | { kind: "check"; check: CheckResult };

export interface TranscriptMessage {
  id: string;
  seq: number;
  role: "user" | "assistant";
  turn_id: string;
  reply_to_message_id: string | null;
  status: TurnStatus | "accepted";
  outcome: Outcome | null;
  stop_reason: StopReason | null;
  content: string;
  thinking: string | null;
  /**
   * Assistant messages: the turn's thinking, tool-call groups and checks in order.
   * `null` for a turn stored before steps existed, and for a turn with none.
   */
  steps: StoredStep[] | null;
  model_id: string;
  effort: string | null;
  skill_hash: string | null;
  /** `skill_hash` differs from the previous assistant message. */
  skill_updated: boolean;
  error: ErrorOut | null;
  /** Accepted revision of this turn. */
  revision: number | null;
  /** Assistant messages only. */
  activity: ToolActivity[];
  activity_summary: ActivitySummary | null;
  created_at: string;
  ended_at: string | null;
}

export interface SessionSummary {
  id: string;
  title: string;
  mode: SessionMode;
  workflow_id: string | null;
  model_id: string;
  effort: string | null;
  running: boolean;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends SessionSummary {
  target_trust: TargetTrust;
  skill_hash: string;
  messages: TranscriptMessage[];
  latest_draft: DraftRevisionOut | null;
  /** Only present when newer than `latest_draft`. */
  latest_unproposed: DraftRevisionOut | null;
  running_turn: RunningTurnSnapshot | null;
  linked_row_changed: boolean;
}

export interface SessionPage {
  items: SessionSummary[];
  next_cursor: string | null;
}

export interface BuilderModelsResponse {
  /** `app.api.capabilities.ModelCatalogEntry`, unchanged. */
  models: CapabilityModelEntry[];
  default_model_id: string;
  /** `Reasoning.default_effort` per model id; `null` for a model without levels. */
  default_efforts: Record<string, string | null>;
}

// --- Session_Stream events ----------------------------------------------------------
//
// On the wire a frame is `{"type": ..., "data": {...}}` and `data` carries no
// `type` key. The stream hook merges them (`{ ...data, type }`) so each event
// below is one member of a union discriminated by `type`.

interface EventBase {
  ts: string;
}

interface TurnScoped extends EventBase {
  turn_id: string;
  /** Strictly increasing within the turn, starts at 1. */
  seq: number;
}

export interface SnapshotEvent extends EventBase {
  type: "snapshot";
  state: "idle" | "running";
  running_turn: RunningTurnSnapshot | null;
  latest_message_id: string | null;
  latest_revision: number | null;
  latest_unproposed_revision: number | null;
}

export interface TurnStartedEvent extends TurnScoped {
  type: "turn_started";
  message_id: string;
  model_id: string;
  effort: string | null;
  skill_hash: string;
}

export interface StageEvent extends TurnScoped {
  type: "stage";
  stage: BuilderStage;
  label: string;
}

export interface ThinkingEvent extends TurnScoped {
  type: "thinking";
  text: string;
}

export interface ToolStartedEvent extends TurnScoped {
  type: "tool_started";
  call_id: string;
  tool: string;
  kind: ToolKind;
  label: string;
  command: string | null;
}

export interface ToolFinishedEvent extends TurnScoped {
  type: "tool_finished";
  call_id: string;
  status: ToolFinishStatus;
  duration_ms: number;
  /** At most 280 characters. */
  summary: string;
}

export interface CheckResultEvent extends TurnScoped {
  type: "check_result";
  source: CheckSource;
  verdict: CheckVerdict;
  errors: number;
  warnings: number;
  attempt: number | null;
  attempts_left: number | null;
}

export interface DraftAppliedEvent extends TurnScoped {
  type: "draft_applied";
  revision: number;
  target_trust: TargetTrust;
  change_summary: ChangeSummary;
  launch_needs: LaunchNeed[];
  manifest: WireManifest;
}

export interface TextEvent extends TurnScoped {
  type: "text";
  text: string;
}

export interface LimitWarningEvent extends TurnScoped {
  type: "limit_warning";
  kind: LimitKind;
  used: number;
  limit: number;
}

export interface TurnCompletedEvent extends TurnScoped {
  type: "turn_completed";
  status: FinalTurnStatus;
  outcome: Outcome;
  stop_reason: StopReason | null;
  message_id: string;
  revision: number | null;
  usage: TokenUsage;
}

/** `turn_id` and `seq` are set when the error belongs to a turn. */
export interface ErrorEvent extends EventBase {
  type: "error";
  turn_id: string | null;
  seq: number | null;
  code: string;
  /** Generic: never a stack trace, SQL text or path. */
  message: string;
  retryable: boolean;
}

export interface DraftRestoredEvent extends EventBase {
  type: "draft_restored";
  revision: number;
  manifest: WireManifest;
}

export interface SessionDeletedEvent extends EventBase {
  type: "session_deleted";
}

export interface SessionRevokedEvent extends EventBase {
  type: "session_revoked";
  session_id: string;
  reason: string;
}

export type BuilderEvent =
  | SnapshotEvent
  | TurnStartedEvent
  | StageEvent
  | ThinkingEvent
  | ToolStartedEvent
  | ToolFinishedEvent
  | CheckResultEvent
  | DraftAppliedEvent
  | TextEvent
  | LimitWarningEvent
  | TurnCompletedEvent
  | ErrorEvent
  | DraftRestoredEvent
  | SessionDeletedEvent
  | SessionRevokedEvent;

export type BuilderEventType = BuilderEvent["type"];

// --- Composer integration (design 3.10.7) -------------------------------------------

export interface ComposerBuilderBinding {
  /** Latest draft for this canvas. Applied once per revision change. */
  draft: {
    revision: number;
    manifest: WorkflowManifest;
    targetTrust: TargetTrust;
  } | null;
  /** True from turn_started (or a running snapshot) until turn_completed, in every tab. */
  turnRunning: boolean;
  /**
   * True while the Builder_Panel is open (not collapsed). The composer switches
   * to Canvas view when this turns true; Simple view keeps working afterwards
   * (Req 3.4, 3.5). Not in the design's interface; added by task 20.4.
   */
  panelOpen: boolean;
  /**
   * The open Builder_Panel's element id. The AI button names it in `aria-controls`
   * while the panel is open, and reports `aria-expanded` either way.
   */
  panelId?: string;
  aiButtonVisible: boolean;
  /**
   * `false` when the saved row the session is linked to has a base other than
   * `custom`. Save then becomes "Save as new" (Req 10.10). Absent or `true`
   * means Save updates the row. Not in the design's interface; added by task 20.5.
   */
  linkedBaseIsCustom?: boolean;
  onAiButton: () => void;
  /** The composer registers a getter; the host calls it to build canvas_state and fingerprints. */
  registerCanvasApi: (api: {
    getManifest: () => WorkflowManifest;
    isDirty: () => boolean;
  }) => void;
  onSaved: (saved: { id: string; baseIsCustom: boolean }) => void;
}
