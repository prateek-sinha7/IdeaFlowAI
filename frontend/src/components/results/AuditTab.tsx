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
  CheckCircle, XCircle, AlertTriangle, Clock, Filter,
  Check, ChevronDown, Lock,
} from "lucide-react";
import type { HookRunEntry } from "@/types/index";
import {
  getToken,
  getRunGateEvents,
  getRunValidationResults,
  getRunExecRuns,
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
}

// ─── Unified audit-row model ─────────────────────────────────────────────────

type AuditCategory = "gate" | "validation" | "exec";

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

// ─── Governance status palette (the SOLE one-chroma exception) ───────────────

type VerdictKind = "done" | "failed" | "amber" | "queued";

function verdictKind(outcome: string): VerdictKind {
  const o = (outcome || "").toLowerCase();
  if (o === "pass" || o === "allowed" || o === "passed") return "done";
  if (o === "block" || o === "blocked" || o === "denied") return "failed";
  if (o === "wait_human" || o === "wait" || o === "killed") return "amber";
  return "queued";
}

const VERDICT_CLASS: Record<VerdictKind, string> = {
  done: "text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]",
  failed: "text-status-failed bg-[var(--status-failed-fill)] border-[var(--status-failed-border)]",
  amber: "text-status-amber bg-[var(--status-amber-fill)] border-[var(--status-amber-border)]",
  queued: "text-status-queued bg-[var(--status-queued-fill)] border-[var(--status-queued-border)]",
};

const VERDICT_ICON: Record<VerdictKind, typeof CheckCircle> = {
  done: CheckCircle,
  failed: XCircle,
  amber: AlertTriangle,
  queued: Clock,
};

function VerdictChip({ outcome }: { outcome: string }) {
  const kind = verdictKind(outcome);
  const Icon = VERDICT_ICON[kind];
  return (
    <span
      className={[
        "inline-flex items-center gap-1 border rounded-[var(--radius-tag)] px-1.5 py-0.5 font-sans text-[9px] font-semibold uppercase tracking-wide leading-none",
        VERDICT_CLASS[kind],
      ].join(" ")}
    >
      <Icon className="h-2.5 w-2.5" />
      {outcome}
    </span>
  );
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

// ─── Category metadata ───────────────────────────────────────────────────────

const CATEGORY_META: Record<AuditCategory, { label: string; icon: typeof Shield }> = {
  gate: { label: "Gate events", icon: ShieldCheck },
  validation: { label: "Validations", icon: FileCheck2 },
  exec: { label: "Exec runs", icon: Terminal },
};

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
  return source === "gate" ? "gate" : "validation";
}

// ─── Three-state outcome (the mock's pass / warn / block) ─────────────────────

type Outcome3 = "pass" | "warn" | "block";

const OUTCOME3_META: Record<Outcome3, { badge: string; kind: VerdictKind; Icon: typeof CheckCircle }> = {
  pass: { badge: "Passed", kind: "done", Icon: Check },
  warn: { badge: "Warning", kind: "amber", Icon: AlertTriangle },
  block: { badge: "Blocked", kind: "failed", Icon: XCircle },
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

// ─── Single audit-row card ───────────────────────────────────────────────────

function AuditRowCard({ row, index }: { row: AuditRow; index: number }) {
  const { icon: Icon } = CATEGORY_META[row.category];
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.16, delay: Math.min(index * 0.03, 0.4) }}
      className="bg-surface-card border border-line-border rounded-[var(--radius-list-row)] px-3 py-2.5"
    >
      <div className="flex items-start gap-2.5">
        <Icon className="h-3.5 w-3.5 text-ink-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] font-semibold text-ink-800 truncate">{row.label}</span>
            {row.severity ? <SeverityChip severity={row.severity} /> : <VerdictChip outcome={row.outcome} />}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-[10px] text-ink-500">{CATEGORY_META[row.category].label}</span>
            <span className="text-[10px] text-ink-300">·</span>
            <span className="text-[10px] text-ink-500">{row.step || "—"}</span>
            {row.created_at && (
              <>
                <span className="text-[10px] text-ink-300">·</span>
                <Clock className="h-2.5 w-2.5 text-ink-400" />
                <span className="text-[10px] text-ink-400">{formatTime(row.created_at)}</span>
              </>
            )}
          </div>
          {row.detail && (
            <p className="text-[11px] text-ink-600 leading-relaxed mt-1 break-words">{row.detail}</p>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ─── Main AuditTab component ─────────────────────────────────────────────────

export function AuditTab({ workflowRunId, runMeta }: AuditTabProps) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeSeverities, setActiveSeverities] = useState<Set<Severity>>(new Set());
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
    ])
      .then(([gates, validations, execs]) => {
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

  // ── Filtered view (severity filter narrows the rendered rows) ──────────────
  const visibleRows = useMemo(() => {
    if (activeSeverities.size === 0) return rows;
    return rows.filter((r) => r.severity != null && activeSeverities.has(r.severity));
  }, [rows, activeSeverities]);

  // ── Counters over ALL rows (coverage), computed once ───────────────────────
  const counts = useMemo(() => {
    const c = {
      gate: rows.filter((r) => r.category === "gate").length,
      validation: rows.filter((r) => r.category === "validation").length,
      exec: rows.filter((r) => r.category === "exec").length,
      gatePass: rows.filter((r) => r.category === "gate" && verdictKind(r.outcome) === "done").length,
      gateBlock: rows.filter((r) => r.category === "gate" && verdictKind(r.outcome) === "failed").length,
      gateWait: rows.filter((r) => r.category === "gate" && verdictKind(r.outcome) === "amber").length,
      execAllowed: rows.filter((r) => r.category === "exec" && verdictKind(r.outcome) === "done").length,
      execDenied: rows.filter((r) => r.category === "exec" && verdictKind(r.outcome) === "failed").length,
      execKilled: rows.filter((r) => r.category === "exec" && verdictKind(r.outcome) === "amber").length,
      sev: Object.fromEntries(
        SEVERITIES.map((s) => [s, rows.filter((r) => r.severity === s).length]),
      ) as Record<Severity, number>,
    };
    return c;
  }, [rows]);

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

  function toggleSeverity(sev: Severity) {
    setActiveSeverities((prev) => {
      const next = new Set(prev);
      if (next.has(sev)) next.delete(sev);
      else next.add(sev);
      return next;
    });
  }

  function exportRows() {
    return visibleRows.map((r) => ({
      category: r.category,
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
            {attribution.duration && <span>Duration <span className="text-ink-700">{attribution.duration}</span></span>}
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

          {/* Verdict banner — green when clean, red when governance stopped the run */}
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
        </div>

        {/* Severity filters (superseded by the group filter row in Task 2) */}
        <div className="flex items-center gap-1.5 flex-wrap mt-3">
          <Filter className="h-3 w-3 text-ink-400" />
          {SEVERITIES.map((sev) => {
            const active = activeSeverities.has(sev);
            return (
              <button
                key={sev}
                type="button"
                data-testid={`sev-filter-${sev}`}
                aria-pressed={active}
                onClick={() => toggleSeverity(sev)}
                className={[
                  "inline-flex items-center gap-1 border rounded-[var(--radius-tag)] px-1.5 py-0.5 font-sans text-[9px] font-semibold uppercase tracking-wide leading-none transition-colors",
                  active
                    ? "bg-brand-fill border-brand-border"
                    : "bg-surface-white border-line-control hover:bg-surface-warm",
                ].join(" ")}
                style={{ color: SEVERITY_VAR[sev] }}
              >
                {sev} {counts.sev[sev]}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Row list ── */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {visibleRows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-center">
            <p className="text-[11px] text-ink-500">No records match the active filters.</p>
          </div>
        ) : (
          visibleRows.map((row, idx) => (
            <AuditRowCard key={row.id} row={row} index={idx} />
          ))
        )}
      </div>
    </div>
  );
}
