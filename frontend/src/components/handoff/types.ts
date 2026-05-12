/**
 * Local types for the /flowin-handoff feature.
 *
 * Kept inside the handoff folder so the feature is self-contained: nothing
 * here is referenced by the existing workflow / chat code, and nothing here
 * references workflow / chat types beyond the global `StreamMessage`
 * envelope (which is part of the shared WebSocket contract, not a
 * workflow-specific shape).
 */

export type HandoffAgentId = "coding_agent" | "test_agent" | "compliance_agent";

export type HandoffAgentStatus = "queued" | "thinking" | "complete" | "error";

export type HandoffPipelineStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "expired";

export interface HandoffEditPreview {
  path: string;
  operation: "create" | "modify" | "delete" | string;
  old_string: string;
  new_string: string;
}

export interface HandoffEditApplyResult {
  path: string;
  operation: string;
  status: "applied" | "rejected";
  reason?: string;
}

export interface HandoffTestReport {
  summary?: string;
  verdict?: "pass" | "concerns" | "fail" | string;
  tests_present?: { path: string; covers: string }[];
  missing_coverage?: { area: string; suggested_test: string }[];
  quality_issues?: { path: string; issue: string; severity: string }[];
  recommended_additions?: string[];
}

export interface HandoffComplianceFinding {
  category: string;
  severity: "low" | "medium" | "high" | "critical" | string;
  location: string;
  issue: string;
  recommendation: string;
}

export interface HandoffComplianceReport {
  summary?: string;
  verdict?: "approve" | "approve_with_changes" | "request_changes" | string;
  findings?: HandoffComplianceFinding[];
  positives?: string[];
}

export interface HandoffAgentState {
  agent_id: HandoffAgentId;
  name: string;
  status: HandoffAgentStatus;
  thinking?: string;
  summary?: string;
  rationale?: string;
  edits?: HandoffEditPreview[];
  edit_count?: number;
  tests_added?: string[];
  follow_ups?: string[];
  test_report?: HandoffTestReport;
  compliance_report?: HandoffComplianceReport;
  error?: string;
  started_at?: number;
  completed_at?: number;
}

export interface HandoffPhaseEvent {
  section: string;
  status: "start" | "end";
  data?: Record<string, unknown>;
  at: number;
}

export interface HandoffPipelineState {
  pipelineStatus: HandoffPipelineStatus;
  phases: HandoffPhaseEvent[];
  agents: Record<HandoffAgentId, HandoffAgentState>;
  editResults: HandoffEditApplyResult[];
  resolvedMode?: "coding" | "test";
  branchName?: string;
  prUrl?: string;
  prNumber?: number;
  error?: string;
  done: boolean;
}

/**
 * Wider event-envelope shape used inside the handoff feature.
 *
 * The shared ``StreamMessage`` type enumerates the event names the
 * existing workflow / chat code emits. The handoff pipeline emits a
 * few extras (``pr_created``, ``handoff_error``, ``handoff_ready``)
 * that don't belong in the global enum, so we narrow to a string at
 * the boundary of the handoff module without touching the shared
 * type.
 */
export interface HandoffStreamMessage {
  type: string;
  chunk?: string;
  section?: string;
  data?: Record<string, unknown>;
}

export const INITIAL_AGENTS: Record<HandoffAgentId, HandoffAgentState> = {
  coding_agent: { agent_id: "coding_agent", name: "Coding agent", status: "queued" },
  test_agent: { agent_id: "test_agent", name: "Test analysis", status: "queued" },
  compliance_agent: {
    agent_id: "compliance_agent",
    name: "Compliance review",
    status: "queued",
  },
};
