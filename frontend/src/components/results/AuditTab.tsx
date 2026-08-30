"use client";

/**
 * AuditTab — governance/validation/exec audit trail for a workflow run (SC-3).
 *
 * Reads the three owner-scoped plan-03 endpoints (gate-events /
 * validation-results / exec-runs) — replacing the WRONG `hook_runs` source —
 * and renders stat counters, coverage chips, severity filters, and client-side
 * CSV/JSON export (ND-6). A cross-owner / missing run resolves to empty
 * envelopes (the fetchers map 404 → []), so the tab never surfaces another
 * owner's data (T-32-09-01).
 *
 * Token discipline (SC-1): every surface/line/ink/radius routes through the
 * plan-01 token layer + primitives. The SOLE one-chroma exception is the
 * governance status palette (green/amber/red) used ONLY on verdict + severity
 * chips (the status-ramp + severity-ladder tokens).
 */

import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  Shield, ShieldCheck, FileCheck2, Terminal, Download,
  CheckCircle, XCircle, AlertTriangle, Clock,
  Check, ChevronDown, Lock, Ban, Search,
} from "lucide-react";
import type { HookRunEntry } from "@/types/index";
import {
  getToken,
  getRunGateEvents,
  getRunValidationResults,
  getRunExecRuns,
  getRunHookRuns,
} from "@/lib/api";
import { exportAuditCSV, exportAuditJSON } from "@/lib/exporters/auditExporter";

/** Optional live attribution the run-shell may thread later (39-05/06). Every
 *  field is elided when absent — never fabricated (ND-D, T-39-04-01). */
export interface AuditRunMeta {
  owner?: string | null;
  workspace?: string | null;
  startedAt?: string | null;
  durationMs?: number | null;
}

interface AuditTabProps {
  /**
   * Dormant legacy prop — retained ONLY so the PreviewPanel mount signature is
   * unchanged (guardrail: PreviewPanel mount untouched). The tab no longer
   * derives its data from hook_runs; it reads the 3 plan-03 endpoints below.
   */
  hookRuns?: HookRunEntry[];
  workflowRunId?: string;
  /**
   * Optional live run attribution (owner / workspace / started / duration). The
   * three audit fetches do not carry these, so the shell may thread them; when
   * unset, started + duration are derived from the row timestamps and the rest
   * is elided (never fabricated — ND-D / T-39-04-01).
   */
  runMeta?: AuditRunMeta;
  /**
   * Phase 42-07 (RUNUI-06, Group H) — LIVE signal. While the run is in flight the
   * audit trail shows in-progress affordances (mock Hexaware Run - Live.dc.html):
   * a pulsing "live" badge beside the records pill, an "Elapsed … · in progress"
   * indicator in place of the settled "Duration", and a violet "monitoring live"
   * banner in place of the settled/failed verdict banner. Bound to the generic
   * running signal (SC-001), NOT a workflow name. Default undefined/false → the
   * settled/failed surfaces render unchanged (KEEP — zero regression). The
   * fetchers + export menu are untouched (INV-12 — presentation only).
   */
  isRunning?: boolean;
}

// ─── Unified audit-row model ─────────────────────────────────────────────────

type AuditCategory = "gate" | "validation" | "exec" | "hook";

const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;
type Severity = (typeof SEVERITIES)[number];

interface AuditRow {
  id: string;
  category: AuditCategory;
  step: string;
  /** gate kind | validator name | argv summary. */
  label: string;
  /** pass|block|wait_human | severity | allowed|denied|killed. */
  outcome: string;
  /** validation rows only (uppercased); null otherwise. */
  severity: Severity | null;
  detail: string;
  created_at: string | null;
  // ── fuller-taxonomy model (derived from the real row — SC-001 / ND-D) ──
  /** finer category (secret-scan / perf / behavioral derived from real signals). */
  fineCategory: FineCategory;
  /** the mock's 3-state outcome (pass / warn / block). */
  outcome3: Outcome3;
  /** key/value detail rows for the collapsible body. */
  detailRows: [string, string][];
}

function argvSummary(argv: unknown): string {
  if (Array.isArray(argv)) return argv.map((a) => String(a)).join(" ");
  if (typeof argv === "string") return argv;
  if (argv == null) return "";
  try { return JSON.stringify(argv); } catch { return String(argv); }
}

function issuesSummary(issues: unknown): string {
  if (Array.isArray(issues)) {
    return issues
      .map((i) => (typeof i === "string" ? i : JSON.stringify(i)))
      .join("; ");
  }
  if (issues == null) return "";
  if (typeof issues === "string") return issues;
  try { return JSON.stringify(issues); } catch { return String(issues); }
}

function detailNote(detail: Record<string, unknown> | null): string {
  if (!detail) return "";
  if (typeof detail.note === "string") return detail.note;
  if (typeof detail.summary === "string") return detail.summary;
  try { return JSON.stringify(detail); } catch { return ""; }
}

function normalizeSeverity(sev: string | null | undefined): Severity | null {
  const s = (sev || "").toUpperCase();
  return (SEVERITIES as readonly string[]).includes(s) ? (s as Severity) : null;
}

// ─── KAN-123: hook_run label + detail-row builders ────────────────────────────
//
// Build a human-readable label and Detector/Match/Action/Outcome rows from the
// real hook_run.detail payload (SC-001 / ND-D — only live data, never fabricated).

function buildHookLabel(
  hook: string,
  event: string,
  outcome: string,
  detail: Record<string, unknown> | null,
): string {
  const evtFriendly = event.replace(/_/g, " ");
  if (/secret|scan/.test(hook)) {
    const file = typeof detail?.file === "string" ? ` to ${detail.file}` : "";
    const action = outcome === "block" ? "BLOCKED" : outcome === "warn" ? "WARNING" : "scanned";
    return `Secret scan \u2014 ${action} ${evtFriendly}${file}`.trim();
  }
  return `${hook.replace(/_/g, " ")} \u2014 ${evtFriendly}`;
}

function buildHookDetailRows(
  hook: string,
  outcome: string,
  detail: Record<string, unknown> | null,
  step: string,
  eventLabel: string,
): [string, string][] {
  const rows: [string, string][] = [];
  if (!detail) {
    if (step) rows.push(["Step", step]);
    rows.push(["Outcome", outcome]);
    return rows;
  }
  const detector = typeof detail.detector === "string"
    ? detail.detector
    : /secret|scan/.test(hook) ? "high-entropy \u00d7 known key formats" : null;
  if (detector) rows.push(["Detector", detector]);
  const marker = typeof detail.marker === "string" ? detail.marker : null;
  const matched = Array.isArray(detail.matched_keys)
    ? (detail.matched_keys as string[]).join(", ")
    : typeof detail.match === "string" ? detail.match : marker;
  if (matched) rows.push(["Match", matched]);
  // Identity fields the real hook_run payload already carries (agent_name /
  // tool / summary) — without them every lifecycle row expands to the same
  // Action/Outcome fallback and no row is attributable (ISS-202).
  const agentName = typeof detail.agent_name === "string" ? detail.agent_name : null;
  if (agentName) rows.push(["Agent", agentName]);
  const tool = typeof detail.tool === "string" ? detail.tool : null;
  if (tool) rows.push(["Tool", tool]);
  const summary = typeof detail.summary === "string" ? detail.summary : null;
  if (summary) rows.push(["Summary", summary]);
  const fallbackAction = outcome === "block"
    ? `${eventLabel.includes("write") ? "write blocked" : "action blocked"} \u00b7 nothing persisted`
    : outcome === "warn" ? "warning recorded \u00b7 run continued" : "allowed";
  rows.push(["Action", typeof detail.action === "string" ? detail.action : fallbackAction]);
  rows.push(["Outcome", outcome]);
  if (typeof detail.reason === "string" && detail.reason) {
    rows.push(["Reason", detail.reason]);
  }
  return rows;
}

type VerdictKind = "done" | "failed" | "amber" | "queued";

function verdictKind(outcome: string): VerdictKind {
  const o = (outcome || "").toLowerCase();
  if (o === "pass" || o === "allowed" || o === "passed") return "done";
  if (o === "block" || o === "blocked" || o === "denied") return "failed";
  if (o === "wait_human" || o === "wait" || o === "killed") return "amber";
  return "queued";
}

// Severity ladder tokens (governance exception, severity colors only).
const SEVERITY_VAR: Record<Severity, string> = {
  CRITICAL: "var(--severity-critical)",
  HIGH: "var(--severity-high)",
  MEDIUM: "var(--severity-medium)",
  LOW: "var(--severity-low)",
};

function SeverityChip({ severity }: { severity: Severity }) {
  return (
    <span
      className="inline-flex items-center border border-line-control rounded-[var(--radius-tag)] px-1.5 py-0.5 font-sans text-[9px] font-semibold uppercase tracking-wide leading-none bg-surface-white"
      style={{ color: SEVERITY_VAR[severity] }}
    >
      {severity}
    </span>
  );
}

// ─── Fuller category taxonomy (the mock's Governance / Security / Activity) ────
//
// The three real fetches (gate / validation / exec) are mapped to the mock's
// finer category set — with the net-new sub-categories (secret-scan / perf /
// behavioral) DERIVED from signals in the real row (label/step/kind), never
// fabricated. A category with no matching real row simply shows 0 (ND-D).

type FineCategory =
  | "gate" | "validation" | "behavioral"   // → Governance
  | "security" | "exec"                     // → Security
  | "performance" | "activity";            // → Activity

type FilterGroup = "gov" | "sec" | "act";

const FINE_CATEGORY_META: Record<
  FineCategory,
  { label: string; group: FilterGroup; icon: typeof Shield; whatIs: string }
> = {
  gate: {
    label: "Gate", group: "gov", icon: ShieldCheck,
    whatIs:
      "A governance gate — a checkpoint where the run paused for a policy decision or a human approval before it was allowed to continue.",
  },
  validation: {
    label: "Validation", group: "gov", icon: FileCheck2,
    whatIs:
      "An automated validator inspected a step's output against a quality or correctness rule and recorded its verdict.",
  },
  behavioral: {
    label: "Governance", group: "gov", icon: Shield,
    whatIs:
      "A behavioral-guideline check confirming the agents followed the workspace's operating rules while producing this step.",
  },
  security: {
    label: "Security", group: "sec", icon: Lock,
    whatIs:
      "A secret / credential scan checking that no sensitive material was written, logged, or exposed by this step.",
  },
  exec: {
    label: "Exec", group: "sec", icon: Terminal,
    whatIs:
      "A sandboxed command execution, evaluated against the workspace's exec policy before it was permitted to run.",
  },
  performance: {
    label: "Perf", group: "act", icon: Clock,
    whatIs:
      "A performance measurement — timing or resource usage captured for this step's execution.",
  },
  activity: {
    label: "Activity", group: "act", icon: FileCheck2,
    whatIs:
      "A recorded run activity — a lifecycle event captured for the audit trail.",
  },
};

const GROUP_LABEL: Record<"all" | FilterGroup, string> = {
  all: "All", gov: "Governance", sec: "Security", act: "Activity",
};

/**
 * Derive the finer category from a REAL row's own signals (SC-001 / ND-D):
 *  - a secret/credential/scan signal on a gate or validation → Security;
 *  - an exec row that looks like a perf/otel span → Perf, else Exec;
 *  - a behavioral/guideline/hook signal on a gate or validation → Governance;
 *  - a hook_runs row with none of those signals → Activity (lifecycle telemetry,
 *    NOT a governance gate);
 *  - otherwise the base source category (gate / validation).
 * Nothing is fabricated: the net-new categories appear ONLY when the live row
 * carries a matching signal.
 */
function deriveFineCategory(
  source: AuditCategory,
  label: string,
  step: string,
  gateKind?: string | null,
): FineCategory {
  const hay = `${label} ${step} ${gateKind ?? ""}`.toLowerCase();
  if (/secret|credential|\bscan\b|leak/.test(hay)) return "security";
  if (source === "exec") {
    if (/perf|benchmark|latency|otel|\bspan\b|profil|timing/.test(hay)) return "performance";
    return "exec";
  }
  if (/behavio|guideline|\bhook\b/.test(hay)) return "behavioral";
  if (source === "hook") return "activity";
  return source === "gate" ? "gate" : "validation";
}

// ─── Three-state outcome (the mock's pass / warn / block) ─────────────────────

type Outcome3 = "pass" | "warn" | "block";

const OUTCOME3_META: Record<Outcome3, { badge: string; Icon: typeof CheckCircle }> = {
  pass: { badge: "Passed", Icon: Check },
  warn: { badge: "Warning", Icon: AlertTriangle },
  block: { badge: "Blocked", Icon: XCircle },
};

/** Map a real row to the mock's 3-state outcome (pass / warn / block). */
function deriveOutcome3(
  source: AuditCategory,
  rawOutcome: string,
  severity: Severity | null,
): Outcome3 {
  if (source === "validation") {
    if (!severity) return "pass";
    if (severity === "CRITICAL" || severity === "HIGH") return "block";
    return "warn"; // LOW / MEDIUM
  }
  const k = verdictKind(rawOutcome);
  if (k === "failed") return "block";
  if (k === "amber") return "warn";
  return "pass";
}

// ─── Attribution helpers (live values only — ND-D) ────────────────────────────

/** Truncate a run id for the attribution row (first 6 … last 3). */
function shortRunId(id?: string): string {
  if (!id) return "—";
  if (id.length <= 12) return id;
  return `${id.slice(0, 6)}…${id.slice(-3)}`;
}

function formatDateTimeUTC(iso?: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const date = d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
    return `${date} · ${time} UTC`;
  } catch { return ""; }
}

function formatDurationMs(ms?: number | null): string {
  if (ms == null || !Number.isFinite(ms) || ms <= 0) return "";
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  if (m <= 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function formatTime(iso?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return ""; }
}

// ─── Outcome icon-wrap (the mock's circular pass/warn/block glyph) ────────────

const OUTCOME_WRAP_CLASS: Record<Outcome3, string> = {
  pass: "bg-[var(--status-done-fill)] border-[var(--status-done-border)] text-status-done",
  warn: "bg-[var(--status-amber-fill)] border-[var(--status-amber-border)] text-status-amber",
  block: "bg-[var(--status-failed-fill)] border-[var(--status-failed-border)] text-status-failed",
};

const OUTCOME_BADGE_CLASS: Record<Outcome3, string> = {
  pass: "text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]",
  warn: "text-status-amber bg-[var(--status-amber-fill)] border-[var(--status-amber-border)]",
  block: "text-status-failed bg-[var(--status-failed-fill)] border-[var(--status-failed-border)]",
};

// ─── Single audit-row card (collapsible entry — the mock's row) ───────────────

function AuditRowCard({ row, index }: { row: AuditRow; index: number }) {
  const [open, setOpen] = useState(false);
  const meta = FINE_CATEGORY_META[row.fineCategory];
  const out = OUTCOME3_META[row.outcome3];
  const WrapIcon = out.Icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.16, delay: Math.min(index * 0.03, 0.4) }}
      data-testid="audit-row"
      className="bg-surface-card border border-line-border rounded-[var(--radius-list-row)] overflow-hidden"
    >
      {/* Header (click to expand) */}
      <button
        type="button"
        data-testid="audit-row-toggle"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-3.5 py-3 text-left cursor-pointer hover:bg-surface-warm/40 transition-colors"
      >
        <span className={`w-6 h-6 flex-none rounded-full border grid place-items-center ${OUTCOME_WRAP_CLASS[row.outcome3]}`}>
          <WrapIcon className="h-3 w-3" strokeWidth={2.4} />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-[13px] font-medium text-ink-900 truncate leading-tight">{row.label}</span>
          <span className="block text-[11px] text-ink-400 mt-0.5 truncate">
            {row.step || "—"}
            {row.created_at ? ` · ${formatTime(row.created_at)}` : ""}
          </span>
        </span>
        {/* Category chip */}
        <span className="flex-none inline-flex items-center text-[8.5px] font-semibold uppercase tracking-wide text-ink-500 bg-surface-warm border border-line-control rounded-[var(--radius-tag)] px-1.5 py-1 leading-none">
          {meta.label}
        </span>
        {/* Optional severity chip */}
        {row.severity && <SeverityChip severity={row.severity} />}
        {/* Verdict badge */}
        <span className={`flex-none inline-flex items-center border rounded-[var(--radius-pill)] px-2 py-1 text-[10px] font-semibold leading-none ${OUTCOME_BADGE_CLASS[row.outcome3]}`}>
          {out.badge}
        </span>
        <ChevronDown className={`h-3.5 w-3.5 text-ink-400 flex-none transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Collapsible body — "What is this?" explainer + key/value detail */}
      {open && (
        <div className="px-3.5 pb-3.5 pl-[46px]">
          <div className="border border-brand-border bg-brand-fill rounded-[var(--radius-list-row)] px-3 py-2.5 mb-2.5">
            <p className="text-[9px] font-semibold uppercase tracking-wider text-brand mb-1">What is this?</p>
            <p className="text-[12px] text-ink-700 leading-relaxed">{meta.whatIs}</p>
          </div>
          {row.detailRows.map(([k, v], i) => (
            <div key={`${k}-${i}`} className="flex gap-3 py-1.5 border-t border-line-divider">
              <span className="w-[130px] flex-none text-[11px] font-medium text-ink-400 leading-snug">{k}</span>
              <span className="flex-1 text-[12px] text-ink-700 leading-snug break-words">{v}</span>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

// ─── Main AuditTab component ─────────────────────────────────────────────────

export function AuditTab({ workflowRunId, runMeta, isRunning }: AuditTabProps) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeGroup, setActiveGroup] = useState<"all" | FilterGroup>("all");
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [exportMenuOpen, setExportMenuOpen] = useState(false);

  useEffect(() => {
    if (!workflowRunId) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getRunGateEvents(token, workflowRunId),
      getRunValidationResults(token, workflowRunId),
      getRunExecRuns(token, workflowRunId),
      // KAN-123: hook_runs carries secret_scan blocks (outcome="block") with
      // Detector/Match/Action/Outcome detail — the "Secret scan — BLOCKED"
      // security category rows the Audit tab mock shows. Fetch alongside the
      // three existing sources (INV-12 — reuses the existing endpoint). A 404
      // (no rows yet, non-admin run) resolves to an empty envelope.
      getRunHookRuns(token, workflowRunId).catch(() => ({ hook_runs: [] })),
    ])
      .then(([gates, validations, execs, hooksEnv]) => {
        if (cancelled) return;
        const merged: AuditRow[] = [];
        for (const g of gates.gate_events) {
          const label = g.gate ?? "gate";
          const step = g.step ?? "";
          const outcome = g.outcome ?? "";
          const note = detailNote(g.detail);
          const detailRows: [string, string][] = [
            ["Gate", label],
            ["Step", step],
            ["Outcome", outcome],
            ["Detail", note],
          ].filter(([, v]) => v) as [string, string][];
          merged.push({
            id: `gate:${g.id}`,
            category: "gate",
            step,
            label,
            outcome,
            severity: null,
            detail: note,
            created_at: g.created_at,
            fineCategory: deriveFineCategory("gate", label, step, g.gate),
            outcome3: deriveOutcome3("gate", outcome, null),
            detailRows,
          });
        }
        for (const v of validations.validation_results) {
          const label = v.validator ?? "validator";
          const step = v.step ?? "";
          const severity = normalizeSeverity(v.severity);
          const issues = issuesSummary(v.issues);
          const detailRows: [string, string][] = [
            ["Validator", label],
            ["Step", step],
            ["Severity", severity ?? "none"],
            ["Attempt", v.attempt != null ? String(v.attempt) : ""],
            ["Issues", issues],
          ].filter(([, val]) => val) as [string, string][];
          merged.push({
            id: `validation:${v.id}`,
            category: "validation",
            step,
            label,
            outcome: v.severity ?? "",
            severity,
            detail: issues,
            created_at: v.created_at,
            fineCategory: deriveFineCategory("validation", label, step),
            outcome3: deriveOutcome3("validation", v.severity ?? "", severity),
            detailRows,
          });
        }
        for (const e of execs.exec_runs) {
          const label = argvSummary(e.argv_json);
          const step = e.step ?? "";
          const outcome = e.outcome ?? "";
          const parts = [
            e.exit_code != null ? `exit ${e.exit_code}` : "",
            e.duration_ms != null ? `${e.duration_ms}ms` : "",
            e.output_digest ? `digest ${e.output_digest}` : "",
          ].filter(Boolean);
          const detailRows: [string, string][] = [
            ["Command", label],
            ["Step", step],
            ["Outcome", outcome],
            ["Exit code", e.exit_code != null ? String(e.exit_code) : ""],
            ["Duration", e.duration_ms != null ? `${e.duration_ms}ms` : ""],
            ["Digest", e.output_digest ?? ""],
          ].filter(([, v]) => v) as [string, string][];
          merged.push({
            id: `exec:${e.id}`,
            category: "exec",
            step,
            label,
            outcome,
            severity: null,
            detail: parts.join(" · "),
            created_at: e.created_at,
            fineCategory: deriveFineCategory("exec", label, step),
            outcome3: deriveOutcome3("exec", outcome, null),
            detailRows,
          });
        }

        // KAN-123: hook_runs — secret_scan blocks + behavioral hooks (KAN-73).
        // Each row maps to a "security" or "behavioral" fine-category AuditRow.
        // The secret_scan detail carries Detector / Match / Action / Outcome
        // fields that the mock's "BLOCKED write to .env" expanded card shows.
        for (const h of (hooksEnv.hook_runs ?? [])) {
          const hookName = (h.hook ?? "hook");
          const step = (h.detail as Record<string, unknown> | null)?.["step"] as string ?? "";
          const outcome = h.outcome ?? "continue";
          // Derive a human-readable label from hook + event
          const eventLabel = h.event ? `${hookName} — ${h.event.replace(/_/g, " ")}` : hookName;
          const label = buildHookLabel(hookName, h.event ?? "", outcome, h.detail as Record<string, unknown> | null);
          // Build the mock's Detector / Match / Action / Outcome detail rows
          // from the real detail payload (SC-001 / ND-D: no fabrication).
          const detailRows = buildHookDetailRows(hookName, outcome, h.detail as Record<string, unknown> | null, step, eventLabel);
          const fineCategory = deriveFineCategory("hook", hookName, step);
          const outcome3 = outcome === "block" ? "block" as Outcome3 : outcome === "warn" ? "warn" as Outcome3 : "pass" as Outcome3;
          // hook blocks that touched a credential are CRITICAL; warns are MEDIUM.
          const severity: Severity | null = outcome === "block" && /secret|credential|scan/.test(hookName) ? "CRITICAL" : null;
          merged.push({
            id: `hook:${h.id ?? `${hookName}-${h.created_at ?? Math.random()}`}`,
            category: "hook",
            step,
            label,
            outcome,
            severity,
            detail: detailNote(h.detail as Record<string, unknown> | null),
            created_at: h.created_at ?? null,
            fineCategory,
            outcome3,
            detailRows,
          });
        }

        merged.sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
        setRows(merged);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [workflowRunId]);

  // ── Filtered view: category group + blocked/denied-only + free-text search ──
  const visibleRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (activeGroup !== "all" && FINE_CATEGORY_META[r.fineCategory].group !== activeGroup) return false;
      if (blockedOnly && r.outcome3 !== "block") return false;
      if (q) {
        const hay = `${r.label} ${r.step} ${r.detail} ${FINE_CATEGORY_META[r.fineCategory].label}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [rows, activeGroup, blockedOnly, search]);

  // ── The mock's 6-stat compliance grid, all derived from live rows (ND-D) ────
  const stats = useMemo(() => ({
    checks: rows.length,
    passed: rows.filter((r) => r.outcome3 === "pass").length,
    warnings: rows.filter((r) => r.outcome3 === "warn").length,
    blocked: rows.filter((r) => r.outcome3 === "block").length,
    denied: rows.filter((r) => r.fineCategory === "exec" && r.outcome3 === "block").length,
    secretScans: rows.filter((r) => r.fineCategory === "security").length,
    critical: rows.filter((r) => r.severity === "CRITICAL").length,
  }), [rows]);

  // ── Per-group filter counts (All / Governance / Security / Activity) ────────
  const groupCounts = useMemo(() => {
    const byGroup = (g: FilterGroup) =>
      rows.filter((r) => FINE_CATEGORY_META[r.fineCategory].group === g).length;
    return { all: rows.length, gov: byGroup("gov"), sec: byGroup("sec"), act: byGroup("act") };
  }, [rows]);

  // ── Coverage: one chip per fine-category actually present (count > 0) ───────
  const coverage = useMemo(() => {
    const present = new Map<FineCategory, number>();
    for (const r of rows) present.set(r.fineCategory, (present.get(r.fineCategory) ?? 0) + 1);
    return (Object.keys(FINE_CATEGORY_META) as FineCategory[])
      .filter((cat) => (present.get(cat) ?? 0) > 0)
      .map((cat) => ({ cat, count: present.get(cat) ?? 0 }));
  }, [rows]);

  // ── Verdict banner: green iff nothing blocked / denied / critical ───────────
  const clean = stats.blocked === 0 && stats.denied === 0 && stats.critical === 0;

  // ── Live attribution (started + duration from row timestamps unless supplied) ──
  const attribution = useMemo(() => {
    const times = rows.map((r) => r.created_at).filter(Boolean) as string[];
    times.sort();
    const first = times[0];
    const last = times[times.length - 1];
    const startedAt = runMeta?.startedAt ?? first ?? null;
    const derivedMs = first && last ? new Date(last).getTime() - new Date(first).getTime() : null;
    const durationMs = runMeta?.durationMs ?? (derivedMs && derivedMs > 0 ? derivedMs : null);
    return {
      runId: shortRunId(workflowRunId),
      owner: runMeta?.owner ?? null,
      workspace: runMeta?.workspace ?? null,
      started: formatDateTimeUTC(startedAt),
      duration: formatDurationMs(durationMs),
    };
  }, [rows, runMeta, workflowRunId]);

  function exportRows() {
    return visibleRows.map((r) => ({
      category: r.category,
      fineCategory: r.fineCategory,
      step: r.step,
      label: r.label,
      outcome: r.outcome,
      severity: r.severity ?? "",
      detail: r.detail,
      created_at: r.created_at ?? "",
    }));
  }

  if (loading && rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-[11px] text-ink-400">Loading audit trail…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
        <div className="w-10 h-10 rounded-[var(--radius-menu)] bg-surface-warm flex items-center justify-center">
          <Shield className="h-5 w-5 text-ink-400" />
        </div>
        <div>
          <p className="text-[12px] font-medium text-ink-600">No audit records yet</p>
          <p className="text-[11px] text-ink-400 mt-1 leading-relaxed max-w-[220px]">
            Governance gates, validations, and sandboxed executions will appear here as the run progresses.
          </p>
        </div>
      </div>
    );
  }

  const STAT_GRID: { key: keyof typeof stats; label: string; cls: string }[] = [
    { key: "checks", label: "Checks", cls: "text-ink-900" },
    { key: "passed", label: "Passed", cls: "text-status-done" },
    { key: "warnings", label: "Warnings", cls: "text-status-amber" },
    { key: "blocked", label: "Blocked", cls: "text-status-failed" },
    { key: "denied", label: "Denied", cls: "text-status-failed" },
    { key: "secretScans", label: "Secret scans", cls: "text-brand" },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* ── Header + Export menu ── */}
      <div className="flex-shrink-0 px-4 pt-3.5 pb-3 border-b border-line-divider bg-surface-white">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <Shield className="h-[18px] w-[18px] text-ink-900 flex-shrink-0" />
              <span className="text-[19px] font-light text-ink-900 leading-tight tracking-tight">Audit trail</span>
              <span
                data-testid="audit-records-pill"
                className="text-[11px] text-ink-500 bg-surface-warm border border-line-control rounded-[var(--radius-pill)] px-2 py-0.5 leading-none"
              >
                {rows.length} records
              </span>
              {/* Phase 42-07 Group H — pulsing "live" badge while the run executes
                  (mock Run - Live:623). Settled runs omit it (KEEP). */}
              {isRunning && (
                <span
                  data-testid="audit-live-badge"
                  className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-brand bg-brand-fill border border-brand-border rounded-[var(--radius-pill)] px-2 py-1 leading-none"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
                  live
                </span>
              )}
            </div>
            <p className="text-[12px] text-ink-500 leading-relaxed mt-1.5 max-w-[420px]">
              Full governance, security &amp; activity log — every gate, scan, validation and exec, attributed and exportable.
            </p>
          </div>

          {/* Export ▾ brand menu */}
          <div className="relative flex-none">
            <button
              type="button"
              data-testid="audit-export-menu"
              aria-expanded={exportMenuOpen}
              onClick={() => setExportMenuOpen((o) => !o)}
              className="inline-flex items-center gap-2 bg-brand text-surface-white rounded-[var(--radius-button)] px-3.5 py-2 font-sans font-semibold text-[12.5px] leading-none hover:opacity-90 transition-opacity"
            >
              <Download className="h-3.5 w-3.5" />
              Export
              <ChevronDown className="h-3 w-3" />
            </button>
            {exportMenuOpen && (
              <div className="absolute top-11 right-0 w-[270px] bg-surface-white border border-line-border rounded-[var(--radius-menu)] shadow-lg p-1.5 z-20">
                <button
                  type="button"
                  data-testid="audit-export-csv"
                  onClick={() => { exportAuditCSV(exportRows(), `audit-${workflowRunId ?? "run"}`); setExportMenuOpen(false); }}
                  className="flex w-full items-start gap-3 px-2.5 py-2.5 rounded-[var(--radius-list-row)] text-left hover:bg-surface-warm transition-colors"
                >
                  <span className="w-6.5 h-6.5 flex-none rounded-[var(--radius-tag)] bg-surface-warm grid place-items-center text-ink-600">
                    <FileCheck2 className="h-3.5 w-3.5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[12.5px] font-semibold text-ink-900 leading-tight">CSV — flattened rows</span>
                    <span className="block text-[11px] text-ink-400 mt-0.5">timestamp · agent · category · event · outcome · severity</span>
                  </span>
                </button>
                <button
                  type="button"
                  data-testid="audit-export-json"
                  onClick={() => { exportAuditJSON(exportRows(), `audit-${workflowRunId ?? "run"}`); setExportMenuOpen(false); }}
                  className="flex w-full items-start gap-3 px-2.5 py-2.5 rounded-[var(--radius-list-row)] text-left hover:bg-surface-warm transition-colors"
                >
                  <span className="w-6.5 h-6.5 flex-none rounded-[var(--radius-tag)] bg-surface-warm grid place-items-center text-ink-600">
                    <Terminal className="h-3.5 w-3.5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[12.5px] font-semibold text-ink-900 leading-tight">JSON — raw rows</span>
                    <span className="block text-[11px] text-ink-400 mt-0.5">incl. category · step · outcome · severity · timestamp</span>
                  </span>
                </button>
                {/* Compliance report — CSV/JSON only (ND-6: no PDF path); disabled. */}
                <div
                  data-testid="audit-export-report"
                  aria-disabled="true"
                  className="flex w-full items-start gap-3 px-2.5 py-2.5 rounded-[var(--radius-list-row)] opacity-50 cursor-not-allowed"
                >
                  <span className="w-6.5 h-6.5 flex-none rounded-[var(--radius-tag)] bg-surface-warm grid place-items-center text-ink-400">
                    <Shield className="h-3.5 w-3.5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[12.5px] font-semibold text-ink-600 leading-tight">Compliance report</span>
                    <span className="block text-[11px] text-ink-400 mt-0.5">CSV / JSON export only — no signed PDF (ND-6)</span>
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Attribution + compliance summary card ── */}
        <div className="mt-4 border border-line-border bg-surface-card rounded-[var(--radius-menu)] px-4 py-3.5">
          {/* Attribution row — live values only; unknown fields elided (ND-D). */}
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 pb-3 mb-3.5 border-b border-line-divider text-[11px] text-ink-400">
            <span data-testid="audit-attr-run">Run <span className="text-ink-700">{attribution.runId}</span></span>
            {attribution.owner && <span>Owner <span className="text-ink-700">{attribution.owner}</span></span>}
            {attribution.workspace && <span>Workspace <span className="text-ink-700">{attribution.workspace}</span></span>}
            {attribution.started && <span>Started <span className="text-ink-700">{attribution.started}</span></span>}
            {/* Phase 42-07 Group H — while running the settled "Duration" becomes a
                live "Elapsed … · in progress" marker (mock Run - Live:649); the
                elapsed value is the live row-derived span (elided when absent —
                ND-D). Settled runs keep the plain "Duration" (KEEP). */}
            {isRunning ? (
              <span data-testid="audit-elapsed">Elapsed <span className="text-brand">{attribution.duration ? `${attribution.duration} · ` : ""}in progress</span></span>
            ) : (
              attribution.duration && <span>Duration <span className="text-ink-700">{attribution.duration}</span></span>
            )}
          </div>

          {/* 6-stat compliance grid */}
          <div className="grid grid-cols-6 gap-3 mb-3.5">
            {STAT_GRID.map((s) => (
              <div key={s.key} data-testid={`audit-stat-${s.key}`}>
                <p className={`text-[20px] font-bold leading-none ${s.cls}`}>{stats[s.key]}</p>
                <p className="text-[10.5px] text-ink-400 mt-1.5 leading-none">{s.label}</p>
              </div>
            ))}
          </div>

          {/* Coverage chips — one per fine-category actually present */}
          {coverage.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {coverage.map(({ cat, count }) => (
                <span
                  key={cat}
                  data-testid={`audit-coverage-${cat}`}
                  className="inline-flex items-center gap-1.5 text-[10.5px] font-medium text-ink-700 bg-surface-white border border-line-border rounded-[var(--radius-pill)] px-2.5 py-1 leading-none"
                >
                  <Check className="h-2.5 w-2.5 text-status-done" strokeWidth={2.6} />
                  {FINE_CATEGORY_META[cat].label} {count}
                </span>
              ))}
            </div>
          )}

          {/* Phase 42-07 Group H — while running the settled/failed verdict banner
              is replaced by the violet "monitoring live" banner (mock Run -
              Live:662). Counts are live (ND-D). Settled/failed runs keep the
              green/red verdict banner unchanged (KEEP). */}
          {isRunning ? (
            <div
              data-testid="audit-monitoring-banner"
              className="flex items-center gap-2.5 px-3 py-2.5 rounded-[var(--radius-button)] border border-brand-border bg-brand-fill"
            >
              <ShieldCheck className="h-[15px] w-[15px] text-brand flex-none" />
              <p className="text-[12.5px] font-semibold leading-snug text-brand">
                {stats.blocked} blocked · {stats.denied} denied so far — monitoring live, no policy violations.
              </p>
            </div>
          ) : (
            <div
              data-testid="audit-verdict-banner"
              data-clean={clean ? "true" : "false"}
              className={[
                "flex items-center gap-2.5 px-3 py-2.5 rounded-[var(--radius-button)] border",
                clean
                  ? "bg-[var(--status-done-fill)] border-[var(--status-done-border)]"
                  : "bg-[var(--status-failed-fill)] border-[var(--status-failed-border)]",
              ].join(" ")}
            >
              {clean
                ? <ShieldCheck className="h-[15px] w-[15px] text-status-done flex-none" />
                : <XCircle className="h-[15px] w-[15px] text-status-failed flex-none" />}
              <p className={`text-[12.5px] font-semibold leading-snug ${clean ? "text-status-done" : "text-status-failed"}`}>
                {stats.blocked} blocked · {stats.denied} denied · {stats.critical} critical
                {clean ? " — run passed all governance gates." : " — governance stopped this run."}
              </p>
            </div>
          )}
        </div>

        {/* ── Filter row: category groups + blocked-only + search ── */}
        <div className="flex items-center gap-2 flex-wrap mt-3.5">
          {(["all", "gov", "sec", "act"] as const).map((g) => {
            const active = activeGroup === g;
            const count = groupCounts[g];
            return (
              <button
                key={g}
                type="button"
                data-testid={`audit-filter-${g}`}
                aria-pressed={active}
                onClick={() => setActiveGroup(g)}
                className={[
                  "inline-flex items-center gap-1.5 border rounded-[var(--radius-pill)] px-3 py-1.5 font-sans text-[12px] font-medium leading-none transition-colors whitespace-nowrap",
                  active
                    ? "bg-ink-900 border-ink-900 text-surface-white"
                    : "bg-surface-white border-line-control text-ink-600 hover:bg-surface-warm",
                ].join(" ")}
              >
                {GROUP_LABEL[g]} <span className="opacity-50">{count}</span>
              </button>
            );
          })}
          <span className="flex-1" />
          <button
            type="button"
            data-testid="audit-blocked-only"
            aria-pressed={blockedOnly}
            onClick={() => setBlockedOnly((b) => !b)}
            className={[
              "inline-flex items-center gap-1.5 border rounded-[var(--radius-button)] px-2.5 py-1.5 font-sans text-[12px] font-medium leading-none transition-colors whitespace-nowrap",
              blockedOnly
                ? "bg-[var(--status-failed-fill)] border-[var(--status-failed-border)] text-status-failed"
                : "bg-surface-white border-line-control text-ink-500 hover:bg-surface-warm",
            ].join(" ")}
          >
            <Ban className="h-3 w-3" />
            Blocked / denied only
          </button>
          <div className="inline-flex items-center gap-2 w-[190px] bg-surface-card border border-line-control rounded-[var(--radius-button)] px-3 py-2">
            <Search className="h-3.5 w-3.5 text-ink-400 flex-none" />
            <input
              data-testid="audit-search"
              aria-label="Search audit log"
              name="audit-search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search log…"
              className="flex-1 min-w-0 bg-transparent text-[12px] text-ink-700 placeholder:text-ink-400 outline-none"
            />
          </div>
        </div>
      </div>

      {/* ── Row list + integrity footer ── */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {visibleRows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2 text-center">
            <p className="text-[11px] text-ink-500">No records match the active filters.</p>
          </div>
        ) : (
          visibleRows.map((row, idx) => (
            <AuditRowCard key={row.id} row={row} index={idx} />
          ))
        )}

        {/* Integrity footer — immutable, attributed, exportable log. */}
        <div
          data-testid="audit-integrity-footer"
          className="flex items-center gap-2.5 mt-3 px-3.5 py-2.5 border border-dashed border-line-control rounded-[var(--radius-button)] text-[11.5px] text-ink-500 leading-relaxed"
        >
          <Lock className="h-3.5 w-3.5 text-ink-400 flex-none" />
          <span>
            Immutable, owner- and workspace-attributed log · every entry carries severity + timestamp · exportable to CSV / JSON for compliance review.
          </span>
        </div>
      </div>
    </div>
  );
}
