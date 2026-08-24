// ─── SSE Terminal Event Types (R-07, ISS-147) ──────────────────────────────────
// SSE-002: the frontend's authoritative terminal event type set — the only event
// types whose arrival means the backend has closed (or is about to close) the SSE
// stream, so the close must settle to `disconnected` rather than schedule a
// reconnect (BUG-015, ISS-147).
//
// This is a MIRROR, not a shared import: the backend is Python and cannot import
// this file. The backend's own set is DERIVED at runtime as
// `gate_pendency.REVIEW_RESOLUTIONS - {"review_gate_approved"}` in
// `backend/app/api/run_stream.py::_STREAM_TERMINAL_TYPES` (review_gate_approved
// resolves a gate but resumes the run on the same queue, so it does NOT close the
// stream — BUG-016). The two sets are kept aligned by an explicit guard test,
// `TestSSETerminalTypesSyncWithFrontend` in
// `backend/tests/unit/test_sse_stream.py`, which fails if either side drifts.
// If you change this list, change that test's `expected` set in the same commit.
export const STREAM_TERMINAL_TYPES: ReadonlySet<string> = new Set([
  "pipeline_complete",
  "pipeline_cancelled",
  "pipeline_failed",
  "budget_aborted",
  "error",
]);

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

// ─── Phase 31 (CHATUI-01) — chat-lane transcript contract ─────────────────────
// A per-turn attachment ref carried on a chat turn. Payload-transient by ND-10 /
// LOCK-E: an image/file attached to a run turn is NOT stored after the run, so
// `retained:false` is the honest default the backend stamps on replay/reopen
// (run_commands._persist_chat_message). `kind`/`name` are always present; the
// mime + size are best-effort metadata the picker fills in on the live send.
export interface ChatAttachment {
  kind: "image" | "file";
  name: string;
  mimeType?: string;
  sizeBytes?: number;
  retained: boolean;
}

// The consume-once deep-link descriptor a narrator result card carries so a card
// can link to the run tab it reports (borrow #6, open-design). `tab` is a GENERIC
// string tab id (never a workflow/agent name — SC-001); `nonce` makes the target
// single-use and re-triggerable (see useTabDeepLink). Distinct from the live
// navigation seam: this is the stored descriptor on the message, the seam mints
// the navigation nonce when the card is actually clicked.
export interface DeepLinkTarget {
  /**
   * Generic panel tab id — present ONLY when the frame explicitly names one.
   * Absent for engine-emitted cards (they carry `anchor` instead), so the card
   * kind's own generic default tab decides where the deep-link lands.
   */
  tab?: string;
  /**
   * The narrator's milestone/artifact ANCHOR as emitted by the backend
   * (`run:<id>` / `clarify:<id>` / `deliverable:<file>` / `spec_revision:<id>:<n>`
   * / a `gate_key`). A semantic reference to WHAT the card reports — never a tab
   * id, and never a workflow/agent name (SC-001).
   */
  anchor?: string;
  nonce: number;
}

export interface ChatMessage {
  id: string;
  chatSessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  steps?: ProcessStep[];
  artifact?: ChatMessageArtifact;
  // ─── Phase 31 (CHATUI-01) additive/OPTIONAL fields — non-breaking (INV-3). ───
  // Existing consumers (the dead-kit MessageBubble/ChatPanel) ignore these; they
  // only appear on the family-anchored transcript the chat lane renders.
  /** Per-turn attachment refs (payload-transient — ND-10). */
  attachments?: ChatAttachment[];
  /** Narrator result-card kind — a GENERIC milestone discriminator (SC-001),
   *  never a workflow/agent literal. Present only on `chat_reply` narrator turns. */
  cardKind?: "clarify" | "gate" | "pipeline" | "deliverable" | "spec_revision";
  /** Deep-link a narrator card carries into a run tab (borrow #6). */
  deepLink?: DeepLinkTarget;
  /**
   * Gate card resolution flag. Set to `true` when `review_gate_approved` fires
   * for the gate this card represents. A resolved gate card renders as a plain
   * inline text ("Review approved — build continues") instead of a styled box.
   * Generic — keyed on message id, never on workflow/agent name (SC-001).
   */
  resolved?: boolean;
  /** Family anchoring (D-02): the run/thread this turn belongs to. A child
   *  (revision) run's turns carry a different `runId` but stitch into the SAME
   *  transcript array so the family transcript accumulates, never swaps. */
  runId?: string;
  threadId?: string;
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
  // backend WS forward and AgentDetailPanel's inline construction/wave tree reads
  // them; no existing event was renamed or removed.
  type: "stream" | "complete" | "error" | "phase_start" | "phase_end" | "title_update" | "step" | "pipeline_start" | "agent_start" | "agent_thinking" | "agent_chunk" | "agent_complete" | "agent_error" | "pipeline_complete" | "questionnaire" | "pipeline_cancelled" | "workflow_title_update" | "planner_start" | "planner_complete" | "planner_timeout" | "planner_error" | "gate_status" | "questionnaire_ready" | "questionnaire_complete" | "clarification_limit_reached" | "agent_input" | "agent_skills" | "tool_call" | "tool_result" | "task_progress" | "task_loop_progress" | "review_gate_ready" | "review_gate_approved" | "pipeline_heartbeat" | "pong" | "workflow_validated" | "validator_result" | "validation_warning" | "gate_started" | "gate_passed" | "gate_blocked" | "wave_started" | "wave_completed" | "wave_failed" | "subagent_spawned" | "subagent_result" | "pipeline_failed";
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
  // SC-001 (plan 04, KAN-101): name-free, structurally-derived flags the FE
  // drives the "Update the Specs" affordance off — never an agent-id literal.
  // Optional/additive; absent on gates that do not carry them.
  update_specs_eligible?: boolean;
  artifact_kind?: string;
  /**
   * ISS-052 — the per-FIRING discriminator. `gate_key` is `{run_id}:{agent_id}`, so it
   * names a gate SLOT: the analyze gate opened INSIDE a spec-revision pass and the one
   * re-opened after that pass returns arrive with the same key AND the same `output`
   * bytes, milliseconds apart, while carrying opposite affordances. `revision_cycle`
   * says which cycle the firing belongs to (0 = no revision has run) and
   * `revision_in_flight` says whether the pass is still on the stack. The PAIR is what
   * identifies a firing — cycle alone cannot separate the in-pass gate from the
   * re-opened one. Optional/additive; absent ⇒ treated as (0, false).
   */
  revision_cycle?: number;
  revision_in_flight?: boolean;
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
 * (deduped by `event_id`) and feeds the list to AgentDetailPanel's inline
 * construction/wave tree.
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

export type WorkflowType = "user_stories" | "user_stories_revision" | "ppt" | "ppt_revision" | "prototype" | "prototype_revision" | "prototype_large_revision" | "prototype_feature_revision" | "app_builder" | "app_builder_revision" | "custom" | "migration" | "mulesoft_to_springboot" | "dotnet_to_azure";

// Phase 16 (WR-01): ISS-016 newly persists "degraded" for a partially-failed
// run (websocket.py), and the revision drainer can persist "revising". The raw
// status is cast through this union at api.ts:288 (`raw.status as ...`); include
// both so the cast is honest and the history-reopen comparisons type-check.
export type WorkflowStatus = "running" | "completed" | "failed" | "cancelled" | "degraded" | "revising" | "planning" | "generating" | "waiting_for_user" | "clarifying" | "analyzing";

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
  // KAN-130: chaining indicator — non-null when this run was launched by chaining
  // from a prior run's output (e.g. User Stories → Prototype chain).
  // Used to show "(Chained)" in the Jump Back In section.
  sourceRunId?: string | null;
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

// ─── Spec 012 (per-agent skills / composable custom agents) — canvas tree ─────
// A `subagents` child group's run strategy (R-04). `fanout` clones one child
// template per task from a `task_source`; `parallel`/`sequential` run the
// declared children as-is.
export type SubagentStrategy = "parallel" | "sequential" | "fanout";

/** Per-step tool grants (mirrors the compiler's `ToolPermissions`). */
export interface AgentToolGrants {
  read_files?: boolean;
  write_files?: boolean;
  exec?: boolean;
  spawn_subagents?: boolean;
}

/** Top-level manifest capability switches (R-07). Only `internet` exists today
 *  (R-25: the switch/field/UI land, the real provider does not). */
export interface WorkflowCapabilities {
  internet?: boolean;
}

/** One step of the full `{"steps": [...]}` manifest shape the backend
 *  `_project` sniffs apart from the compact EMP-03 selections map (spec 012,
 *  `backend/app/api/user_workflows.py::_project`). Mirrors
 *  `agents/workflows/manifest.py`'s step schema (R-01..R-05). A built-in step
 *  carries `agent_id`; a custom-agent instance carries `agent: "custom-agent"`
 *  plus its own `instance_id`/`name`/`prompt` (R-02/R-03/R-03a). */
export interface ManifestStep {
  agent_id?: string;
  agent?: "custom-agent";
  /** Generated once at node creation; matches `^[a-z0-9][a-z0-9-]*$`; never
   *  regenerated on rename (R-03). Custom-agent steps only. */
  instance_id?: string;
  /** Freely editable display name; never affects `instance_id` (R-03). */
  name?: string;
  /** Custom-agent-only prompt override (R-02/R-06). */
  prompt?: string;
  /** Per-step staged skill ids (R-01/R-13). */
  skills?: string[];
  /** Per-step tool grants. Absent means the compiler's least-privilege
   *  defaults apply (read_files on, everything else off). */
  tools?: AgentToolGrants;
  /** Per-step HITL review gates. Always emitted explicitly (even `[]`) so a
   *  saved manifest never relies on an implicit default. */
  gates?: string[];
  /** Leaf-step execution strategy — always `"single_shot"` for a step with
   *  no children. Parent steps (with `subagents`) never carry this; their
   *  strategy lives at `subagents.mode` instead. */
  strategy?: string;
  /** Upstream data dependencies, as backend agent ids (`custom-agent:<instance_id>`
   *  for composed steps). DERIVED from position at serialise time — never stored
   *  per-node, so reordering/deleting can never leave it stale. The engine reads
   *  it to build each step's roster block (`_build_roster`), which is what tells a
   *  step where its upstream inputs actually live. */
  depends_on?: string[];
  subagents?: {
    mode: SubagentStrategy;
    max_parallel?: number;
    task_source?: { kind: string; parser?: string | null; source_step?: string };
    steps: ManifestStep[];
  };
}

/** The full per-step manifest persisted into `workflows.manifest_json`
 *  (R-01..R-09, R-27) once a workflow declares any per-node skill, custom
 *  prompt, or sub-agent tree — as opposed to the flat EMP-03 selections map
 *  a from-scratch built-in-only composition still persists. */
/** Workflow-level run settings (deliverable/planner/clarify) — the fields the
 *  backend previously had to synthesize with hardcoded defaults at launch
 *  time (`raw_manifest.setdefault(...)` in run_commands.py's Case 3 branch)
 *  because a Composer-saved manifest never carried them. Now UI-editable;
 *  the backend's setdefault calls remain as a fallback for any manifest
 *  saved before this existed. */
export interface WorkflowRunConfig {
  deliverable?: { strategy: string; name: string };
  planner?: "skip" | "run";
  clarify?: { mode: "skip" | "auto"; defaults: string[] };
}

export interface WorkflowManifest {
  steps: ManifestStep[];
  capabilities?: WorkflowCapabilities;
  deliverable?: { strategy: string; name: string };
  planner?: "skip" | "run";
  clarify?: { mode: "skip" | "auto"; defaults: string[] };
}

export interface AgentDef {
  id: string;
  name: string;
  role: string;
  description: string;
  /** Backend returns a single string for single-pipeline agents, or a list of
   *  strings for shared agents that participate in multiple pipelines.
   *  Use getPrimaryPipelineType() to obtain a single string for display/sort. */
  pipeline_type: string | string[];
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

  // ─── Spec 012 — Canvas tree (R-02/R-35/R-36) ────────────────────────────
  /** True for a blank custom-agent instance (vs. a built-in library agent).
   *  Gates the unrestricted-skills rule (R-34), the prompt editor (R-06), and
   *  which `ManifestStep` shape this node compiles to. */
  isCustom?: boolean;
  /** Stable identity for a custom-agent instance (R-03): generated once at
   *  node creation, matches `^[a-z0-9][a-z0-9-]*$`, and NEVER changes —
   *  renaming edits `name` only. Present only on `isCustom` nodes. */
  instance_id?: string;
  /** Custom-agent-only prompt override (R-02/R-06). */
  prompt?: string;
  /** Per-node staged skill ids (R-01/R-13/R-36). Unrestricted for custom
   *  agents (R-34); filtered by each skill's `compatible_agents` for
   *  built-ins (R-38). */
  skills?: string[];
  /** Per-node tool grants (R-01 tools block). Absent means the compiler's
   *  least-privilege defaults apply. */
  tools?: AgentToolGrants;
  /** Child sub-agent nodes rendered below this node on the canvas (R-35). */
  children?: AgentDef[];
  /** The child group's run strategy (R-04/R-36). Present only when
   *  `children` is non-empty. */
  strategy?: SubagentStrategy;
  /** Bounds `parallel`/`fanout` concurrency (R-04); defaults to 3. */
  maxParallel?: number;
}

export interface PipelineConfig {
  pipeline_type: string;
  agents: AgentDef[];
  total_estimated_duration: number;
}

export interface AttachedSkill {
  id: string;
  name: string;
  category: string;
  content: string;
}

export interface AttachedHook {
  id: string;
  name: string;
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
  // From the `agent_skills` SSE event — the skills/hooks actually injected into
  // THIS agent's system prompt.
  attachedSkills?: AttachedSkillEntry[];
  attachedHooks?: AttachedHookEntry[];
  // Skills are now ADVERTISED (name + description staged to the sandbox), not
  // injected in full — the model loads a body on demand via read_file. These
  // two fields (also from the `agent_skills` SSE event) surface that contract:
  // reasons a skill failed to stage/was clamped, and the per-agent prompt cost
  // of advertising them (464 + 66 × count, advisory).
  skillsLoadErrors?: string[];
  estimatedTokens?: number;
}

/** A source of context for an agent — either a summarized prior-agent output,
 *  a typed Artifact from the Artifact_Store, or a run-originating source
 *  (user brief / template / design system). KAN-129: added "run_input" and
 *  "context_block" types + `label` field to match what the backend emits. */
export interface ContextSource {
  type: "summary" | "artifact" | "run_input" | "context_block";
  // For type="summary":
  agent_id?: string;
  agent_name?: string;
  summary_length?: number;
  full_output_length?: number;
  // For type="artifact":
  artifact_type?: string;
  artifact_size_chars?: number;
  // For type="run_input" and type="context_block" (KAN-129):
  // Human-readable label emitted by the backend (e.g. "prompt.md",
  // "Template: ibm-carbon", "Design system: ibm-carbon").
  label?: string;
  size_chars?: number;
}

/** A single tool invocation recorded in the Thinking tab. */
export interface ToolCallEntry {
  tool: string;
  args: Record<string, unknown>;
  result: string | null;
  timestamp: string;
}

/** A skill/hook the backend actually injected into THIS agent's system prompt,
 *  from the `agent_skills` SSE event (engine.py). This reflects what the agent
 *  really received, not just what the run attached. Distinct from
 *  `AttachedSkill`/`AttachedHook` (the pre-run composer-selection shape in
 *  SkillsHooksContext). */
export interface AttachedSkillEntry {
  name: string;
  source: string;
  content: string;
}

/** A hook the backend actually injected into THIS agent's system prompt, from
 *  the `agent_skills` SSE event's `attached_hooks` — mirrors the fields
 *  `render_behavioral_block` (agents/capabilities/hooks/behavioral.py) uses to
 *  synthesize the "Active Behavioral Hooks" prompt block. */
export interface AttachedHookEntry {
  name: string;
  event: string;
  trigger: string;
  description: string;
}

/** A single clarify question surfaced to the user during a run's clarify pause.
 *  Shared contract consumed by the inline clarify surfaces (InlineClarifyActions,
 *  StepsOverviewSpine, RunChatLane, PreviewPanel/AgentThinkingTab). Relocated here
 *  from the deleted QuestionnairePanel.tsx (Phase 42-02) so it survives the panel's
 *  removal. */
export interface ClarifyQuestion {
  id: string;
  question: string;
  options: string[];
  allowMultiple?: boolean;
  /** "single_choice" | "multi_select" | "short_text" | "hybrid" */
  answerType?: string;
  recommendedAnswer?: string;
  recommendedReasoning?: string;
  recommendedDisplay?: string;
  ambiguityCategory?: string;
  impactLevel?: string;
}

// Legacy alias — kept for callers that use the MCQQuestion type name.
export type MCQQuestion = ClarifyQuestion;

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
  // KAN-153 — total task count known as soon as the first task_loop_progress fires.
  // Sourced from the `total_tasks` field the backend emits on every task_loop_progress
  // event (task_loop.py). Lets the ConstructionBlock render ALL tasks as "pending"
  // upfront rather than one-by-one. Optional so history/reopen callers are unchanged.
  protoTotalTasks?: number;
  // KAN-153 — task titles parsed from the planner agent's output the moment
  // the first task_loop_progress fires. Indexed by 1-based task number so the
  // ConstructionBlock can show "Task 1 · HTML Shell & Navigation" upfront.
  // Optional; falls back to "Task N" placeholder when absent.
  protoPlannedTasks?: Array<{ number: number; title: string }>;
  // The 1-based task the loop most recently STARTED, and the agent running it —
  // both straight off `task_loop_progress` (task_loop.py:319-329), whose
  // `agent_id` the handler previously dropped on the floor. Without the agent id
  // the counters are pipeline-global and cannot be attributed to a row, so an
  // agent row had no way to say which of its tasks is in flight.
  protoCurrentTask?: number;
  protoTaskAgentId?: string;
  // Phase 13
  degraded?: boolean;
  degradedFailedAgents?: string[];
  // Phase 16
  failed?: boolean;
  failedAgents?: string[];
  // ISS-035 (Phase 32 / SC-4): additive terminal marker set by the
  // pipeline_cancelled reducer case (mirrors the `failed` marker). A downstream
  // selector (RunLaneState) derives the LIVE-STATE-CONTRACT §1 cancelled state
  // ("Cancelled by you" ack + relaunch) from this flag instead of falling
  // through to idle. Absent on non-cancelled runs.
  cancelled?: boolean;
  // KAN-73 — live audit trail from hook_run WS events
  hookRuns?: HookRunEntry[];
  // Workstream C1 (POR §6.2/§6.5) — answered clarify rounds retained per run so
  // they survive the questionnaire panel unmount (consumed by C2's ClarificationsCard).
  clarifications?: ClarifyRound[];
  // Phase 39 (RUNUI-06) — the settled deliverable's filename/version, surfaced
  // from the pipeline_complete event that ALREADY carries them (D39-4: the data
  // already flows). Lets the run lane render the mock's "Delivered as v{n} ·
  // <filename> · open in preview" card without a workflow-name branch (SC-001).
  // ADDITIVE optional — no existing field/handler/consumer changed.
  deliverableFilename?: string;
  deliverableVersion?: number;
  // Phase 39 (RUNUI-06) — the run's created_at (ISO), surfaced from pipeline_start
  // so the lane header can render a relative age ("23h ago") for a settled run.
  // ADDITIVE optional.
  createdAt?: string;
  // ISS-063/ISS-080 — the restart history of this run: per agent id, the durable
  // IDENTITIES (`event_id`, else `seq`) of the `agent_start` events seen so far. An
  // update_specs pass re-runs a contiguous head of the pipeline, so the number of
  // starts of the pipeline HEAD names the current spec-revision cycle (see
  // `deriveSpecRevisionCount`). Accumulated in the `agent_start` reducer and CARRIED
  // ACROSS a same-run `pipeline_start`: a resume or a replay-from-zero re-delivers
  // that frame after the revisions, and rebuilding the map there would erase the
  // history the banner is reporting.
  // A SET of identities, never a tally: a history reopen delivers every durable event
  // TWICE (the REST replay and the SSE replay), so anything shaped `+= 1` counts
  // deliveries instead of events and doubles. ADDITIVE optional.
  agentStartEventIds?: Record<string, string[]>;
  // ISS-082 — this run's frame-identity cursor, the reducer's OWN protection for the
  // fields that GROW out of their previous value (output, thinkingText, toolCalls,
  // validationIssues, hookRuns, agentStartEventIds). Until ISS-082 their correctness was
  // a property of the CALLERS' dedup, which is exactly what ISS-080 died of.
  //
  // `lastAppliedSeq` is the highest per-run `seq` already folded in. One cursor decides
  // every persisted frame in O(1), which is the whole point: `agent_chunk` is the
  // highest-volume frame in the system (~25k on one real run), so a per-frame id SET
  // copied immutably would be O(n^2) on replay. Sound because `seq` comes from ONE
  // monotonic per-run allocator (engine.execute), both transports carry it (live SSE
  // stamps data.seq; getRunEvents merges the authoritative column), and both replay
  // passes are seq-ordered.
  //
  // `appliedUnsequencedIds` is the fallback for frames the engine never stamps with a
  // `seq` — today only `hook_run`, which is pushed straight onto the live queue and so
  // never reaches the stamping chokepoint. Small by construction, because only unstamped
  // types can reach it.
  //
  // Both are ADDITIVE optional and reset on a pipeline_start that is NOT a same-run
  // re-announcement, so they never carry one run's high-water mark into the next (INV-2).
  lastAppliedSeq?: number;
  appliedUnsequencedIds?: string[];
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
