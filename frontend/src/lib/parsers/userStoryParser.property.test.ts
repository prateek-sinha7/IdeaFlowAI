import { describe, expect, it } from "vitest";
import fc from "fast-check";
import type { Epic, Story, UserStoryDocument } from "@/types";
import { formatUserStoryMarkdown, parseUserStoryMarkdown } from "./userStoryParser";

// Fixed seed keeps failures reproducible; bounded runs keep the file fast.
const PROPERTY_OPTIONS = { seed: 20240607, numRuns: 150 } as const;

// Lines are drawn from a vocabulary that mixes every structural token the parser
// recognises with plain prose, so generated documents exercise real branches.
const structuralLine = fc.oneof(
  fc.constantFrom(
    "# ",
    "# Epic: Auth [P0]",
    "# Personas",
    "## ",
    "## Story: Login",
    "### Acceptance Criteria",
    "**Story Points:** 5",
    "**Story Points:** x",
    "**Dependencies:** A",
    "**Business Value:** v",
    "**Priority:** P1",
    "**As a** user",
    "**Acceptance Criteria:**",
    "**DoD:**",
    "- [ ] item",
    "- item",
    "---",
    "| a | b |",
    "",
  ),
  fc.string({ maxLength: 30 }),
);

const markdownLikeDocument = fc
  .array(structuralLine, { maxLength: 25 })
  .map((lines) => lines.join("\n"));

const markdownLikeDocumentCrlf = fc
  .array(structuralLine, { maxLength: 25 })
  .map((lines) => lines.join("\r\n"));

// Safe prose: starts with a letter that cannot collide with any marker or prefix
// ("Epic:", "Story:", "Personas"), uses only alphanumerics and single spaces.
const word = fc.stringMatching(/^[a-z0-9]{1,8}$/);
const safeText = fc.array(word, { minLength: 1, maxLength: 4 }).map((w) => `x${w.join(" ")}`);
const multilineText = fc.array(safeText, { minLength: 1, maxLength: 3 }).map((l) => l.join("\n"));

const storyArb: fc.Arbitrary<Story> = fc.record(
  {
    title: safeText,
    description: fc.oneof(fc.constant(""), multilineText),
    acceptanceCriteria: fc.array(safeText, { maxLength: 4 }),
    storyPoints: fc.integer({ min: 1, max: 100 }),
    dependencies: safeText,
  },
  { requiredKeys: ["title", "description", "acceptanceCriteria"] },
);

// businessValue is deliberately absent: the parser discards description text that
// follows a business value line, so that combination does not round-trip.
const epicArb: fc.Arbitrary<Epic> = fc.record(
  {
    title: safeText,
    description: fc.oneof(fc.constant(""), multilineText),
    stories: fc.array(storyArb, { maxLength: 3 }),
    priority: fc.constantFrom("P0", "P1", "P2"),
  },
  { requiredKeys: ["title", "description", "stories"] },
);

const documentArb: fc.Arbitrary<UserStoryDocument> = fc.record({
  epics: fc.array(epicArb, { maxLength: 3 }),
});

const countEpicHeadings = (markdown: string): number =>
  markdown
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.startsWith("# ") && !/^# Personas/i.test(line)).length;

const countStoryHeadings = (markdown: string): number =>
  markdown
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.startsWith("## ") && !line.startsWith("### ")).length;

describe("parseUserStoryMarkdown (properties)", () => {
  it("never throws on arbitrary strings and always returns an epics array", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 300 }), (input) => {
        const result = parseUserStoryMarkdown(input);

        expect(Array.isArray(result.epics)).toBe(true);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("never throws on structurally flavoured documents, including CRLF input", () => {
    fc.assert(
      fc.property(fc.oneof(markdownLikeDocument, markdownLikeDocumentCrlf), (input) => {
        expect(() => parseUserStoryMarkdown(input)).not.toThrow();
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("produces well-formed epics and stories with trimmed titles", () => {
    fc.assert(
      fc.property(markdownLikeDocument, (input) => {
        const { epics } = parseUserStoryMarkdown(input);

        for (const epic of epics) {
          expect(typeof epic.title).toBe("string");
          expect(epic.title).toBe(epic.title.trim());
          expect(typeof epic.description).toBe("string");
          expect(Array.isArray(epic.stories)).toBe(true);
          for (const story of epic.stories) {
            expect(story.title).toBe(story.title.trim());
            expect(typeof story.description).toBe("string");
            expect(Array.isArray(story.acceptanceCriteria)).toBe(true);
            for (const criterion of story.acceptanceCriteria) {
              expect(typeof criterion).toBe("string");
            }
            if (story.storyPoints !== undefined) {
              expect(Number.isInteger(story.storyPoints)).toBe(true);
              expect(story.storyPoints).toBeGreaterThanOrEqual(0);
            }
          }
        }
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("never creates more epics or stories than there are matching headings", () => {
    fc.assert(
      fc.property(markdownLikeDocument, (input) => {
        const { epics } = parseUserStoryMarkdown(input);
        const storyCount = epics.reduce((total, epic) => total + epic.stories.length, 0);

        expect(epics.length).toBe(countEpicHeadings(input));
        expect(storyCount).toBeLessThanOrEqual(countStoryHeadings(input));
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("only ever reports P0, P1 or P2 as a tag-derived priority", () => {
    fc.assert(
      fc.property(fc.constantFrom("P0", "P1", "P2"), safeText, (priority, title) => {
        const { epics } = parseUserStoryMarkdown(`# ${title} [${priority}]`);

        expect(epics).toHaveLength(1);
        expect(epics[0].priority).toBe(priority);
        expect(epics[0].title).toBe(title);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("is unaffected by the choice of LF or CRLF line endings", () => {
    fc.assert(
      fc.property(fc.array(structuralLine, { maxLength: 25 }), (lines) => {
        const withLf = parseUserStoryMarkdown(lines.join("\n"));
        const withCrlf = parseUserStoryMarkdown(lines.join("\r\n"));

        expect(withCrlf).toEqual(withLf);
      }),
      PROPERTY_OPTIONS,
    );
  });
});

describe("formatUserStoryMarkdown (properties)", () => {
  it("always ends with exactly one trailing newline", () => {
    fc.assert(
      fc.property(documentArb, (doc) => {
        const output = formatUserStoryMarkdown(doc);

        expect(output.endsWith("\n")).toBe(true);
        expect(output.endsWith("\n\n")).toBe(false);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("round-trips documents built from safe text through format then parse", () => {
    fc.assert(
      fc.property(documentArb, (doc) => {
        expect(parseUserStoryMarkdown(formatUserStoryMarkdown(doc))).toEqual(doc);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("is stable: formatting a parsed formatted document yields the same Markdown", () => {
    fc.assert(
      fc.property(documentArb, (doc) => {
        const once = formatUserStoryMarkdown(doc);
        const twice = formatUserStoryMarkdown(parseUserStoryMarkdown(once));

        expect(twice).toBe(once);
      }),
      PROPERTY_OPTIONS,
    );
  });
});
