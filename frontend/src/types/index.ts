export interface User {
  id: string;
  email: string;
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
  type: "stream" | "complete" | "error" | "phase_start" | "phase_end" | "title_update" | "step" | "pipeline_start" | "agent_start" | "agent_thinking" | "agent_chunk" | "agent_complete" | "agent_error" | "pipeline_complete" | "questionnaire";
  chunk?: string;
  section?: string;
  data?: FinalOutput | ErrorDetail | ProcessStep | Record<string, unknown>;
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

export type WorkflowType = "user_stories" | "ppt" | "prototype" | "validate_pitch" | "app_builder" | "reverse_engineer" | "custom";

export type WorkflowStatus = "running" | "completed" | "failed";

export interface WorkflowRun {
  id: string;
  title: string;
  type: WorkflowType;
  status: WorkflowStatus;
  input: string;
  output?: string;
  agentOutputs?: AgentThinkingEntry[];
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
}

export interface PipelineConfig {
  pipeline_type: string;
  agents: AgentDef[];
  total_estimated_duration: number;
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
}

export interface PipelineRunState {
  isRunning: boolean;
  pipeline_type: string;
  agents: AgentRunState[];
  currentAgentIndex: number;
  totalDuration: number | null;
  completedCount: number;
}

export type PipelineMessageType =
  | "pipeline_start"
  | "agent_start"
  | "agent_thinking"
  | "agent_chunk"
  | "agent_complete"
  | "agent_error"
  | "pipeline_complete";
