"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowLeft, Zap, DollarSign, Activity, Layers,
  RefreshCw, CheckCircle2, XCircle, Clock3,
} from "lucide-react";
import { getToken, getWorkflows, getPreferences } from "@/lib/api";
import type { WorkflowRun } from "@/types/index";

interface AnalyticsPageProps {
  onBack: () => void;
}

type DateFilter = "today" | "3d" | "7d" | "30d" | "90d" | "all";
type PipelineFilter = "all" | "user_stories" | "ppt" | "prototype" | "app_builder" | "custom";

// ─── Model metadata ───────────────────────────────────────────────────────────
const MODEL_META: Record<string, { name: string; short: string; inputRate: string; outputRate: string; context: string }> = {
  "eu.anthropic.claude-haiku-4-5-20251001-v1:0":  { name: "Claude Haiku 4.5",  short: "Haiku 4.5",   inputRate: "$0.25 / 1M",  outputRate: "$1.25 / 1M",  context: "200K" },
  "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": { name: "Claude Sonnet 4.5", short: "Sonnet 4.5",  inputRate: "$3.00 / 1M",  outputRate: "$15.00 / 1M", context: "200K" },
  "eu.anthropic.claude-sonnet-4-6":               { name: "Claude Sonnet 4.6", short: "Sonnet 4.6",  inputRate: "$3.00 / 1M",  outputRate: "$15.00 / 1M", context: "1M"   },
  "eu.anthropic.claude-opus-4-5-20251101-v1:0":   { name: "Claude Opus 4.5",   short: "Opus 4.5",    inputRate: "$15.00 / 1M", outputRate: "$75.00 / 1M", context: "200K" },
  "eu.anthropic.claude-opus-4-6-v1":              { name: "Claude Opus 4.6",   short: "Opus 4.6",    inputRate: "$15.00 / 1M", outputRate: "$75.00 / 1M", context: "200K" },
};
const DEFAULT_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0";

/** Infer the model ID for a run that has no stored model_id, using cost-per-token ratio. */
function inferModelId(run: WorkflowRun): string {
  if (run.tokenUsage?.model_id) return run.tokenUsage.model_id;
  if (run.modelId) return run.modelId;
  if (run.tokenUsage && run.tokenUsage.total_tokens > 0) {
    const cpt = run.tokenUsage.estimated_cost_usd / run.tokenUsage.total_tokens;
    if (cpt < 0.000003) return "eu.anthropic.claude-haiku-4-5-20251001-v1:0";
    if (cpt < 0.00002)  return "eu.anthropic.claude-sonnet-4-5-20250929-v1:0";
    return "eu.anthropic.claude-opus-4-5-20251101-v1:0";
  }
  return DEFAULT_MODEL_ID;
}

const PIPELINE_LABELS: Record<string, string> = {
  user_stories: "User Stories", user_stories_revision: "User Stories",
  ppt: "Presentation", ppt_revision: "Presentation",
  od_ppt: "Presentation", od_ppt_revision: "Presentation",
  prototype: "Prototype", prototype_revision: "Prototype",
  od_prototype: "Prototype", od_prototype_revision: "Prototype",
  app_builder: "App Builder", app_builder_revision: "App Builder",
  custom: "Custom", mulesoft_to_springboot: "Mulesoft Migration",
  dotnet_to_azure: ".NET Migration",
};

// Palette: each pipeline type gets a distinct navy-family shade
const PIPELINE_PALETTE: Record<string, { bar: string; badge: string; text: string }> = {
  "User Stories":      { bar: "#1B2A4A", badge: "bg-[#E8EDF5] text-[#1B2A4A]", text: "#1B2A4A" },
  "Presentation":      { bar: "#2E4A7A", badge: "bg-[#EAF0FB] text-[#2E4A7A]", text: "#2E4A7A" },
  "Prototype":         { bar: "#3D6B9E", badge: "bg-[#EBF3FB] text-[#3D6B9E]", text: "#3D6B9E" },
  "App Builder":       { bar: "#5B8DB8", badge: "bg-[#EDF4FA] text-[#5B8DB8]", text: "#5B8DB8" },
  "Custom":            { bar: "#8AAEC8", badge: "bg-[#F0F5F9] text-[#8AAEC8]", text: "#8AAEC8" },
  "Mulesoft Migration":{ bar: "#6B7280", badge: "bg-gray-100 text-gray-600",    text: "#6B7280" },
  ".NET Migration":    { bar: "#9CA3AF", badge: "bg-gray-100 text-gray-500",    text: "#9CA3AF" },
};

function getPalette(label: string) {
  return PIPELINE_PALETTE[label] ?? { bar: "#1B2A4A", badge: "bg-[#E8EDF5] text-[#1B2A4A]", text: "#1B2A4A" };
}

// ─── Formatters ───────────────────────────────────────────────────────────────
function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.001) return "<$0.001";
  return `$${usd.toFixed(3)}`;
}
function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ─── Timezone-safe helpers (module-level — no stale closure risk) ─────────────
function toLocalDateKey(dateInput: Date | string): string {
  const d = typeof dateInput === "string" ? new Date(dateInput) : dateInput;
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join("-");
}
function localDaysAgo(n: number): string {
  const d = new Date(); d.setDate(d.getDate() - n); return toLocalDateKey(d);
}
function localMidnightMsAgo(n: number): number {
  const d = new Date(); d.setDate(d.getDate() - n); d.setHours(0, 0, 0, 0); return d.getTime();
}

// ─── Bar chart ────────────────────────────────────────────────────────────────
function BarChart({ data, color = "#1B2A4A" }: {
  data: { label: string; value: number; runs?: number }[];
  color?: string;
}) {
  if (!data.length) return null;
  const hasTokens = data.some(d => d.value > 0);
  const display = hasTokens ? data : data.map(d => ({ ...d, value: d.runs ?? 0 }));
  const max = Math.max(...display.map(d => d.value), 1);

  return (
    <div className="flex items-end gap-[3px] h-20 w-full">
      {display.map((d, i) => {
        const pct = (d.value / max) * 100;
        const tip = hasTokens
          ? `${d.label}: ${formatTokens(d.value)} tokens`
          : `${d.label}: ${d.value} run${d.value !== 1 ? "s" : ""}`;
        return (
          <div key={i} className="flex-1 flex flex-col justify-end group relative h-full">
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: `${Math.max(pct, d.value > 0 ? 6 : 0)}%` }}
              transition={{ duration: 0.5, delay: i * 0.02, ease: "easeOut" }}
              className="w-full rounded-t-[3px] cursor-pointer"
              style={{ background: color, opacity: d.value > 0 ? 0.75 + (i / display.length) * 0.25 : 0.12 }}
            />
            <div className="absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-[9px] px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20 shadow-lg">
              {tip}
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Animated counter ─────────────────────────────────────────────────────────
function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const [display, setDisplay] = useState(0);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (!mounted) return;
    if (value === 0) { setDisplay(0); return; }
    let start = 0;
    const duration = 700;
    const steps = 30;
    const increment = value / steps;
    let count = 0;
    const timer = setInterval(() => {
      count++;
      start += increment;
      if (count >= steps) { setDisplay(value); clearInterval(timer); }
      else setDisplay(Math.floor(start));
    }, duration / steps);
    return () => clearInterval(timer);
  }, [value, mounted]);

  return <>{format(mounted ? display : value)}</>;
}

// ─── Stat card ────────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, rawValue, sub, format }: {
  icon: typeof Zap; label: string; value: string; rawValue?: number;
  sub?: string; format?: (n: number) => string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:shadow-md transition-shadow"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">{label}</span>
        <div className="h-7 w-7 rounded-lg bg-[#E8EDF5] flex items-center justify-center">
          <Icon className="h-3.5 w-3.5 text-[#1B2A4A]" />
        </div>
      </div>
      <p className="text-[24px] font-bold text-gray-900 leading-none tracking-tight">
        {rawValue !== undefined && format
          ? <AnimatedNumber value={rawValue} format={format} />
          : value}
      </p>
      {sub && <p className="text-[10px] text-gray-400 mt-1.5">{sub}</p>}
    </motion.div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export function AnalyticsPage({ onBack }: AnalyticsPageProps) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFilter, setDateFilter] = useState<DateFilter>("30d");
  const [pipelineFilter, setPipelineFilter] = useState<PipelineFilter>("all");
  const [modelFilter, setModelFilter] = useState<string>("all");
  const [preferredModelId, setPreferredModelId] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    Promise.all([
      getWorkflows(token, { limit: 500 }),
      getPreferences(token).catch(() => null),
    ])
      .then(([{ runs: wf }, prefs]) => {
        setRuns(wf);
        if (prefs) setPreferredModelId(prefs.preferred_model);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filteredRuns = useMemo(() => {
    const cutoff: Record<DateFilter, number> = {
      "today": localMidnightMsAgo(0),
      "3d":    localMidnightMsAgo(2),
      "7d":    localMidnightMsAgo(6),
      "30d":   localMidnightMsAgo(29),
      "90d":   localMidnightMsAgo(89),
      "all":   0,
    };
    return runs.filter(r => {
      if (new Date(r.createdAt).getTime() < cutoff[dateFilter]) return false;
      if (pipelineFilter !== "all") {
        // Normalise od_ppt → ppt, od_prototype → prototype before comparing
        const baseType = r.type
          .replace("od_ppt", "ppt")
          .replace("od_prototype", "prototype")
          .replace("_revision", "");
        if (baseType !== pipelineFilter) return false;
      }
      if (modelFilter !== "all") {
        if (inferModelId(r) !== modelFilter) return false;
      }
      return true;
    });
  }, [runs, dateFilter, pipelineFilter, modelFilter]);

  // Derive the set of models that appear in the full run history (for the dropdown)
  const availableModelIds = useMemo(() => {
    const seen = new Set<string>();
    for (const r of runs) {
      if (r.status === "completed") seen.add(inferModelId(r));
    }
    return Array.from(seen).sort();
  }, [runs]);

  const completedRuns = useMemo(() => filteredRuns.filter(r => r.status === "completed"), [filteredRuns]);
  const failedRuns    = useMemo(() => filteredRuns.filter(r => r.status === "failed"), [filteredRuns]);

  const tokenStats = useMemo(() => {
    let totalInput = 0, totalOutput = 0, totalCost = 0;
    for (const r of completedRuns) {
      if (r.tokenUsage) {
        totalInput  += r.tokenUsage.total_input_tokens;
        totalOutput += r.tokenUsage.total_output_tokens;
        totalCost   += r.tokenUsage.estimated_cost_usd;
      }
    }
    return { totalInput, totalOutput, total: totalInput + totalOutput, totalCost };
  }, [completedRuns]);

  const avgTokens = completedRuns.length > 0 ? Math.round(tokenStats.total / completedRuns.length) : 0;
  const successRate = filteredRuns.length > 0
    ? Math.round((completedRuns.length / filteredRuns.length) * 100) : 0;

  const pipelineBreakdown = useMemo(() => {
    const map: Record<string, { runs: number; tokens: number; cost: number }> = {};
    for (const r of completedRuns) {
      // Normalise od_ppt → ppt, od_prototype → prototype before label lookup
      const normType = r.type
        .replace("od_ppt", "ppt")
        .replace("od_prototype", "prototype")
        .replace("_revision", "");
      const label = PIPELINE_LABELS[normType] || normType;
      if (!map[label]) map[label] = { runs: 0, tokens: 0, cost: 0 };
      map[label].runs++;
      if (r.tokenUsage) { map[label].tokens += r.tokenUsage.total_tokens; map[label].cost += r.tokenUsage.estimated_cost_usd; }
    }
    return Object.entries(map).map(([label, v]) => ({ label, ...v }))
      .sort((a, b) => b.tokens !== a.tokens ? b.tokens - a.tokens : b.runs - a.runs);
  }, [completedRuns]);

  const dailyUsage = useMemo(() => {
    const chartDays = dateFilter === "today" ? 1 : dateFilter === "3d" ? 3 : 14;
    const days: Record<string, { tokens: number; runs: number }> = {};
    for (let i = chartDays - 1; i >= 0; i--) days[localDaysAgo(i)] = { tokens: 0, runs: 0 };
    for (const r of completedRuns) {
      const key = toLocalDateKey(r.createdAt);
      if (key in days) {
        days[key].runs++;
        if (r.tokenUsage) days[key].tokens += r.tokenUsage.total_tokens;
      }
    }
    return Object.entries(days).map(([dk, v]) => ({
      label: new Date(`${dk}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      value: v.tokens, runs: v.runs,
    }));
  }, [completedRuns, dateFilter]);

  const recentRuns = completedRuns.slice(0, 6);

  const DATE_LABELS: Record<DateFilter, string> = {
    today: "Today", "3d": "Last 3 days", "7d": "Last 7 days",
    "30d": "Last 30 days", "90d": "Last 90 days", all: "All time",
  };

  return (
    <div className="h-full flex flex-col overflow-y-auto" style={{ background: "#F4F5F7" }}>

      {/* ── Header ── */}
      <div className="px-6 pt-5 pb-4 border-b border-gray-100 bg-white flex-shrink-0">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <button onClick={onBack} className="h-8 w-8 rounded-lg hover:bg-gray-100 flex items-center justify-center transition-colors">
              <ArrowLeft className="h-4 w-4 text-gray-500" />
            </button>
            <div>
              <h1 className="text-[17px] font-semibold text-gray-900 leading-tight">Analytics</h1>
              <p className="text-[11px] text-gray-400 mt-0.5">Token usage · Cost · Pipeline performance</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Date pills */}
            <div className="flex items-center gap-0.5 bg-gray-100 rounded-xl p-0.5">
              {(["today", "3d", "7d", "30d", "90d", "all"] as DateFilter[]).map(f => (
                <button key={f} onClick={() => setDateFilter(f)}
                  className={`px-3 py-1.5 rounded-lg text-[10px] font-semibold transition-all ${
                    dateFilter === f ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
                  }`}>
                  {f === "all" ? "All" : f === "today" ? "Today" : f}
                </button>
              ))}
            </div>
            {/* Pipeline select */}
            <select value={pipelineFilter} onChange={e => setPipelineFilter(e.target.value as PipelineFilter)}
              className="text-[11px] border border-gray-200 rounded-xl px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:border-[#1B2A4A] transition-colors">
              <option value="all">All pipelines</option>
              <option value="user_stories">User Stories</option>
              <option value="ppt">Presentation</option>
              <option value="prototype">Prototype</option>
              <option value="app_builder">App Builder</option>
              <option value="custom">Custom</option>
            </select>
            {/* Model select — only shown when multiple models exist in history */}
            {availableModelIds.length > 1 && (
              <select value={modelFilter} onChange={e => setModelFilter(e.target.value)}
                className="text-[11px] border border-gray-200 rounded-xl px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:border-[#1B2A4A] transition-colors">
                <option value="all">All models</option>
                {availableModelIds.map(id => (
                  <option key={id} value={id}>
                    {MODEL_META[id]?.short ?? id}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <RefreshCw className="h-5 w-5 animate-spin text-gray-300" />
            <p className="text-[11px] text-gray-400">Loading analytics…</p>
          </div>
        </div>
      ) : (
        <div className="px-5 py-5 space-y-4 max-w-5xl mx-auto w-full">

          {/* ── KPI row ── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard icon={Zap}        label="Total Tokens"  value={formatTokens(tokenStats.total)}
              rawValue={tokenStats.total} format={formatTokens}
              sub={`${formatTokens(tokenStats.totalInput)} in · ${formatTokens(tokenStats.totalOutput)} out`} />
            <StatCard icon={DollarSign} label="Est. Cost"     value={formatCost(tokenStats.totalCost)}
              sub={`across ${completedRuns.length} completed runs`} />
            <StatCard icon={Activity}   label="Avg / Run"     value={formatTokens(avgTokens)}
              rawValue={avgTokens} format={formatTokens}
              sub="tokens per pipeline" />
            <StatCard icon={Layers}     label="Total Runs"    value={String(filteredRuns.length)}
              rawValue={filteredRuns.length} format={n => String(n)}
              sub={`${completedRuns.length} completed · ${failedRuns.length} failed`} />
          </div>

          {/* ── Activity chart + Success rate ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">

            {/* Chart — takes 2/3 */}
            <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-[13px] font-semibold text-gray-900">Daily Activity</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">{DATE_LABELS[dateFilter]}</p>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
                  <span className="h-2 w-2 rounded-sm inline-block" style={{ background: "#1B2A4A" }} />
                  {dailyUsage.some(d => d.value > 0) ? "Tokens" : "Runs"}
                </div>
              </div>

              {dailyUsage.every(d => d.value === 0 && (d.runs ?? 0) === 0) ? (
                <div className="h-20 flex flex-col items-center justify-center gap-1">
                  <Activity className="h-5 w-5 text-gray-200" />
                  <p className="text-[11px] text-gray-400">No activity in this period</p>
                </div>
              ) : (
                <>
                  <BarChart data={dailyUsage} color="#1B2A4A" />
                  <div className="flex mt-2">
                    {dailyUsage.map((d, i) => (
                      <div key={i} className="flex-1 text-center">
                        {(dailyUsage.length <= 3 || i % Math.ceil(dailyUsage.length / 5) === 0) && (
                          <span className="text-[8px] text-gray-400">{d.label}</span>
                        )}
                      </div>
                    ))}
                  </div>
                  {!dailyUsage.some(d => d.value > 0) && (
                    <p className="text-[9px] text-gray-400 mt-1 text-center italic">
                      Showing run counts — token data available for new runs
                    </p>
                  )}
                </>
              )}
            </div>

            {/* Success rate donut — 1/3 */}
            <div className="bg-white rounded-2xl border border-gray-100 px-5 py-4 flex flex-col items-center justify-center hover:shadow-md transition-shadow">
              <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-4">Success Rate</p>
              {/* SVG donut */}
              <div className="relative">
                <svg width="88" height="88" viewBox="0 0 88 88">
                  <circle cx="44" cy="44" r="36" fill="none" stroke="#F3F4F6" strokeWidth="10" />
                  <motion.circle
                    cx="44" cy="44" r="36" fill="none"
                    stroke="#1B2A4A"
                    strokeWidth="10" strokeLinecap="round"
                    strokeDasharray={`${2 * Math.PI * 36}`}
                    initial={{ strokeDashoffset: 2 * Math.PI * 36 }}
                    animate={{ strokeDashoffset: 2 * Math.PI * 36 * (1 - successRate / 100) }}
                    transition={{ duration: 1, ease: "easeOut" }}
                    transform="rotate(-90 44 44)"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-[20px] font-bold text-gray-900">{successRate}%</span>
                </div>
              </div>
              <div className="mt-4 space-y-1.5 w-full">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="flex items-center gap-1.5 text-gray-500">
                    <CheckCircle2 className="h-3 w-3 text-gray-400" /> Completed
                  </span>
                  <span className="font-semibold text-gray-800">{completedRuns.length}</span>
                </div>
                <div className="flex items-center justify-between text-[10px]">
                  <span className="flex items-center gap-1.5 text-gray-500">
                    <XCircle className="h-3 w-3 text-gray-400" /> Failed
                  </span>
                  <span className="font-semibold text-gray-800">{failedRuns.length}</span>
                </div>
                <div className="flex items-center justify-between text-[10px]">
                  <span className="flex items-center gap-1.5 text-gray-500">
                    <Clock3 className="h-3 w-3 text-gray-400" /> Total
                  </span>
                  <span className="font-semibold text-gray-800">{filteredRuns.length}</span>
                </div>
              </div>
            </div>
          </div>

          {/* ── Pipeline breakdown + Recent runs ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

            {/* Pipeline breakdown */}
            <div className="bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:shadow-md transition-shadow">
              <p className="text-[13px] font-semibold text-gray-900 mb-4">By Pipeline Type</p>
              {pipelineBreakdown.length === 0 ? (
                <p className="text-[11px] text-gray-400 py-6 text-center">No data for this period</p>
              ) : (
                <div className="space-y-3.5">
                  {pipelineBreakdown.map((p, i) => {
                    const palette = getPalette(p.label);
                    const hasTokens = pipelineBreakdown.some(x => x.tokens > 0);
                    const maxVal = hasTokens
                      ? Math.max(...pipelineBreakdown.map(x => x.tokens), 1)
                      : Math.max(...pipelineBreakdown.map(x => x.runs), 1);
                    const barVal = hasTokens ? p.tokens : p.runs;
                    const pct = Math.max(Math.round((barVal / maxVal) * 100), barVal > 0 ? 3 : 0);
                    return (
                      <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2">
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-md ${palette.badge}`}>{p.label}</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] text-gray-500">
                            <span className="font-medium">{p.runs} run{p.runs !== 1 ? "s" : ""}</span>
                            {p.tokens > 0 && <><span className="text-gray-300">·</span><span className="font-semibold text-gray-700">{formatTokens(p.tokens)}</span><span className="text-gray-400">{formatCost(p.cost)}</span></>}
                          </div>
                        </div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <motion.div className="h-full rounded-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.6, delay: i * 0.05, ease: "easeOut" }}
                            style={{ background: palette.bar }}
                          />
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Recent runs — compact list */}
            <div className="bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:shadow-md transition-shadow">
              <p className="text-[13px] font-semibold text-gray-900 mb-4">Recent Runs</p>
              {recentRuns.length === 0 ? (
                <p className="text-[11px] text-gray-400 py-6 text-center">No completed runs yet</p>
              ) : (
                <div className="space-y-0">
                  {recentRuns.map((r, i) => {
                    const normType = r.type
                      .replace("od_ppt", "ppt")
                      .replace("od_prototype", "prototype")
                      .replace("_revision", "");
                    const label = PIPELINE_LABELS[normType] || normType;
                    const palette = getPalette(label);
                    return (
                      <motion.div key={r.id}
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.04 }}
                        className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0"
                      >
                        {/* Color dot */}
                        <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: palette.bar }} />
                        {/* Info */}
                        <div className="flex-1 min-w-0">
                          <p className="text-[11px] font-medium text-gray-800 truncate leading-tight">{r.title}</p>
                          <div className="flex items-center gap-1 mt-0.5">
                            <span className="text-[9px] text-gray-400">{label}</span>
                            <span className="text-gray-200 text-[9px]">·</span>
                            <span className="text-[9px] text-gray-400">{formatDate(r.createdAt)}</span>
                          </div>
                        </div>
                        {/* Token badge */}
                        {r.tokenUsage && r.tokenUsage.total_tokens > 0 ? (
                          <div className="flex-shrink-0 text-right">
                            <p className="text-[11px] font-semibold text-gray-800">{formatTokens(r.tokenUsage.total_tokens)}</p>
                            <p className="text-[9px] text-gray-400">{formatCost(r.tokenUsage.estimated_cost_usd)}</p>
                          </div>
                        ) : (
                          <span className="text-[9px] text-gray-300 flex-shrink-0">—</span>
                        )}
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* ── Token ratio + Model info ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

            {/* Input vs Output ratio */}
            <div className="bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-3">
                <p className="text-[13px] font-semibold text-gray-900">Token Breakdown</p>
                {tokenStats.total > 0 && (
                  <span className="text-[10px] text-gray-400">
                    {Math.round((tokenStats.totalInput / tokenStats.total) * 100)}% in ·{" "}
                    {Math.round((tokenStats.totalOutput / tokenStats.total) * 100)}% out
                  </span>
                )}
              </div>
              {tokenStats.total === 0 ? (
                <p className="text-[11px] text-gray-400 py-3 text-center">No token data yet</p>
              ) : (
                <>
                  <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden flex mb-3">
                    <motion.div className="h-full bg-[#1B2A4A] rounded-l-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${(tokenStats.totalInput / tokenStats.total) * 100}%` }}
                      transition={{ duration: 0.8, ease: "easeOut" }}
                    />
                    <motion.div className="h-full bg-[#8AAEC8] rounded-r-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${(tokenStats.totalOutput / tokenStats.total) * 100}%` }}
                      transition={{ duration: 0.8, ease: "easeOut", delay: 0.1 }}
                    />
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { label: "Input", value: tokenStats.totalInput, color: "#1B2A4A" },
                      { label: "Output", value: tokenStats.totalOutput, color: "#8AAEC8" },
                      { label: "Total", value: tokenStats.total, color: "#374151" },
                    ].map(item => (
                      <div key={item.label} className="bg-gray-50 rounded-xl px-3 py-2.5">
                        <div className="flex items-center gap-1.5 mb-1">
                          <span className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} />
                          <span className="text-[9px] text-gray-400 font-medium">{item.label}</span>
                        </div>
                        <p className="text-[13px] font-bold text-gray-800">{formatTokens(item.value)}</p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Model info */}
            <div className="bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:shadow-md transition-shadow">
              <p className="text-[13px] font-semibold text-gray-900 mb-3">Model Details</p>
              {(() => {
                // If a model filter is active, show that model's details directly
                let activeModelId: string | null = modelFilter !== "all" ? modelFilter : null;

                // Otherwise infer from run data (stored model_id → cost-per-token → default)
                if (!activeModelId) {
                  activeModelId = completedRuns
                    .find(r => r.tokenUsage?.model_id)?.tokenUsage?.model_id
                    ?? completedRuns.find(r => r.modelId)?.modelId
                    ?? null;

                  if (!activeModelId) {
                    const runsWithData = completedRuns.filter(r => r.tokenUsage && r.tokenUsage.total_tokens > 0);
                    if (runsWithData.length > 0) {
                      const totalTokens = runsWithData.reduce((s, r) => s + (r.tokenUsage?.total_tokens ?? 0), 0);
                      const totalCost = runsWithData.reduce((s, r) => s + (r.tokenUsage?.estimated_cost_usd ?? 0), 0);
                      const avgCostPerToken = totalTokens > 0 ? totalCost / totalTokens : 0;
                      if (avgCostPerToken < 0.000003) activeModelId = "eu.anthropic.claude-haiku-4-5-20251001-v1:0";
                      else if (avgCostPerToken < 0.00002) activeModelId = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0";
                      else activeModelId = "eu.anthropic.claude-opus-4-5-20251101-v1:0";
                    }
                  }
                }

                const displayModelId = activeModelId ?? DEFAULT_MODEL_ID;
                const meta = MODEL_META[displayModelId] ?? MODEL_META[DEFAULT_MODEL_ID];
                const preferenceLabel = preferredModelId ? (MODEL_META[preferredModelId]?.name ?? null) : null;
                const showPreferenceNote = preferenceLabel && preferenceLabel !== meta.name && modelFilter === "all";

                return (
                  <>
                    <div className="space-y-2.5">
                      {[
                        { label: "Model",          value: meta.name },
                        { label: "Input rate",     value: `${meta.inputRate} tokens` },
                        { label: "Output rate",    value: `${meta.outputRate} tokens` },
                        { label: "Context window", value: `${meta.context} tokens` },
                      ].map(item => (
                        <div key={item.label} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                          <span className="text-[11px] text-gray-500">{item.label}</span>
                          <span className="text-[11px] font-semibold text-gray-800">{item.value}</span>
                        </div>
                      ))}
                    </div>
                    {showPreferenceNote && (
                      <div className="mt-3 rounded-lg bg-amber-50 border border-amber-100 px-3 py-2">
                        <p className="text-[10px] text-amber-700">
                          New runs will use <span className="font-semibold">{preferenceLabel}</span>
                        </p>
                      </div>
                    )}
                  </>
                );
              })()}
              {tokenStats.totalCost > 0 && (
                <div className="mt-3 bg-[#E8EDF5] border border-[#D0DAF0] rounded-xl px-3 py-2.5 flex items-center justify-between">
                  <span className="text-[10px] text-[#1B2A4A] font-medium">Total spend ({DATE_LABELS[dateFilter]})</span>
                  <span className="text-[13px] font-bold text-[#1B2A4A]">{formatCost(tokenStats.totalCost)}</span>
                </div>
              )}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
