"use client";

import { motion } from "motion/react";
import { Zap } from "lucide-react";
import type { PipelineRunState } from "@/types/index";

interface TokenUsageSummaryProps {
  pipelineState: PipelineRunState;
  modelId?: string;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function TokenUsageSummary({ pipelineState, modelId }: TokenUsageSummaryProps) {
  const { totalTokens, totalInputTokens, totalOutputTokens, cacheReadTokens, cacheWriteTokens } = pipelineState;

  // Don't render if no token data yet
  if (!totalTokens && !totalInputTokens) return null;

  const input = totalInputTokens ?? 0;
  const output = totalOutputTokens ?? 0;
  const total = totalTokens ?? (input + output);
  const cacheRead = cacheReadTokens ?? 0;
  const cacheWrite = cacheWriteTokens ?? 0;

  // Uncached input = prompt tokens actually billed at full rate
  // (gross input includes cache_read + cache_write per ChatBedrockConverse convention).
  const uncachedInput = Math.max(0, input - cacheRead - cacheWrite);
  const hasCaching = cacheRead > 0 || cacheWrite > 0;

  // Steps tab: compact single line — total · input (uncached when caching active) · output.
  // Cache breakdown is surfaced on the Analytics page, not here.
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex items-center gap-1.5 flex-wrap px-1 py-0.5"
    >
      <Zap className="h-3 w-3 text-gray-400 flex-shrink-0" />
      <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider flex-shrink-0">
        Token Usage
      </span>
      <span className="text-[10px] font-bold text-gray-900 flex-shrink-0">
        {formatTokens(total)} total
      </span>
      <span className="text-[10px] text-gray-400 flex-shrink-0">·</span>
      <span
        className="text-[10px] text-gray-500 flex-shrink-0"
        title={hasCaching ? `Total context sent: ${formatTokens(input)} (${formatTokens(cacheRead)} cached)` : undefined}
      >
        {formatTokens(hasCaching ? uncachedInput : input)} input
      </span>
      <span className="text-[10px] text-gray-400 flex-shrink-0">·</span>
      <span className="text-[10px] text-gray-500 flex-shrink-0">
        {formatTokens(output)} output
      </span>
    </motion.div>
  );
}

// ─── Per-agent token pill — shown inside AgentCard ────────────────────────────
interface AgentTokenPillProps {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
}

export function AgentTokenPill({ inputTokens, outputTokens, totalTokens }: AgentTokenPillProps) {
  const total = totalTokens ?? ((inputTokens ?? 0) + (outputTokens ?? 0));
  if (!total) return null;

  return (
    <span className="text-[9px] text-gray-400 font-mono">
      {formatTokens(total)} tokens
    </span>
  );
}
