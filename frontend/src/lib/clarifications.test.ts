import { describe, expect, it } from "vitest";
import { parseClarificationArtifacts, renderClarificationsMarkdown } from "./clarifications";

// ─────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D4 / §11) — clarify-artifact transform lib.
// Pure-lib unit tests (no DOM), cloning the runInput.test.ts idiom.
// Ordering is BY the content `round` field (artifacts have no created_at).
// ─────────────────────────────────────────────────────────────────

function itemsJson(items: Array<Record<string, unknown>>): string {
  return JSON.stringify(items);
}

describe("parseClarificationArtifacts — empty / malformed", () => {
  it("returns [] for an empty node list", () => {
    expect(parseClarificationArtifacts([])).toEqual([]);
  });

  it("skips nodes with no content and returns []", () => {
    expect(parseClarificationArtifacts([{}, { content: "" }, { content: "   " }])).toEqual([]);
  });

  it("never throws on non-JSON / malformed content — returns []", () => {
    expect(parseClarificationArtifacts([{ content: "not json {{{" }])).toEqual([]);
    expect(parseClarificationArtifacts([{ content: "{\"not\":\"a list\"}" }])).toEqual([]);
  });
});

describe("parseClarificationArtifacts — grouping + ordering", () => {
  it("groups a single node's JSON list spanning 2 rounds, sorted ascending", () => {
    const node = {
      content: itemsJson([
        { question_id: "q1", question_text: "Auth?", impact_level: "high", answer: "OAuth", round: 1 },
        { question_id: "q2", question_text: "DB?", impact_level: "medium", answer: "Postgres", round: 2 },
      ]),
    };
    const rounds = parseClarificationArtifacts([node]);
    expect(rounds.length).toBe(2);
    expect(rounds[0].round).toBe(1);
    expect(rounds[1].round).toBe(2);
    expect(rounds[0].qa[0]).toEqual({
      question_id: "q1",
      question_text: "Auth?",
      impact_level: "high",
      answer: "OAuth",
    });
    expect(rounds[1].qa[0].question_text).toBe("DB?");
    expect(rounds[1].qa[0].impact_level).toBe("medium");
  });

  it("flattens MULTIPLE nodes and groups them by round (out-of-order input sorts)", () => {
    const nodeB = { content: itemsJson([{ question_id: "q3", question_text: "Scale?", impact_level: "low", answer: "Yes", round: 2 }]) };
    const nodeA = { content: itemsJson([{ question_id: "q1", question_text: "Auth?", impact_level: "high", answer: "OAuth", round: 1 }]) };
    const rounds = parseClarificationArtifacts([nodeB, nodeA]);
    expect(rounds.map(r => r.round)).toEqual([1, 2]);
    expect(rounds[0].qa[0].question_id).toBe("q1");
    expect(rounds[1].qa[0].question_id).toBe("q3");
  });

  it("tolerates a null answer and a missing impact_level", () => {
    const node = { content: itemsJson([{ question_id: "q1", question_text: "Skipped?", answer: null, round: 1 }]) };
    const rounds = parseClarificationArtifacts([node]);
    expect(rounds[0].qa[0].answer).toBeNull();
    expect(rounds[0].qa[0].impact_level).toBe("");
  });
});

describe("renderClarificationsMarkdown", () => {
  it("returns an empty string for no rounds", () => {
    expect(renderClarificationsMarkdown([])).toBe("");
  });

  it("renders each round heading + each question and its answer", () => {
    const md = renderClarificationsMarkdown([
      { round: 1, qa: [{ question_id: "q1", question_text: "Auth method?", impact_level: "high", answer: "OAuth" }] },
      { round: 2, qa: [{ question_id: "q2", question_text: "Database?", impact_level: "medium", answer: "Postgres" }] },
    ]);
    expect(md).toContain("Round 1");
    expect(md).toContain("Round 2");
    expect(md).toContain("Auth method?");
    expect(md).toContain("OAuth");
    expect(md).toContain("Database?");
    expect(md).toContain("Postgres");
  });
});
