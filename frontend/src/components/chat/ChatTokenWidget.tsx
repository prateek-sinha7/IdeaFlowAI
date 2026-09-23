"use client";

/**
 * ChatTokenWidget — the chat lane's compact token-usage widget (Phase 31,
 * CHATUI-03). Mirrors `TokenUsageSummary` (P26) but sized for the lane: it reads
 * the live run state's telemetry fields and renders
 * "N tokens · $cost · ⚡ M cached (P%)".
 *
 * FIGURE-TO-FIELD (P26): every figure is PINNED to its live-state field — no
 * invented number. `totalTokens` / `totalInputTokens` / `totalOutputTokens` /
 * `estimatedCostUsd` come from the `agent_complete` / `pipeline_complete` token
 * totals; `cacheReadTokens` is the cache-telemetry split. The cached segment
 * only renders when `cacheReadTokens > 0`. SC-001: keyed purely on generic
 * telemetry fields — never a workflow/agent name.
 *
 * Phase 33 (D-08): the widget also surfaces the COMPOSED-CONTEXT usage — the
 * bounded conversation-context size relative to its budget — so the user can SEE
 * when history nears budget (the trigger for the RunChatLane compact affordance).
 * FE DISPLAYS ONLY — no FE compression. The composed-context fields are not yet
 * emitted by the run stream (Phase-34 live); they are declared locally as an
 * optional telemetry extension so the widget degrades gracefully (hides the
 * sub-display) rather than erroring when the value is absent.
 */
import { Zap } from "lucide-react";

import type { PipelineRunState } from "@/types/index";

interface ChatTokenWidgetProps {
  /**
   * Live run telemetry. Accepts the optional composed-context extension so the
   * widget can surface conversation-context usage when the stream supplies it,
   * while remaining a plain `PipelineRunState` when it does not (D-08).
   */
  pipelineState: PipelineRunState & Partial<ComposedContextTelemetry>;
}

/**
 * Optional composed-context telemetry — the bounded conversation-context size
 * and its budget. Declared LOCALLY (not on the shared `PipelineRunState`) so
 * this display-only extension degrades gracefully today without a schema change;
 * Phase-34 wires the live stream fields. GENERIC — no workflow/agent name.
 */
export interface ComposedContextTelemetry {
  /** Current composed-context size in tokens (bounded history + injected context). */
  composedContextTokens?: number;
  /** The context budget the composed size is measured against. */
  contextBudgetTokens?: number;
}

/** Usage at/above this fraction of budget surfaces the compact affordance. */
export const COMPACT_THRESHOLD_PCT = 80;

/**
 * Composed-context usage relative to budget, or `null` when the run stream has
 * not (yet) supplied it — the single source of truth shared with RunChatLane's
 * compact affordance. Degrades gracefully (D-08 display-only; no FE compression).
 */
export function composedContextUsage(
  pipelineState: PipelineRunState & Partial<ComposedContextTelemetry>,
): { tokens: number; budget: number; pct: number } | null {
  const tokens = pipelineState.composedContextTokens ?? 0;
  const budget = pipelineState.contextBudgetTokens ?? 0;
  if (tokens <= 0 || budget <= 0) return null;
  const pct = Math.round((tokens / budget) * 100);
  return { tokens, budget, pct };
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatCost(usd: number): string {
  if (usd === 0) return "—";
  if (usd < 0.001) return "<$0.001";
  return `~$${usd.toFixed(3)}`;
}

export function ChatTokenWidget({ pipelineState }: ChatTokenWidgetProps) {
  const {
    totalTokens,
    totalInputTokens,
    totalOutputTokens,
    estimatedCostUsd,
    cacheReadTokens,
    cacheWriteTokens,
  } = pipelineState;

  // No token data yet → render nothing (mirrors TokenUsageSummary).
  if (!totalTokens && !totalInputTokens) return null;

  const input = totalInputTokens ?? 0;
  const output = totalOutputTokens ?? 0;
  const total = totalTokens ?? input + output;
  const cost = estimatedCostUsd ?? 0;
  const cacheRead = cacheReadTokens ?? 0;
  const cacheWrite = cacheWriteTokens ?? 0;

  // `input` = total prompt tokens (uncached + cache_read + cache_write) per
  // ChatBedrockConverse convention — shown in full so the "in" figure reconciles
  // against the "tokens" total, with the cached share called out beside it.
  const hasCaching = cacheRead > 0 || cacheWrite > 0;
  const cacheReadPct = Math.round((cacheRead / Math.max(1, input)) * 100);

  // Composed-context usage sub-display (D-08). Null → hidden (graceful degrade).
  const ctx = composedContextUsage(pipelineState);
  const ctxHigh = ctx !== null && ctx.pct >= COMPACT_THRESHOLD_PCT;

  return (
    <div
      data-testid="chat-token-widget"
      className="inline-flex items-center gap-1.5 text-[10px] text-gray-500"
    >
      <Zap className="h-3 w-3 text-gray-400 flex-shrink-0" />
      <span className="font-bold text-gray-900">{formatTokens(total)} tokens</span>
      <span className="text-gray-400">·</span>
      <span>{formatCost(cost)}</span>
      <span className="text-gray-400">·</span>
      <span>{formatTokens(input)} in</span>
      {hasCaching && (
        <>
          <span className="text-gray-400">·</span>
          <span className="text-amber-600">
            ⚡ {formatTokens(cacheRead)} cached ({cacheReadPct}%)
          </span>
        </>
      )}
      {ctx && (
        <>
          <span className="text-gray-400">·</span>
          <span
            data-testid="chat-context-usage"
            data-context-high={ctxHigh ? "true" : "false"}
            title="Conversation context vs budget"
            className={ctxHigh ? "text-amber-600 font-semibold" : "text-gray-500"}
          >
            🧠 {ctx.pct}% context
          </span>
        </>
      )}
    </div>
  );
}
