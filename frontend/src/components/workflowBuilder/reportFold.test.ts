import { describe, expect, it } from "vitest";

import { foldReport } from "./reportFold";

describe("foldReport", () => {
  it("splits a report at the first level-2 heading", () => {
    const text =
      "Context loaded this turn: 3 files\nShort summary.\n\n## Details\nBody\n## Run it\nx";
    const result = foldReport(text);
    expect(result).toEqual({
      folded: true,
      summary: "Context loaded this turn: 3 files\nShort summary.\n\n",
      report: "## Details\nBody\n## Run it\nx",
    });
  });

  it("does not fold a reply without the marker", () => {
    const text = "Here you go.\n\n## Details\nBody";
    expect(foldReport(text)).toEqual({ folded: false, text });
  });

  it("does not fold when the marker is not on the first line", () => {
    const text = "Hello\nContext loaded this turn\n## Details";
    expect(foldReport(text)).toEqual({ folded: false, text });
  });

  it("does not fold a report that has no level-2 heading", () => {
    const text = "Context loaded this turn\n### Sub heading\nBody";
    expect(foldReport(text)).toEqual({ folded: false, text });
  });

  it("does not treat an indented or inline '## ' as a heading", () => {
    const text = "Context loaded this turn\nuse ## here\n  ## indented";
    expect(foldReport(text)).toEqual({ folded: false, text });
  });

  it("keeps every character when lines end in CRLF", () => {
    const text = "Context loaded this turn\r\nSummary\r\n## Full\r\nBody";
    const result = foldReport(text);
    expect(result.folded).toBe(true);
    if (result.folded) {
      expect(result.summary + result.report).toBe(text);
      expect(result.report.startsWith("## Full")).toBe(true);
    }
  });

  it("skips a '## ' line inside a fenced code block", () => {
    const text = "Context loaded this turn\n```md\n## not a heading\n```\nSummary\n## Details\nBody";
    const result = foldReport(text);
    expect(result.folded).toBe(true);
    if (result.folded) {
      expect(result.report).toBe("## Details\nBody");
    }
  });

  it("does not fold when the only '## ' line is inside a tilde fence", () => {
    const text = "Context loaded this turn\n~~~\n## code\n~~~";
    expect(foldReport(text)).toEqual({ folded: false, text });
  });

  it("treats an unclosed fence as running to the end", () => {
    const text = "Context loaded this turn\n```\n## code\n## more code";
    expect(foldReport(text)).toEqual({ folded: false, text });
  });

  it("needs a closing fence of the same character and at least the same length", () => {
    const text = "Context loaded this turn\n````\n```\n## still code\n````\n## Details";
    const result = foldReport(text);
    expect(result.folded).toBe(true);
    if (result.folded) {
      expect(result.report).toBe("## Details");
    }
  });
});
