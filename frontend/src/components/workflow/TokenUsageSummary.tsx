"use client";

import { motion } from "motion/react";
import { Zap } from "lucide-react";
import type { PipelineRunState } from "@/types/index";
import { runUsage } from "@/lib/runStats";

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
  const { totalTokens, totalInputTokens, totalOutputTokens, agents } = pipelineState;

  // Don't render if no token data yet
  if (!totalTokens && !totalInputTokens) return null;

  // Shown exactly as the backend counts them (agents/capabilities/token_usage.py):
  // input = uncached input + cache write, total = input + output. Cache reads are
  // never in them — only Analytics shows those. Each figure is the larger of the
  // engine's run total (complete at the end, incl. calls made outside any step) and
  // the steps' sum (the only figure while the run is live).
  const output = Math.max(totalOutputTokens ?? 0, runUsage(agents, "outputTokens"));
  const input = Math.max(totalInputTokens ?? ((totalTokens ?? 0) - output), runUsage(agents, "inputTokens"));
  const total = input + output;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex items-center gap-1.5 flex-wrap px-1 py-0.5"
    >
      <Zap className="h-3 w-3 text-ink-400 flex-shrink-0" />
      <span className="text-[10px] font-semibold text-ink-500 uppercase tracking-wider flex-shrink-0">
        Token Usage
      </span>
      <span data-testid="token-usage-total" className="text-[10px] font-bold text-ink-900 flex-shrink-0">
        {formatTokens(total)} total
      </span>
      <span className="text-[10px] text-ink-400 flex-shrink-0">·</span>
      <span data-testid="token-usage-input" className="text-[10px] text-ink-500 flex-shrink-0">
        {formatTokens(input)} input
      </span>
      <span className="text-[10px] text-ink-400 flex-shrink-0">·</span>
      <span data-testid="token-usage-output" className="text-[10px] text-ink-500 flex-shrink-0">
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
    <span className="text-[9px] text-ink-400 font-mono">
      {formatTokens(total)} tokens
    </span>
  );
}
