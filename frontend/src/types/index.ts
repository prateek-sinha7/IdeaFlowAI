export interface User {
  id: string;
  email: string;
  tier: "basic" | "pro" | "enterprise";
  is_admin?: boolean;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface ChatSession {
  id: string;
  title: string;
  lastActivity: string;
  createdAt: string;
}

export interface ChatMessageArtifact {
  type: "user-stories" | "ppt" | "prototype";
  filename: string;
  content: string;
  summary: string;
}

export interface ChatMessage {
  id: string;
  chatSessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  steps?: ProcessStep[];
  artifact?: ChatMessageArtifact;
}

export interface StreamMessage {
  // NOTE: the trailing validator_result/validation_warning/gate_started/
  // gate_passed/gate_blocked entries are ADDITIVE (Phase 8 / API-03) — they
  // extend the contract; no existing event was renamed or removed. They flow
  // through the generic backend WS forward and the ValidatorIssuePanel reads them.
  //
  // The wave_started/wave_completed/wave_failed/subagent_spawned/subagent_result
  // entries are ADDITIVE (Phase 12 / §22) — the wave scheduler's wave/subagent
  // lifecycle events (statuses only, D-14). They flow through the same generic
  // backend WS forward and the WaveTreePanel reads them; no existing event was
  // renamed or removed.
  type: "stream" | "complete" | "error" | "phase_start" | "phase_end" | "title_update" | "step" | "pipeline_start" | "agent_start" | "agent_thinking" | "agent_chunk" | "agent_complete" | "agent_error" | "pipeline_complete" | "questionnaire" | "pipeline_cancelled" | "workflow_title_update" | "planner_start" | "planner_complete" | "planner_timeout" | "planner_error" | "gate_status" | "questionnaire_ready" | "questionnaire_complete" | "clarification_limit_reached" | "agent_input" | "tool_call" | "tool_result" | "task_progress" | "task_loop_progress" | "review_gate_ready" | "review_gate_approved" | "pipeline_heartbeat" | "pong" | "workflow_validated" | "validator_result" | "validation_warning" | "gate_started" | "gate_passed" | "gate_blocked" | "wave_started" | "wave_completed" | "wave_failed" | "subagent_spawned" | "subagent_result" | "pipeline_failed";
  chunk?: string;
  section?: string;
  data?: FinalOutput | ErrorDetail | ProcessStep | Record<string, unknown>;
}

/**
 * Inbound `review_gate_ready` event data shape (REDO-GATE F-fe5).
 *
 * `redoable` is a GENERIC, server-set discriminator (additive): the engine stamps
 * it `true` ONLY from the inline human-gate call site (a structural path — no
 * workflow/agent literal, SC-001). The FE renders the Redo control IFF `redoable`
 * is true, so a declared/user-composed `gate:human` step (which carries
 * `redoable=false`) shows NO Redo button. Optional + backward-compatible: an event
 * without the field is treated as not-redoable.
 */
export interface ReviewGateReadyData {
  gate_key: string;
  agent_id: string;
  agent_name: string;
  output: string;
  pipeline_run_id: string;
  redoable?: boolean;
}

/** One worker leaf under a wave group — an agent + its lifecycle status. */
export interface WaveWorker {
  agent: string;
  status: string;
  /**
   * The per-wave worker index emitted by the backend (`data.worker`, 12-06
   * contract). Worker leaves are keyed by this index so N parallel workers of
   * the SAME agent (the `sample_wave` self×N shape) render as N distinct leaves
   * instead of collapsing into one flapping leaf (CR-06 FE half).
   */
  worker?: number;
}

/**
 * One wave group in the wave/subagent tree (Phase 12 / §22). Assembled from the
 * additive `wave_*` / `subagent_*` lifecycle events (statuses only — D-14, no
 * live token stream). The dashboard WS handler routes the events into this shape
 * (deduped by `event_id`) and feeds the list to the WaveTreePanel.
 */
export interface WaveGroup {
  waveIndex: number;
  /**
   * The wave_scheduler step id this group belongs to (`data.step`, 12-06
   * contract). Wave groups are keyed by `step:waveIndex` so two wave_scheduler
   * steps in one run do not collide on their wave-index-0 groups (IN-06).
   */
  step?: string;
  taskIds: string[];
  status: string;
  workers: WaveWorker[];
}

/** Severity tier for a validator/gate issue (mirrors the backend P0–P3 map). */
export type IssueSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

/**
 * One validator/gate issue surfaced from a `validator_result` /
 * `validation_warning` WS event (Phase 8 / API-03). Additive — does not change
 * any existing event payload.
 */
export interface ValidationIssue {
  severity: IssueSeverity;
  message: string;
  validator?: string;
  /** true for a `validation_warning` (warnings-first, non-blocking). */
  warning?: boolean;
}

export interface ProcessStep {
  id: string;
  label: string;
  detail?: string;
  status: "running" | "done" | "error";
  icon?: string;
  timestamp?: string;
}

export interface ErrorDetail {
  message: string;
  code?: string;
}

export interface FinalOutput {
  auth: object | null;
  realtime: object | null;
  dashboard: object | null;
  discovery: object | null;
  requirements: object | null;
  user_stories: object | null;
  ppt: SlideData | null;
  prototype: PrototypeDefinition | null;
  ui_design: object | null;
  ui_preview: object | null;
}

export interface SlideData {
  slides: Slide[];
}

export interface Slide {
  title: string;
  subtitle?: string;
  content: BulletPoint[];
  type: "text" | "chart" | "table" | "comparison" | "icon" | "title" | "two-column" | "quote" | "timeline";
  colorScheme: {
    background: string;
    text: string;
    accent: string;
  };
  speakerNotes?: string;
  layout?: string;
  chartData?: ChartData;
  tableData?: TableData;
  comparisonData?: ComparisonData;
  icons?: string[];
  quote?: { text: string; author: string };
  columns?: [string[], string[]] | [BulletPoint[], BulletPoint[]];
}

export interface ChartData {
  type: "bar" | "pie" | "line";
  labels: string[];
  values: number[];
  title?: string;
}

export interface TableData {
  headers: string[];
  rows: string[][];
}

export interface ComparisonData {
  left: { title: string; items: string[] };
  right: { title: string; items: string[] };
}

export interface BulletPoint {
  text: string;
  subPoints?: string[];
}

export interface PrototypeDefinition {
  pages: PrototypePage[];
  navigation: NavigationConfig;
  behavior: BehaviorConfig;
}

export interface PrototypePage {
  name: string;
  route: string;
  components: PrototypeComponent[];
  states?: Record<string, string>;
}

export interface PrototypeComponent {
  type: string;
  props: Record<string, unknown>;
  children?: PrototypeComponent[];
  dataFlow?: string;
}

export interface NavigationConfig {
  routes?: Record<string, string>;
  type?: string;
  items?: NavigationItem[];
  defaultRoute?: string;
}

export interface NavigationItem {
  label: string;
  route: string;
  icon?: string;
}

export interface BehaviorConfig {
  interactions: Record<string, string>;
  animations?: Record<string, string>;
  responsive?: Record<string, unknown>;
}

export interface UserStoryDocument {
  epics: Epic[];
  personas?: Persona[];
}

export interface Persona {
  name: string;
  role: string;
  goals: string;
  painPoints: string;
}

export interface Epic {
  title: string;
  description: string;
  stories: Story[];
  priority?: string;
  businessValue?: string;
}

export interface Story {
  title: string;
  description: string;
  acceptanceCriteria: string[];
  storyPoints?: number;
  dependencies?: string;
}

// ============================================================
// WORKFLOW / PIPELINE TYPES
// ============================================================

export type WorkflowType = "user_stories" | "user_stories_revision" | "ppt" | "ppt_revision" | "od_ppt" | "od_ppt_revision" | "prototype" | "prototype_revision" | "od_prototype" | "app_builder" | "app_builder_revision" | "custom" | "migration" | "mulesoft_to_springboot" | "dotnet_to_azure";

// Phase 16 (WR-01): ISS-016 newly persists "degraded" for a partially-failed
// run (websocket.py), and the revision drainer can persist "revising". The raw
// status is cast through this union at api.ts:288 (`raw.status as ...`); include
// both so the cast is honest and the history-reopen comparisons type-check.
export type WorkflowStatus = "running" | "completed" | "failed" | "cancelled" | "degraded" | "revising";

export interface WorkflowRun {
  id: string;
  title: string;
  type: WorkflowType;
  status: WorkflowStatus;
  input: string;
  output?: string;
  agentOutputs?: AgentThinkingEntry[];
  tokenUsage?: {
    total_input_tokens: number;
    total_output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    total_cache_read_tokens?: number;
    total_cache_write_tokens?: number;
    model_id?: string;
    per_agent?: Record<string, {
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
    }>;
  };
  modelId?: string;
  // UXFIX-02 (22-03 / D-19): the persisted declared/resolved deliverable shape.
  // History-reopen prefers this over deriveDeliverableMimetype so a binary
  // deliverable (e.g. application/zip) re-renders faithfully; absent on legacy
  // NULL rows → the heuristic fallback applies (parity).
  deliverableMimetype?: string;
  deliverableFilename?: string;
  // Revision Families (B1 / D1-D2-D7): the child-run family model unified at the
  // read layer. parentRunId is the run this run revised (null for a standalone /
  // root run); rootRunId is the family root, computed server-side (a standalone
  // run is its own root).
  parentRunId: string | null;
  rootRunId: string;
  createdAt: string;
  completedAt?: string;
  duration?: number;
  agentCount: number;
  error?: string;
}

// Revision Families (B1): raw wire shape from GET /api/runs/{id}/family. Carries
// the API's snake_case field names on purpose (like ChainContext) — this is the
// unnormalized read model the family view consumes directly.
export interface FamilyMember {
  id: string;
  type: string;
  title: string;
  status: string;
  revision_index: number;
  parent_run_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface RunFamily {
  root_id: string;
  members: FamilyMember[];
}

export interface AgentThinkingEntry {
  agent_id: string;
  name: string;
  role: string;
  icon: string;
  thinking: string;
  output: string;
  duration: number | null;
}

// ─── ISS-021 (18-01 BE → 18-03 FE) — type-driven deliverable contract ─────────
// The `pipeline_complete` event now carries two ADDITIVE keys sourced from the
// resolved `ectx.deliverable` (18-01): the declared mimetype + filename. The FE
// dispatches the generic fallback renderer on the DECLARED mimetype (live),
// never a workflow name (SC-001). Optional so existing consumers/tests are
// unaffected; the four known branches ignore them.
export interface PipelineCompleteData {
  final_output?: string;
  pipeline_type?: string;
  status?: string;
  deliverable_mimetype?: string;
  deliverable_filename?: string;
}

// A single generic deliverable channel for ANY pipeline_type that matched none
// of the known FE render branches — carried from `pipeline_complete` live and
// derived from the persisted run output on history-reopen. PreviewPanel +
// FilesTab dispatch on `mimetype` (text/html → sandboxed iframe, text/markdown
// → MarkdownPreview, application/zip → bundle view).
export interface GenericDeliverable {
  mimetype?: string;
  filename?: string;
  content?: string;
}

// ─── ISS-021 reopen heuristic (shared) ────────────────────────────────────────
// On the history-REOPEN path there is no `deliverable_mimetype` event — the
// persisted run carries only the output bytes. Both reopen surfaces (page.tsx's
// generic channel AND WorkflowHistory.tsx's detail view) MUST agree on what to
// render, so they share THIS single helper. It is a FE RENDER heuristic on the
// already-persisted output shape — distinct from the REJECTED backend
// content-sniff (the manifest DECLARES the shape live; this only covers reopen
// where the declared mimetype was not persisted).
//
//   • `<!doctype`/`<html` prefix (case-insensitive, leading whitespace
//     tolerated)                         → `text/html`
//   • a serialized-sandbox file bundle   → `application/zip`  (WR-02)
//   • everything else / empty / null     → `text/markdown`    (nothing to frame)
//
// WR-02 (18 review fix): the helper previously only ever returned text/html or
// text/markdown, so a custom serialized-sandbox bundle was mis-typed to markdown
// on reopen (and offered as a `.md` download) while the live path carries the
// true `application/zip`. The bundle is recognised structurally — the same
// ```filename: …``` fenced-block shape the AppBuilder bundle parser consumes —
// so live and reopen now agree for zip/bundle custom deliverables too. (The
// ideal fix is persisting the declared mimetype on the run row; until that
// additive column lands this content heuristic keeps the two surfaces in sync —
// recorded as a known reopen limitation in 18-REVIEW-FIX.md.)
const _BUNDLE_FILENAME_BLOCK = /```\s*filename:\s*[^\n]+\n/i;

export function deriveDeliverableMimetype(output: string | null | undefined): string {
  const raw = output ?? "";
  const trimmed = raw.trimStart().toLowerCase();
  if (trimmed.startsWith("<!doctype") || trimmed.startsWith("<html")) {
    return "text/html";
  }
  // A serialized-sandbox / app-bundle deliverable is a markdown carrier of
  // ```filename: path``` fenced blocks — type it as a bundle so the reopen
  // surface renders the file-bundle view and offers a bundle download (matching
  // the live serialized_sandbox → application/zip default), not a flat `.md`.
  if (_BUNDLE_FILENAME_BLOCK.test(raw)) {
    return "application/zip";
  }
  return "text/markdown";
}

// ─── UXFIX-02 (22-03 / D-19) reopen resolution (shared) ───────────────────────
// The single resolution BOTH reopen surfaces (page.tsx's generic channel AND
// WorkflowHistory.tsx's detail view) call so they cannot diverge (the 18-03
// shared-helper invariant). Prefer the PERSISTED `deliverable_mimetype` written
// on the run row (22-03 backend) — so a custom BINARY deliverable (e.g.
// application/zip) re-renders true to type — and fall back to the
// `deriveDeliverableMimetype` text heuristic ONLY for legacy rows where the
// persisted value is NULL/absent. SC-001: structural, never a workflow-name check.
export function resolveReopenMimetype(
  persistedMimetype: string | null | undefined,
  output: string | null | undefined,
): string {
  const persisted = (persistedMimetype ?? "").trim();
  if (persisted) {
    return persisted;
  }
  return deriveDeliverableMimetype(output);
}

export interface AgentDef {
  id: string;
  name: string;
  role: string;
  description: string;
  pipeline_type: string;
  order: number;
  icon: string;
  estimated_duration: number;
  has_skill: boolean;
  /** Static HITL gate from the agent's AGENT.md frontmatter: "Human_Gate"
   *  (default-gated, pre-checked in the Review-gates toggle), a "Validation_Gate",
   *  or null/absent (no static gate). Sourced from the real backend registry. */
  gate?: string | null;
  /** Full AGENT.md prompt body (markdown text after the YAML frontmatter).
   *  Populated when the agent is fetched from the /api/agents/library or
   *  /api/agents/pipelines/{type} endpoint (KAN-76). May be absent on
   *  static AgentLibraryData entries that have not been refreshed from the API. */
  prompt_body?: string;
}

export interface PipelineConfig {
  pipeline_type: string;
  agents: AgentDef[];
  total_estimated_duration: number;
}

export interface AttachedSkill {
  id: string;
  name: string;
  source: "ecc" | "superpowers" | "gsd";
  sourceLabel: string;
  category: string;
  content: string;
}

export interface AttachedHook {
  id: string;
  name: string;
  source: "ecc" | "superpowers" | "gsd";
  sourceLabel: string;
  event: string;
  trigger: string;
  description?: string;
}

export type AgentStatusType = "idle" | "thinking" | "running" | "done" | "error";

export interface AgentRunState {
  id: string;
  name: string;
  role: string;
  icon: string;
  status: AgentStatusType;
  output: string;
  thinking: string;
  duration: number | null;
  error: string | null;
  index: number;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  estimatedCostUsd?: number;
  // Phase 3 (T042) — Thinking tab fields
  inputPrompt?: string;
  contextSources?: ContextSource[];
  toolCalls?: ToolCallEntry[];
  thinkingText?: string;
  // KAN-81 — validation result from post_step: revision_validation
  validationIssues?: ValidationIssue[];
  validationPassed?: boolean;
}

/** A source of context for an agent — either a summarized prior-agent output
 *  or a typed Artifact from the Artifact_Store. */
export interface ContextSource {
  type: "summary" | "artifact";
  // For type="summary":
  agent_id?: string;
  agent_name?: string;
  summary_length?: number;
  full_output_length?: number;
  // For type="artifact":
  artifact_type?: string;
  artifact_size_chars?: number;
}

/** A single tool invocation recorded in the Thinking tab. */
export interface ToolCallEntry {
  tool: string;
  args: Record<string, unknown>;
  result: string | null;
  timestamp: string;
}

/** One answered clarify round (POR §6.5). Mirrors the backend kind="clarifications"
 *  artifact content — a JSON list of {question_id, question_text, impact_level,
 *  answer, round} grouped by round. Surfaced by C2's ClarificationsCard. */
export interface ClarifyRound {
  round: number;
  qa: {
    question_id: string;
    question_text: string;
    impact_level: string;
    answer: string | null;
  }[];
}

export interface PipelineRunState {
  isRunning: boolean;
  pipeline_type: string;
  agents: AgentRunState[];
  currentAgentIndex: number;
  totalDuration: number | null;
  completedCount: number;
  totalInputTokens?: number;
  totalOutputTokens?: number;
  totalTokens?: number;
  estimatedCostUsd?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
  modelId?: string;
  // Phase 2 (Universal Engine) — planner + gate state
  pipelineRunId?: string;
  plannerStatus?: "idle" | "running" | "complete" | "timeout" | "error";
  plannerSummary?: string;
  executionGate?: "PROCEED" | "CLARIFY_REQUIRED";
  clarificationLimitReached?: boolean;
  // Phase 3 (T063)
  dagEdges?: Array<{ from: string; to: string; artifact_type: string }>;
  unresolvedEdges?: Array<{ consuming_agent_id: string; artifact_type: string }>;
  protoCompletedTasks?: Array<{ number: number; title: string; summary: string }>;
  protoCompletedTaskCount?: number;
  // Phase 13
  degraded?: boolean;
  degradedFailedAgents?: string[];
  // Phase 16
  failed?: boolean;
  failedAgents?: string[];
  // KAN-73 — live audit trail from hook_run WS events
  hookRuns?: HookRunEntry[];
  // Workstream C1 (POR §6.2/§6.5) — answered clarify rounds retained per run so
  // they survive the questionnaire panel unmount (consumed by C2's ClarificationsCard).
  clarifications?: ClarifyRound[];
  // KAN-101: tracks how many spec revision cycles have been triggered by
  // "Update the Specs". 0 = first run (no revision), 1 = first revision, etc.
  // Incremented in handlePipelineMessage when prototype-specify agent_start fires
  // on an agent that was already done (sub-pipeline re-run).
  specRevisionCount?: number;
}

/** One audit entry from a hook_run WS event or persisted hook_runs DB row (KAN-73). */
export interface HookRunEntry {
  id?: string;
  hook: string;
  event: string;
  outcome: string;
  detail?: {
    agent_id?: string;
    agent_name?: string;
    event?: string;
    step_index?: number;
    timestamp?: string;
    summary?: string;
    severity?: string;
    hook_type?: string;
    [key: string]: unknown;
  } | null;
  created_at?: string | null;
}

export type PipelineMessageType =
  | "pipeline_start"
  | "agent_start"
  | "agent_thinking"
  | "agent_chunk"
  | "agent_complete"
  | "agent_error"
  | "pipeline_complete"
  // F3 (13-06): terminal failure — every agent in the run hard-failed. ADDITIVE.
  | "pipeline_failed";
