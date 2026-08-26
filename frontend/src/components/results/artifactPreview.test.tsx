import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { discriminateArtifact, SpecPreview, TasksPreview, AnalysisPreview, GateWell, gateAsk } from "./artifactPreview";

// ─── discriminateArtifact — the name-free artifact discriminator (SC-001) ──────
// Characterization ported from ReviewGatePanel.tsx:270-273. The discriminator
// keys ONLY on (output, artifactKind) — never a workflow-name or agent-id
// literal — and returns the card/preview kind or null for a generic degrade.
describe("discriminateArtifact — name-free discriminator (SC-001)", () => {
  it("returns 'spec' when artifactKind === 'spec' (declared kind is authoritative)", () => {
    expect(discriminateArtifact("no tags here", "spec")).toBe("spec");
  });

  it("returns 'spec' when the output carries a <spec> wrapper tag (name-free fallback)", () => {
    expect(discriminateArtifact("<spec>\n## Overview\nx\n</spec>")).toBe("spec");
    expect(discriminateArtifact("<spec ver=1>x</spec>")).toBe("spec");
  });

  it("returns 'tasks' when artifactKind === 'task_list'", () => {
    expect(discriminateArtifact("no tags", "task_list")).toBe("tasks");
  });

  it("returns 'tasks' when the output carries a <tasks> wrapper tag", () => {
    expect(discriminateArtifact("<tasks>\n## Task 1: Do\n</tasks>")).toBe("tasks");
  });

  it("returns 'analysis' when artifactKind === 'summary' (and not spec/tasks)", () => {
    expect(discriminateArtifact("plain text", "summary")).toBe("analysis");
  });

  it("returns 'analysis' when the output carries an <analysis> wrapper tag", () => {
    expect(discriminateArtifact("<analysis>\n### Readiness verdict\nx\n</analysis>")).toBe(
      "analysis",
    );
  });

  it("returns null for ordinary agent output with no kind and no recognized tag (generic degrade)", () => {
    expect(discriminateArtifact("just some prose output")).toBeNull();
    expect(discriminateArtifact("")).toBeNull();
  });

  it("prefers spec over tasks/analysis when both a spec tag and other tags are present", () => {
    expect(discriminateArtifact("<spec>x</spec>\n<tasks>y</tasks>")).toBe("spec");
  });

  it("prefers tasks over analysis when both tasks and analysis tags are present", () => {
    expect(discriminateArtifact("<tasks>x</tasks>\n<analysis>y</analysis>")).toBe("tasks");
  });

  it("is case-insensitive on the wrapper tag", () => {
    expect(discriminateArtifact("<SPEC>x</SPEC>")).toBe("spec");
    expect(discriminateArtifact("<Tasks>x</Tasks>")).toBe("tasks");
    expect(discriminateArtifact("<ANALYSIS>x</ANALYSIS>")).toBe("analysis");
  });
});

// ─── SpecPreview — parses <spec> into `## ` sections ───────────────────────────
describe("SpecPreview", () => {
  it("renders each `## ` heading and its body lines as escaped text", () => {
    render(
      <SpecPreview content={"<spec>\n# Title\n## Overview\nA thing.\n## Goals\nShip it.\n</spec>"} />,
    );
    expect(screen.getByText("Overview")).toBeTruthy();
    expect(screen.getByText("A thing.")).toBeTruthy();
    expect(screen.getByText("Goals")).toBeTruthy();
    expect(screen.getByText("Ship it.")).toBeTruthy();
  });

  it("falls back to a raw <pre> when there are no `## ` sections", () => {
    const { container } = render(<SpecPreview content={"<spec>\nplain body no headings\n</spec>"} />);
    expect(container.querySelector("pre")).not.toBeNull();
    expect(screen.getByText(/plain body no headings/)).toBeTruthy();
  });

  it("parses raw content when the <spec> wrapper is absent", () => {
    render(<SpecPreview content={"## Overview\nunwrapped"} />);
    expect(screen.getByText("Overview")).toBeTruthy();
    expect(screen.getByText("unwrapped")).toBeTruthy();
  });
});

// ─── TasksPreview — parses <tasks> into numbered task rows (read-only) ──────────
describe("TasksPreview", () => {
  it("renders `## Task N: title` blocks with their `**Goal**` lines", () => {
    render(
      <TasksPreview
        content={"<tasks>\n## Task 1: Build the thing\n**Goal**: make it work\n## Task 2: Ship it\n**Goal**: deploy\n</tasks>"}
      />,
    );
    expect(screen.getByText("Build the thing")).toBeTruthy();
    expect(screen.getByText("make it work")).toBeTruthy();
    expect(screen.getByText("Ship it")).toBeTruthy();
    expect(screen.getByText("deploy")).toBeTruthy();
  });

  it("preserves numbering / renders one row per task", () => {
    const { container } = render(
      <TasksPreview content={"<tasks>\n## Task 1: A\n## Task 2: B\n## Task 3: C\n</tasks>"} />,
    );
    expect(screen.getByText("A")).toBeTruthy();
    expect(screen.getByText("B")).toBeTruthy();
    expect(screen.getByText("C")).toBeTruthy();
    // Read-only: no delete affordance is rendered.
    expect(container.querySelector('button[title="Remove this task"]')).toBeNull();
  });

  it("falls back to a raw <pre> when there are no Task blocks", () => {
    const { container } = render(<TasksPreview content={"<tasks>\nno task headings\n</tasks>"} />);
    expect(container.querySelector("pre")).not.toBeNull();
  });
});

// ─── AnalysisPreview — parses <analysis> verdict + `### ` sections ─────────────
describe("AnalysisPreview", () => {
  it("renders the `### Readiness verdict` first line and classifies READY", () => {
    render(
      <AnalysisPreview
        content={"<analysis>\n### Readiness verdict\nREADY TO BUILD\n### Risks\nnone\n</analysis>"}
      />,
    );
    // The verdict text surfaces in the banner (and again in its own section body).
    expect(screen.getAllByText(/READY TO BUILD/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Risks")).toBeTruthy();
  });

  it("renders the CAUTION and NEEDS REVISION verdict classes", () => {
    const { rerender } = render(
      <AnalysisPreview content={"<analysis>\n### Readiness verdict\nCAUTION advised\n</analysis>"} />,
    );
    expect(screen.getAllByText(/CAUTION advised/).length).toBeGreaterThanOrEqual(1);
    rerender(
      <AnalysisPreview
        content={"<analysis>\n### Readiness verdict\nNEEDS REVISION now\n</analysis>"}
      />,
    );
    expect(screen.getAllByText(/NEEDS REVISION now/).length).toBeGreaterThanOrEqual(1);
  });

  it("falls back to a raw <pre> when there are no `### ` sections", () => {
    const { container } = render(<AnalysisPreview content={"<analysis>\nplain analysis\n</analysis>"} />);
    expect(container.querySelector("pre")).not.toBeNull();
  });
});

// ─── GateWell — the review gate's evidence well ──────────────────────────────
describe("GateWell", () => {
  it("hoists the readiness verdict into a banner above the prose", () => {
    // REGRESSION: the gate used to render <analysis> through AnalysisPreview,
    // which surfaces this verdict as a coloured banner. Swapping the gate to
    // GateWell dropped it, burying "CAUTION advised" in the body as ordinary
    // text — on an approval gate, the worst possible line to lose.
    render(
      <GateWell
        content={"<analysis>\n### Readiness verdict\nCAUTION advised\n\n### Risks\n- one\n</analysis>"}
        artifactKind="summary"
      />,
    );
    const banner = screen.getByTestId("gate-well-verdict");
    expect(banner).toHaveTextContent("CAUTION advised");
    expect(banner).toHaveAttribute("data-verdict-tone", "caution");
  });

  it("renders no banner when the artifact carries no verdict", () => {
    render(<GateWell content={"# Settings\n\nJust a spec."} artifactKind="spec" />);
    expect(screen.queryByTestId("gate-well-verdict")).toBeNull();
    expect(screen.getByTestId("gate-well")).toHaveAttribute("data-well-kind", "prose");
  });

  it("renders markdown structure, not escaped source", () => {
    render(<GateWell content={"| A | B |\n|---|---|\n| 1 | 2 |"} artifactKind="spec" />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "A" })).toBeInTheDocument();
  });

  it("routes a source artifact to the code block, not the prose renderer", () => {
    render(<GateWell content={"<!DOCTYPE html>\n<html></html>"} artifactKind="html_file" />);
    expect(screen.getByTestId("gate-well")).toHaveAttribute("data-well-kind", "code");
    expect(screen.getByTestId("gate-well-copy")).toBeInTheDocument();
  });

  it("gateAsk derives the ask from the artifact kind only (SC-001)", () => {
    expect(gateAsk("spec", null).approve).toBe("Approve the spec");
    expect(gateAsk("task_list", null).approve).toBe("Approve the plan");
    expect(gateAsk(undefined, "analysis").ask).toBe("Approve this analysis and continue?");
    expect(gateAsk(undefined, null).approve).toBe("Approve & build");
  });
});
