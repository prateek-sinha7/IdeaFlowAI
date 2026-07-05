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

function formatCost(usd: number): string {
  if (usd === 0) return "—";
  if (usd < 0.001) return `<$0.001`;
  return `~$${usd.toFixed(3)}`;
}

// Model ID → short display name for the cost label
const MODEL_SHORT_NAMES: Record<string, string> = {
  "eu.anthropic.claude-haiku-4-5-20251001-v1:0":  "Haiku 4.5",
  "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": "Sonnet 4.5",
  "eu.anthropic.claude-sonnet-4-6":               "Sonnet 4.6",
  "eu.anthropic.claude-opus-4-5-20251101-v1:0":   "Opus 4.5",
  "eu.anthropic.claude-opus-4-6-v1":              "Opus 4.6",
};

export function TokenUsageSummary({ pipelineState, modelId }: TokenUsageSummaryProps) {
  const { totalTokens, totalInputTokens, totalOutputTokens, estimatedCostUsd, cacheReadTokens, cacheWriteTokens } = pipelineState;

  // Don't render if no token data yet
  if (!totalTokens && !totalInputTokens) return null;

  const input = totalInputTokens ?? 0;
  const output = totalOutputTokens ?? 0;
  const total = totalTokens ?? (input + output);
  const cost = estimatedCostUsd ?? 0;
  const cacheRead = cacheReadTokens ?? 0;
  const cacheWrite = cacheWriteTokens ?? 0;
  const pct = Math.round(cacheRead / Math.max(1, input) * 100);

  // KAN-83: single compact line — token count + input/output + cost only
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
      <span className="text-[10px] text-gray-500 flex-shrink-0">
        {formatTokens(input)} input
      </span>
      {cacheRead > 0 && (
        <>
          <span className="text-[10px] text-gray-400 flex-shrink-0">·</span>
          <span className="text-[10px] text-amber-600 flex-shrink-0">
            ⚡ {formatTokens(cacheRead)} cached ({pct}%)
            {cacheWrite > 0 && ` · ${formatTokens(cacheWrite)} written`}
          </span>
        </>
      )}
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
