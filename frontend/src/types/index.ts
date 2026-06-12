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

export type WorkflowStatus = "running" | "completed" | "failed" | "cancelled";

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
    model_id?: string;
    per_agent?: Record<string, {
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
    }>;
  };
  modelId?: string;
  createdAt: string;
  completedAt?: string;
  duration?: number;
  agentCount: number;
  error?: string;
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
  modelId?: string;
  // Phase 2 (Universal Engine) — planner + gate state
  pipelineRunId?: string;            // UUID from planner_start, used for submit_questionnaire
  plannerStatus?: "idle" | "running" | "complete" | "timeout" | "error";
  plannerSummary?: string;           // inferred_intent shown while planning
  executionGate?: "PROCEED" | "CLARIFY_REQUIRED";
  clarificationLimitReached?: boolean;
  // Phase 3 (T063) — DAG edges from workflow_validated event
  dagEdges?: Array<{ from: string; to: string; artifact_type: string }>;
  unresolvedEdges?: Array<{ consuming_agent_id: string; artifact_type: string }>;
  // Prototype build progress — per-task completion from report_task_complete tool
  protoCompletedTasks?: Array<{ number: number; title: string; summary: string }>;
  protoCompletedTaskCount?: number;
  // Phase 13 (IN-03) — pipeline_complete arrived with status:"degraded":
  // the run produced a deliverable but the agents in degradedFailedAgents
  // errored and never completed (WR-05 semantics). Not a full success.
  degraded?: boolean;
  degradedFailedAgents?: string[];
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
