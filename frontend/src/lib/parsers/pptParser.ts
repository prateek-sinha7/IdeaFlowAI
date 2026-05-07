import type { SlideData } from "@/types";

/**
 * Extract JSON from a string that might contain markdown code fences,
 * extra text before/after the JSON, or other wrapping.
 */
function extractJSON(input: string): string {
  let str = input.trim();

  // Remove markdown code fences: ```json ... ``` or ``` ... ```
  const fenceMatch = str.match(/```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/);
  if (fenceMatch) {
    str = fenceMatch[1].trim();
  }

  // Try to find JSON object boundaries
  const firstBrace = str.indexOf("{");
  const lastBrace = str.lastIndexOf("}");
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    str = str.slice(firstBrace, lastBrace + 1);
  }

  return str;
}

/**
 * Attempt to repair truncated JSON by closing open brackets/braces.
 */
function repairTruncatedJSON(json: string): string {
  let str = json.trim();
  
  // Count open/close brackets
  let openBraces = 0;
  let openBrackets = 0;
  let inString = false;
  let escaped = false;

  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (escaped) { escaped = false; continue; }
    if (ch === "\\") { escaped = true; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (inString) continue;
    if (ch === "{") openBraces++;
    if (ch === "}") openBraces--;
    if (ch === "[") openBrackets++;
    if (ch === "]") openBrackets--;
  }

  // If we're inside a string, close it
  if (inString) {
    str += '"';
  }

  // Remove trailing comma if present
  str = str.replace(/,\s*$/, "");

  // Close any open brackets/braces
  while (openBrackets > 0) { str += "]"; openBrackets--; }
  while (openBraces > 0) { str += "}"; openBraces--; }

  return str;
}

/**
 * Parse a JSON string into a validated SlideData object.
 * Handles common LLM output issues:
 * - Markdown code fences around JSON
 * - Extra text before/after JSON
 * - Missing optional fields
 * - Relaxed validation (doesn't fail on extra content)
 */
export function parsePPTSlideData(json: string): SlideData {
  const extracted = extractJSON(json);

  let parsed: unknown;
  try {
    parsed = JSON.parse(extracted);
  } catch (e) {
    // Try to repair truncated JSON
    try {
      const repaired = repairTruncatedJSON(extracted);
      parsed = JSON.parse(repaired);
    } catch (e2) {
      throw new Error(
        `Failed to parse PPT slide JSON: ${e instanceof Error ? e.message : "Invalid JSON"}`
      );
    }
  }

  if (!parsed || typeof parsed !== "object") {
    throw new Error("Invalid PPT slide data: expected an object");
  }

  const obj = parsed as Record<string, unknown>;

  // Handle case where the response is the slides array directly
  if (Array.isArray(parsed)) {
    return { slides: normalizeSlides(parsed) };
  }

  if (!Array.isArray(obj.slides)) {
    // Try to find slides in nested structure
    if (obj.presentation && typeof obj.presentation === "object") {
      const pres = obj.presentation as Record<string, unknown>;
      if (Array.isArray(pres.slides)) {
        return { slides: normalizeSlides(pres.slides) };
      }
    }
    throw new Error(
      'Invalid PPT slide data: missing "slides" array'
    );
  }

  return { slides: normalizeSlides(obj.slides) };
}

/**
 * Normalize slides array — ensure each slide has required fields with defaults.
 */
function normalizeSlides(slides: unknown[]): SlideData["slides"] {
  return slides.map((slide, i) => {
    if (!slide || typeof slide !== "object") {
      return {
        title: `Slide ${i + 1}`,
        content: [{ text: "Content unavailable", subPoints: [] }],
        type: "text" as const,
        colorScheme: { background: "#ffffff", text: "#141413", accent: "#c96442" },
      };
    }

    const s = slide as Record<string, unknown>;

    return {
      title: (s.title as string) || `Slide ${i + 1}`,
      subtitle: (s.subtitle as string) || undefined,
      content: normalizeContent(s.content),
      type: (s.type as string) || "text",
      layout: (s.layout as string) || undefined,
      colorScheme: normalizeColorScheme(s.colorScheme),
      speakerNotes: (s.speakerNotes as string) || (s.speaker_notes as string) || undefined,
      chartData: s.chartData || s.chart_data || undefined,
      tableData: s.tableData || s.table_data || undefined,
      comparisonData: s.comparisonData || s.comparison_data || undefined,
      columns: s.columns || undefined,
      quote: s.quote || undefined,
    } as SlideData["slides"][number];
  });
}

/**
 * Normalize content array — handle various formats Claude might output.
 */
function normalizeContent(content: unknown): { text: string; subPoints?: string[] }[] {
  if (!content) return [];
  if (!Array.isArray(content)) {
    // If content is a string, wrap it
    if (typeof content === "string") {
      return [{ text: content, subPoints: [] }];
    }
    return [];
  }

  return content.map((item) => {
    if (typeof item === "string") {
      return { text: item, subPoints: [] };
    }
    if (item && typeof item === "object") {
      const obj = item as Record<string, unknown>;
      return {
        text: (obj.text as string) || (obj.bullet as string) || (obj.point as string) || "",
        subPoints: Array.isArray(obj.subPoints) ? obj.subPoints.filter((s): s is string => typeof s === "string") :
                   Array.isArray(obj.sub_points) ? obj.sub_points.filter((s): s is string => typeof s === "string") : [],
      };
    }
    return { text: String(item), subPoints: [] };
  });
}

/**
 * Normalize color scheme with light theme defaults.
 */
function normalizeColorScheme(cs: unknown): { background: string; text: string; accent: string } {
  const defaults = { background: "#ffffff", text: "#141413", accent: "#c96442" };
  if (!cs || typeof cs !== "object") return defaults;
  const obj = cs as Record<string, unknown>;
  return {
    background: (obj.background as string) || defaults.background,
    text: (obj.text as string) || defaults.text,
    accent: (obj.accent as string) || defaults.accent,
  };
}

/**
 * Serialize a SlideData object to a JSON string.
 */
export function serializePPTSlideData(data: SlideData): string {
  return JSON.stringify(data);
}
