"use client";

/**
 * AuditTab — user-friendly audit trail for workflow runs (KAN-73).
 * Shows live entries during execution and persisted entries from history.
 * Designed for non-technical users: plain English, clear icons, no raw field names.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Shield, CheckCircle, AlertTriangle, XCircle,
  ChevronDown, Clock, Activity, Play, Flag,
  Lock, Eye, Info,
} from "lucide-react";
import type { HookRunEntry } from "@/types/index";
import { getRunHookRuns, getToken } from "@/lib/api";

interface AuditTabProps {
  hookRuns?: HookRunEntry[];
  workflowRunId?: string;
}

// ─── Human-readable hook descriptions ────────────────────────────────────────

/** What each hook type does, in plain English for the tooltip / detail panel. */
const HOOK_DESCRIPTIONS: Record<string, { label: string; description: string }> = {
  audit_logger: {
    label: "Activity Log",
    description: "Tracks when each agent starts and finishes running.",
  },
  secret_scan: {
    label: "Security Check",
    description: "Scans the agent's output for sensitive data like passwords or API keys before saving it.",
  },
  otel_tracing: {
    label: "Performance Trace",
    description: "Records timing and performance data for this agent step.",
  },
  behavioral: {
    label: "Behavioral Guideline",
    description: "A custom hook you added via the workflow configuration. It was injected as a behavioural instruction into each agent's system prompt for this run.",
  },
};

function hookInfo(hookName: string) {
  return HOOK_DESCRIPTIONS[hookName] ?? {
    label: hookName,
    description: "An automated check that ran during this step.",
  };
}

// For tool events, override the description shown in "What is this?"
function entryDescription(hook: string, event: string): string {
  if (event === "tool_call") return "Records every tool the agent invoked — e.g. reading a file, running a search, or calling an API.";
  if (event === "tool_result") return "Records the result returned to the agent after each tool call.";
  return hookInfo(hook).description;
}

// ─── Tool name → friendly label ───────────────────────────────────────────────
function friendlyToolName(tool: string): string {
  const MAP: Record<string, string> = {
    read_file: "Read file", write_file: "Write file", list_files: "List files",
    run_command: "Run command", search_files: "Search files",
    report_task_complete: "Mark task complete", spawn_subagents: "Spawn sub-agents",
    web_search: "Web search", fetch_url: "Fetch URL",
    create_file: "Create file", delete_file: "Delete file",
    execute_code: "Execute code", git_commit: "Git commit", git_push: "Git push",
  };
  return MAP[tool] ?? tool.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Outcome helpers ──────────────────────────────────────────────────────────

function OutcomeIcon({ outcome }: { outcome: string }) {
  if (outcome === "block")
    return <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />;
  if (outcome === "warn")
    return <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0" />;
  return <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />;
}

function outcomeBadge(outcome: string) {
  if (outcome === "block")
    return <span className="text-[10px] font-semibold text-red-600 bg-red-50 px-1.5 py-0.5 rounded-full">Blocked</span>;
  if (outcome === "warn")
    return <span className="text-[10px] font-semibold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">Warning</span>;
  return <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-full">Passed</span>;
}

// ─── Event icon ───────────────────────────────────────────────────────────────

function EventIcon({ event }: { event: string }) {
  if (event === "before_step")
    return <Play className="h-2.5 w-2.5 text-blue-400" />;
  if (event === "after_step")
    return <Flag className="h-2.5 w-2.5 text-indigo-400" />;
  if (event === "before_write")
    return <Lock className="h-2.5 w-2.5 text-amber-400" />;
  if (event === "tool_call")
    return <Activity className="h-2.5 w-2.5 text-violet-400" />;
  if (event === "tool_result")
    return <CheckCircle className="h-2.5 w-2.5 text-teal-400" />;
  return <Eye className="h-2.5 w-2.5 text-gray-400" />;
}

function eventLabel(event: string): string {
  if (event === "before_step") return "Agent started";
  if (event === "after_step") return "Agent completed";
  if (event === "before_write") return "Output security scan";
  if (event === "pre_commit") return "Pre-save check";
  if (event === "tool_call") return "Tool used";
  if (event === "tool_result") return "Tool result";
  return event;
}

// ─── Time formatter ───────────────────────────────────────────────────────────

function formatTime(iso?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return ""; }
}

// ─── Build user-friendly title + detail rows ─────────────────────────────────

interface DetailRow { label: string; value: string; highlight?: boolean }

function buildEntryContent(entry: HookRunEntry): {
  title: string;
  subtitle: string;
  rows: DetailRow[];
} {
  const detail = entry.detail ?? {};
  const hook = entry.hook;
  const event = entry.event;
  const agentName = (detail.agent_name as string) || (detail.agent_id as string) || "Agent";
  const { label: hookLabel } = hookInfo(hook);

  // ── tool_call — check BEFORE audit_logger (same hook, different event) ──────
  if (event === "tool_call") {
    const tool = (detail.tool as string) || "unknown";
    const argsSummary = (detail.args_summary as string) || "";
    return {
      title: `Tool used: ${friendlyToolName(tool)}`,
      subtitle: `Tool call · ${agentName} invoked a tool`,
      rows: [
        { label: "Agent", value: agentName },
        { label: "Tool", value: friendlyToolName(tool) },
        ...(argsSummary ? [{ label: "Parameters", value: argsSummary }] : []),
        { label: "Status", value: "Invoked successfully" },
      ],
    };
  }

  // ── tool_result — check BEFORE audit_logger (same hook, different event) ─
  if (event === "tool_result") {
    const tool = (detail.tool as string) || "unknown";
    const preview = (detail.result_preview as string) || "";
    return {
      title: `Tool result received: ${friendlyToolName(tool)}`,
      subtitle: `Tool call · ${agentName} received tool output`,
      rows: [
        { label: "Agent", value: agentName },
        { label: "Tool", value: friendlyToolName(tool) },
        ...(preview ? [{ label: "Output preview", value: preview }] : []),
        { label: "Status", value: "Result returned" },
      ],
    };
  }

  // ── audit_logger (lifecycle events only: before_step / after_step) ────────
  if (hook === "audit_logger") {
    const isStart = event === "before_step";
    const taskIndex = (detail.step_index as number) ?? 0;
    // For task-loop agents (step_index > 0 on same agent), show task number
    const taskLabel = taskIndex > 0 ? ` (Task ${taskIndex + 1})` : "";
    const title = isStart
      ? `${agentName} started${taskLabel}`
      : `${agentName} finished${taskLabel}`;
    const subtitle = isStart
      ? "Activity log · Agent began executing"
      : "Activity log · Agent completed successfully";

    const rows: DetailRow[] = [
      { label: "Agent", value: agentName },
      { label: "Step", value: `Step ${taskIndex + 1}` },
      { label: "Check type", value: "Activity logging" },
      { label: "Result", value: "Recorded successfully" },
    ];
    return { title, subtitle, rows };
  }

  // ── secret_scan ───────────────────────────────────────────────────────────
  if (hook === "secret_scan") {
    const matched = detail.matched as boolean | undefined;
    const isClean = !matched;
    const title = isClean
      ? "Security scan passed — no sensitive data found"
      : "Security scan blocked — sensitive data detected";
    const subtitle = isClean
      ? "Security check · Output is safe to save"
      : "Security check · Output was not saved";

    const rows: DetailRow[] = [
      { label: "Check type", value: "Sensitive data scan (passwords, API keys, tokens)" },
      {
        label: "Result",
        value: isClean ? "Clean — nothing sensitive found" : "Blocked — sensitive content detected",
        highlight: !isClean,
      },
    ];
    if (!isClean && detail.marker) {
      rows.push({ label: "Pattern matched", value: "Credential-like value (not shown for security)", highlight: true });
    }
    return { title, subtitle, rows };
  }

  // ── behavioral (attached hooks from workflow config popup) ───────────────
  if (hook === "behavioral") {
    const hookName = (detail.hook_name as string) || agentName;
    const eventType = (detail.event_type as string) || "";
    const desc = (detail.description as string) || "";
    return {
      title: `Behavioral guideline active: ${hookName}`,
      subtitle: `Workflow hook · injected into all agents for this run`,
      rows: [
        { label: "Hook name", value: hookName },
        { label: "Fires on", value: eventType },
        { label: "What it does", value: desc },
        { label: "Status", value: "Active for this run" },
      ],
    };
  }
  if (hook === "otel_tracing") {
    return {
      title: "Performance trace recorded",
      subtitle: "Performance trace · Timing data captured",
      rows: [
        { label: "Check type", value: "Performance monitoring" },
        { label: "Result", value: "Timing data recorded" },
      ],
    };
  }

  // ── Generic fallback ──────────────────────────────────────────────────────
  const fallbackSummary = (detail.summary as string) || `${hookLabel}: ${eventLabel(event)}`;
  return {
    title: fallbackSummary,
    subtitle: `${hookLabel} · ${eventLabel(event)}`,
    rows: [
      { label: "Check type", value: hookLabel },
      { label: "Event", value: eventLabel(event) },
      { label: "Result", value: entry.outcome === "block" ? "Blocked" : entry.outcome === "warn" ? "Warning" : "Passed" },
    ],
  };
}

// ─── Single audit entry card ──────────────────────────────────────────────────

function AuditEntry({ entry, index }: { entry: HookRunEntry; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const ts = (entry.detail?.timestamp as string | null) || entry.created_at;
  const isToolEvent = entry.event === "tool_call" || entry.event === "tool_result";
  const { label: hookLabel } = isToolEvent
    ? { label: entry.event === "tool_call" ? "Tool Call" : "Tool Result" }
    : hookInfo(entry.hook);
  const resolvedDesc = entryDescription(entry.hook, entry.event);
  const { title, subtitle, rows } = buildEntryContent(entry);

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, delay: Math.min(index * 0.04, 0.5) }}
      className="rounded-xl border border-gray-100 bg-white overflow-hidden shadow-[0_1px_3px_rgba(0,0,0,0.04)]"
    >
      {/* ── Collapsed row ── */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center gap-3 px-3.5 py-3 text-left hover:bg-gray-50/70 transition-colors"
        aria-expanded={expanded}
      >
        <OutcomeIcon outcome={entry.outcome} />

        <div className="flex-1 min-w-0">
          {/* Main title */}
          <p className="text-[12px] font-semibold text-gray-800 leading-snug truncate">
            {title}
          </p>
          {/* Sub-line: hook label + time */}
          <div className="flex items-center gap-1.5 mt-0.5">
            <EventIcon event={entry.event} />
            <span className="text-[10px] text-gray-500">{hookLabel}</span>
            {ts && (
              <>
                <span className="text-[10px] text-gray-300">·</span>
                <Clock className="h-2.5 w-2.5 text-gray-400" />
                <span className="text-[10px] text-gray-400">{formatTime(ts)}</span>
              </>
            )}
          </div>
        </div>

        {outcomeBadge(entry.outcome)}

        <ChevronDown
          className={`h-3.5 w-3.5 text-gray-400 flex-shrink-0 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {/* ── Expanded detail ── */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="border-t border-gray-100 bg-gray-50/60 px-3.5 py-3 space-y-3">

              {/* What is this check? */}
              <div className="flex items-start gap-2 rounded-lg bg-blue-50/60 border border-blue-100/60 px-3 py-2">
                <Info className="h-3.5 w-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-[10px] font-semibold text-blue-700 uppercase tracking-wide mb-0.5">
                    What is this?
                  </p>
                  <p className="text-[11px] text-blue-700/80 leading-relaxed">
                    {resolvedDesc}
                  </p>
                </div>
              </div>

              {/* Detail rows */}
              <div className="space-y-1.5">
                {rows.map((row) => (
                  <div key={row.label} className="flex items-start gap-2">
                    <span className="text-[10px] text-gray-400 min-w-[100px] flex-shrink-0 pt-px">
                      {row.label}
                    </span>
                    <span className={`text-[11px] font-medium leading-snug ${
                      row.highlight ? "text-red-600" : "text-gray-700"
                    }`}>
                      {row.value}
                    </span>
                  </div>
                ))}
              </div>

              {/* Subtitle tag */}
              <p className="text-[9px] text-gray-400 italic">{subtitle}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── Main AuditTab component ──────────────────────────────────────────────────

export function AuditTab({ hookRuns, workflowRunId }: AuditTabProps) {
  const [historicRuns, setHistoricRuns] = useState<HookRunEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!workflowRunId || (hookRuns && hookRuns.length > 0)) return;
    const token = getToken();
    if (!token) return;
    setLoading(true);
    getRunHookRuns(token, workflowRunId)
      .then((res) => {
        setHistoricRuns(res.hook_runs.map((r) => ({
          id: r.id,
          hook: r.hook,
          event: r.event,
          outcome: r.outcome,
          detail: r.detail as HookRunEntry["detail"],
          created_at: r.created_at,
        })));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [workflowRunId, hookRuns]);

  const entries = (hookRuns && hookRuns.length > 0) ? hookRuns : historicRuns;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-[11px] text-gray-400">Loading audit trail…</p>
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
        <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
          <Shield className="h-5 w-5 text-gray-400" />
        </div>
        <div>
          <p className="text-[12px] font-medium text-gray-600">No audit records yet</p>
          <p className="text-[11px] text-gray-400 mt-1 leading-relaxed max-w-[200px]">
            Automatic checks will appear here as each agent runs.
          </p>
        </div>
      </div>
    );
  }

  // Count by outcome
  const passCount = entries.filter(e => e.outcome === "continue" || e.outcome === "pass").length;
  const warnCount = entries.filter(e => e.outcome === "warn").length;
  const blockCount = entries.filter(e => e.outcome === "block").length;

  // Count by check type for the header
  const activityCount = entries.filter(e =>
    e.hook === "audit_logger" && (e.event === "before_step" || e.event === "after_step")
  ).length;
  const toolCallCount = entries.filter(e => e.event === "tool_call" || e.event === "tool_result").length;
  const securityCount = entries.filter(e => e.hook === "secret_scan").length;
  const behavioralCount = entries.filter(e => e.hook === "behavioral").length;

  return (
    <div className="flex flex-col h-full">

      {/* ── Header: what this tab is ── */}
      <div className="flex-shrink-0 px-4 pt-3 pb-2 border-b border-gray-100 bg-white">
        <div className="flex items-center gap-2 mb-1.5">
          <Shield className="h-3.5 w-3.5 text-indigo-500 flex-shrink-0" />
          <span className="text-[12px] font-semibold text-gray-700">
            Automated Checks
          </span>
          <span className="ml-auto text-[10px] text-gray-400">{entries.length} records</span>
        </div>
        <p className="text-[10px] text-gray-400 leading-relaxed mb-2">
          Every agent run is automatically monitored. These checks run silently in the background — no action needed from you.
        </p>

        {/* Check type pills */}
        <div className="flex items-center gap-2 flex-wrap">
          {activityCount > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">
              <Activity className="h-2.5 w-2.5" />
              {activityCount} activity logs
            </span>
          )}
          {toolCallCount > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full border border-violet-100">
              <Eye className="h-2.5 w-2.5" />
              {toolCallCount} tool calls
            </span>
          )}
          {securityCount > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-purple-600 bg-purple-50 px-2 py-0.5 rounded-full border border-purple-100">
              <Lock className="h-2.5 w-2.5" />
              {securityCount} security scans
            </span>
          )}
          {behavioralCount > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full border border-orange-100">
              <Shield className="h-2.5 w-2.5" />
              {behavioralCount} workflow hooks
            </span>
          )}
          <span className="ml-auto flex items-center gap-1 text-[10px] text-emerald-600 font-semibold">
            <CheckCircle className="h-3 w-3" />
            {passCount} passed
            {warnCount > 0 && (
              <span className="text-amber-500 ml-1">· {warnCount} warning</span>
            )}
            {blockCount > 0 && (
              <span className="text-red-500 ml-1">· {blockCount} blocked</span>
            )}
          </span>
        </div>
      </div>

      {/* ── Entry list ── */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {entries.map((entry, idx) => (
          <AuditEntry
            key={entry.id || `${entry.hook}-${entry.event}-${idx}`}
            entry={entry}
            index={idx}
          />
        ))}
      </div>
    </div>
  );
}
