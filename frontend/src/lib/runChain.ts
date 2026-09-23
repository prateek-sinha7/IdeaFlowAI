/**
 * runChain — what a step spent its time doing, as a trail of kinds.
 *
 * `stepActivity(agent)` folds a step's reasoning, its tool calls and its output
 * into a short list of runs (`reason → read ×4 → write → output`) that the
 * ActivityTrail strip draws. Ported from the impeccable-redesign branch; the
 * tool vocabulary is this backend's (ls, file_info, edit_file, playwright_*,
 * ask_user), not a generic one.
 */

import type { AgentRunState } from "@/types/index";

export type ActivityKind =
  | "reason"
  | "read"
  | "write"
  | "search"
  | "run"
  | "browse"
  | "ask"
  | "tool"
  | "output";

export interface ActivityRun {
  kind: ActivityKind;
  /** How many consecutive calls of this kind were collapsed into this box. */
  count: number;
  /** Up to five distinct file paths the collapsed calls touched, in order. */
  paths?: string[];
  /** At least one collapsed call came back with an error result. */
  hasFailed?: boolean;
  /** The tool names collapsed into this box (distinct, in order). */
  tools?: string[];
}

/**
 * A tool call FAILED when its result came back as an error. A `null` result
 * means the result has not arrived yet (the store fills it on `tool_result`),
 * so it is never a failure — a live step's current call must not show "!".
 */
const FAILED_RESULT = /^\s*(?:error|traceback|exception|denied|permission denied|not found|no such file|failed)\b/i;
export function toolCallFailed(result: string | null | undefined): boolean {
  return typeof result === "string" && FAILED_RESULT.test(result);
}

/** Bookkeeping calls that say nothing about what the step did. */
const SILENT_TOOLS = /^(report_task_complete|done)$/i;

export function toolKind(tool: string): ActivityKind {
  const t = tool.toLowerCase();
  if (/playwright|browser|navigate|snapshot|screenshot|click|type_text/.test(t)) return "browse";
  if (/^ask_user$|clarify|question/.test(t)) return "ask";
  if (/^ls$|list|glob|grep|search|find/.test(t)) return "search";
  if (/read|open|fetch|get_file|file_info|^cat$|info$/.test(t)) return "read";
  if (/write|edit|create|append|patch|save|mkdir/.test(t)) return "write";
  if (/bash|exec|shell|command|^run|test/.test(t)) return "run";
  return "tool";
}

/** The first string-valued argument that looks like a file path. */
function extractPath(args: Record<string, unknown> | undefined): string | undefined {
  if (!args) return undefined;
  for (const key of ["path", "file_path", "filename", "file", "target", "url"]) {
    const v = args[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  for (const value of Object.values(args)) {
    if (typeof value === "string" && /[/.]/.test(value) && value.length < 200) return value;
  }
  return undefined;
}

type ToolCallLike = { tool: string; args?: Record<string, unknown>; result?: string | null };

/**
 * The trail for one step: reasoning first, then each tool call in order with
 * consecutive calls of one kind collapsed into a counted box, then the output.
 */
export function stepActivity(agent: {
  thinkingText?: string | null;
  output?: string | null;
  toolCalls?: ToolCallLike[] | null;
}): ActivityRun[] {
  const runs: ActivityRun[] = [];
  if (agent.thinkingText?.trim()) runs.push({ kind: "reason", count: 1 });

  for (const call of agent.toolCalls ?? []) {
    if (!call?.tool || SILENT_TOOLS.test(call.tool)) continue;
    const kind = toolKind(call.tool);
    const path = extractPath(call.args);
    const failed = toolCallFailed(call.result);
    const last = runs[runs.length - 1];
    if (last && last.kind === kind) {
      last.count += 1;
      if (path && !(last.paths ??= []).includes(path) && last.paths.length < 5) last.paths.push(path);
      if (!(last.tools ??= []).includes(call.tool)) last.tools.push(call.tool);
      if (failed) last.hasFailed = true;
    } else {
      runs.push({
        kind,
        count: 1,
        ...(path ? { paths: [path] } : {}),
        tools: [call.tool],
        ...(failed ? { hasFailed: true } : {}),
      });
    }
  }

  if (agent.output?.trim()) runs.push({ kind: "output", count: 1 });
  return runs;
}

/** Convenience for callers holding a full AgentRunState. */
export function agentActivity(agent: AgentRunState): ActivityRun[] {
  return stepActivity(agent);
}
