"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronLeft, ChevronRight, Presentation } from "lucide-react";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";
import type { Slide } from "@/types";

interface PPTPreviewProps {
  content?: string;
}

/**
 * Renders PPT slides in a carousel with prev/next navigation.
 * Features 16:9 aspect ratio cards, dot indicators, circular nav buttons,
 * and a thumbnail strip for multiple slides.
 */
export function PPTPreview({ content }: PPTPreviewProps) {
  const [currentSlide, setCurrentSlide] = useState(0);

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
    <div className="flex h-full flex-col p-4 gap-3">
      {/* Slide card with 16:9 aspect ratio feel */}
      <div className="relative flex-1 min-h-0">
        <AnimatePresence mode="wait">
          <motion.div
            key={safeIndex}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 flex flex-col rounded-xl border border-grey/20 overflow-hidden shadow-lg"
            style={{
              backgroundColor: slide.colorScheme?.background || "#001f3f",
              color: slide.colorScheme?.text || "#FFFFFF",
            }}
          >
            {/* Slide content */}
            <div className="flex-1 flex flex-col p-6">
              <h2 className="mb-4 text-base font-bold leading-tight">{slide.title}</h2>

              <div className="flex-1 space-y-2.5 overflow-y-auto">
                {slide.content.map((bullet, bulletIdx) => (
                  <div key={bulletIdx}>
                    <p className="text-sm leading-relaxed">
                      <span className="opacity-60 mr-2">•</span>
                      {bullet.text}
                    </p>
                    {bullet.subPoints && bullet.subPoints.length > 0 && (
                      <div className="ml-5 mt-1 space-y-1">
                        {bullet.subPoints.map((sub, subIdx) => (
                          <p key={subIdx} className="text-xs opacity-70 leading-relaxed">
                            <span className="opacity-60 mr-2">◦</span>
                            {sub}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Slide type badge */}
              <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between">
                <span
                  className="text-[10px] uppercase tracking-widest font-medium opacity-50"
                  style={{ color: slide.colorScheme?.accent || "#AAAAAA" }}
                >
                  {slide.type}
                </span>
                <span className="text-[10px] opacity-40">
                  {safeIndex + 1} / {slides.length}
                </span>
              </div>
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Circular navigation buttons overlaid on slide */}
        {slides.length > 1 && (
          <>
            <button
              onClick={goToPrev}
              disabled={safeIndex === 0}
              className="absolute left-2 top-1/2 -translate-y-1/2 flex h-8 w-8 items-center justify-center rounded-full bg-black/50 border border-grey/20 text-white/80 hover:bg-black/70 hover:text-white transition-all duration-200 disabled:opacity-0 disabled:pointer-events-none backdrop-blur-sm"
              aria-label="Previous slide"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={goToNext}
              disabled={safeIndex === slides.length - 1}
              className="absolute right-2 top-1/2 -translate-y-1/2 flex h-8 w-8 items-center justify-center rounded-full bg-black/50 border border-grey/20 text-white/80 hover:bg-black/70 hover:text-white transition-all duration-200 disabled:opacity-0 disabled:pointer-events-none backdrop-blur-sm"
              aria-label="Next slide"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </>
        )}
      </div>

      {/* Dot indicators */}
      {slides.length > 1 && (
        <div className="flex items-center justify-center gap-1.5">
          {slides.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentSlide(idx)}
              className={`rounded-full transition-all duration-200 ${
                idx === safeIndex
                  ? "h-2 w-5 bg-white"
                  : "h-2 w-2 bg-grey/30 hover:bg-grey/50"
              }`}
              aria-label={`Go to slide ${idx + 1}`}
            />
          ))}
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
