"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronLeft, ChevronRight, Presentation, ChevronDown, ChevronUp, StickyNote } from "lucide-react";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";
import type { Slide, ChartData, TableData, ComparisonData } from "@/types";

interface PPTPreviewProps {
  content?: string;
  isStreaming?: boolean;
}

function getLayoutBadgeColor(layout?: string): string {
  switch (layout) {
    case "title": return "bg-purple-400/20 text-purple-400";
    case "content": return "bg-blue-400/20 text-blue-400";
    case "two-column": return "bg-cyan-400/20 text-cyan-400";
    case "image-text": return "bg-emerald-400/20 text-emerald-400";
    case "quote": return "bg-amber-400/20 text-amber-400";
    case "chart": return "bg-rose-400/20 text-rose-400";
    case "timeline": return "bg-indigo-400/20 text-indigo-400";
    case "comparison": return "bg-orange-400/20 text-orange-400";
    default: return "bg-grey/20 text-grey/70";
  }
}

/* ─── Chart Renderers ─── */

function BarChart({ data, accent }: { data: ChartData; accent: string }) {
  const maxVal = Math.max(...data.values);
  return (
    <div className="flex flex-col gap-1.5 w-full">
      {data.title && (
        <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70 mb-1">{data.title}</p>
      )}
      {data.labels.map((label, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-[9px] w-8 text-right opacity-70 shrink-0">{label}</span>
          <div className="flex-1 h-4 rounded-sm overflow-hidden bg-white/5">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(data.values[i] / maxVal) * 100}%` }}
              transition={{ duration: 0.8, delay: i * 0.1, ease: "easeOut" }}
              className="h-full rounded-sm"
              style={{ backgroundColor: accent }}
            />
          </div>
          <span className="text-[9px] w-6 opacity-60">{data.values[i]}</span>
        </div>
      ))}
    </div>
  );
}

function PieChart({ data, accent }: { data: ChartData; accent: string }) {
  const total = data.values.reduce((a, b) => a + b, 0);
  const colors = [accent, `${accent}CC`, `${accent}99`, `${accent}66`, `${accent}44`];

  let cumulativePercent = 0;
  const segments = data.values.map((val, i) => {
    const percent = (val / total) * 100;
    const start = cumulativePercent;
    cumulativePercent += percent;
    return { start, percent, color: colors[i % colors.length], label: data.labels[i], value: val };
  });

  const gradientStops = segments
    .map((seg) => `${seg.color} ${seg.start}% ${seg.start + seg.percent}%`)
    .join(", ");

  return (
    <div className="flex items-center gap-4 w-full">
      <div
        className="w-20 h-20 rounded-full shrink-0"
        style={{ background: `conic-gradient(${gradientStops})` }}
      />
      <div className="flex flex-col gap-1">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: seg.color }} />
            <span className="text-[9px] opacity-80">{seg.label}</span>
            <span className="text-[9px] opacity-50">{seg.value}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LineChart({ data, accent }: { data: ChartData; accent: string }) {
  const maxVal = Math.max(...data.values);
  const width = 200;
  const height = 60;
  const padding = 10;
  const points = data.values.map((val, i) => ({
    x: padding + (i / (data.values.length - 1)) * (width - padding * 2),
    y: height - padding - ((val / maxVal) * (height - padding * 2)),
  }));
  const polyline = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <div className="w-full">
      {data.title && (
        <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70 mb-1">{data.title}</p>
      )}
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-16">
        <polyline
          points={polyline}
          fill="none"
          stroke={accent}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill={accent} />
        ))}
      </svg>
      <div className="flex justify-between px-2">
        {data.labels.map((label, i) => (
          <span key={i} className="text-[8px] opacity-50">{label}</span>
        ))}
      </div>
    </div>
  );
}

/* ─── Table Renderer ─── */

function SlideTable({ data, accent, textColor }: { data: TableData; accent: string; textColor: string }) {
  return (
    <div className="w-full overflow-x-auto rounded-md border border-white/10">
      <table className="w-full text-[9px] border-collapse">
        <thead>
          <tr style={{ backgroundColor: accent }}>
            {data.headers.map((header, i) => (
              <th key={i} className="px-2 py-1.5 text-left font-bold" style={{ color: "#FFFFFF" }}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className="border-t border-white/5"
              style={{ backgroundColor: rowIdx % 2 === 0 ? "rgba(255,255,255,0.03)" : "transparent" }}
            >
              {row.map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  className="px-2 py-1.5"
                  style={{
                    color: cell.includes("✓") || cell.includes("\u2713")
                      ? "#4ADE80"
                      : cell.includes("✗") || cell.includes("\u2717")
                        ? "#6B7280"
                        : textColor,
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Comparison Renderer ─── */

function ComparisonView({ data }: { data: ComparisonData }) {
  return (
    <div className="flex gap-2 w-full">
      <div className="flex-1 rounded-lg p-3 bg-red-900/20 border border-red-500/20">
        <p className="text-[10px] font-bold mb-2 text-red-300">{data.left.title}</p>
        <div className="space-y-1.5">
          {data.left.items.map((item, i) => (
            <p key={i} className="text-[9px] opacity-80 leading-relaxed">
              <span className="text-red-400 mr-1">✗</span> {item}
            </p>
          ))}
        </div>
      </div>
      <div className="flex-1 rounded-lg p-3 bg-green-900/20 border border-green-500/20">
        <p className="text-[10px] font-bold mb-2 text-green-300">{data.right.title}</p>
        <div className="space-y-1.5">
          {data.right.items.map((item, i) => (
            <p key={i} className="text-[9px] opacity-80 leading-relaxed">
              <span className="text-green-400 mr-1">✓</span> {item}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Two-Column Renderer ─── */

function TwoColumnView({ slide }: { slide: Slide }) {
  const columns = slide.columns;
  if (!columns) return null;

  const leftItems = columns[0];
  const rightItems = columns[1];

  const getItemText = (item: string | { text: string }): string => {
    if (typeof item === "string") return item;
    return item.text;
  };

  return (
    <div className="flex gap-3 w-full">
      <div className="flex-1 border-r border-white/10 pr-3">
        <p className="text-[10px] font-bold mb-2 opacity-70 uppercase tracking-wide">Frontend</p>
        <div className="space-y-1.5">
          {leftItems.map((item, i) => (
            <p key={i} className="text-[10px] opacity-80">
              <span className="opacity-50 mr-1.5">▸</span>
              {getItemText(item as string | { text: string })}
            </p>
          ))}
        </div>
      </div>
      <div className="flex-1 pl-3">
        <p className="text-[10px] font-bold mb-2 opacity-70 uppercase tracking-wide">Backend</p>
        <div className="space-y-1.5">
          {rightItems.map((item, i) => (
            <p key={i} className="text-[10px] opacity-80">
              <span className="opacity-50 mr-1.5">▸</span>
              {getItemText(item as string | { text: string })}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Title Slide Renderer ─── */

function TitleSlideContent({ slide }: { slide: Slide }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
      <h2 className="text-xl font-bold leading-tight mb-3">{slide.title}</h2>
      <div className="w-12 h-0.5 rounded-full mb-3" style={{ backgroundColor: slide.colorScheme?.accent || "#AAAAAA" }} />
      {slide.subtitle && (
        <p className="text-sm opacity-70">{slide.subtitle}</p>
      )}
      {!slide.subtitle && slide.content.length > 0 && (
        <p className="text-sm opacity-70">{slide.content[0]?.text}</p>
      )}
    </div>
  );
}

/* ─── Quote Slide Renderer ─── */

function QuoteSlideContent({ slide }: { slide: Slide }) {
  const quote = slide.quote;
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
      <span className="text-3xl opacity-30 mb-2">&ldquo;</span>
      <p className="text-sm italic leading-relaxed opacity-90 max-w-[80%]">
        {quote?.text || slide.content[0]?.text || ""}
      </p>
      <span className="text-3xl opacity-30 mt-2">&rdquo;</span>
      {quote?.author && (
        <p className="text-[10px] mt-3 opacity-60">— {quote.author}</p>
      )}
    </div>
  );
}

/* ─── Slide Content Router ─── */

function SlideContent({ slide }: { slide: Slide }) {
  const accent = slide.colorScheme?.accent || "#AAAAAA";
  const textColor = slide.colorScheme?.text || "#FFFFFF";

  switch (slide.type) {
    case "title":
      return <TitleSlideContent slide={slide} />;

    case "quote":
      return <QuoteSlideContent slide={slide} />;

    case "chart":
      return (
        <div className="flex-1 flex flex-col p-6">
          <h2 className="mb-3 text-base font-bold leading-tight">{slide.title}</h2>
          <div className="flex-1 flex flex-col justify-center">
            {slide.chartData && (
              <div className="mb-3">
                {slide.chartData.type === "bar" && <BarChart data={slide.chartData} accent={accent} />}
                {slide.chartData.type === "pie" && <PieChart data={slide.chartData} accent={accent} />}
                {slide.chartData.type === "line" && <LineChart data={slide.chartData} accent={accent} />}
              </div>
            )}
            {slide.content.length > 0 && (
              <div className="space-y-1 mt-2">
                {slide.content.map((bullet, i) => (
                  <p key={i} className="text-[10px] opacity-70">
                    <span className="opacity-50 mr-1.5">•</span>{bullet.text}
                  </p>
                ))}
              </div>
            )}
          </div>
        </div>
      );

    case "table":
      return (
        <div className="flex-1 flex flex-col p-6">
          <h2 className="mb-3 text-base font-bold leading-tight">{slide.title}</h2>
          <div className="flex-1 flex flex-col justify-center">
            {slide.tableData && <SlideTable data={slide.tableData} accent={accent} textColor={textColor} />}
            {slide.content.length > 0 && (
              <div className="space-y-1 mt-3">
                {slide.content.map((bullet, i) => (
                  <p key={i} className="text-[10px] opacity-70">
                    <span className="opacity-50 mr-1.5">•</span>{bullet.text}
                  </p>
                ))}
              </div>
            )}
          </div>
        </div>
      );

    case "two-column":
      return (
        <div className="flex-1 flex flex-col p-6">
          <h2 className="mb-4 text-base font-bold leading-tight">{slide.title}</h2>
          <div className="flex-1 flex flex-col justify-center">
            <TwoColumnView slide={slide} />
            {slide.content.length > 0 && (
              <div className="space-y-1 mt-3">
                {slide.content.map((bullet, i) => (
                  <p key={i} className="text-[10px] opacity-60">
                    <span className="opacity-50 mr-1.5">•</span>{bullet.text}
                  </p>
                ))}
              </div>
            )}
          </div>
        </div>
      );

    case "comparison":
      return (
        <div className="flex-1 flex flex-col p-6">
          <h2 className="mb-3 text-base font-bold leading-tight">{slide.title}</h2>
          <div className="flex-1 flex flex-col justify-center">
            {slide.comparisonData && <ComparisonView data={slide.comparisonData} />}
            {slide.content.length > 0 && (
              <div className="space-y-1 mt-3">
                {slide.content.map((bullet, i) => (
                  <p key={i} className="text-[10px] opacity-60">
                    <span className="opacity-50 mr-1.5">•</span>{bullet.text}
                  </p>
                ))}
              </div>
            )}
          </div>
        </div>
      );

    default:
      // Default text/bullet rendering
      return (
        <div className="flex-1 flex flex-col p-6">
          <h2 className="mb-4 text-base font-bold leading-tight">{slide.title}</h2>
          <div className="flex-1 space-y-2.5 overflow-y-auto">
            {slide.content.map((bullet, bulletIdx) => (
              <div key={bulletIdx}>
                <p className="text-sm leading-relaxed">
                  <span className="opacity-60 mr-2">&bull;</span>
                  {bullet.text}
                </p>
                {bullet.subPoints && bullet.subPoints.length > 0 && (
                  <div className="ml-5 mt-1 space-y-1">
                    {bullet.subPoints.map((sub, subIdx) => (
                      <p key={subIdx} className="text-xs opacity-70 leading-relaxed">
                        <span className="opacity-60 mr-2">&#9702;</span>
                        {sub}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      );
  }
}

/**
 * Renders PPT slides in a carousel with prev/next navigation.
 * Features 16:9 aspect ratio cards, dot indicators, circular nav buttons,
 * speaker notes (collapsible), layout type badges, and slide count.
 */
export function PPTPreview({ content, isStreaming }: PPTPreviewProps) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [showNotes, setShowNotes] = useState(false);

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-navy/50 border border-grey/10 mb-4">
          <Presentation className="h-7 w-7 text-grey/40" />
        </div>
        <p className="text-sm font-medium text-grey/60 mb-1">No Slides Yet</p>
        <p className="text-xs text-grey/40 text-center max-w-[200px]">
          PPT slide content will appear here once generation begins.
        </p>
      </div>
    );
  }

  let slides: Slide[];
  let parseError: string | null = null;

  try {
    const data = parsePPTSlideData(content);
    slides = data.slides;
  } catch (e) {
    // While streaming, always show loading — don't flash parse errors
    if (isStreaming) {
      return (
        <div className="flex h-full flex-col items-center justify-center px-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-navy/50 border border-grey/10 mb-3 animate-pulse">
            <Presentation className="h-5 w-5 text-grey/50" />
          </div>
          <p className="text-xs text-grey/50">Generating slides...</p>
        </div>
      );
    }
    parseError = e instanceof Error ? e.message : "Failed to parse slide data";
    slides = [];
  }

  if (parseError) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="rounded-xl border border-grey/20 bg-navy/30 p-4 text-center">
          <p className="text-sm text-grey">{parseError}</p>
        </div>
      </div>
    );
  }

  if (slides.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-grey">No slides to display.</p>
      </div>
    );
  }

  const safeIndex = Math.min(currentSlide, slides.length - 1);
  const slide = slides[safeIndex];

  const goToPrev = () => {
    setCurrentSlide((prev) => Math.max(0, prev - 1));
  };

  const goToNext = () => {
    setCurrentSlide((prev) => Math.min(slides.length - 1, prev + 1));
  };

  return (
    <div className="p-5 space-y-4">
      {/* Navigation header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {slides.length > 1 && (
            <button
              onClick={goToPrev}
              disabled={safeIndex === 0}
              className="flex h-7 w-7 items-center justify-center rounded-md bg-white/5 border border-white/10 text-white/60 hover:text-white hover:bg-white/10 transition-all disabled:opacity-30"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
          )}
          <span className="text-[11px] text-white/50 font-medium">
            Slide {safeIndex + 1} of {slides.length}
          </span>
          {slides.length > 1 && (
            <button
              onClick={goToNext}
              disabled={safeIndex === slides.length - 1}
              className="flex h-7 w-7 items-center justify-center rounded-md bg-white/5 border border-white/10 text-white/60 hover:text-white hover:bg-white/10 transition-all disabled:opacity-30"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {slide.layout && (
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${getLayoutBadgeColor(slide.layout)}`}>
              {slide.layout}
            </span>
          )}
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-medium bg-grey/10 text-grey/60`}>
            {slide.type}
          </span>
        </div>
      </div>

      {/* Slide card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={safeIndex}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.25, ease: "easeInOut" }}
          className="w-full max-w-[420px] mx-auto rounded-lg border border-grey/20 overflow-hidden shadow-xl shadow-black/30"
          style={{
            backgroundColor: slide.colorScheme?.background || "#001f3f",
            color: slide.colorScheme?.text || "#FFFFFF",
            aspectRatio: "16 / 9",
          }}
        >
          <div className="h-full flex flex-col overflow-y-auto">
            <SlideContent slide={slide} />
            <div className="px-4 pb-2 pt-1 border-t border-white/10 flex items-center justify-between mt-auto">
              <span className="text-[8px] uppercase tracking-widest font-medium opacity-40" style={{ color: slide.colorScheme?.accent || "#AAAAAA" }}>
                {slide.type}
              </span>
              <span className="text-[8px] opacity-30">{safeIndex + 1} / {slides.length}</span>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Speaker Notes */}
      {slide.speakerNotes && (
        <div className="rounded-lg border border-grey/15 bg-black/30 overflow-hidden">
          <button
            onClick={() => setShowNotes(!showNotes)}
            className="flex items-center justify-between w-full px-3 py-2 text-[11px] font-medium text-grey/60 hover:text-white transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <StickyNote className="h-3 w-3" />
              <span>Speaker Notes</span>
            </div>
            {showNotes ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          <AnimatePresence>
            {showNotes && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="px-3 pb-3 text-[11px] text-grey/70 leading-relaxed border-t border-grey/10 pt-2">
                  {slide.speakerNotes}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Thumbnail strip */}
      {slides.length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {slides.map((s, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentSlide(idx)}
              className={`flex-shrink-0 rounded-md border p-1.5 transition-all duration-200 min-w-[72px] ${
                idx === safeIndex
                  ? "border-white/40 bg-navy/50"
                  : "border-grey/15 bg-black/30 hover:border-grey/30"
              }`}
            >
              <div
                className="rounded-sm h-9 flex items-center justify-center"
                style={{ backgroundColor: s.colorScheme?.background || "#001f3f" }}
              >
                <span className="text-[8px] font-medium text-white/70 truncate px-1">
                  {s.title}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
