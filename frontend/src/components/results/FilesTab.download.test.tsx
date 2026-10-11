import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// Coverage-extension suite for FilesTab: download dispatch, workspace
// reconciliation, Figma flow, building hero, app-builder layout and helpers.
// System boundaries mocked at the exact import paths FilesTab uses.

const api = vi.hoisted(() => ({
  getToken: vi.fn<() => string | null>(() => "tok"),
  getWorkflow: vi.fn(),
  resolveRunDeliverable: vi.fn(),
  getRunSandboxFileBlob: vi.fn(),
  getRunSandboxFile: vi.fn(),
  authedFetch: vi.fn(),
}));
const exportFigmaZip = vi.hoisted(() => vi.fn());
const exportUserStories = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => api);
vi.mock("@/lib/exporters/figmaExporter", () => ({ exportFigmaZip }));
vi.mock("@/lib/exporters/storyExporter", () => ({ exportUserStories }));

const STRIPPED = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_t, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
          React.createElement(
            prop,
            Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))),
            children,
          ),
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

import { FilesTab, deriveDeliverableFilename, downloadBlob } from "./FilesTab";

let alertSpy: ReturnType<typeof vi.spyOn>;
let clickSpy: ReturnType<typeof vi.spyOn>;
const createObjectURL = vi.fn(() => "blob:made");
const revokeObjectURL = vi.fn();

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.getToken.mockReturnValue("tok");
  api.resolveRunDeliverable.mockResolvedValue(null);
  exportFigmaZip.mockReset();
  exportUserStories.mockReset();
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
  alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
  clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  delete (window as unknown as { JSZip?: unknown }).JSZip;
});

describe("deriveDeliverableFilename", () => {
  it.each([
    ["user_stories", "# My Story!\nbody", undefined, undefined, "my-story.md"],
    ["user_stories_revision", "no heading", undefined, undefined, "user-stories.md"],
    ["user_stories", undefined, undefined, undefined, "user-stories.md"],
    ["user_stories", undefined, "fb.md", undefined, "fb.md"],
    ["custom", "# Hello World", undefined, undefined, "hello-world.md"],
    ["custom", "plain", undefined, undefined, "custom-output.md"],
    ["custom", undefined, undefined, undefined, "custom-output.md"],
    ["custom", undefined, "x.md", undefined, "x.md"],
    ["ppt", "<title>Deck One</title>", undefined, undefined, "deck-one.html"],
    ["ppt", "<title>Presentation</title><h1>Big Idea</h1>", undefined, undefined, "big-idea.html"],
    ["ppt_revision", "nothing", undefined, undefined, "presentation.html"],
    ["ppt", undefined, undefined, undefined, "presentation.html"],
    ["ppt", undefined, "d.html", undefined, "d.html"],
    ["prototype", "<title>Shop App</title>", undefined, undefined, "shop-app.html"],
    ["prototype", "<title>!!!</title>", undefined, undefined, "prototype.html"],
    ["prototype_revision", "none", undefined, undefined, "prototype.html"],
    ["prototype", undefined, undefined, undefined, "prototype.html"],
    ["prototype", undefined, "p.html", undefined, "p.html"],
    ["app_builder", "x", undefined, undefined, "project.zip"],
    ["other", "x", undefined, undefined, "deliverable"],
    ["other", "x", "out", undefined, "out"],
    ["other", "x", "out", "application/zip", "out.zip"],
    ["other", "x", "out.txt", "application/zip", "out.txt"],
  ] as const)("%s/%s/%s/%s -> %s", (type, content, fallback, mime, expected) => {
    expect(deriveDeliverableFilename(type, content, fallback, mime)).toBe(expected);
  });
});

describe("downloadBlob", () => {
  it("creates and revokes an object URL for text content", () => {
    downloadBlob("hello", "a.txt", "text/plain");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:made");
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("passes a blob: url through untouched and does not revoke it", () => {
    downloadBlob("blob:abc", "a.bin", "");
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(revokeObjectURL).not.toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });
});

describe("FilesTab — downloads of derived rows", () => {
  it("routes user-stories download to the story exporter with the extension stripped", async () => {
    const user = userEvent.setup();
    render(<FilesTab workflowType="user_stories" userStoryContent={"# Hello\nbody"} />);
    await user.click(screen.getByRole("button", { name: /^download$/i }));
    expect(exportUserStories).toHaveBeenCalledWith("# Hello\nbody", "hello");
  });

  it("downloads a ppt deck through the generic blob path and offers Download All", async () => {
    const user = userEvent.setup();
    render(<FilesTab workflowType="ppt" pptContent={"<title>Deck</title>"} />);
    expect(screen.getByText("deck.html")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^download$/i }));
    expect(createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
  });

  it("Download All fires a staggered download for every row", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(
      <FilesTab
        workflowType="custom"
        userStoryContent={"# Doc"}
        agentOutputs={[{ name: "A", output: "a" }, { name: "B", output: "b" }]}
        runInput="Build me a thing"
      />,
    );
    await user.click(screen.getByRole("button", { name: /download all/i }));
    await vi.advanceTimersByTimeAsync(1000);
    // 1 deliverable + 2 agents + prompt.md
    expect(clickSpy).toHaveBeenCalledTimes(4);
  });

  it("downloads a run-input card", async () => {
    const user = userEvent.setup();
    render(<FilesTab workflowType="custom" userStoryContent={"# Doc"} runInput="Build me a thing" />);
    await user.click(screen.getByRole("button", { name: "download prompt.md" }));
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it("downloads a generic agent output row", async () => {
    const user = userEvent.setup();
    render(<FilesTab workflowType="ppt" agentOutputs={[{ name: "Solo", output: "x" }]} />);
    await user.click(screen.getByRole("button", { name: "Download 01-solo.md" }));
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it("uses a placeholder avatar and the pluralised subline", () => {
    render(<FilesTab workflowType="ppt" agentOutputs={[{ name: "", output: "x" }]} />);
    expect(screen.getByText("··")).toBeInTheDocument();
    expect(screen.getByText(/1 file available/i)).toBeInTheDocument();
  });
});

describe("FilesTab — workspace reconciliation", () => {
  it("renames the primary row after the run's own file and downloads its bytes", async () => {
    const user = userEvent.setup();
    api.resolveRunDeliverable.mockResolvedValue({ path: "out/deck.pptx", size: 2048 });
    api.getRunSandboxFileBlob.mockResolvedValue(new Blob(["x"], { type: "application/zip" }));
    render(<FilesTab workflowType="ppt" pptContent={"<title>Deck</title>"} runId="run-1" />);

    expect(await screen.findByText("deck.pptx")).toBeInTheDocument();
    expect(screen.getByText(/PPTX \(\.pptx\) · 2\.0 KB/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^download$/i }));

    await waitFor(() => expect(api.getRunSandboxFileBlob).toHaveBeenCalledWith("tok", "run-1", "out/deck.pptx"));
    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it("alerts when the workspace file cannot be downloaded", async () => {
    const user = userEvent.setup();
    api.resolveRunDeliverable.mockResolvedValue({ path: "noext", size: 5 });
    api.getRunSandboxFileBlob.mockRejectedValue(new Error("gone"));
    render(<FilesTab workflowType="ppt" pptContent={"<title>Deck</title>"} runId="run-1" />);

    await screen.findByText("noext");
    await user.click(screen.getByRole("button", { name: /^download$/i }));
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Could not download noext."));
  });

  it("keeps the derived row when no token is available", async () => {
    api.getToken.mockReturnValue(null);
    render(<FilesTab workflowType="ppt" pptContent={"<title>Deck</title>"} runId="run-1" />);
    expect(await screen.findByText("deck.html")).toBeInTheDocument();
    expect(api.resolveRunDeliverable).not.toHaveBeenCalled();
  });

  it("keeps the derived row when the workspace listing fails", async () => {
    api.resolveRunDeliverable.mockRejectedValue(new Error("boom"));
    render(<FilesTab workflowType="ppt" pptContent={"<title>Deck</title>"} runId="run-1" />);
    await waitFor(() => expect(api.resolveRunDeliverable).toHaveBeenCalled());
    expect(screen.getByText("deck.html")).toBeInTheDocument();
  });

  it("does not fetch while the run is still running", () => {
    render(<FilesTab workflowType="ppt" pptContent={"<title>Deck</title>"} runId="run-1" isRunning />);
    expect(api.resolveRunDeliverable).not.toHaveBeenCalled();
  });

  it("ignores a late workspace hit after unmount", async () => {
    let resolve!: (v: unknown) => void;
    api.resolveRunDeliverable.mockReturnValue(new Promise((r) => { resolve = r; }));
    const { unmount } = render(<FilesTab workflowType="ppt" pptContent={"<title>Deck</title>"} runId="run-1" />);
    await waitFor(() => expect(api.resolveRunDeliverable).toHaveBeenCalled());
    unmount();
    resolve({ path: "late.pptx", size: 1 });
    await Promise.resolve();
    expect(screen.queryByText("late.pptx")).not.toBeInTheDocument();
  });
});

describe("FilesTab — building hero", () => {
  it("shows the building hero with task counts and hides downloads", () => {
    render(
      <FilesTab
        workflowType="prototype"
        isRunning
        buildingTaskIndex={9}
        buildingTaskTotal={4}
        buildingFilename="index.html"
      />,
    );
    expect(screen.getByTestId("files-building-hero")).toBeInTheDocument();
    expect(screen.getByText("index.html")).toBeInTheDocument();
    expect(screen.getByText(/task 4 of 4 · not yet validated/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /download all/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/no files available/i)).not.toBeInTheDocument();
  });

  it("elides the filename and task counts when unknown", () => {
    render(<FilesTab workflowType="prototype" isRunning />);
    expect(screen.getByText("Final output · building")).toBeInTheDocument();
    expect(screen.getByText("not yet validated")).toBeInTheDocument();
  });

  it("defaults the task index to 1 and uses the streamed deliverable name when present", () => {
    render(
      <FilesTab workflowType="prototype" isRunning prototypeContent="<title>Live</title>" buildingTaskTotal={3} />,
    );
    expect(screen.getByText("live.html")).toBeInTheDocument();
    expect(screen.getByText(/HTML \(\.html\) · task 1 of 3 · not yet validated/)).toBeInTheDocument();
  });
});

describe("FilesTab — Figma export flow", () => {
  async function openFigma(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: "Download shop-app-figma.json" }));
    return screen.findByRole("dialog", { name: "Export to Figma" });
  }

  it("opens the guide and exports the ZIP on confirm", async () => {
    const user = userEvent.setup();
    render(<FilesTab workflowType="prototype" prototypeContent="<title>Shop App</title>" runId="r9" />);
    await openFigma(user);
    await user.click(screen.getByRole("button", { name: /Done — frames ready/ }));
    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));

    await waitFor(() => expect(exportFigmaZip).toHaveBeenCalledWith("<title>Shop App</title>", "shop-app", "r9"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("uses the row name for the stem when the html has no title and closes via Cancel", async () => {
    const user = userEvent.setup();
    render(<FilesTab workflowType="prototype" prototypeContent="<div>x</div>" />);
    await user.click(screen.getByRole("button", { name: "Download prototype-figma.json" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("alerts when the Figma exporter fails", async () => {
    const user = userEvent.setup();
    exportFigmaZip.mockRejectedValue(new Error("nope"));
    render(<FilesTab workflowType="prototype" prototypeContent="<title>Shop App</title>" />);
    await openFigma(user);
    await user.click(screen.getByRole("button", { name: /Done — frames ready/ }));
    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Figma ZIP export failed. Please try again."));
  });

  it("fetches the html from the sandbox for a reopened run", async () => {
    const user = userEvent.setup();
    api.getRunSandboxFile.mockResolvedValue("<title>Old Run</title>");
    render(<FilesTab workflowType="prototype" runId="r1" />);
    await user.click(screen.getByRole("button", { name: /^download$/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(api.getRunSandboxFile).toHaveBeenCalledWith("tok", "r1", "prototype.html");
  });

  it("alerts when the sandbox html is empty", async () => {
    const user = userEvent.setup();
    api.getRunSandboxFile.mockResolvedValue("");
    render(<FilesTab workflowType="prototype" runId="r1" />);
    await user.click(screen.getByRole("button", { name: /^download$/i }));
    await waitFor(() =>
      expect(alertSpy).toHaveBeenCalledWith("Prototype content not available. Please try again after the run completes."),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("alerts when the sandbox fetch throws", async () => {
    const user = userEvent.setup();
    api.getRunSandboxFile.mockRejectedValue(new Error("x"));
    render(<FilesTab workflowType="prototype" runId="r1" />);
    await user.click(screen.getByRole("button", { name: /^download$/i }));
    await waitFor(() =>
      expect(alertSpy).toHaveBeenCalledWith("Could not load prototype content for Figma export. Please try again."),
    );
  });
});

describe("FilesTab — app_builder layout", () => {
  const code = "```filename: src/app.ts\nexport const a = 1;\n```\n";

  it("renders ZIP, code and doc sections and builds the ZIP with JSZip", async () => {
    const user = userEvent.setup();
    const zipFile = vi.fn();
    class FakeZip {
      file = zipFile;
      generateAsync = vi.fn().mockResolvedValue(new Blob(["z"]));
    }
    (window as unknown as { JSZip: unknown }).JSZip = FakeZip;

    render(
      <FilesTab
        workflowType="app_builder"
        userStoryContent={`# App\n${code}`}
        agentOutputs={[
          { name: "Analyzer", agentId: "material-analyzer", output: "arch doc" },
          { name: "Other Doc", output: "doc two" },
          { name: "Empty", output: "  " },
          { name: "Coder", agentId: "app-code-generator", output: "```filename: src/b.ts\nlet b = 2;\n```\n" },
        ]}
      />,
    );
    expect(screen.getByText("Project Download")).toBeInTheDocument();
    expect(screen.getByText("Source Code Files")).toBeInTheDocument();
    expect(screen.getByText("01-architecture.md")).toBeInTheDocument();
    expect(screen.getByText("project.zip")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Download project.zip" }));
    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(zipFile).toHaveBeenCalledWith("src/app.ts", expect.stringContaining("export const a"));
    expect(zipFile).toHaveBeenCalledWith("src/b.ts", expect.any(String));
    expect(zipFile).toHaveBeenCalledWith("docs/01-architecture.md", "arch doc");
  });

  it("alerts when ZIP generation fails", async () => {
    const user = userEvent.setup();
    (window as unknown as { JSZip: unknown }).JSZip = class {
      file = vi.fn();
      generateAsync = vi.fn().mockRejectedValue(new Error("zip"));
    };
    render(<FilesTab workflowType="app_builder_revision" userStoryContent={`# App\n${code}`} />);
    await user.click(screen.getByRole("button", { name: "Download project.zip" }));
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to generate ZIP."));
  });

  it("injects the JSZip script when absent and alerts if it fails to load", async () => {
    const user = userEvent.setup();
    render(<FilesTab workflowType="app_builder" userStoryContent={`# App\n${code}`} />);
    await user.click(screen.getByRole("button", { name: "Download project.zip" }));
    const script = document.head.querySelector('script[src*="jszip"]') as HTMLScriptElement;
    expect(script).not.toBeNull();
    script.onerror?.(new Event("error"));
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to generate ZIP."));
    script.remove();
  });

  it("falls back to a single markdown file when no code files parse", () => {
    render(<FilesTab workflowType="app_builder" userStoryContent={"# My Blueprint!\nno code"} />);
    expect(screen.getByText("my-blueprint.md")).toBeInTheDocument();
    expect(screen.queryByText("Source Code Files")).not.toBeInTheDocument();
  });

  it("uses app-blueprint when the fallback has no heading", () => {
    render(<FilesTab workflowType="app_builder" userStoryContent={"just text"} />);
    expect(screen.getByText("app-blueprint.md")).toBeInTheDocument();
  });

  it("downloads a doc file via the generic blob path", async () => {
    const user = userEvent.setup();
    render(
      <FilesTab
        workflowType="app_builder"
        agentOutputs={[{ name: "Doc Agent", output: "content", role: "Writer" }]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Download 01-doc-agent.md" }));
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });
});

describe("FilesTab — base version section edge cases", () => {
  it("shows the empty message when the parent fetch fails", async () => {
    const user = userEvent.setup();
    api.getWorkflow.mockRejectedValue(new Error("x"));
    render(<FilesTab workflowType="prototype" parentRunId="p1" agentOutputs={[{ name: "A", output: "a" }]} />);
    await user.click(screen.getByRole("button", { name: "From version previous" }));
    expect(await screen.findByText("No files in the base version.")).toBeInTheDocument();
  });

  it("reconciles base rows with the parent's workspace file and collapses again", async () => {
    const user = userEvent.setup();
    api.getWorkflow.mockResolvedValue({ type: "ppt", output: "<title>Old</title>", deliverableFilename: "old.pptx" });
    api.resolveRunDeliverable.mockResolvedValue({ path: "old.pptx", size: 10 });
    render(<FilesTab workflowType="prototype" parentRunId="p1" parentVersionNumber={2} agentOutputs={[{ name: "A", output: "a" }]} />);
    const toggle = screen.getByRole("button", { name: "From version 2" });
    await user.click(toggle);
    expect(await screen.findByText("old.pptx")).toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("old.pptx")).not.toBeInTheDocument();
  });

  it("keeps derived base rows when the parent workspace cannot be listed", async () => {
    const user = userEvent.setup();
    api.getWorkflow.mockResolvedValue({ type: "ppt", output: "<title>Old</title>" });
    api.resolveRunDeliverable.mockRejectedValue(new Error("swept"));
    api.getToken.mockReturnValue(null);
    render(<FilesTab workflowType="prototype" parentRunId="p1" parentVersionNumber={2} agentOutputs={[{ name: "A", output: "a" }]} />);
    await user.click(screen.getByRole("button", { name: "From version 2" }));
    expect(await screen.findByText("old.html")).toBeInTheDocument();
  });
});

describe("FilesTab — failed banner", () => {
  it("renders the banner on a failed run with no files and hides it when files exist", () => {
    const { rerender } = render(<FilesTab workflowType="ppt" runStatus="failed" runInput="brief" />);
    expect(screen.getByText(/build incomplete/i)).toBeInTheDocument();
    rerender(<FilesTab workflowType="ppt" runStatus="failed" pptContent="<title>Deck</title>" />);
    expect(screen.queryByText(/build incomplete/i)).not.toBeInTheDocument();
  });
});

describe("FilesTab — generic deliverable formats", () => {
  it.each([
    ["application/zip", "ZIP Archive (.zip)", "bundle.zip", "bundle"],
    ["application/json", "JSON (.json)", "d.json", "d.json"],
    ["application/x-weird", "application/x-weird (.bin)", "deliverable.bin", undefined],
  ])("labels %s as %s", (mimetype, format, name, filename) => {
    render(
      <FilesTab
        workflowType={"unknown_type" as never}
        genericDeliverable={{ mimetype, filename, content: "abc" }}
      />,
    );
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`${format.replace(/[().]/g, "\\$&")} · 3 B`))).toBeInTheDocument();
  });
});
