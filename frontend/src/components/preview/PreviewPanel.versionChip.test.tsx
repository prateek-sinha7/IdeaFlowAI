import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import React from "react";
import type { RunFamily, WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Live version chip (B3 / POR §5 D5): real rendered-DOM behavior specs for the
// PreviewPanel version chip + dropdown + read-only override (UI-SPEC Surface 3).
// Scaffold cloned from PreviewPanel.degraded.test.tsx (child stubs) +
// WorkflowHistory.family.test.tsx (motion mock + id-keyed getWorkflow).
//
// Since 24f11270 / e4eecb70 (landed on dev via 9efb704d) the chip is the
// RunHeader VersionMenu: its options are the run's git TAGS fetched from
// getRunSandboxRefs (not the family members), the chip's accessible name is its
// visible text ("v3 ▾", no "Version …, choose version" aria-label), options are
// listed newest first, and picking a tag resolves it to the family member that
// carries that git_tag before loading it read-only via getWorkflow. The
// @/lib/api mock therefore also exports getRunSandboxRefs + the sandbox readers
// PreviewPanel/RunHeader import, so nothing is undefined.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();
const mockGetRunSandboxRefs = vi.fn<(token: string, id: string) => Promise<string[]>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
  getRunSandboxRefs: (token: string, id: string) => mockGetRunSandboxRefs(token, id),
  // Sandbox readers the panel touches once a run settles / a tag is pinned —
  // an empty workspace keeps the Download button disabled and the ref preview
  // on its loading placeholder, which is all this spec needs.
  getRunSandbox: async () => ({ files: [] }),
  getRunSandboxFile: async () => "",
  getRunSandboxFileBlob: async () => new Blob(),
  getRunSandboxZip: async () => new Blob(),
  resolveRunDeliverable: async () => null,
  authedFetch: async () => new Response(null, { status: 404 }),
  postShareRun: async () => ({ share_url: "/s/test" }),
  deleteShareRun: async () => undefined,
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

// Completed members carry the git tag the sandbox cut for them (types/index.ts
// `git_tag`) — the VersionMenu resolves a picked tag back to its member by it.
const M = [
  { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0, git_tag: "v1" },
  { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1, git_tag: "v2" },
  { id: "r2", type: "prototype_revision", title: "v3", status: "completed", revision_index: 2, parent_run_id: "r1", created_at: t2, completed_at: t2, git_tag: "v3" },
] as const;

const family2: RunFamily = { root_id: "root", members: [M[0], M[1]] };
const family3: RunFamily = { root_id: "root", members: [M[0], M[1], M[2]] };

// The version chooser — the RunHeader chip whose accessible name is its visible
// version text ("v3 ▾"; "Viewing v1 ▾" while a tag is pinned).
const findChip = (label: RegExp) => screen.findByRole("button", { name: label });
const VERSION_CHIP = /^(Viewing )?v\d+\b/;

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
  mockGetRunFamily.mockReset();
  // The sandbox has tagged every completed family member.
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2", "v3"]);
});

describe("Live version chip (B3 / D5) — PreviewPanel", () => {
  it("chip visibility: present as v{N} for a ≥2-member family; absent when no family", async () => {
    const { rerender } = render(
      <PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />,
    );
    const chip = await findChip(/^v3\b/);
    expect(chip).toHaveAttribute("aria-haspopup", "listbox");

    // No family → chip absent.
    rerender(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={null} liveRunId={null} />);
    await waitFor(() => expect(screen.queryByRole("button", { name: VERSION_CHIP })).toBeNull());
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("dropdown + read-only load: selecting an older version fetches it via getWorkflow and shows the read-only banner; Back to latest restores live", async () => {
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, output: `<html>${id}</html>` } as WorkflowRun));

    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />);

    // Open the dropdown.
    fireEvent.click(await findChip(/^v3\b/));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(3);

    // Select the oldest version (v1 = "root", older than the latest "r2").
    fireEvent.click(screen.getByRole("option", { name: "v1" }));
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));

    // The amber read-only banner announces the read-only context. Two status
    // strips announce it now (the header banner and the Preview tab's ref
    // view); every one of them must say which version is on screen, read-only.
    const statuses = await screen.findAllByRole("status");
    for (const s of statuses) {
      expect(s).toHaveTextContent(/Viewing v1/);
      expect(s).toHaveTextContent(/read-only/);
    }
    const banner = await screen.findByText(/Viewing v1 \(read-only\)/);
    const bannerStrip = banner.closest('[role="status"]') as HTMLElement;
    expect(bannerStrip).not.toBeNull();

    // Back to latest → banner gone (live content restored).
    fireEvent.click(within(bannerStrip).getByRole("button", { name: /Back to latest/ }));
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(await findChip(/^v3\b/)).toBeInTheDocument();
  });

  it("keyboard nav: opening focuses the listbox, ArrowUp moves focus, Enter loads a version, Escape closes + returns focus to the chip", async () => {
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, output: `<html>${id}</html>` } as WorkflowRun));

    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />);

    // Open the dropdown → keyboard focus ENTERS the listbox (onto the active option).
    // Assertions unchanged — only the chip locator moved to the current DOM. The
    // keyboard contract was dropped by 24f11270 and restored in RunHeader's VersionMenu.
    fireEvent.click(await findChip(/^v3\b/));
    const listbox = screen.getByRole("listbox");
    expect(listbox.contains(document.activeElement)).toBe(true);
    const focusedOnOpen = document.activeElement;

    // An arrow key moves the highlight+focus to an OLDER option, still inside the
    // listbox. Options are listed newest first since e4eecb70 (previously oldest
    // first), so "older" is now ArrowDown — the key that was ArrowUp when v1 sat on top.
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(screen.getByRole("listbox").contains(document.activeElement)).toBe(true);
    expect(document.activeElement).not.toBe(focusedOnOpen);

    // Enter selects the highlighted (older) version → loaded read-only via getWorkflow.
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());

    // Re-open, then Escape closes the dropdown AND returns focus to the chip button.
    fireEvent.click(await findChip(VERSION_CHIP));
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: VERSION_CHIP }));
  });

  it("chip tick: when the family grows the chip label increments v2 → v3", async () => {
    // The sandbox's tag list grows with the family: v1/v2 while r1 is live.
    mockGetRunSandboxRefs.mockImplementation(async (_t, id) => (id === "r1" ? ["v1", "v2"] : ["v1", "v2", "v3"]));
    const { rerender } = render(
      <PreviewPanel workflowType="prototype" prototypeContent="<html>v2</html>" runFamily={family2} liveRunId="r1" />,
    );
    expect(await findChip(/^v2\b/)).toBeInTheDocument();

    // A revision completed → the threaded family grew and the live run advanced.
    rerender(<PreviewPanel workflowType="prototype" prototypeContent="<html>v3</html>" runFamily={family3} liveRunId="r2" />);
    expect(await findChip(/^v3\b/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^v2\b/ })).toBeNull();
  });

  it("a11y: chip carries aria-haspopup/aria-expanded; the dropdown is a listbox with aria-selected options", async () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family3} liveRunId="r2" />);

    const chip = await findChip(/^v3\b/);
    expect(chip).toHaveAttribute("aria-haspopup", "listbox");
    expect(chip).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    const options = screen.getAllByRole("option");
    expect(options.length).toBeGreaterThanOrEqual(2);
    for (const opt of options) expect(opt.hasAttribute("aria-selected")).toBe(true);
    // The active (latest) option is selected. Options are now listed newest
    // first, so address it by name rather than by position.
    expect(screen.getByRole("option", { name: "v3" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("option", { name: "v1" }).getAttribute("aria-selected")).toBe("false");
  });
});
