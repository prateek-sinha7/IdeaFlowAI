"use client";

import { motion } from "motion/react";
import { Zap } from "lucide-react";
import type { PipelineRunState } from "@/types/index";

interface TokenUsageSummaryProps {
  pipelineState: PipelineRunState;
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

export function TokenUsageSummary({ pipelineState }: TokenUsageSummaryProps) {
  const { totalTokens, totalInputTokens, totalOutputTokens, estimatedCostUsd } = pipelineState;

  // Don't render if no token data yet
  if (!totalTokens && !totalInputTokens) return null;

  const input = totalInputTokens ?? 0;
  const output = totalOutputTokens ?? 0;
  const total = totalTokens ?? (input + output);
  const cost = estimatedCostUsd ?? 0;

  // Input/output ratio bar
  const inputPct = total > 0 ? Math.round((input / total) * 100) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-1.5">
          <Zap className="h-3 w-3 text-gray-400" />
          <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
            Token Usage
          </span>
        </div>
        <span className="text-[11px] font-bold text-gray-900">
          {formatTokens(total)} total
        </span>
      </div>

      {/* Input / Output breakdown */}
      <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1.5">
        <span>{formatTokens(input)} input</span>
        <span>{formatTokens(output)} output</span>
      </div>

      {/* Ratio bar */}
      <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden mb-2.5">
        <div
          className="h-full bg-[#1B2A4A] rounded-full transition-all duration-500"
          style={{ width: `${inputPct}%` }}
        />
      </div>

      {/* Cost estimate */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-gray-400">Est. cost (Haiku)</span>
        <span className="text-[11px] font-semibold text-gray-700">{formatCost(cost)}</span>
      </div>
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
