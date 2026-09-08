import { describe, it, expect } from "vitest";
import { parsePPTSlideData, serializePPTSlideData } from "./pptParser";
import type { SlideData } from "@/types";

describe("parsePPTSlideData", () => {
  it("should parse valid PPT slide JSON with slides array", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Title Slide",
          content: [{ text: "Introduction" }],
          type: "text",
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides).toHaveLength(1);
    expect(result.slides[0].title).toBe("Title Slide");
  });

  it("should extract JSON from markdown code fences with json tag", () => {
    const json = `\`\`\`json
    {
      "slides": [
        { "title": "Slide 1", "content": [] }
      ]
    }
    \`\`\``;
    const result = parsePPTSlideData(json);
    expect(result.slides[0].title).toBe("Slide 1");
  });

  it("should extract JSON from markdown code fences without language tag", () => {
    const json = `\`\`\`
    {
      "slides": [
        { "title": "Slide 1", "content": [] }
      ]
    }
    \`\`\``;
    const result = parsePPTSlideData(json);
    expect(result.slides[0].title).toBe("Slide 1");
  });

  it("should extract JSON when wrapped in extra text", () => {
    const json = `Here's the PPT data:
    { "slides": [ { "title": "Title", "content": [] } ] }
    Hope this helps!`;
    const result = parsePPTSlideData(json);
    expect(result.slides[0].title).toBe("Title");
  });

  it("should handle nested presentation object", () => {
    const json = JSON.stringify({
      presentation: {
        slides: [{ title: "Nested Slide", content: [] }],
      },
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].title).toBe("Nested Slide");
  });

  it("should handle and throw on very truncated JSON that cannot be repaired", () => {
    const json = `{ "slides": [ { "title": `;
    expect(() => parsePPTSlideData(json)).toThrow();
  });

  it("should repair truncated JSON by closing open braces", () => {
    // This should repair by adding closing braces
    const json = `{ "slides": [ { "title": "Test", "content": [] }`;
    const result = parsePPTSlideData(json);
    expect(result.slides).toBeDefined();
    expect(result.slides[0].title).toBe("Test");
  });

  it("should use slide number as default title when missing", () => {
    const json = JSON.stringify({
      slides: [
        { content: [] },
        { title: "Explicit", content: [] },
        { content: [] },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].title).toBe("Slide 1");
    expect(result.slides[1].title).toBe("Explicit");
    expect(result.slides[2].title).toBe("Slide 3");
  });

  it("should handle string content as text", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: "Just a string",
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].content[0].text).toBe("Just a string");
  });

  it("should handle array of strings as content", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: ["First bullet", "Second bullet"],
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].content).toHaveLength(2);
    expect(result.slides[0].content[0].text).toBe("First bullet");
  });

  it("should extract text from content objects with text field", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [{ text: "Main point" }],
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].content[0].text).toBe("Main point");
  });

  it("should extract text from content objects with bullet field", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [{ bullet: "Main point" }],
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].content[0].text).toBe("Main point");
  });

  it("should extract text from content objects with point field", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [{ point: "Main point" }],
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].content[0].text).toBe("Main point");
  });

  it("should handle subPoints array in content", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [
            {
              text: "Main",
              subPoints: ["Sub 1", "Sub 2"],
            },
          ],
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].content[0].subPoints).toEqual(["Sub 1", "Sub 2"]);
  });

  it("should handle sub_points field (snake_case)", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [
            {
              text: "Main",
              sub_points: ["Sub 1", "Sub 2"],
            },
          ],
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].content[0].subPoints).toEqual(["Sub 1", "Sub 2"]);
  });

  it("should handle color scheme with all fields", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [],
          colorScheme: {
            background: "#000000",
            text: "#ffffff",
            accent: "#ff00ff",
          },
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].colorScheme.background).toBe("#000000");
    expect(result.slides[0].colorScheme.text).toBe("#ffffff");
    expect(result.slides[0].colorScheme.accent).toBe("#ff00ff");
  });

  it("should use default color scheme when not provided", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [],
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].colorScheme.background).toBe("#ffffff");
    expect(result.slides[0].colorScheme.text).toBe("#141413");
    expect(result.slides[0].colorScheme.accent).toBe("#c96442");
  });

  it("should handle speakerNotes field", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [],
          speakerNotes: "Remember to emphasize this point",
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].speakerNotes).toBe("Remember to emphasize this point");
  });

  it("should handle speaker_notes field (snake_case)", () => {
    const json = JSON.stringify({
      slides: [
        {
          title: "Slide",
          content: [],
          speaker_notes: "Remember to emphasize this point",
        },
      ],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].speakerNotes).toBe("Remember to emphasize this point");
  });

  it("should throw error for invalid JSON that cannot be repaired", () => {
    const json = "{]not valid";
    expect(() => parsePPTSlideData(json)).toThrow();
  });

  it("should throw error when slides field is missing and not in presentation", () => {
    const json = JSON.stringify({ title: "No slides" });
    expect(() => parsePPTSlideData(json)).toThrow();
  });

  it("should throw error for non-object input", () => {
    const json = JSON.stringify("just a string");
    expect(() => parsePPTSlideData(json)).toThrow();
  });

  it("should provide default content for invalid slide", () => {
    const json = JSON.stringify({
      slides: [null],
    });
    const result = parsePPTSlideData(json);
    expect(result.slides[0].title).toBe("Slide 1");
    expect(result.slides[0].content).toBeDefined();
    expect(result.slides[0].content.length).toBeGreaterThan(0);
  });
});

describe("serializePPTSlideData", () => {
  it("should serialize slide data to JSON string", () => {
    const data: SlideData = {
      slides: [
        {
          title: "Test Slide",
          content: [{ text: "Content" }],
          type: "text",
          colorScheme: { background: "#fff", text: "#000", accent: "#f00" },
        },
      ],
    };
    const json = serializePPTSlideData(data);
    const parsed = JSON.parse(json);
    expect(parsed.slides[0].title).toBe("Test Slide");
  });

  it("should roundtrip serialize and parse correctly", () => {
    const original: SlideData = {
      slides: [
        {
          title: "Slide 1",
          subtitle: "Subtitle",
          content: [{ text: "Point 1", subPoints: ["Detail 1", "Detail 2"] }],
          type: "title",
          colorScheme: { background: "#fff", text: "#000", accent: "#f00" },
        },
      ],
    };
    const serialized = serializePPTSlideData(original);
    const deserialized = parsePPTSlideData(serialized);
    expect(deserialized.slides[0].title).toBe("Slide 1");
    expect(deserialized.slides[0].content[0].text).toBe("Point 1");
  });
});
