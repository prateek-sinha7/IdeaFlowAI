/**
 * blocks.types — the ChatBlock render contract + AgentEvent input union
 * (open-design borrow #4 companion).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * This is the interface-first contract the revived chat lane renders against:
 * `AgentEvent` is the ordered, low-level stream the transport produces;
 * `ChatBlock` is the coalesced render union `buildBlocks` reduces it into.
 * Downstream plans (31-02 tool-renderer registry / block components, 31-04 the
 * lane) import these types and render the blocks — so the union is kept minimal
 * and generic.
 *
 * SC-001: every discriminator is a GENERIC event/render `kind` — NEVER a
 * workflow or agent name. A crafted workflow name can therefore never select a
 * privileged renderer (T-31-01-T).
 */

/** A single file-system operation surfaced by a file-family tool. */
export interface FileOp {
  path: string;
  op: "create" | "edit" | "delete" | "read";
}

/** Resolved lifecycle of a tool invocation. */
export type ToolStatus = "pending" | "success" | "error";

/**
 * The ordered low-level event stream fed into `buildBlocks`. Discriminated on a
 * generic `kind` only (SC-001). Text/thinking arrive as deltas that coalesce;
 * tool_use pairs with tool_result; file_op runs group; usage/status are points.
 */
export type AgentEvent =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string; durationMs?: number }
  | { kind: "tool_use"; id?: string; name: string; args?: unknown }
  | {
      kind: "tool_result";
      id?: string;
      name?: string;
      result?: unknown;
      isError?: boolean;
    }
  | {
      kind: "usage";
      inputTokens: number;
      outputTokens: number;
      costUsd?: number;
      durationMs?: number;
    }
  | { kind: "status"; status: string }
  | { kind: "file_op"; path: string; op: FileOp["op"] };

/**
 * The coalesced render union. One `ChatBlock` maps to one transcript element.
 * Discriminated on a generic `kind` only (SC-001).
 */
export type ChatBlock =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string; durationMs?: number }
  | {
      kind: "tool";
      name: string;
      status: ToolStatus;
      args?: unknown;
      result?: unknown;
      isError?: boolean;
    }
  | {
      kind: "usage";
      inputTokens: number;
      outputTokens: number;
      costUsd?: number;
      durationMs?: number;
    }
  | { kind: "file_ops"; files: FileOp[] };
