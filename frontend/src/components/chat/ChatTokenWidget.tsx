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
 */
import { Zap } from "lucide-react";

import type { PipelineRunState } from "@/types/index";

interface ChatTokenWidgetProps {
  pipelineState: PipelineRunState;
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
  } = pipelineState;

  // No token data yet → render nothing (mirrors TokenUsageSummary).
  if (!totalTokens && !totalInputTokens) return null;

  const input = totalInputTokens ?? 0;
  const output = totalOutputTokens ?? 0;
  const total = totalTokens ?? input + output;
  const cost = estimatedCostUsd ?? 0;
  const cacheRead = cacheReadTokens ?? 0;
  const pct = Math.round((cacheRead / Math.max(1, input)) * 100);

  return (
    <div
      data-testid="chat-token-widget"
      className="inline-flex items-center gap-1.5 text-[10px] text-gray-500"
    >
      <Zap className="h-3 w-3 text-gray-400 flex-shrink-0" />
      <span className="font-bold text-gray-900">{formatTokens(total)} tokens</span>
      <span className="text-gray-400">·</span>
      <span>{formatCost(cost)}</span>
      {cacheRead > 0 && (
        <>
          <span className="text-gray-400">·</span>
          <span className="text-amber-600">
            ⚡ {formatTokens(cacheRead)} cached ({pct}%)
          </span>
        </>
      )}
    </div>
  );
}
