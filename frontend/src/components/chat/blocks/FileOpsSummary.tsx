/**
 * FileOpsSummary — a "files this turn" strip for a grouped file-op run
 * (open-design borrow #7).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of upstream's `runtime/file-ops.ts` + `FileOpsSummary` —
 * the compact strip summarising the file operations of one turn. Renders the
 * plan-01 `{kind:'file_ops', files: FileOp[]}` block (the same-family grouping
 * `buildBlocks` produces). Paths are inert text (T-31-02-I: no HTML/eval).
 *
 * CURRENT SKIN (D-15): raw Tailwind + lucide-react.
 */

"use client";

import { FilePen, FilePlus, FileText, FileX } from "lucide-react";

import type { ChatBlock, FileOp } from "../runtime/blocks.types";

type FileOpsData = Extract<ChatBlock, { kind: "file_ops" }>;

const OP_ICON: Record<FileOp["op"], { Icon: typeof FileText; tone: string }> = {
  create: { Icon: FilePlus, tone: "text-green-400" },
  edit: { Icon: FilePen, tone: "text-blue-400" },
  delete: { Icon: FileX, tone: "text-red-400" },
  read: { Icon: FileText, tone: "text-grey/60" },
};

export function FileOpsSummary({ block }: { block: FileOpsData }) {
  const { files } = block;

  return (
    <div
      data-testid="chat-file-ops"
      role="group"
      aria-label={`${files.length} file ${
        files.length === 1 ? "operation" : "operations"
      } this turn`}
      className="my-2 rounded-lg border border-grey/15 bg-navy/40 px-3 py-2"
    >
      <div className="mb-1.5 text-[12px] font-medium text-white/90">
        {files.length} {files.length === 1 ? "file" : "files"} this turn
      </div>
      <ul className="flex flex-col gap-1">
        {files.map((file, i) => {
          const { Icon, tone } = OP_ICON[file.op];
          return (
            <li
              key={i}
              data-file-op={file.op}
              className="flex items-center gap-2 text-[13px] text-grey/80"
            >
              <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${tone}`} aria-hidden="true" />
              <span className="truncate font-mono text-[12px]">{file.path}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
