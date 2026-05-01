import type { SlideData } from "@/types";

const MAX_SLIDES = 10;
const MAX_BULLETS_PER_SLIDE = 5;

/**
 * Parse a JSON string into a validated SlideData object.
 * Throws a descriptive error on malformed JSON or validation failure.
 */
export function parsePPTSlideData(json: string): SlideData {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch (e) {
    throw new Error(
      `Failed to parse PPT slide JSON: ${e instanceof Error ? e.message : "Invalid JSON"}`
    );
  }

  if (!parsed || typeof parsed !== "object") {
    throw new Error("Invalid PPT slide data: expected an object");
  }

  const obj = parsed as Record<string, unknown>;

  if (!Array.isArray(obj.slides)) {
    throw new Error(
      'Invalid PPT slide data: missing or invalid "slides" array'
    );
  }

  if (obj.slides.length > MAX_SLIDES) {
    throw new Error(
      `Invalid PPT slide data: too many slides (${obj.slides.length}), maximum is ${MAX_SLIDES}`
    );
  }

  for (let i = 0; i < obj.slides.length; i++) {
    const slide = obj.slides[i];
    if (!slide || typeof slide !== "object") {
      throw new Error(`Invalid PPT slide data: slide at index ${i} is invalid`);
    }

    const s = slide as Record<string, unknown>;
    if (!Array.isArray(s.content)) {
      throw new Error(
        `Invalid PPT slide data: slide at index ${i} has missing or invalid "content" array`
      );
    }

    if (s.content.length > MAX_BULLETS_PER_SLIDE) {
      throw new Error(
        `Invalid PPT slide data: slide at index ${i} has too many bullet points (${s.content.length}), maximum is ${MAX_BULLETS_PER_SLIDE}`
      );
    }
  }

  return obj as unknown as SlideData;
}

/**
 * Serialize a SlideData object to a JSON string.
 */
export function serializePPTSlideData(data: SlideData): string {
  return JSON.stringify(data);
}
