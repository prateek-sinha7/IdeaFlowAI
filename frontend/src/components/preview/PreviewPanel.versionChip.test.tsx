import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { RunFamily, WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Live version chip (B3 / POR §5 D5): real rendered-DOM behavior specs for the
// PreviewPanel version chip + dropdown + read-only override (UI-SPEC Surface 3).
// Scaffold cloned from PreviewPanel.degraded.test.tsx (child stubs) +
// WorkflowHistory.family.test.tsx (motion mock + id-keyed getWorkflow). The
// @/lib/api mock exports ALL THREE fetchers (getToken/getWorkflow/getRunFamily)
// so nothing is undefined even though this spec only drives getWorkflow.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
}));

// Strip animation-only props so role/text queries still find rendered nodes.
const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

// Cheap markers for the heavy bespoke preview children (same as the degraded
// spec) — the chip/dropdown/banner under test live in PreviewPanel/LiveVersionChip.
vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
    if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
      if (!content) return fallback || "user-stories.md";
      const match = content.match(/^#\s+(.+)/m);
      if (match) return match[1].toLowerCase() + ".md";
      return fallback || "user-stories.md";
    }
    if (workflowType === "ppt" || workflowType === "ppt_revision") {
      if (!content) return fallback || "presentation.html";
      if (content.match(/<title>/i) || content.match(/<h1[^>]*>/i)) return "presentation.html";
      return fallback || "presentation.html";
    }
    if (workflowType === "prototype" || workflowType === "prototype_revision") {
      if (!content) return fallback || "prototype.html";
      if (content.match(/<title>/i)) return "prototype.html";
      return fallback || "prototype.html";
    }
    if (workflowType === "app_builder" || workflowType === "app_builder_revision") return "project.zip";
    return fallback || "deliverable";
  },
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const t0 = new Date("2026-05-12T10:00:00Z").toISOString();
const t1 = new Date("2026-05-12T11:00:00Z").toISOString();
const t2 = new Date("2026-05-12T12:00:00Z").toISOString();

const M = [
  { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
  { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
  { id: "r2", type: "prototype_revision", title: "v3", status: "completed", revision_index: 2, parent_run_id: "r1", created_at: t2, completed_at: t2 },
] as const;

const family2: RunFamily = { root_id: "root", members: [M[0], M[1]] };
const family3: RunFamily = { root_id: "root", members: [M[0], M[1], M[2]] };

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
  mockGetRunFamily.mockReset();
});

describe("Live version chip (B3 / D5) — PreviewPanel", () => {
  it("chip visibility: present as v{N} for a ≥2-member family; absent when no family", () => {
    const { rerender } = render(
      <PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />,
    );
    const chip = screen.getByLabelText(/Version v3, choose version/);
    expect(chip).toHaveAttribute("aria-haspopup", "listbox");

    // No family → chip absent.
    rerender(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={null} liveRunId={null} />);
    expect(screen.queryByLabelText(/Version/)).toBeNull();
  });

  it("dropdown + read-only load: selecting an older version fetches it via getWorkflow and shows the read-only banner; Back to latest restores live", async () => {
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, output: `<html>${id}</html>` } as WorkflowRun));

    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />);

    // Open the dropdown.
    fireEvent.click(screen.getByLabelText(/Version v3/));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(3);

    // Select the oldest version (v1 = "root", older than the latest "r2").
    fireEvent.click(options[0]);
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));

    // The amber read-only banner announces the read-only context.
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(/Viewing v/);
    expect(banner).toHaveTextContent(/read-only/);

    // Back to latest → banner gone (live content restored).
    fireEvent.click(screen.getByText(/Back to latest/));
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });

  it("keyboard nav: opening focuses the listbox, ArrowUp moves focus, Enter loads a version, Escape closes + returns focus to the chip", async () => {
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, output: `<html>${id}</html>` } as WorkflowRun));

    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />);

    // Open the dropdown → keyboard focus ENTERS the listbox (onto the active option).
    fireEvent.click(screen.getByLabelText(/Version v3/));
    const listbox = screen.getByRole("listbox");
    expect(listbox.contains(document.activeElement)).toBe(true);
    const focusedOnOpen = document.activeElement;

    // ArrowUp moves the highlight+focus to another option, still inside the listbox.
    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    expect(screen.getByRole("listbox").contains(document.activeElement)).toBe(true);
    expect(document.activeElement).not.toBe(focusedOnOpen);

    // Enter selects the highlighted (older) version → loaded read-only via getWorkflow.
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());

    // Re-open, then Escape closes the dropdown AND returns focus to the chip button.
    fireEvent.click(screen.getByLabelText(/Version/));
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    expect(document.activeElement).toBe(screen.getByLabelText(/Version/));
  });

  it("chip tick: when the family grows the chip label increments v2 → v3", () => {
    const { rerender } = render(
      <PreviewPanel workflowType="prototype" prototypeContent="<html>v2</html>" runFamily={family2} liveRunId="r1" />,
    );
    expect(screen.getByLabelText(/Version v2, choose version/)).toBeInTheDocument();

    // A revision completed → the threaded family grew and the live run advanced.
    rerender(<PreviewPanel workflowType="prototype" prototypeContent="<html>v3</html>" runFamily={family3} liveRunId="r2" />);
    expect(screen.getByLabelText(/Version v3, choose version/)).toBeInTheDocument();
  });

  it("a11y: chip carries aria-haspopup/aria-expanded; the dropdown is a listbox with aria-selected options", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />);

    const chip = screen.getByLabelText(/Version v3/);
    expect(chip).toHaveAttribute("aria-haspopup", "listbox");
    expect(chip).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    const options = screen.getAllByRole("option");
    expect(options.length).toBeGreaterThanOrEqual(2);
    for (const opt of options) expect(opt.hasAttribute("aria-selected")).toBe(true);
    // The active (latest) option is selected.
    expect(options[2].getAttribute("aria-selected")).toBe("true");
  });
});
