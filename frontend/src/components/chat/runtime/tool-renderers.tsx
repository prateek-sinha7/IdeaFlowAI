/**
 * tool-renderers — the three-tier tool-block render dispatch
 * (open-design borrow #3).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of upstream's tool-renderer registry + dispatch
 * (`runtime/tool-renderers.ts` + `ToolCard.tsx:37-77`; `deriveToolStatus` /
 * `toRenderProps` are pure). The dispatch is a three-tier resolution:
 *
 *   1. a `Map`-based renderer REGISTRY keyed on the generic tool NAME
 *      (ships empty — the SC-001-safe extension point the lane populates), then
 *   2. a `GenericToolCard` fallback (name + resolved status) when no renderer is
 *      registered.
 *
 * Each registered renderer is invoked inside a try/catch so a single bad
 * renderer degrades to the generic card and never breaks the transcript
 * (T-31-02-T tampering mitigation).
 *
 * SC-001: renderers are looked up by the GENERIC tool `name` string ONLY — no
 * branch references a workflow or agent name. A crafted tool name can at worst
 * miss the registry and fall back to the inert generic card.
 */

import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import type { ChatBlock, ToolStatus } from "./blocks.types";

type ToolBlock = Extract<ChatBlock, { kind: "tool" }>;

/** The pure, framework-neutral props every tool renderer receives. */
export interface ToolRenderProps {
  status: ToolStatus;
  name: string;
  args?: unknown;
  result?: unknown;
  isError?: boolean;
}

/** A registered renderer: pure props in, React node out. */
export type ToolRenderer = (props: ToolRenderProps) => ReactNode;

// Module-singleton registry. Empty by default — the extension point the lane
// (plan 04) or a workflow populates. Keyed on the GENERIC tool name (SC-001).
const registry = new Map<string, ToolRenderer>();

/**
 * Register (or replace) the renderer for a generic tool `name`. Returns an
 * unregister callback so callers can scope a registration to a lifetime.
 */
export function registerToolRenderer(
  name: string,
  render: ToolRenderer,
): () => void {
  registry.set(name, render);
  return () => {
    if (registry.get(name) === render) registry.delete(name);
  };
}

/** Test/utility hook: whether a renderer is registered for a name. */
export function hasToolRenderer(name: string): boolean {
  return registry.has(name);
}

/**
 * Pure: derive the resolved lifecycle from a raw result shape. The coalescing
 * reducer (`buildBlocks`) already resolves `block.status`, but this keeps the
 * mapping explicit and unit-testable and lets a renderer re-derive from a raw
 * `{ result, isError }` pair if needed.
 */
export function deriveToolStatus(input: {
  result?: unknown;
  isError?: boolean;
}): ToolStatus {
  if (input.isError) return "error";
  if (input.result !== undefined) return "success";
  return "pending";
}

/** Pure: project a `tool` ChatBlock onto the flat renderer props. */
export function toRenderProps(block: ToolBlock): ToolRenderProps {
  const props: ToolRenderProps = { status: block.status, name: block.name };
  if (block.args !== undefined) props.args = block.args;
  if (block.result !== undefined) props.result = block.result;
  if (block.isError !== undefined) props.isError = block.isError;
  return props;
}

const STATUS_LABEL: Record<ToolStatus, string> = {
  pending: "Running",
  success: "Completed",
  error: "Failed",
};

/**
 * The tier-2 fallback card: renders the generic tool `name` + resolved status.
 * Inert — args/result are surfaced as plain text only (no HTML/eval),
 * mitigating info-disclosure at the render boundary (T-31-02-I).
 */
export function GenericToolCard(props: ToolRenderProps): ReactNode {
  const { status, name } = props;
  const label = STATUS_LABEL[status];
  const Icon =
    status === "error"
      ? AlertTriangle
      : status === "success"
        ? CheckCircle2
        : Loader2;
  const tone =
    status === "error"
      ? "text-red-400"
      : status === "success"
        ? "text-green-400"
        : "text-grey/70";

  return (
    <div
      data-testid="chat-tool-card"
      data-tool-name={name}
      data-tool-status={status}
      role="group"
      aria-label={`Tool ${name}: ${label}`}
      className="my-2 rounded-lg border border-grey/15 bg-navy/40 px-3 py-2 text-[13px]"
    >
      <div className="flex items-center gap-2">
        <Icon
          aria-hidden="true"
          className={`h-3.5 w-3.5 ${tone} ${
            status === "pending" ? "animate-spin" : ""
          }`}
        />
        <span className="font-medium text-white/90">{name}</span>
        <span className={`ml-auto text-[11px] ${tone}`}>{label}</span>
      </div>
    </div>
  );
}

/**
 * Dispatch a `tool` ChatBlock to its renderer: registry → generic fallback,
 * with per-renderer try/catch isolation. A registered renderer that throws
 * degrades to `GenericToolCard` rather than propagating (transcript stays
 * intact). Lookup keys on the generic `name` ONLY (SC-001).
 */
export function renderToolBlock(block: ToolBlock): ReactNode {
  const props = toRenderProps(block);
  const custom = registry.get(block.name);
  if (custom) {
    try {
      return custom(props);
    } catch {
      // Isolated: one bad renderer never breaks the transcript (T-31-02-T).
      return <GenericToolCard {...props} />;
    }
  }
  return <GenericToolCard {...props} />;
}
