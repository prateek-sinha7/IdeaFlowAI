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
} from "lucide-react";
import type { HookRunEntry } from "@/types/index";
import {
  getToken,
  getRunGateEvents,
  getRunValidationResults,
  getRunExecRuns,
} from "@/lib/api";
import { exportAuditCSV, exportAuditJSON } from "@/lib/exporters/auditExporter";

interface AuditTabProps {
  /**
   * Dormant legacy prop — retained ONLY so the PreviewPanel mount signature is
   * unchanged (guardrail: PreviewPanel mount untouched). The tab no longer
   * derives its data from hook_runs; it reads the 3 plan-03 endpoints below.
   */
  hookRuns?: HookRunEntry[];
  workflowRunId?: string;
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

// ─── Counter pill ────────────────────────────────────────────────────────────

function CounterPill({ label, value }: { label: string; value: number }) {
  return (
    <span className="inline-flex items-center gap-1 bg-surface-white text-ink-700 border border-line-control rounded-[var(--radius-pill)] px-2 py-0.5 font-sans text-[10px] leading-none">
      <span className="font-semibold text-ink-800">{value}</span>
      <span className="text-ink-500">{label}</span>
    </span>
  );
}

// ─── Main AuditTab component ─────────────────────────────────────────────────

export function AuditTab({ workflowRunId }: AuditTabProps) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeSeverities, setActiveSeverities] = useState<Set<Severity>>(new Set());

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
          merged.push({
            id: `gate:${g.id}`,
            category: "gate",
            step: g.step ?? "",
            label: g.gate ?? "gate",
            outcome: g.outcome ?? "",
            severity: null,
            detail: detailNote(g.detail),
            created_at: g.created_at,
          });
        }
        for (const v of validations.validation_results) {
          merged.push({
            id: `validation:${v.id}`,
            category: "validation",
            step: v.step ?? "",
            label: v.validator ?? "validator",
            outcome: v.severity ?? "",
            severity: normalizeSeverity(v.severity),
            detail: issuesSummary(v.issues),
            created_at: v.created_at,
          });
        }
        for (const e of execs.exec_runs) {
          const parts = [
            e.exit_code != null ? `exit ${e.exit_code}` : "",
            e.duration_ms != null ? `${e.duration_ms}ms` : "",
            e.output_digest ? `digest ${e.output_digest}` : "",
          ].filter(Boolean);
          merged.push({
            id: `exec:${e.id}`,
            category: "exec",
            step: e.step ?? "",
            label: argvSummary(e.argv_json),
            outcome: e.outcome ?? "",
            severity: null,
            detail: parts.join(" · "),
            created_at: e.created_at,
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

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ── */}
      <div className="flex-shrink-0 px-4 pt-3 pb-2.5 border-b border-line-divider bg-surface-white">
        <div className="flex items-center gap-2 mb-2">
          <Shield className="h-3.5 w-3.5 text-brand flex-shrink-0" />
          <span className="text-[12px] font-semibold text-ink-700">Audit trail</span>
          <span className="ml-auto text-[10px] text-ink-400">{rows.length} records</span>
        </div>

        {/* Coverage chips (per-category totals) */}
        <div className="flex items-center gap-1.5 flex-wrap mb-2">
          {(Object.keys(CATEGORY_META) as AuditCategory[]).map((cat) => {
            const Icon = CATEGORY_META[cat].icon;
            return (
              <span
                key={cat}
                data-testid={`audit-coverage-${cat}`}
                className="inline-flex items-center gap-1 bg-surface-white text-ink-600 border border-line-control rounded-[var(--radius-pill)] px-2 py-0.5 font-sans text-[10px] leading-none"
              >
                <Icon className="h-2.5 w-2.5 text-ink-400" />
                {counts[cat]} {CATEGORY_META[cat].label.toLowerCase()}
              </span>
            );
          })}
        </div>

        {/* Stat counters (governance verdict / severity breakdown) */}
        <div className="flex items-center gap-1.5 flex-wrap mb-2">
          <CounterPill label="pass" value={counts.gatePass} />
          <CounterPill label="block" value={counts.gateBlock} />
          <CounterPill label="wait" value={counts.gateWait} />
          <span className="text-[10px] text-ink-300">|</span>
          <CounterPill label="allowed" value={counts.execAllowed} />
          <CounterPill label="denied" value={counts.execDenied} />
          <CounterPill label="killed" value={counts.execKilled} />
        </div>

        {/* Severity filters */}
        <div className="flex items-center gap-1.5 flex-wrap">
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

      {/* ── Export bar ── */}
      <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 border-b border-line-divider bg-surface-paper">
        <span className="text-[10px] text-ink-500">
          {visibleRows.length} shown
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <button
            type="button"
            data-testid="audit-export-csv"
            onClick={() => exportAuditCSV(exportRows(), `audit-${workflowRunId ?? "run"}`)}
            className="inline-flex items-center gap-1 bg-surface-card text-ink-900 border border-line-control rounded-[var(--radius-button)] px-2.5 py-1 font-sans font-semibold text-[11px] leading-none hover:bg-surface-warm transition-colors"
          >
            <Download className="h-3 w-3" />
            Export CSV
          </button>
          <button
            type="button"
            data-testid="audit-export-json"
            onClick={() => exportAuditJSON(exportRows(), `audit-${workflowRunId ?? "run"}`)}
            className="inline-flex items-center gap-1 bg-surface-card text-ink-900 border border-line-control rounded-[var(--radius-button)] px-2.5 py-1 font-sans font-semibold text-[11px] leading-none hover:bg-surface-warm transition-colors"
          >
            <Download className="h-3 w-3" />
            Export JSON
          </button>
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
