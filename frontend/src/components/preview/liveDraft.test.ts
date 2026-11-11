import { describe, expect, it } from "vitest";
import type { SandboxFile } from "@/lib/api";
import { liveDraftStage, pickLiveDraftPath } from "./liveDraft";

const f = (path: string): SandboxFile => ({ path, size: 1, modified: 0, text: true });

describe("pickLiveDraftPath", () => {
  it("prefers the declared deliverable when it is on disk", () => {
    expect(pickLiveDraftPath([f("index.html"), f("deck.html")], "deck.html")).toBe("deck.html");
  });

  it("falls back to the main-output names in order", () => {
    expect(pickLiveDraftPath([f("index.html"), f("prototype.html"), f("example.html")])).toBe("prototype.html");
    expect(pickLiveDraftPath([f("slides.html"), f("index.html")], "missing.html")).toBe("slides.html");
  });

  it("ignores nested files and unrelated html", () => {
    expect(pickLiveDraftPath([f(".chain/prototype.html"), f("example.html"), f("spec.md")])).toBeNull();
  });
});

describe("liveDraftStage", () => {
  it("names the step and task progress", () => {
    expect(liveDraftStage("Build", 6, 11)).toBe("Build · 6/11 tasks done");
    expect(liveDraftStage("Fix", 11, 11)).toBe("Fix · 11/11 tasks done");
    expect(liveDraftStage(undefined, 0, 0)).toBe("Building");
  });
});
