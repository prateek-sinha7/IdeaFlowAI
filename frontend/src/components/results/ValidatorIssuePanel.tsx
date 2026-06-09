"use client";

/**
 * ValidatorIssuePanel — surfaces live validator/issue data from the run stream
 * (API-03 / API-06 / D-11).
 *
 * Consumes the ADDITIVE `validator_result` / `validation_warning` WS events
 * (Phase 8 — additive only; no existing event renamed/removed) and renders the
 * issues grouped by severity (CRITICAL / HIGH / MEDIUM / LOW), mirroring the
 * `ReviewGatesSection` / `AgentProgressPanel` run-surface event-consumption
 * pattern. It is fed the issues as a prop (the parent's WS handler routes the
 * `validator_result` / `validation_warning` events into this list) — the same
 * props-driven shape `AgentProgressPanel` uses, so the panel stays decoupled
 * from the WS plumbing.
 *
 * Additive results panel — it does not change any existing results surface.
 */

import { ShieldAlert, AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import type { IssueSeverity, ValidationIssue } from "@/types/index";

export interface ValidatorIssuePanelProps {
  /**
   * Issues parsed from the live `validator_result` / `validation_warning` run
   * events. Empty = no issues reported yet (clean run so far).
   */
  issues: ValidationIssue[];
}

const SEVERITY_ORDER: IssueSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

const SEVERITY_STYLE: Record<
  IssueSeverity,
  { label: string; chip: string; row: string }
> = {
  CRITICAL: {
    label: "Critical",
    chip: "text-red-700 bg-red-100",
    row: "border-red-100 bg-red-50",
  },
  HIGH: {
    label: "High",
    chip: "text-orange-700 bg-orange-100",
    row: "border-orange-100 bg-orange-50",
  },
  MEDIUM: {
    label: "Medium",
    chip: "text-amber-700 bg-amber-100",
    row: "border-amber-100 bg-amber-50",
  },
  LOW: {
    label: "Low",
    chip: "text-gray-600 bg-gray-100",
    row: "border-gray-100 bg-gray-50",
  },
};

function SeverityIcon({ severity }: { severity: IssueSeverity }) {
  if (severity === "CRITICAL" || severity === "HIGH") {
    return <ShieldAlert className="h-3 w-3 flex-shrink-0" />;
  }
  if (severity === "MEDIUM") {
    return <AlertTriangle className="h-3 w-3 flex-shrink-0" />;
  }
  return <Info className="h-3 w-3 flex-shrink-0" />;
}

export function ValidatorIssuePanel({ issues }: ValidatorIssuePanelProps) {
  // Group the flat issue list by severity, preserving the CRITICAL→LOW order.
  const bySeverity = new Map<IssueSeverity, ValidationIssue[]>();
  for (const issue of issues) {
    const list = bySeverity.get(issue.severity) ?? [];
    list.push(issue);
    bySeverity.set(issue.severity, list);
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5 mb-2">
        <ShieldAlert className="h-3.5 w-3.5 text-[#1B2A4A]" />
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Validator / Issues
        </p>
      </div>

      {issues.length === 0 ? (
        <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 bg-emerald-50 rounded-lg px-2.5 py-1.5">
          <CheckCircle2 className="h-3 w-3 flex-shrink-0" />
          No validator issues reported.
        </div>
      ) : (
        <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1">
          {SEVERITY_ORDER.map((severity) => {
            const group = bySeverity.get(severity);
            if (!group || group.length === 0) return null;
            const style = SEVERITY_STYLE[severity];
            return (
              <div key={severity}>
                <div className="flex items-center gap-1.5 mb-1">
                  <span
                    className={`text-[8px] font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded ${style.chip}`}
                  >
                    {style.label} ({group.length})
                  </span>
                </div>
                <div className="space-y-1">
                  {group.map((issue, idx) => (
                    <div
                      key={`${severity}-${idx}`}
                      className={`flex items-start gap-2 border rounded-lg px-2.5 py-1.5 ${style.row}`}
                    >
                      <SeverityIcon severity={severity} />
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] text-gray-800 break-words">
                          {issue.message}
                        </p>
                        {(issue.validator || issue.warning) && (
                          <p className="text-[9px] text-gray-400 mt-0.5">
                            {issue.validator}
                            {issue.warning ? " · warning" : ""}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
