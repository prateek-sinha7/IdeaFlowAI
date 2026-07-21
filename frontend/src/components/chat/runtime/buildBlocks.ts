/**
 * buildBlocks — coalesce an ordered AgentEvent[] into merged ChatBlock[]
 * (open-design borrow #4).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of upstream `AssistantMessage.buildBlocks()`
 * (`AssistantMessage.tsx:3148`). A PURE reducer over the typed event stream — no
 * React, no side effects — so it is maximally testable and shared by the lane
 * and the block components.
 *
 * Coalescing model (order-preserving, single forward pass):
 *   - consecutive `text` deltas merge into ONE text block (accumulated string);
 *   - consecutive `thinking` deltas merge into one thinking block (durations sum);
 *   - a `tool_use` opens a pending `tool` block; its matching `tool_result`
 *     (by id, else the most-recent pending block of the same name) resolves it to
 *     success/error via `isError`. Same-name runs stay separate, ordered blocks;
 *   - consecutive `file_op` events group into one `file_ops` block (the
 *     same-family grouping);
 *   - `usage` is a point block; `status` carries no transcript block.
 * Every branch keys on the GENERIC event kind — never a workflow name (SC-001).
 */

import type { AgentEvent, ChatBlock, FileOp } from "./blocks.types";

type ToolBlock = Extract<ChatBlock, { kind: "tool" }>;

export function buildBlocks(events: AgentEvent[]): ChatBlock[] {
  const blocks: ChatBlock[] = [];
  // Parallel tracking of open tool blocks so a later tool_result can resolve the
  // right one without leaking an `id` into the render contract.
  const tools: Array<{ block: ToolBlock; id?: string }> = [];

  const last = (): ChatBlock | undefined => blocks[blocks.length - 1];

  for (const ev of events) {
    switch (ev.kind) {
      case "text": {
        const l = last();
        if (l && l.kind === "text") l.text += ev.text;
        else blocks.push({ kind: "text", text: ev.text });
        break;
      }

      case "thinking": {
        const l = last();
        if (l && l.kind === "thinking") {
          l.text += ev.text;
          if (ev.durationMs != null) {
            l.durationMs = (l.durationMs ?? 0) + ev.durationMs;
          }
        } else {
          const block: Extract<ChatBlock, { kind: "thinking" }> = {
            kind: "thinking",
            text: ev.text,
          };
          if (ev.durationMs != null) block.durationMs = ev.durationMs;
          blocks.push(block);
        }
        break;
      }

      case "file_op": {
        const l = last();
        const file: FileOp = { path: ev.path, op: ev.op };
        if (l && l.kind === "file_ops") l.files.push(file);
        else blocks.push({ kind: "file_ops", files: [file] });
        break;
      }

      case "tool_use": {
        const block: ToolBlock = {
          kind: "tool",
          name: ev.name,
          status: "pending",
        };
        if (ev.args !== undefined) block.args = ev.args;
        blocks.push(block);
        tools.push({ block, id: ev.id });
        break;
      }

      case "tool_result": {
        // Resolve the matching open tool block: by id when present, else the
        // most-recent pending block of the same name, else the most-recent
        // pending block.
        let match: ToolBlock | undefined;
        for (let k = tools.length - 1; k >= 0; k--) {
          const t = tools[k];
          if (t.block.status !== "pending") continue;
          if (ev.id !== undefined) {
            if (t.id === ev.id) {
              match = t.block;
              break;
            }
            continue;
          }
          if (ev.name !== undefined && t.block.name !== ev.name) continue;
          match = t.block;
          break;
        }
        if (match) {
          match.status = ev.isError ? "error" : "success";
          if (ev.result !== undefined) match.result = ev.result;
          if (ev.isError !== undefined) match.isError = ev.isError;
        } else {
          // Orphan result (no open tool_use) — surface a resolved block so the
          // information is not silently dropped.
          const block: ToolBlock = {
            kind: "tool",
            name: ev.name ?? "unknown",
            status: ev.isError ? "error" : "success",
          };
          if (ev.result !== undefined) block.result = ev.result;
          if (ev.isError !== undefined) block.isError = ev.isError;
          blocks.push(block);
        }
        break;
      }

      case "usage": {
        const block: Extract<ChatBlock, { kind: "usage" }> = {
          kind: "usage",
          inputTokens: ev.inputTokens,
          outputTokens: ev.outputTokens,
        };
        if (ev.costUsd != null) block.costUsd = ev.costUsd;
        if (ev.durationMs != null) block.durationMs = ev.durationMs;
        blocks.push(block);
        break;
      }

      case "status":
        // Connection/lifecycle signal — carries no transcript block.
        break;
    }
  }

  return blocks;
}
