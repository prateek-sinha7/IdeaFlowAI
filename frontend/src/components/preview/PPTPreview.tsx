"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  ChevronLeft,
  ChevronRight,
  Presentation,
  Grid3X3,
  Maximize2,
  BarChart3,
  PieChart as PieIcon,
  TrendingUp,
  Table2,
  GitCompare,
  Quote,
  Columns,
  Target,
  Lightbulb,
  Rocket,
  Shield,
  Zap,
  Globe,
  Users,
  CheckCircle2,
  ArrowRight,
} from "lucide-react";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";
import type { Slide, ChartData, TableData } from "@/types";

interface PPTPreviewProps {
  content?: string;
  isStreaming?: boolean;
}

/* --- Color Palette --- */
const CHART_COLORS = ["#C96442", "#1E3A5F", "#10B981", "#8B5CF6", "#F59E0B", "#EC4899", "#06B6D4", "#84CC16"];

/* --- Icon Mapper --- */
const SLIDE_ICONS: Record<string, React.ReactNode> = {
  target: <Target className="h-4 w-4" />,
  lightbulb: <Lightbulb className="h-4 w-4" />,
  rocket: <Rocket className="h-4 w-4" />,
  shield: <Shield className="h-4 w-4" />,
  zap: <Zap className="h-4 w-4" />,
  globe: <Globe className="h-4 w-4" />,
  users: <Users className="h-4 w-4" />,
  check: <CheckCircle2 className="h-4 w-4" />,
};

function getSlideIcon(slide: Slide, index: number): React.ReactNode {
  if (slide.icons && slide.icons.length > 0) {
    const iconKey = slide.icons[0].toLowerCase();
    if (SLIDE_ICONS[iconKey]) return SLIDE_ICONS[iconKey];
  }
  const fallbackIcons = [Target, Lightbulb, Rocket, Shield, Zap, Globe, Users, CheckCircle2];
  const Icon = fallbackIcons[index % fallbackIcons.length];
  return <Icon className="h-4 w-4" />;
}

/* --- Chart Components --- */

function BarChartViz({ data }: { data: ChartData }) {
  const maxVal = Math.max(...data.values, 1);
  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      {data.title && (
        <p className="text-[9px] font-semibold text-center mb-1 text-[#1E3A5F] flex-shrink-0 truncate px-2">{data.title}</p>
      )}
      <div className="flex-1 min-h-0 flex items-end justify-center gap-2 px-3 pb-4 pt-4 relative">
        {/* Grid lines */}
        <div className="absolute inset-x-3 top-3 bottom-4 flex flex-col justify-between pointer-events-none">
          {[0, 1, 2].map((i) => (
            <div key={i} className="border-b border-dashed border-[#e8e6dc]" />
          ))}
        </div>
        {data.labels.slice(0, 6).map((label, i) => (
          <div key={i} className="flex flex-col items-center gap-0.5 flex-1 max-w-[50px] relative z-10 h-full justify-end">
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: `${Math.max((data.values[i] / maxVal) * 80, 8)}%`, opacity: 1 }}
              transition={{ duration: 0.8, delay: i * 0.1, ease: [0.34, 1.56, 0.64, 1] }}
              className="w-full rounded-t-sm relative"
              style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
            >
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[6px] font-bold text-[#141413]">
                {data.values[i]}
              </span>
            </motion.div>
            <span className="text-[5px] text-[#5e5d59] truncate w-full text-center leading-none flex-shrink-0">
              {label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PieChartViz({ data }: { data: ChartData }) {
  const total = data.values.reduce((a, b) => a + b, 0) || 1;
  let cumulative = 0;
  return (
    <div className="flex items-center justify-center gap-4 h-full px-2 overflow-hidden">
      <div className="relative w-[70px] h-[70px] flex-shrink-0">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          {data.values.slice(0, 6).map((val, i) => {
            const pct = (val / total) * 100;
            const dashArray = (pct / 100) * 251.33;
            const dashOffset = -(cumulative / total) * 251.33;
            cumulative += val;
            return (
              <circle
                key={i}
                cx="50" cy="50" r="40" fill="none" strokeWidth="18"
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                strokeDasharray={`${dashArray} 251.33`}
                strokeDashoffset={dashOffset}
                strokeLinecap="round"
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[8px] font-bold text-[#1E3A5F]">{total}</span>
        </div>
      </div>
      <div className="space-y-1 min-w-0 overflow-hidden">
        {data.labels.slice(0, 5).map((label, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }} />
            <span className="text-[6px] text-[#5e5d59] leading-tight truncate">
              {label} ({Math.round((data.values[i] / total) * 100)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LineChartViz({ data }: { data: ChartData }) {
  const maxVal = Math.max(...data.values, 1);
  const minVal = Math.min(...data.values);
  const range = maxVal - minVal || 1;
  const points = data.values.slice(0, 8).map((v, i) => ({
    x: 10 + (i / Math.max(data.values.length - 1, 1)) * 80,
    y: 80 - ((v - minVal) / range) * 60,
  }));
  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaD = pathD + ` L ${points[points.length - 1].x} 90 L ${points[0].x} 90 Z`;

  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      {data.title && <p className="text-[9px] font-semibold text-center mb-0.5 text-[#1E3A5F] flex-shrink-0 truncate px-2">{data.title}</p>}
      <div className="flex-1 min-h-0 relative px-1">
        <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#C96442" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#C96442" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {/* Grid */}
          {[0, 1, 2].map((i) => (
            <line key={i} x1="8" y1={25 + i * 25} x2="92" y2={25 + i * 25} stroke="#e8e6dc" strokeWidth="0.3" strokeDasharray="2 2" />
          ))}
          <path d={areaD} fill="url(#areaGrad)" />
          <path d={pathD} fill="none" stroke="#C96442" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          {points.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r="2.5" fill="white" stroke="#C96442" strokeWidth="1.5" />
          ))}
          {points.map((p, i) => (
            <text key={`v${i}`} x={p.x} y={p.y - 5} textAnchor="middle" fontSize="4.5" fill="#141413" fontWeight="600">
              {data.values[i]}
            </text>
          ))}
        </svg>
      </div>
      <div className="flex justify-between px-3 flex-shrink-0">
        {data.labels.slice(0, 8).map((l, i) => <span key={i} className="text-[5px] text-[#5e5d59]">{l}</span>)}
      </div>
    </div>
  );
}

/* --- Table Component --- */

function TableViz({ data }: { data: TableData }) {
  return (
    <div className="w-full overflow-auto rounded-lg border border-[#e8e6dc] shadow-sm">
      <table className="w-full text-[8px] border-collapse">
        {data.headers && (
          <thead>
            <tr className="bg-gradient-to-r from-[#1E3A5F] to-[#2a4f7a]">
              {data.headers.map((h, i) => (
                <th key={i} className="px-2.5 py-2 text-left font-semibold text-white tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {data.rows?.map((row, ri) => (
            <motion.tr
              key={ri}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: ri * 0.05 }}
              className={`${ri % 2 === 0 ? "bg-[#faf9f5]" : "bg-white"} hover:bg-[#f0eee6] transition-colors`}
            >
              {row.map((cell, ci) => (
                <td key={ci} className={`px-2.5 py-1.5 border-t border-[#e8e6dc] text-[#141413] ${ci === 0 ? "font-medium" : ""}`}>
                  {cell}
                </td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


/* --- Slide Content Router --- */

function SlideContent({ slide, index }: { slide: Slide; index: number }) {
  const accent = slide.colorScheme?.accent || "#C96442";
  const hasChart = slide.chartData && slide.chartData.labels && slide.chartData.values && slide.chartData.labels.length > 0;
  const hasTable = slide.tableData && slide.tableData.headers && slide.tableData.headers.length > 0;
  const hasComparison = slide.comparisonData && slide.comparisonData.left && slide.comparisonData.right;
  const hasQuote = slide.quote && slide.quote.text;
  const hasColumns = slide.columns && slide.columns.length >= 2;

  // TITLE SLIDE
  if (slide.type === "title") {
    const isFirst = index === 0;
    // Use content array as key highlights on title slides
    const highlights = (slide.content || []).slice(0, 3);
    return (
      <div className="h-full w-full flex relative overflow-hidden">
        {/* Decorative side panel for first slide */}
        {isFirst && (
          <motion.div
            initial={{ x: -100, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.6 }}
            className="absolute left-0 top-0 bottom-0 w-[28%]"
            style={{ background: `linear-gradient(135deg, #1E3A5F 0%, #2a5280 100%)` }}
          >
            <div className="absolute inset-0 opacity-10">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="absolute rounded-full bg-white/20" style={{
                  width: 20 + i * 15, height: 20 + i * 15,
                  top: `${20 + i * 20}%`, left: `${10 + i * 15}%`,
                }} />
              ))}
            </div>
            {/* Key stats on the navy panel */}
            {isFirst && highlights.length > 0 && (
              <div className="absolute bottom-4 left-3 right-3 space-y-1.5">
                {highlights.map((h, i) => (
                  <div key={i} className="bg-white/10 rounded px-2 py-1">
                    <p className="text-[6px] text-white/90 font-medium truncate">{h.text}</p>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}
        <div className={`w-full h-full flex flex-col justify-center ${isFirst ? "pl-[32%] pr-4" : "items-center text-center px-6"}`}>
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.5 }}
            className={isFirst ? "" : "flex flex-col items-center"}
          >
            {!isFirst && (
              <div className="flex justify-center mb-2">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${accent}15` }}>
                  <span style={{ color: accent }}>{getSlideIcon(slide, index)}</span>
                </div>
              </div>
            )}
            <h2 className="text-[13px] font-bold leading-snug mb-1.5 text-[#141413]">{slide.title}</h2>
            <div className={`w-8 h-[2px] rounded-full mb-1.5 ${isFirst ? "" : "mx-auto"}`} style={{ backgroundColor: accent }} />
            {slide.subtitle && (
              <p className={`text-[9px] text-[#5e5d59] leading-relaxed ${isFirst ? "max-w-[90%]" : "max-w-[80%]"}`}>{slide.subtitle}</p>
            )}
            {/* Highlights as tags on non-first title slides */}
            {!isFirst && highlights.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2 justify-center">
                {highlights.map((h, i) => (
                  <span key={i} className="text-[6px] px-1.5 py-0.5 rounded-full border border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59]">{h.text}</span>
                ))}
              </div>
            )}
            {/* Date/branding line for first slide */}
            {isFirst && (
              <p className="text-[7px] text-[#87867f] mt-3">Powered by IdeaFlow AI</p>
            )}
          </motion.div>
        </div>
      </div>
    );
  }

  // CHART SLIDE (explicit type or has chartData)
  if (slide.type === "chart" || hasChart) {
    return (
      <div className="h-full w-full flex flex-col p-3 overflow-hidden">
        <div className="flex items-center gap-2 mb-1.5 flex-shrink-0">
          <div className="w-5 h-5 rounded-md flex items-center justify-center" style={{ backgroundColor: `${accent}15` }}>
            {slide.chartData?.type === "pie" ? <PieIcon className="h-3 w-3" style={{ color: accent }} /> :
             slide.chartData?.type === "line" ? <TrendingUp className="h-3 w-3" style={{ color: accent }} /> :
             <BarChart3 className="h-3 w-3" style={{ color: accent }} />}
          </div>
          <h2 className="text-[10px] font-bold text-[#141413] truncate">{slide.title}</h2>
        </div>
        <div className="flex-1 min-h-0 rounded-lg bg-[#faf9f5] border border-[#e8e6dc] p-1.5 overflow-hidden">
          {slide.chartData?.type === "pie" ? <PieChartViz data={slide.chartData} /> :
           slide.chartData?.type === "line" ? <LineChartViz data={slide.chartData} /> :
           slide.chartData ? <BarChartViz data={slide.chartData} /> :
           <p className="text-[8px] opacity-40 text-center mt-4">No chart data available</p>}
        </div>
      </div>
    );
  }

  // TABLE SLIDE
  if (slide.type === "table" || hasTable) {
    return (
      <div className="h-full w-full flex flex-col p-3 overflow-hidden">
        <div className="flex items-center gap-2 mb-1.5 flex-shrink-0">
          <div className="w-5 h-5 rounded-md flex items-center justify-center" style={{ backgroundColor: `${accent}15` }}>
            <Table2 className="h-3 w-3" style={{ color: accent }} />
          </div>
          <h2 className="text-[10px] font-bold text-[#141413] truncate">{slide.title}</h2>
        </div>
        <div className="flex-1 min-h-0 overflow-auto">
          {slide.tableData ? <TableViz data={slide.tableData} /> : null}
        </div>
      </div>
    );
  }

  // COMPARISON SLIDE
  if (slide.type === "comparison" || hasComparison) {
    return (
      <div className="h-full w-full flex flex-col p-3 overflow-hidden">
        <div className="flex items-center gap-2 mb-1.5 flex-shrink-0">
          <div className="w-5 h-5 rounded-md flex items-center justify-center" style={{ backgroundColor: `${accent}15` }}>
            <GitCompare className="h-3 w-3" style={{ color: accent }} />
          </div>
          <h2 className="text-[10px] font-bold text-[#141413] truncate">{slide.title}</h2>
        </div>
        {slide.comparisonData && (
          <div className="flex-1 flex gap-1.5 min-h-0 overflow-hidden">
            <div className="flex-1 rounded-md bg-[#faf9f5] border border-[#e8e6dc] p-2 overflow-y-auto">
              <p className="text-[8px] font-bold mb-1.5 flex items-center gap-1" style={{ color: accent }}>
                <ArrowRight className="h-2 w-2" />
                {slide.comparisonData.left.title}
              </p>
              {slide.comparisonData.left.items.map((item, i) => (
                <p key={i} className="text-[7px] mb-0.5 flex items-start gap-1 text-[#141413]">
                  <span className="mt-0.5 w-1 h-1 rounded-full flex-shrink-0" style={{ backgroundColor: accent }} />
                  <span className="line-clamp-2">{item}</span>
                </p>
              ))}
            </div>
            <div className="flex items-center">
              <div className="w-5 h-5 rounded-full bg-[#f0eee6] border border-[#e8e6dc] flex items-center justify-center">
                <span className="text-[6px] font-bold text-[#87867f]">VS</span>
              </div>
            </div>
            <div className="flex-1 rounded-md bg-[#faf9f5] border border-[#e8e6dc] p-2 overflow-y-auto">
              <p className="text-[8px] font-bold mb-1.5 flex items-center gap-1 text-[#1E3A5F]">
                <ArrowRight className="h-2 w-2" />
                {slide.comparisonData.right.title}
              </p>
              {slide.comparisonData.right.items.map((item, i) => (
                <p key={i} className="text-[7px] mb-0.5 flex items-start gap-1 text-[#141413]">
                  <span className="mt-0.5 w-1 h-1 rounded-full flex-shrink-0 bg-[#1E3A5F]" />
                  <span className="line-clamp-2">{item}</span>
                </p>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // QUOTE SLIDE
  if (slide.type === "quote" || hasQuote) {
    const quoteText = slide.quote?.text || slide.content?.[0]?.text || "";
    const quoteAuthor = slide.quote?.author || "";
    return (
      <div className="h-full w-full flex flex-col items-center justify-center p-4 relative overflow-hidden">
        <div className="absolute top-2 left-4 text-[32px] leading-none font-serif opacity-10" style={{ color: accent }}>&ldquo;</div>
        <div className="max-w-[85%] rounded-lg bg-[#faf9f5] border border-[#e8e6dc] p-4 shadow-sm text-center">
          <Quote className="h-3.5 w-3.5 mx-auto mb-1.5 opacity-30" style={{ color: accent }} />
          <p className="text-[9px] italic leading-relaxed text-[#141413] mb-2 line-clamp-4">&ldquo;{quoteText}&rdquo;</p>
          {quoteAuthor && (
            <p className="text-[7px] font-semibold" style={{ color: accent }}>— {quoteAuthor}</p>
          )}
        </div>
      </div>
    );
  }

  // TWO-COLUMN SLIDE
  if (slide.type === "two-column" || hasColumns) {
    return (
      <div className="h-full w-full flex flex-col p-3 overflow-hidden">
        <div className="flex items-center gap-2 mb-1.5 flex-shrink-0">
          <div className="w-5 h-5 rounded-md flex items-center justify-center" style={{ backgroundColor: `${accent}15` }}>
            <Columns className="h-3 w-3" style={{ color: accent }} />
          </div>
          <h2 className="text-[10px] font-bold text-[#141413] truncate">{slide.title}</h2>
        </div>
        <div className="flex-1 flex gap-1.5 min-h-0 overflow-hidden">
          {slide.columns && slide.columns.slice(0, 2).map((col, ci) => (
            <div key={ci} className="flex-1 rounded-md bg-[#faf9f5] border border-[#e8e6dc] p-2 overflow-y-auto">
              {(col as string[]).map((item, ii) => (
                <p key={ii} className="text-[7px] mb-0.5 flex items-start gap-1 text-[#141413]">
                  <span className="mt-0.5 w-1 h-1 rounded-full flex-shrink-0" style={{ backgroundColor: ci === 0 ? accent : "#1E3A5F" }} />
                  <span className="line-clamp-2">{typeof item === "string" ? item : (item as { text?: string })?.text || ""}</span>
                </p>
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // DEFAULT: Content/text slide with rich bullets and icons
  return (
    <div className="h-full w-full flex flex-col p-3 overflow-hidden">
      {/* Title with icon and accent bar */}
      <div className="flex items-center gap-2 mb-1 flex-shrink-0">
        <div className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${accent}15` }}>
          <span style={{ color: accent }}>{getSlideIcon(slide, index)}</span>
        </div>
        <div className="min-w-0">
          <h2 className="text-[10px] font-bold text-[#141413] leading-tight truncate">{slide.title}</h2>
          {slide.subtitle && <p className="text-[6px] text-[#87867f] truncate">{slide.subtitle}</p>}
        </div>
      </div>
      <div className="w-6 h-[2px] rounded-full mb-1.5 ml-7" style={{ backgroundColor: accent, opacity: 0.5 }} />

      {/* Bullet content — scrollable */}
      <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-1">
        {(slide.content || []).slice(0, 4).map((bullet, idx) => (
          <div key={idx} className="ml-1">
            <p className="text-[8px] leading-relaxed flex items-start gap-1.5">
              <span className="mt-1 w-1 h-1 rounded-full flex-shrink-0" style={{ backgroundColor: accent }} />
              <span className="text-[#141413] line-clamp-2">{bullet.text}</span>
            </p>
            {bullet.subPoints?.slice(0, 2).map((sub, si) => (
              <p key={si} className="text-[6px] text-[#5e5d59] ml-4 leading-relaxed mt-0.5 flex items-start gap-1">
                <span className="mt-0.5 w-0.5 h-0.5 rounded-full flex-shrink-0 bg-[#c9c8c3]" />
                <span className="line-clamp-1">{sub}</span>
              </p>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}


/* --- Main Component --- */

export function PPTPreview({ content, isStreaming }: PPTPreviewProps) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [viewMode, setViewMode] = useState<"single" | "grid">("single");

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setCurrentSlide((p) => p + 1);
      if (e.key === "ArrowLeft") setCurrentSlide((p) => Math.max(p - 1, 0));
      if (e.key === "g") setViewMode((m) => m === "grid" ? "single" : "grid");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#f0eee6] to-[#e8e6dc] border border-[#e8e6dc] mb-4 shadow-sm">
          <Presentation className="h-7 w-7 text-[#87867f]" />
        </div>
        <p className="text-sm font-medium text-[#5e5d59]">No Slides Yet</p>
        <p className="text-[11px] text-[#87867f] mt-1">Run the pipeline to generate your presentation</p>
      </div>
    );
  }

  if (isStreaming) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <div className="relative">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#f0eee6] border border-[#e8e6dc]">
            <Presentation className="h-6 w-6 text-[#87867f]" />
          </div>
          <motion.div
            className="absolute -inset-1 rounded-xl border-2 border-[#c96442]"
            animate={{ opacity: [0.3, 1, 0.3], scale: [1, 1.05, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
        </div>
        <p className="text-[11px] text-[#5e5d59] font-medium">Generating slides...</p>
      </div>
    );
  }

  let slides: Slide[];
  try {
    slides = parsePPTSlideData(content).slides;
  } catch (e) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-center max-w-sm shadow-sm">
          <Presentation className="h-7 w-7 text-red-400 mx-auto mb-3" />
          <p className="text-xs font-semibold text-red-800">Failed to parse presentation data</p>
          <p className="text-[10px] text-red-600 mt-2 leading-relaxed">{e instanceof Error ? e.message : "Unknown error"}</p>
        </div>
      </div>
    );
  }

  if (!slides?.length) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-xs text-[#87867f]">No slides found in the output.</p>
      </div>
    );
  }

  const safeIndex = Math.min(Math.max(currentSlide, 0), slides.length - 1);
  if (currentSlide !== safeIndex) setCurrentSlide(safeIndex);
  const slide = slides[safeIndex];
  const progress = ((safeIndex + 1) / slides.length) * 100;

  // GRID VIEW
  if (viewMode === "grid") {
    return (
      <div className="p-4 h-full overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Presentation className="h-4 w-4 text-[#c96442]" />
            <span className="text-[12px] font-semibold text-[#141413]">{slides.length} Slides</span>
          </div>
          <button onClick={() => setViewMode("single")} className="text-[10px] text-[#c96442] hover:underline flex items-center gap-1 font-medium">
            <Maximize2 className="h-3 w-3" /> Slide View
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {slides.map((s, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.03 }}
              whileHover={{ scale: 1.03, y: -2 }}
              onClick={() => { setCurrentSlide(idx); setViewMode("single"); }}
              className={`cursor-pointer rounded-lg border overflow-hidden transition-all shadow-sm hover:shadow-md ${
                idx === safeIndex ? "border-[#c96442] ring-2 ring-[#c96442]/20" : "border-[#e8e6dc]"
              }`}
              style={{ aspectRatio: "16/9", backgroundColor: "#fff" }}
            >
              <div className="h-full flex flex-col relative">
                <div className="h-1 w-full" style={{ backgroundColor: s.colorScheme?.accent || "#c96442" }} />
                <div className="flex-1 p-2 overflow-hidden">
                  <p className="text-[7px] font-bold truncate text-[#141413]">{s.title}</p>
                  {s.subtitle && <p className="text-[5px] text-[#87867f] mt-0.5 truncate">{s.subtitle}</p>}
                  <div className="mt-1 flex items-center gap-1">
                    <span className="text-[5px] px-1 py-0.5 rounded bg-[#f0eee6] text-[#5e5d59] font-medium">{s.type}</span>
                    {s.chartData && <BarChart3 className="h-2 w-2 text-[#c96442]" />}
                    {s.tableData && <Table2 className="h-2 w-2 text-[#1E3A5F]" />}
                    {s.comparisonData && <GitCompare className="h-2 w-2 text-[#8B5CF6]" />}
                  </div>
                </div>
                <div className="absolute bottom-1 right-1.5 text-[6px] text-[#87867f] font-medium">{idx + 1}</div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    );
  }

  // SINGLE SLIDE VIEW
  return (
    <div className="flex flex-col h-full">
      {/* Controls */}
      <div className="flex items-center justify-between px-4 py-2.5 flex-shrink-0 border-b border-[#e8e6dc]/50">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentSlide(Math.max(0, safeIndex - 1))}
            disabled={safeIndex === 0}
            className="h-7 w-7 flex items-center justify-center rounded-lg bg-[#f0eee6] border border-[#e8e6dc] text-[#5e5d59] hover:bg-[#e8e6dc] hover:text-[#141413] disabled:opacity-30 transition-all"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <div className="flex items-center gap-1.5 px-2">
            <span className="text-[11px] font-semibold text-[#141413]">{safeIndex + 1}</span>
            <span className="text-[10px] text-[#87867f]">/</span>
            <span className="text-[11px] text-[#5e5d59]">{slides.length}</span>
          </div>
          <button
            onClick={() => setCurrentSlide(Math.min(slides.length - 1, safeIndex + 1))}
            disabled={safeIndex === slides.length - 1}
            className="h-7 w-7 flex items-center justify-center rounded-lg bg-[#f0eee6] border border-[#e8e6dc] text-[#5e5d59] hover:bg-[#e8e6dc] hover:text-[#141413] disabled:opacity-30 transition-all"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[9px] px-2 py-0.5 rounded-full bg-[#f0eee6] text-[#5e5d59] font-medium border border-[#e8e6dc]">
            {slide.type}
          </span>
          <button onClick={() => setViewMode("grid")} className="text-[10px] text-[#87867f] hover:text-[#141413] flex items-center gap-1 transition-colors">
            <Grid3X3 className="h-3.5 w-3.5" /> Grid
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-[3px] bg-[#f0eee6] mx-4 rounded-full overflow-hidden flex-shrink-0">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: slide.colorScheme?.accent || "#c96442" }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>

      {/* Slide Canvas */}
      <div className="flex-1 flex items-center justify-center p-3 min-h-0">
        <AnimatePresence mode="wait">
          <motion.div
            key={safeIndex}
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="w-full max-w-[520px] rounded-xl border border-[#e8e6dc] overflow-hidden shadow-xl shadow-black/5 relative flex flex-col"
            style={{
              aspectRatio: "16/9",
              backgroundColor: slide.colorScheme?.background || "#fff",
              color: slide.colorScheme?.text || "#141413",
            }}
          >
            {/* Top accent bar */}
            <div className="absolute top-0 left-0 right-0 h-[3px] z-10" style={{ background: `linear-gradient(90deg, ${slide.colorScheme?.accent || "#c96442"}, ${slide.colorScheme?.accent || "#c96442"}80, transparent)` }} />
            <div className="flex-1 min-h-0 pt-[3px]">
              <SlideContent slide={slide} index={safeIndex} />
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Thumbnail strip */}
      <div className="flex gap-1.5 px-4 pb-3 overflow-x-auto flex-shrink-0">
        {slides.map((s, idx) => (
          <button
            key={idx}
            onClick={() => setCurrentSlide(idx)}
            className={`flex-shrink-0 rounded-md border overflow-hidden transition-all ${
              idx === safeIndex
                ? "border-[#c96442] ring-2 ring-[#c96442]/20 scale-105 shadow-sm"
                : "border-[#e8e6dc] opacity-50 hover:opacity-100 hover:border-[#c9c8c3]"
            }`}
            style={{ width: 52, height: 30, backgroundColor: "#fff" }}
          >
            <div className="w-full h-full p-0.5 flex flex-col">
              <div className="h-[2px] w-full rounded-full" style={{ backgroundColor: s.colorScheme?.accent || "#c96442" }} />
              <div className="flex-1 flex items-center justify-center">
                <p className="text-[4px] font-medium truncate px-0.5 text-[#141413]">{s.title}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
