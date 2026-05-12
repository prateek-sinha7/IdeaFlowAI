"use client";

import { FilePlus, FileX, FileEdit } from "lucide-react";
import type { HandoffEditApplyResult, HandoffEditPreview } from "./types";

/**
 * Renders the coding agent's edit plan as a stacked before/after diff
 * per file. Designed to be visually equivalent to the slide preview in
 * the pptx workflow — same right-side pane layout, just rendering code
 * deltas instead of slides.
 *
 * No external diff library is used. The agent emits ``old_string`` and
 * ``new_string`` already trimmed to the minimal substring that changed,
 * so showing them stacked (red box / green box) IS the diff.
 */

function OpBadge({ op }: { op: string }) {
  if (op === "create") {
    return (
      <span className="inline-flex items-center gap-1 rounded text-[9px] font-bold px-1.5 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200">
        <FilePlus className="h-2.5 w-2.5" />
        CREATE
      </span>
    );
  }
  if (op === "delete") {
    return (
      <span className="inline-flex items-center gap-1 rounded text-[9px] font-bold px-1.5 py-0.5 bg-red-50 text-red-700 border border-red-200">
        <FileX className="h-2.5 w-2.5" />
        DELETE
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded text-[9px] font-bold px-1.5 py-0.5 bg-blue-50 text-blue-700 border border-blue-200">
      <FileEdit className="h-2.5 w-2.5" />
      MODIFY
    </span>
  );
}

function StatusBadge({ status, reason }: { status?: string; reason?: string }) {
  if (status === "applied") {
    return (
      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
        APPLIED
      </span>
    );
  }
  if (status === "rejected") {
    return (
      <span
        title={reason}
        className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200"
      >
        REJECTED
      </span>
    );
  }
  return (
    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 border border-gray-200">
      PROPOSED
    </span>
  );
}

function CodeBlock({
  text,
  tone,
  label,
}: {
  text: string;
  tone: "remove" | "add";
  label: string;
}) {
  if (!text) return null;
  const bg = tone === "remove" ? "bg-red-50" : "bg-emerald-50";
  const border = tone === "remove" ? "border-red-100" : "border-emerald-100";
  const ind = tone === "remove" ? "text-red-700" : "text-emerald-700";
  return (
    <div className={`border ${border} ${bg} rounded-md overflow-hidden`}>
      <div className={`text-[9px] uppercase tracking-wide ${ind} font-semibold px-2 py-1 border-b ${border}`}>
        {label}
      </div>
      <pre className="text-[11px] leading-relaxed font-mono px-3 py-2 whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
        {text}
      </pre>
    </div>
  );
}

export function DiffView({
  edits,
  results,
  testsAdded,
  followUps,
}: {
  edits: HandoffEditPreview[];
  results: HandoffEditApplyResult[];
  testsAdded?: string[];
  followUps?: string[];
}) {
  const resultByKey = new Map(
    results.map((r) => [`${r.path}::${r.operation}`, r] as const)
  );

  if (edits.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-center p-8">
        <div className="max-w-sm">
          <FileEdit className="h-8 w-8 mx-auto text-gray-300 mb-3" />
          <p className="text-[12px] text-gray-500">
            No file edits proposed yet. The diff preview will fill out as the
            coding agent runs.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5 space-y-5">
      <div>
        <h3 className="text-[13px] font-semibold text-gray-900 mb-1">
          Proposed file changes ({edits.length})
        </h3>
        <p className="text-[11px] text-gray-500">
          The coding agent proposed these edits. Each is path-traversal
          validated before being applied to the workspace.
        </p>
      </div>

      {edits.map((edit, idx) => {
        const result = resultByKey.get(`${edit.path}::${edit.operation}`);
        const showOld = edit.operation !== "create" && edit.old_string;
        const showNew = edit.operation !== "delete" && edit.new_string;
        return (
          <div
            key={`${edit.path}-${idx}`}
            className="border border-gray-200 rounded-lg bg-white overflow-hidden"
          >
            <div className="flex items-center justify-between gap-2 px-4 py-2.5 bg-gray-50 border-b border-gray-200">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <OpBadge op={edit.operation} />
                <code className="text-[12px] font-mono text-gray-800 truncate">
                  {edit.path}
                </code>
              </div>
              <StatusBadge status={result?.status} reason={result?.reason} />
            </div>
            {result?.status === "rejected" && result?.reason && (
              <div className="px-4 py-2 bg-amber-50 border-b border-amber-100 text-[11px] text-amber-800">
                Rejected: {result.reason}
              </div>
            )}
            <div className="p-3 space-y-3">
              {showOld && (
                <CodeBlock text={edit.old_string} tone="remove" label="− Removed" />
              )}
              {showNew && (
                <CodeBlock text={edit.new_string} tone="add" label="+ Added" />
              )}
            </div>
          </div>
        );
      })}

      {testsAdded && testsAdded.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h4 className="text-[12px] font-semibold text-gray-900 mb-2">
            Tests added by the coding agent
          </h4>
          <ul className="text-[12px] text-gray-700 space-y-1">
            {testsAdded.map((p) => (
              <li key={p} className="font-mono">
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {followUps && followUps.length > 0 && (
        <div className="rounded-lg border border-amber-100 bg-amber-50 p-4">
          <h4 className="text-[12px] font-semibold text-amber-900 mb-2">
            Out-of-scope items flagged for follow-up
          </h4>
          <ul className="text-[12px] text-amber-900 space-y-1 list-disc pl-5">
            {followUps.map((f, idx) => (
              <li key={idx}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
