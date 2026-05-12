"use client";

import { CheckCircle2, AlertTriangle, AlertOctagon, ShieldCheck, TestTube } from "lucide-react";
import type { HandoffComplianceReport, HandoffTestReport } from "./types";

/**
 * Render the TestAgent and ComplianceAgent reports as visually distinct
 * preview panes. Each is laid out like a code review: verdict pill at
 * the top, summary, sectioned bullet lists below. The exact same data
 * lands in the eventual GitHub PR body — this is just the live view.
 */

function VerdictPill({
  verdict,
  type,
}: {
  verdict?: string;
  type: "test" | "compliance";
}) {
  const v = (verdict || "").toLowerCase();
  const positive = type === "test" ? "pass" : "approve";
  const warning = type === "test" ? "concerns" : "approve_with_changes";
  const negative = type === "test" ? "fail" : "request_changes";

  let style = "bg-gray-50 text-gray-700 border-gray-200";
  let Icon = CheckCircle2;
  if (v === positive) {
    style = "bg-emerald-50 text-emerald-700 border-emerald-200";
    Icon = CheckCircle2;
  } else if (v === warning) {
    style = "bg-amber-50 text-amber-700 border-amber-200";
    Icon = AlertTriangle;
  } else if (v === negative) {
    style = "bg-red-50 text-red-700 border-red-200";
    Icon = AlertOctagon;
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide border ${style}`}
    >
      <Icon className="h-3 w-3" />
      {(verdict || "pending").replace(/_/g, " ")}
    </span>
  );
}

function SeverityPill({ severity }: { severity: string }) {
  const sev = (severity || "").toLowerCase();
  const style =
    sev === "critical" || sev === "high"
      ? "bg-red-50 text-red-700 border-red-200"
      : sev === "medium"
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-gray-50 text-gray-600 border-gray-200";
  return (
    <span
      className={`inline-block rounded text-[9px] font-bold uppercase px-1.5 py-0.5 border ${style}`}
    >
      {severity}
    </span>
  );
}

function EmptyState({
  icon: Icon,
  label,
}: {
  icon: typeof CheckCircle2;
  label: string;
}) {
  return (
    <div className="h-full flex items-center justify-center text-center p-8">
      <div className="max-w-sm">
        <Icon className="h-8 w-8 mx-auto text-gray-300 mb-3" />
        <p className="text-[12px] text-gray-500">{label}</p>
      </div>
    </div>
  );
}

export function TestReportView({ report }: { report?: HandoffTestReport }) {
  if (!report) {
    return (
      <EmptyState
        icon={TestTube}
        label="The test report will appear here when the Test analysis agent finishes."
      />
    );
  }
  return (
    <div className="h-full overflow-y-auto p-5 space-y-4">
      <div className="flex items-center gap-2">
        <TestTube className="h-4 w-4 text-purple-600" />
        <h3 className="text-[13px] font-semibold text-gray-900">Test coverage report</h3>
        <span className="ml-auto">
          <VerdictPill verdict={report.verdict} type="test" />
        </span>
      </div>
      {report.summary && (
        <p className="text-[12px] text-gray-700 leading-relaxed">{report.summary}</p>
      )}

      {report.missing_coverage && report.missing_coverage.length > 0 && (
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Missing coverage ({report.missing_coverage.length})
          </h4>
          <ul className="space-y-2">
            {report.missing_coverage.map((m, idx) => (
              <li
                key={idx}
                className="rounded-md border border-gray-200 bg-white px-3 py-2 text-[12px]"
              >
                <div className="font-semibold text-gray-900">{m.area}</div>
                <div className="text-gray-600 mt-0.5">{m.suggested_test}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.quality_issues && report.quality_issues.length > 0 && (
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Test-quality issues ({report.quality_issues.length})
          </h4>
          <ul className="space-y-2">
            {report.quality_issues.map((q, idx) => (
              <li
                key={idx}
                className="rounded-md border border-gray-200 bg-white px-3 py-2 text-[12px]"
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <SeverityPill severity={q.severity} />
                  <code className="text-[11px] text-gray-500">{q.path}</code>
                </div>
                <div className="text-gray-700">{q.issue}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.recommended_additions && report.recommended_additions.length > 0 && (
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Recommended new tests
          </h4>
          <ul className="space-y-1 text-[12px] text-gray-700 list-disc pl-5">
            {report.recommended_additions.map((r, idx) => (
              <li key={idx}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      {report.tests_present && report.tests_present.length > 0 && (
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Existing test coverage
          </h4>
          <ul className="space-y-1 text-[12px] text-gray-700">
            {report.tests_present.map((t, idx) => (
              <li key={idx} className="font-mono text-[11px]">
                {t.path}
                <span className="ml-2 text-gray-500 font-sans">{t.covers}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function ComplianceReportView({
  report,
}: {
  report?: HandoffComplianceReport;
}) {
  if (!report) {
    return (
      <EmptyState
        icon={ShieldCheck}
        label="The compliance report will appear here when the Compliance review agent finishes."
      />
    );
  }
  const findings = report.findings ?? [];
  const grouped = findings.reduce<Record<string, typeof findings>>((acc, f) => {
    const sev = (f.severity || "low").toLowerCase();
    (acc[sev] = acc[sev] || []).push(f);
    return acc;
  }, {});
  const order = ["critical", "high", "medium", "low"];
  return (
    <div className="h-full overflow-y-auto p-5 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-green-700" />
        <h3 className="text-[13px] font-semibold text-gray-900">Compliance review</h3>
        <span className="ml-auto">
          <VerdictPill verdict={report.verdict} type="compliance" />
        </span>
      </div>
      {report.summary && (
        <p className="text-[12px] text-gray-700 leading-relaxed">{report.summary}</p>
      )}

      {findings.length > 0 && (
        <section className="space-y-3">
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
            Findings ({findings.length})
          </h4>
          {order.flatMap((sev) =>
            (grouped[sev] || []).map((f, idx) => (
              <div
                key={`${sev}-${idx}`}
                className="rounded-md border border-gray-200 bg-white px-3 py-2 text-[12px]"
              >
                <div className="flex items-center gap-2 mb-1">
                  <SeverityPill severity={f.severity} />
                  <span className="text-[10px] uppercase tracking-wide text-gray-500">
                    {f.category}
                  </span>
                  <code className="text-[11px] text-gray-500 ml-auto truncate">
                    {f.location}
                  </code>
                </div>
                <div className="text-gray-900 font-medium">{f.issue}</div>
                {f.recommendation && (
                  <div className="text-gray-600 mt-1 italic">{f.recommendation}</div>
                )}
              </div>
            ))
          )}
        </section>
      )}

      {report.positives && report.positives.length > 0 && (
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">
            What the change does well
          </h4>
          <ul className="space-y-1 text-[12px] text-gray-700 list-disc pl-5">
            {report.positives.map((p, idx) => (
              <li key={idx}>{p}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
