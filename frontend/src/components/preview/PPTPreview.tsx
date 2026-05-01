"use client";

import { useState } from "react";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";
import type { Slide } from "@/types";

interface PPTPreviewProps {
  content?: string;
}

/**
 * Renders PPT slides in a carousel with prev/next navigation.
 * Each slide is rendered as a card following the approved color palette.
 */
export function PPTPreview({ content }: PPTPreviewProps) {
  const [currentSlide, setCurrentSlide] = useState(0);

  if (!content) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-grey">
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
        <div className="rounded-lg border border-grey/30 bg-navy/30 p-4 text-center">
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
    <div className="flex h-full flex-col p-4">
      {/* Slide card */}
      <div
        className="flex flex-1 flex-col rounded-lg border border-grey/30 p-6 fade-in"
        style={{
          backgroundColor: slide.colorScheme?.background || "#001f3f",
          color: slide.colorScheme?.text || "#FFFFFF",
        }}
      >
        <h2 className="mb-4 text-lg font-bold">{slide.title}</h2>

        <div className="flex-1 space-y-2">
          {slide.content.map((bullet, bulletIdx) => (
            <div key={bulletIdx}>
              <p className="text-sm">• {bullet.text}</p>
              {bullet.subPoints && bullet.subPoints.length > 0 && (
                <div className="ml-4 space-y-1">
                  {bullet.subPoints.map((sub, subIdx) => (
                    <p key={subIdx} className="text-xs opacity-80">
                      ◦ {sub}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-white/20 pt-3">
          <span
            className="text-xs uppercase tracking-wide opacity-60"
            style={{ color: slide.colorScheme?.accent || "#AAAAAA" }}
          >
            {slide.type}
          </span>
        </div>
      </div>

      {/* Navigation controls */}
      <div className="mt-3 flex items-center justify-between">
        <button
          onClick={goToPrev}
          disabled={safeIndex === 0}
          className="rounded border border-grey/30 px-3 py-1 text-sm text-white transition-colors hover:bg-navy/50 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Previous slide"
        >
          ← Prev
        </button>

        <span className="text-xs text-grey">
          {safeIndex + 1} / {slides.length}
        </span>

        <button
          onClick={goToNext}
          disabled={safeIndex === slides.length - 1}
          className="rounded border border-grey/30 px-3 py-1 text-sm text-white transition-colors hover:bg-navy/50 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Next slide"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
