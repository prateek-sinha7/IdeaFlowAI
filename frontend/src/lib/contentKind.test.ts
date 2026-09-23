/**
 * contentKind — ported with the classifier from `impeccable-redesign`.
 *
 * These cases are the ones the Steps drill-down actually hits: a run's own
 * synthesis document, an agent's streamed transcript, and the JSON a validator
 * writes. Each has to arrive as itself.
 */
import { describe, expect, it } from "vitest";

import { classifyContent } from "./contentKind";

describe("classifyContent", () => {
  it("calls a document markdown once two different signals agree", () => {
    expect(classifyContent("## Screens\n\n- Account # [text]\n").kind).toBe("markdown");
    expect(classifyContent("**Organization**: Allianz\n\n- one\n").kind).toBe("markdown");
  });

  it("does not promote one hyphenated line to a document", () => {
    // Eating the hyphen and reflowing the line is worse than leaving it alone.
    expect(classifyContent("The run finished - nothing left to do.").kind).toBe("plain");
  });

  it("treats a lone pair of backticks as markdown", () => {
    expect(classifyContent("Should it stay `DELETE /accounts/:id`?").kind).toBe("markdown");
  });

  it("parses JSON rather than guessing from the first character", () => {
    const validate = '{"documents_expected": 4, "gaps": []}';
    expect(classifyContent(validate)).toMatchObject({ kind: "code", language: "json" });
    // A sentence that merely opens with a brace is not JSON.
    expect(classifyContent("{this is not json, just a note").kind).toBe("plain");
  });

  it("recognises a built artifact and anything else opening with a tag", () => {
    expect(classifyContent("<!DOCTYPE html><html></html>")).toMatchObject({
      kind: "code",
      language: "html",
    });
    expect(classifyContent("<section>hi</section>").kind).toBe("code");
  });

  it("calls prose carrying a wall of raw markup code, not markdown", () => {
    // The markdown renderer would drop every tag and reflow the rest.
    const quoted =
      "Here is the shell:\n<div><span>a</span><b>c</b></div><p>x</p><i>y</i><em>z</em>";
    expect(classifyContent(quoted).kind).toBe("code");
  });

  it("calls a mostly-fenced body code, taking the language from the longest fence", () => {
    const body = "A caption.\n\n```html\n" + "<div>x</div>\n".repeat(40) + "```";
    expect(classifyContent(body)).toMatchObject({ kind: "code", language: "html" });
  });

  it("keeps a document whose long fence named no language as markdown", () => {
    // The live case: a spec writer's reply — headings, bold, a numbered list —
    // ending in one big unlabelled ledger block. Called code, the whole reply
    // was drawn as a monospace slab labelled "TEXT" with its markup showing.
    const body =
      "I'll start the 5-phase process.\n\n**PHASE 3 LEDGER**\n\n1. One\n2. Two\n\n```\n" +
      "screen-a -> Screen\n".repeat(40) +
      "```";
    expect(classifyContent(body).kind).toBe("markdown");
  });

  it("closes a fence the writer has not finished, so the rest still renders", () => {
    // A live reply is read mid-write. An open ``` would otherwise swallow every
    // heading after it.
    const { kind, body } = classifyContent("# Title\n\n- one\n\n```\nstill typing");
    expect(kind).toBe("markdown");
    expect(body.endsWith("\n```")).toBe(true);
    expect(body.match(/```/g)!.length % 2).toBe(0);
  });

  it("leaves a closed fence alone", () => {
    const { body } = classifyContent("# Title\n\n- one\n\n```\ndone\n```");
    expect(body.endsWith("```")).toBe(true);
    expect(body.match(/```/g)!.length).toBe(2);
  });

  it("unwraps the product's own envelope before classifying", () => {
    const { kind, body } = classifyContent("<spec>\n# Title\n\n- one\n- two\n</spec>");
    expect(kind).toBe("markdown");
    expect(body.startsWith("# Title")).toBe(true);
  });

  it("leaves an agent transcript as plain so its line breaks survive", () => {
    const transcript = "Reading pages 1-21.\nNow I'll read pages 6-10.\nContinue with 11-15.";
    expect(classifyContent(transcript).kind).toBe("plain");
  });

  it("returns plain for nothing at all", () => {
    expect(classifyContent("")).toMatchObject({ kind: "plain", body: "" });
    expect(classifyContent("   \n  ").kind).toBe("plain");
  });
});
