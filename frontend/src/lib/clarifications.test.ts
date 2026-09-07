import { describe, it, expect } from "vitest";
import {
  parseClarificationArtifacts,
  renderClarificationsMarkdown,
} from "./clarifications";

describe("parseClarificationArtifacts", () => {
  it("should parse a single round with one question", () => {
    const nodes = [
      {
        content: JSON.stringify([
          {
            question_id: "q1",
            question_text: "What color?",
            impact_level: "high",
            answer: "Blue",
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(1);
    expect(result[0].round).toBe(0);
    expect(result[0].qa).toHaveLength(1);
    expect(result[0].qa[0]).toEqual({
      question_id: "q1",
      question_text: "What color?",
      impact_level: "high",
      answer: "Blue",
    });
  });

  it("should group questions by round", () => {
    const nodes = [
      {
        content: JSON.stringify([
          {
            question_id: "q1",
            question_text: "First?",
            impact_level: "low",
            answer: "Yes",
            round: 0,
          },
          {
            question_id: "q2",
            question_text: "Second?",
            impact_level: "high",
            answer: "No",
            round: 1,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(2);
    expect(result[0].round).toBe(0);
    expect(result[1].round).toBe(1);
  });

  it("should merge questions from multiple nodes", () => {
    const nodes = [
      {
        content: JSON.stringify([
          {
            question_id: "q1",
            question_text: "Q1?",
            answer: "A1",
            round: 0,
          },
        ]),
      },
      {
        content: JSON.stringify([
          {
            question_id: "q2",
            question_text: "Q2?",
            answer: "A2",
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(1);
    expect(result[0].qa).toHaveLength(2);
    expect(result[0].qa[0].question_id).toBe("q1");
    expect(result[0].qa[1].question_id).toBe("q2");
  });

  it("should sort rounds in ascending order", () => {
    const nodes = [
      {
        content: JSON.stringify([
          {
            question_id: "q1",
            question_text: "Round 2",
            answer: "A",
            round: 2,
          },
          {
            question_id: "q2",
            question_text: "Round 0",
            answer: "B",
            round: 0,
          },
          {
            question_id: "q3",
            question_text: "Round 1",
            answer: "C",
            round: 1,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(3);
    expect(result[0].round).toBe(0);
    expect(result[1].round).toBe(1);
    expect(result[2].round).toBe(2);
  });

  it("should handle missing optional fields with defaults", () => {
    const nodes = [
      {
        content: JSON.stringify([
          {
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(1);
    expect(result[0].qa[0]).toEqual({
      question_id: "",
      question_text: "",
      impact_level: "",
      answer: null,
    });
  });

  it("should treat missing round as 0", () => {
    const nodes = [
      {
        content: JSON.stringify([
          {
            question_id: "q1",
            question_text: "No round specified",
            answer: "Yes",
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result[0].round).toBe(0);
  });

  it("should handle null answer", () => {
    const nodes = [
      {
        content: JSON.stringify([
          {
            question_id: "q1",
            question_text: "Unanswered?",
            answer: null,
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result[0].qa[0].answer).toBeNull();
  });

  it("should return empty array for empty nodes", () => {
    expect(parseClarificationArtifacts([])).toEqual([]);
  });

  it("should return empty array for null/undefined", () => {
    expect(parseClarificationArtifacts(undefined as unknown as Array<{ content?: string }>)).toEqual([]);
    expect(parseClarificationArtifacts(null as unknown as Array<{ content?: string }>)).toEqual([]);
  });

  it("should skip nodes with missing/empty content", () => {
    const nodes = [
      { content: "" },
      { content: undefined },
      {},
      {
        content: JSON.stringify([
          {
            question_id: "valid",
            question_text: "Valid question",
            answer: "Valid answer",
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(1);
    expect(result[0].qa).toHaveLength(1);
    expect(result[0].qa[0].question_id).toBe("valid");
  });

  it("should skip nodes with malformed JSON", () => {
    const nodes = [
      { content: "not json" },
      { content: "{invalid json}" },
      {
        content: JSON.stringify([
          {
            question_id: "valid",
            question_text: "Valid",
            answer: "Valid",
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(1);
    expect(result[0].qa[0].question_id).toBe("valid");
  });

  it("should skip non-array JSON content", () => {
    const nodes = [
      { content: JSON.stringify({ not: "array" }) },
      {
        content: JSON.stringify([
          {
            question_id: "valid",
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result).toHaveLength(1);
  });

  it("should skip invalid items in valid arrays", () => {
    const nodes = [
      {
        content: JSON.stringify([
          null,
          "string",
          123,
          {
            question_id: "valid",
            question_text: "Valid question",
            round: 0,
          },
        ]),
      },
    ];

    const result = parseClarificationArtifacts(nodes);

    expect(result[0].qa).toHaveLength(1);
    expect(result[0].qa[0].question_id).toBe("valid");
  });
});

describe("renderClarificationsMarkdown", () => {
  it("should render a single round with one question", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q1",
            question_text: "What color?",
            impact_level: "high",
            answer: "Blue",
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    expect(result).toContain("# Clarifications");
    expect(result).toContain("## Round 0");
    expect(result).toContain("What color?");
    expect(result).toContain("(high impact)");
    expect(result).toContain("**Answer:** Blue");
  });

  it("should render multiple rounds", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q1",
            question_text: "First?",
            impact_level: "low",
            answer: "Yes",
          },
        ],
      },
      {
        round: 1,
        qa: [
          {
            question_id: "q2",
            question_text: "Second?",
            impact_level: "high",
            answer: "No",
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    expect(result).toContain("## Round 0");
    expect(result).toContain("## Round 1");
    expect(result).toContain("First?");
    expect(result).toContain("Second?");
  });

  it("should handle missing impact level", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q1",
            question_text: "No impact?",
            impact_level: "",
            answer: "Yes",
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    expect(result).toContain("No impact?");
    expect(result).not.toContain("impact)");
  });

  it("should handle null answer", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q1",
            question_text: "Unanswered?",
            impact_level: "",
            answer: null,
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    expect(result).toContain("**Answer:** (no answer)");
  });

  it("should use question_id when question_text is missing", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q123",
            question_text: "",
            impact_level: "",
            answer: "Yes",
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    expect(result).toContain("### q123");
  });

  it("should render multiple questions in one round", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q1",
            question_text: "Question 1",
            impact_level: "",
            answer: "Answer 1",
          },
          {
            question_id: "q2",
            question_text: "Question 2",
            impact_level: "",
            answer: "Answer 2",
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    expect(result).toContain("Question 1");
    expect(result).toContain("Question 2");
    expect(result).toContain("Answer 1");
    expect(result).toContain("Answer 2");
  });

  it("should return empty string for empty rounds", () => {
    expect(renderClarificationsMarkdown([])).toBe("");
  });

  it("should return empty string for null/undefined", () => {
    expect(renderClarificationsMarkdown(undefined as never)).toBe("");
    expect(renderClarificationsMarkdown(null as never)).toBe("");
  });

  it("should trim trailing newlines", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q1",
            question_text: "Q?",
            impact_level: "",
            answer: "A",
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    expect(result.endsWith("\n")).toBe(true);
    expect(result.endsWith("\n\n")).toBe(false);
  });

  it("should format as valid markdown", () => {
    const rounds = [
      {
        round: 0,
        qa: [
          {
            question_id: "q1",
            question_text: "What is your name?",
            impact_level: "critical",
            answer: "John Doe",
          },
        ],
      },
    ];

    const result = renderClarificationsMarkdown(rounds);

    // Verify structure
    expect(result.split("\n")[0]).toBe("# Clarifications");
    expect(result).toMatch(/^# Clarifications[\s\S]*## Round \d+[\s\S]*### .*[\s\S]*\*\*Answer:\*/);
  });
});
