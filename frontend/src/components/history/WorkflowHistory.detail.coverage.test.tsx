/**
 * WorkflowHistory (detail view) — branch/interaction coverage: loading the
 * full run, deliverable dispatch by type / mimetype / filename, tab switching,
 * persisted agent-output normalisation, file-bundle parsing, PPT download /
 * full-screen, revise flow, chain options (built-in + saved, success and
 * non-success sources), version switching, family and clarification lookups.
 *
 * Boundaries mocked: @/lib/api, next/navigation and the motion shim. Heavy
 * deliverable previews and the Files / Thinking / Audit tabs are replaced by
 * thin stubs that surface the props they receive (each has its own test file).
 * RunDetailPage and the list rows render for real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { FamilyMember, RunFamily, WorkflowRun } from "@/types/index";
import type { RunSummary, UserWorkflowSummary } from "@/lib/api";
import globalReducer from "@/store/slices/globalSlice";
import { CHAIN_SOURCE_STATUS_KEY } from "@/lib/workflowChaining";
import { renderWithProviders } from "@/test/renderWithProviders";

type RunsPage = { runs: WorkflowRun[]; total: number };

const mockGetToken = vi.fn<() => string | null>(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<RunsPage>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();
const mockGetRunSummary = vi.fn<(token: string, id: string) => Promise<RunSummary>>();
const mockGetRunArtifacts = vi.fn<
  (token: string, id: string, opts?: unknown) => Promise<{ workflow_id: string; artifacts: { content?: string }[] }>
>();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => mockGetToken(),
    getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
    getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
    deleteWorkflow: vi.fn(),
    getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
    getRunSummary: (token: string, id: string) => mockGetRunSummary(token, id),
    getRunArtifacts: (token: string, id: string, opts?: unknown) => mockGetRunArtifacts(token, id, opts),
  };
});

// Stubs expose received props as JSON so the dispatch contract is observable.
vi.mock("@/components/preview/PPTPreview", () => ({
  PPTPreview: ({ content, pipelineType }: { content: string; pipelineType: string }) => (
    <div data-testid="ppt-preview" data-pipeline={pipelineType}>{content}</div>
  ),
}));
vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="userstory-preview">{content}</div>,
}));
vi.mock("@/components/preview/PrototypePreview", () => ({
  PrototypePreview: ({ content }: { content: string }) => <div data-testid="prototype-preview">{content}</div>,
}));
vi.mock("@/components/preview/MarkdownPreview", () => ({
  MarkdownPreview: ({ content }: { content: string }) => <div data-testid="markdown-preview">{content}</div>,
}));
vi.mock("@/components/preview/AppBuilderPreview", () => ({
  AppBuilderPreview: ({ files, projectName }: { files: { path: string; language: string }[]; projectName?: string }) => (
    <div data-testid="app-builder-preview" data-project={projectName}>
      {files.map((f) => `${f.path}:${f.language}`).join("|")}
    </div>
  ),
}));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: (props: Record<string, unknown>) => <div data-testid="files-tab" data-props={JSON.stringify(props)} />,
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({
  AgentThinkingTab: (props: Record<string, unknown>) => <div data-testid="thinking-tab" data-props={JSON.stringify(props)} />,
}));
vi.mock("@/components/results/AuditTab", () => ({
  AuditTab: ({ workflowRunId }: { workflowRunId: string }) => <div data-testid="audit-tab">{workflowRunId}</div>,
}));

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => {
  // One stable component per tag: a fresh component per render would remount
  // (and blur) inputs such as the revision textarea on every keystroke.
  const cache = new Map<string, React.ComponentType<{ children?: React.ReactNode } & Record<string, unknown>>>();
  return {
    motion: new Proxy(
      {},
      {
        get: (_target, prop: string) => {
          if (!cache.has(prop)) {
            cache.set(prop, ({ children, ...rest }) => {
              const cleaned = Object.fromEntries(
                Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
              );
              return React.createElement(prop, cleaned, children);
            });
          }
          return cache.get(prop);
        },
      },
    ),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

import { WorkflowHistory } from "./WorkflowHistory";

// ─── Builders ────────────────────────────────────────────────────────────────
function makeRun(overrides: Partial<WorkflowRun> & { id: string }): WorkflowRun {
  return {
    title: `Run ${overrides.id}`,
    type: "prototype",
    status: "completed",
    input: "brief",
    output: "stored output",
    createdAt: new Date(Date.now() - 60_000).toISOString(),
    agentCount: 2,
    parentRunId: null,
    rootRunId: overrides.id,
    ...overrides,
  } as WorkflowRun;
}

function summaryFor(run: WorkflowRun, members: FamilyMember[] = []): RunSummary {
  return {
    id: run.id, title: run.title, type: run.type, status: run.status, duration: null, agent_count: 0,
    token_usage: {}, error: run.error ?? null, agents: [], root_id: run.rootRunId, members,
  };
}

function member(overrides: Partial<FamilyMember> & { id: string }): FamilyMember {
  return {
    type: "prototype", title: overrides.id, status: "completed", revision_index: 1,
    parent_run_id: null, created_at: "2026-07-01T10:00:00", completed_at: null, ...overrides,
  };
}

function catalogState() {
  const base = globalReducer(undefined, { type: "@@init" });
  const wf = (id: string, name: string, chainedFrom: Array<{ id: string; beta: boolean }>) => ({
    id, name, display_name: name, description: "", step_count: 1, steps: [], user_launchable: true,
    chained_from: chainedFrom.map((c) => ({ ...c, text: c.id })),
  });
  return {
    global: {
      ...base,
      workflows: [
        wf("user_stories", "User Stories", [{ id: "ppt", beta: false }, { id: "prototype", beta: false }]),
        wf("prototype", "Prototype", [{ id: "ppt", beta: true }]),
      ] as unknown as typeof base.workflows,
    },
  };
}

function uiProps(extra: Partial<React.ComponentProps<typeof WorkflowHistory>> = {}) {
  return { onBack: vi.fn(), ...extra };
}

/** Render the list, click the run's row and wait for the detail heading. */
async function openDetail(
  run: WorkflowRun,
  props: Partial<React.ComponentProps<typeof WorkflowHistory>> = {},
  opts: { fullRun?: WorkflowRun } = {},
) {
  const user = userEvent.setup();
  mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
  mockGetWorkflow.mockResolvedValue(opts.fullRun ?? run);
  mockGetRunSummary.mockResolvedValue(summaryFor(run));
  const view = renderWithProviders(<WorkflowHistory {...uiProps(props)} />, { preloadedState: catalogState() });
  await user.click(await screen.findByRole("button", { name: new RegExp(`^Open ${run.title}`) }));
  await screen.findByRole("heading", { level: 2 });
  return { user, ...view };
}

const propsOf = (testId: string) =>
  JSON.parse(screen.getByTestId(testId).getAttribute("data-props") ?? "{}") as Record<string, unknown>;

const downloads: string[] = [];

beforeEach(() => {
  vi.clearAllMocks();
  downloads.length = 0;
  sessionStorage.clear();
  mockGetToken.mockReturnValue("test-token");
  mockGetWorkflows.mockResolvedValue({ runs: [], total: 0 });
  mockGetRunFamily.mockResolvedValue({ root_id: "", members: [] });
  mockGetRunArtifacts.mockResolvedValue({ workflow_id: "x", artifacts: [] });
  mockGetRunSummary.mockRejectedValue(new Error("no summary"));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ─── Opening / loading ───────────────────────────────────────────────────────
describe("WorkflowHistory detail — loading the run", () => {
  it("fetches the full run when the row carries no output and shows its deliverable", async () => {
    const run = makeRun({ id: "r1", title: "Sparse run", type: "user_stories", output: undefined });
    await openDetail(run, {}, { fullRun: { ...run, output: "# Stories from server" } });

    expect(await screen.findByTestId("userstory-preview")).toHaveTextContent("# Stories from server");
    expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "r1");
  });

  it("does not fetch the full run when the row already has output", async () => {
    await openDetail(makeRun({ id: "r1", title: "Full run", type: "user_stories", output: "inline" }));

    expect(screen.getByTestId("userstory-preview")).toHaveTextContent("inline");
    expect(mockGetWorkflow).not.toHaveBeenCalled();
  });

  it("hides the deliverable while the full run is loading", async () => {
    const run = makeRun({ id: "r1", title: "Slow run", type: "user_stories", output: undefined });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    let resolveFull: (r: WorkflowRun) => void = () => {};
    mockGetWorkflow.mockReturnValue(new Promise<WorkflowRun>((r) => { resolveFull = r; }));
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
    const user = userEvent.setup();
    renderWithProviders(<WorkflowHistory {...uiProps()} />, { preloadedState: catalogState() });
    await user.click(await screen.findByRole("button", { name: /^Open Slow run/ }));

    await screen.findByRole("heading", { level: 2 });
    expect(screen.queryByText("No preview available")).not.toBeInTheDocument();
    expect(screen.queryByTestId("userstory-preview")).not.toBeInTheDocument();

    await act(async () => { resolveFull({ ...run, output: "arrived" }); });
    expect(await screen.findByTestId("userstory-preview")).toHaveTextContent("arrived");
  });

  it("falls back to the neutral empty state when fetching the full run fails", async () => {
    mockGetWorkflow.mockRejectedValue(new Error("boom"));
    const run = makeRun({ id: "r1", title: "Broken fetch", output: undefined });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
    const user = userEvent.setup();
    renderWithProviders(<WorkflowHistory {...uiProps()} />, { preloadedState: catalogState() });

    await user.click(await screen.findByRole("button", { name: /^Open Broken fetch/ }));

    expect(await screen.findByText("No preview available")).toBeInTheDocument();
  });

  it("skips every authenticated lookup when the token disappears before opening", async () => {
    const run = makeRun({ id: "r1", title: "Token gone", output: undefined });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    const user = userEvent.setup();
    renderWithProviders(<WorkflowHistory {...uiProps()} />, { preloadedState: catalogState() });
    const row = await screen.findByRole("button", { name: /^Open Token gone/ });
    mockGetToken.mockReturnValue(null);

    await user.click(row);

    expect(await screen.findByText("Not authenticated.")).toBeInTheDocument();
    expect(mockGetWorkflow).not.toHaveBeenCalled();
    expect(mockGetRunFamily).not.toHaveBeenCalled();
    expect(mockGetRunArtifacts).not.toHaveBeenCalled();
  });

  it("returns to the list from the summary column's back button", async () => {
    const { user } = await openDetail(makeRun({ id: "r1", title: "Back me" }));

    await user.click(screen.getByRole("button", { name: "Back to history" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Run History" })).toBeInTheDocument();
  });
});

// ─── Deliverable dispatch ────────────────────────────────────────────────────
describe("WorkflowHistory detail — deliverable preview", () => {
  it.each<[string, WorkflowRun["type"], string, string | null]>([
    ["prototype", "prototype", "prototype-preview", null],
    ["prototype revision", "prototype_revision", "prototype-preview", null],
    ["large prototype revision", "prototype_large_revision" as WorkflowRun["type"], "prototype-preview", null],
    ["feature prototype revision", "prototype_feature_revision" as WorkflowRun["type"], "prototype-preview", null],
    ["user stories", "user_stories", "userstory-preview", null],
    ["user stories revision", "user_stories_revision", "userstory-preview", null],
    ["presentation", "ppt", "ppt-preview", "ppt"],
    ["presentation v2", "ppt_v2" as WorkflowRun["type"], "ppt-preview", "ppt_v2"],
    ["presentation revision", "ppt_revision", "ppt-preview", "ppt_revision"],
  ])("renders a %s run with the matching preview", async (_label, type, testId, pipeline) => {
    await openDetail(makeRun({ id: "r1", title: "Typed run", type, output: "deliverable body" }));

    const preview = screen.getByTestId(testId);
    expect(preview).toHaveTextContent("deliverable body");
    if (pipeline) expect(preview).toHaveAttribute("data-pipeline", pipeline);
  });

  it("shows the neutral empty state for a non-failed run without output", async () => {
    await openDetail(makeRun({ id: "r1", title: "Empty run", type: "prototype", output: "" }));

    expect(await screen.findByText("No preview available")).toBeInTheDocument();
  });

  it.each(["failed", "cancelled", "degraded", "diverted"] as const)(
    "suppresses the empty state for a %s run (the summary column explains it)",
    async (status) => {
      await openDetail(makeRun({ id: "r1", title: "Ended run", status, output: "" }));

      expect(screen.queryByText("No preview available")).not.toBeInTheDocument();
    },
  );

  describe("generic (custom) deliverables", () => {
    it("renders html in a sandboxed iframe without same-origin access", async () => {
      await openDetail(makeRun({ id: "r1", title: "Html run", type: "custom", output: "<!doctype html><p>hi</p>" }));

      const frame = screen.getByTitle("Deliverable Preview");
      expect(frame).toHaveAttribute("sandbox", "allow-scripts");
      expect(frame).toHaveAttribute("srcdoc", "<!doctype html><p>hi</p>");
    });

    it("routes presentation.html to the deck viewer", async () => {
      await openDetail(
        makeRun({ id: "r1", title: "Deck run", type: "custom", output: "<html>deck</html>", deliverableFilename: "presentation.html" }),
      );

      expect(screen.getByTestId("ppt-preview")).toHaveAttribute("data-pipeline", "ppt");
      expect(screen.queryByTitle("Deliverable Preview")).not.toBeInTheDocument();
    });

    it("routes user_stories.md markdown to the story viewer", async () => {
      await openDetail(
        makeRun({ id: "r1", title: "Stories run", type: "custom", output: "# Epic", deliverableFilename: "user_stories.md" }),
      );

      expect(screen.getByTestId("userstory-preview")).toHaveTextContent("# Epic");
    });

    it("renders other markdown as plain markdown", async () => {
      await openDetail(makeRun({ id: "r1", title: "Notes run", type: "custom", output: "just notes" }));

      expect(screen.getByTestId("markdown-preview")).toHaveTextContent("just notes");
    });

    it("renders a serialized file bundle as a project and names it after the run", async () => {
      const output = "```filename: src/main.py\nprint(1)\n```";
      await openDetail(makeRun({ id: "r1", title: "Bundle run", type: "custom", output }));

      const preview = screen.getByTestId("app-builder-preview");
      expect(preview).toHaveTextContent("src/main.py:python");
      expect(preview).toHaveAttribute("data-project", "Bundle run");
    });

    it("falls back to markdown when a persisted zip deliverable has no parseable files", async () => {
      await openDetail(
        makeRun({ id: "r1", title: "Zip run", type: "custom", output: "opaque archive text", deliverableMimetype: "application/zip" }),
      );

      expect(screen.getByTestId("markdown-preview")).toHaveTextContent("opaque archive text");
      expect(screen.queryByTestId("app-builder-preview")).not.toBeInTheDocument();
    });

    it("prefers the persisted mimetype over the content heuristic", async () => {
      await openDetail(
        makeRun({ id: "r1", title: "Persisted run", type: "custom", output: "<!doctype html><p>x</p>", deliverableMimetype: "text/markdown" }),
      );

      expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
      expect(screen.queryByTitle("Deliverable Preview")).not.toBeInTheDocument();
    });
  });

  describe("app builder projects", () => {
    const BUNDLE = [
      "```filename: src/index.ts",
      "const a = 1;",
      "```",
      "",
      "```filename: Dockerfile",
      "FROM node",
      "```",
      "",
      "```filename: README",
      "has no extension",
      "```",
      "",
      "```filename: empty.ts",
      "",
      "```",
      "",
      "```filename: src/index.ts",
      "duplicate path",
      "```",
      "",
      "```filename: data.weird",
      "x",
      "```",
      "",
      "### src/styles/app.css",
      "```css",
      "body { margin: 0 }",
      "```",
      "",
      "### Via Node.js",
      "```",
      "npm i",
      "```",
      "",
      "**`src/util.js`**",
      "```js",
      "export {}",
      "```",
    ].join("\n");

    it("parses fenced file blocks in all three layouts, dropping prose headings, duplicates and empty or extensionless files", async () => {
      await openDetail(makeRun({ id: "r1", title: "App run", type: "app_builder", output: BUNDLE }));

      expect(screen.getByTestId("app-builder-preview")).toHaveTextContent(
        "src/index.ts:typescript|Dockerfile:plaintext|data.weird:plaintext|src/styles/app.css:css|src/util.js:javascript",
      );
    });

    it("merges files from code-producing agents with the final output, without duplicating paths", async () => {
      const agentOutputs = [
        { agent_id: "app-code-generator", name: "Coder", role: "Dev", icon: "", output: "```filename: src/a.ts\nA\n```\n```filename: src/shared.ts\nS\n```", duration: 1 },
        { agent_id: "reviewer", name: "Reviewer", role: "QA", icon: "", output: "```filename: src/ignored.ts\nI\n```", duration: 1 },
        { agent_id: "app-test-implementation", name: "Tester", role: "QA", icon: "", output: "   ", duration: 1 },
      ];
      await openDetail(
        makeRun({
          id: "r1", title: "App run", type: "app_builder",
          output: "```filename: src/shared.ts\nS2\n```\n```filename: src/b.ts\nB\n```",
          agentOutputs: agentOutputs as unknown as WorkflowRun["agentOutputs"],
        }),
      );

      expect(screen.getByTestId("app-builder-preview")).toHaveTextContent("src/a.ts:typescript|src/shared.ts:typescript|src/b.ts:typescript");
    });

    it("names the project after the analyzer's heading, stripped of punctuation", async () => {
      const agentOutputs = [{ agent_id: "material-analyzer", name: "Analyzer", role: "Arch", icon: "", output: "# My Cool App!!\ntext", duration: 1 }];
      await openDetail(
        makeRun({
          id: "r1", title: "App run", type: "app_builder", output: "```filename: a.ts\nA\n```",
          agentOutputs: agentOutputs as unknown as WorkflowRun["agentOutputs"],
        }),
      );

      expect(screen.getByTestId("app-builder-preview")).toHaveAttribute("data-project", "My Cool App");
    });

    it("falls back to the output heading, then the run title, for the project name", async () => {
      await openDetail(makeRun({ id: "r1", title: "Heading run", type: "app_builder", output: "# Output Heading\n```filename: a.ts\nA\n```" }));
      expect(screen.getByTestId("app-builder-preview")).toHaveAttribute("data-project", "Output Heading");
    });

    it("uses the run title when nothing provides a heading", async () => {
      await openDetail(makeRun({ id: "r1", title: "Plain title run", type: "app_builder", output: "```filename: a.ts\nA\n```" }));

      expect(screen.getByTestId("app-builder-preview")).toHaveAttribute("data-project", "Plain title run");
    });

    it("shows the raw markdown when the output yields no files", async () => {
      await openDetail(makeRun({ id: "r1", title: "App run", type: "app_builder", output: "no files here" }));

      expect(screen.getByTestId("markdown-preview")).toHaveTextContent("no files here");
    });

    it("shows the empty state for an app builder run with no output", async () => {
      await openDetail(makeRun({ id: "r1", title: "App run", type: "app_builder", output: "" }));

      expect(await screen.findByText("No preview available")).toBeInTheDocument();
    });

    it("suppresses the empty state for a failed app builder run with no output", async () => {
      await openDetail(makeRun({ id: "r1", title: "App run", type: "app_builder", status: "failed", output: "" }));

      expect(screen.queryByText("No preview available")).not.toBeInTheDocument();
    });
  });
});

// ─── PPT actions ─────────────────────────────────────────────────────────────
describe("WorkflowHistory detail — presentation actions", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    createObjectURL = vi.fn(() => "blob:deck");
    revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push(`${this.download}|${this.href}`);
    });
  });

  afterEach(() => {
    delete (URL as unknown as Record<string, unknown>).createObjectURL;
    delete (URL as unknown as Record<string, unknown>).revokeObjectURL;
  });

  const blobText = async () => (createObjectURL.mock.calls[0][0] as Blob).text();

  it("downloads the deck as presentation.html, stripping a markdown code fence", async () => {
    const { user } = await openDetail(
      makeRun({ id: "r1", title: "Deck", type: "ppt", output: "```html\n<html>deck</html>\n```" }),
    );

    await user.click(screen.getByRole("button", { name: "Download" }));

    expect(await blobText()).toBe("<html>deck</html>");
    expect(downloads).toEqual(["presentation.html|blob:deck"]);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:deck");
  });

  it("downloads unfenced html unchanged", async () => {
    const { user } = await openDetail(makeRun({ id: "r1", title: "Deck", type: "ppt", output: "  <html>raw</html>  " }));

    await user.click(screen.getByRole("button", { name: "Download" }));

    expect(await blobText()).toBe("<html>raw</html>");
  });

  it("opens the deck full screen in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const { user } = await openDetail(
      makeRun({ id: "r1", title: "Deck", type: "ppt", output: "```\n<html>deck</html>\n```" }),
    );

    await user.click(screen.getByRole("button", { name: "Full Screen" }));

    expect(await blobText()).toBe("<html>deck</html>");
    expect(open).toHaveBeenCalledWith("blob:deck", "_blank");
  });

  it("offers deck actions only on the Preview tab of a presentation with output", async () => {
    const { user } = await openDetail(makeRun({ id: "r1", title: "Deck", type: "ppt", output: "<html/>" }));
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Files" }));

    expect(screen.queryByRole("button", { name: "Download" })).not.toBeInTheDocument();
  });

  it("offers no deck actions for non-presentation runs", async () => {
    await openDetail(makeRun({ id: "r1", title: "Proto", type: "prototype", output: "<html/>" }));

    expect(screen.queryByRole("button", { name: "Full Screen" })).not.toBeInTheDocument();
  });
});

// ─── Tabs ────────────────────────────────────────────────────────────────────
describe("WorkflowHistory detail — tabs", () => {
  const AGENTS = [
    { agent_id: "a1", name: "Analyst", role: "Analysis", icon: "", output: "first pass", duration: 5, input_tokens: 10, output_tokens: 20, total_tokens: 30, model_id: "model-a", input_prompt: "prompt!", thinking_text: "hmm" },
    { agent_id: "a1", name: "Analyst", role: "Analysis", icon: "", output: "   ", duration: null, input_tokens: 1, output_tokens: 2, total_tokens: 3 },
    { agent_id: "a1", name: "Analyst", role: "Analysis", icon: "", output: "final pass", duration: 7, input_tokens: 4, output_tokens: 5, total_tokens: 9, model_id: "model-b" },
    { name: "Orphan", role: "none", icon: "", output: "no id", duration: 1 },
    { agent_id: "a2", name: "Writer", role: "Docs", icon: "✍", output: "", duration: 2 },
  ];

  it("shows persisted agent runs merged by id on the Thinking tab", async () => {
    const { user } = await openDetail(
      makeRun({ id: "r1", title: "Agents run", agentOutputs: AGENTS as unknown as WorkflowRun["agentOutputs"] }),
    );

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    const agents = propsOf("thinking-tab").agents as Array<Record<string, unknown>>;
    expect(agents).toHaveLength(2);
    expect(agents[0]).toMatchObject({
      id: "a1", name: "Analyst", output: "final pass", duration: 12, modelId: "model-b",
      status: "done", index: 0, inputPrompt: "prompt!", thinkingText: "hmm",
    });
    expect(agents[1]).toMatchObject({ id: "a2", name: "Writer", icon: "✍", output: "", index: 1 });
  });

  it("accepts agent outputs persisted as a JSON string", async () => {
    const { user } = await openDetail(
      makeRun({ id: "r1", title: "Agents run", agentOutputs: JSON.stringify(AGENTS.slice(0, 1)) as unknown as WorkflowRun["agentOutputs"] }),
    );

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    expect((propsOf("thinking-tab").agents as unknown[])).toHaveLength(1);
  });

  it("treats unparseable persisted agent outputs as none", async () => {
    const { user } = await openDetail(
      makeRun({ id: "r1", title: "Agents run", agentOutputs: "{not json" as unknown as WorkflowRun["agentOutputs"] }),
    );

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    expect(propsOf("thinking-tab").agents).toEqual([]);
  });

  it("passes the run input and original-brief root for a revision run", async () => {
    const { user } = await openDetail(
      makeRun({ id: "r2", title: "Revised", parentRunId: "r1", rootRunId: "r0", input: "make it blue" }),
    );

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    expect(propsOf("thinking-tab")).toMatchObject({ runInput: "make it blue", originalBriefRootRunId: "r0" });
  });

  it("omits the original-brief root for a standalone run", async () => {
    const { user } = await openDetail(makeRun({ id: "r1", title: "Standalone" }));

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    expect(propsOf("thinking-tab").originalBriefRootRunId).toBeUndefined();
  });

  it("shows the Audit tab for the open run", async () => {
    const { user } = await openDetail(makeRun({ id: "r1", title: "Audit me" }));

    await user.click(screen.getByRole("button", { name: "Audit" }));

    expect(screen.getByTestId("audit-tab")).toHaveTextContent("r1");
  });

  it("returns to the Preview tab", async () => {
    const { user } = await openDetail(makeRun({ id: "r1", title: "Proto", output: "<html/>" }));
    await user.click(screen.getByRole("button", { name: "Audit" }));

    await user.click(screen.getByRole("button", { name: "Preview" }));

    expect(screen.getByTestId("prototype-preview")).toBeInTheDocument();
  });

  describe("Files tab", () => {
    it.each<[string, WorkflowRun["type"], string]>([
      ["user stories", "user_stories", "userStoryContent"],
      ["app builder", "app_builder", "userStoryContent"],
      ["presentation", "ppt", "pptContent"],
      ["prototype", "prototype", "prototypeContent"],
    ])("hands a %s run's output to the matching content slot", async (_label, type, slot) => {
      const { user } = await openDetail(makeRun({ id: "r1", title: "Files run", type, output: "payload" }));

      await user.click(screen.getByRole("button", { name: "Files" }));

      const props = propsOf("files-tab");
      expect(props[slot]).toBe("payload");
      expect(props.runId).toBe("r1");
      expect(props.workflowType).toBe(type);
      expect(props.genericDeliverable).toBeUndefined();
    });

    it("describes a generic deliverable with its declared name and resolved mimetype", async () => {
      const { user } = await openDetail(
        makeRun({ id: "r1", title: "Generic run", type: "custom", output: "<!doctype html>x", deliverableFilename: "report.html" }),
      );

      await user.click(screen.getByRole("button", { name: "Files" }));

      expect(propsOf("files-tab").genericDeliverable).toEqual({
        mimetype: "text/html", filename: "report.html", content: "<!doctype html>x",
      });
    });

    it("leaves the deliverable filename undefined when none was declared", async () => {
      const { user } = await openDetail(makeRun({ id: "r1", title: "Generic run", type: "custom", output: "notes" }));

      await user.click(screen.getByRole("button", { name: "Files" }));

      expect(propsOf("files-tab").genericDeliverable).toEqual({ mimetype: "text/markdown", content: "notes" });
    });

    it("lists only agents that produced output, and none when there are no agents", async () => {
      const { user } = await openDetail(
        makeRun({ id: "r1", title: "Agents run", agentOutputs: AGENTS as unknown as WorkflowRun["agentOutputs"] }),
      );

      await user.click(screen.getByRole("button", { name: "Files" }));

      expect(propsOf("files-tab").agentOutputs).toEqual([
        { name: "Analyst", role: "Analysis", output: "final pass", agentId: "a1" },
      ]);
    });

    it("passes no agent outputs when the run has none", async () => {
      const { user } = await openDetail(makeRun({ id: "r1", title: "No agents" }));

      await user.click(screen.getByRole("button", { name: "Files" }));

      expect(propsOf("files-tab").agentOutputs).toBeUndefined();
    });
  });
});

// ─── Family + clarifications ─────────────────────────────────────────────────
describe("WorkflowHistory detail — family and clarifications", () => {
  it("derives the parent's version number from the fetched family", async () => {
    mockGetRunFamily.mockResolvedValue({
      root_id: "r0",
      members: [
        member({ id: "r2", revision_index: 3, parent_run_id: "r1" }),
        member({ id: "r0", revision_index: 1 }),
        member({ id: "r1", revision_index: 2, parent_run_id: "r0" }),
      ],
    });
    const { user } = await openDetail(makeRun({ id: "r2", title: "Third", parentRunId: "r1", rootRunId: "r0" }));
    await waitFor(() => expect(mockGetRunFamily).toHaveBeenCalledWith("test-token", "r0"));

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    await waitFor(() => expect(propsOf("thinking-tab").revisionParentVersion).toBe(2));
  });

  it("leaves the parent version unset when the parent is missing from the family", async () => {
    mockGetRunFamily.mockResolvedValue({ root_id: "r0", members: [member({ id: "r0", revision_index: 1 })] });
    const { user } = await openDetail(makeRun({ id: "r2", title: "Orphan", parentRunId: "gone", rootRunId: "r0" }));
    await waitFor(() => expect(mockGetRunFamily).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    expect(propsOf("thinking-tab").revisionParentVersion).toBeUndefined();
  });

  it("leaves the parent version unset for a root run", async () => {
    mockGetRunFamily.mockResolvedValue({ root_id: "r1", members: [member({ id: "r1" })] });
    const { user } = await openDetail(makeRun({ id: "r1", title: "Root" }));

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    expect(propsOf("thinking-tab").revisionParentVersion).toBeUndefined();
  });

  it("logs and degrades gracefully when the family lookup fails", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    mockGetRunFamily.mockRejectedValue(new Error("family down"));
    const { user } = await openDetail(makeRun({ id: "r2", title: "Child", parentRunId: "r1", rootRunId: "r0" }));
    await waitFor(() => expect(warn).toHaveBeenCalledWith("[revision-family] family fetch failed", expect.any(Error)));

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    expect(propsOf("thinking-tab").revisionParentVersion).toBeUndefined();
  });

  it("parses answered clarification rounds for the open run", async () => {
    mockGetRunArtifacts.mockResolvedValue({
      workflow_id: "x",
      artifacts: [
        { content: JSON.stringify([{ question_id: "q2", question_text: "Later?", impact_level: "low", answer: "yes", round: 2 }]) },
        { content: JSON.stringify([{ question_id: "q1", question_text: "First?", impact_level: "high", answer: "no", round: 1 }]) },
        { content: "not json" },
      ],
    });
    const { user } = await openDetail(makeRun({ id: "r1", title: "Clarified" }));
    await user.click(screen.getByRole("button", { name: "Thinking" }));

    await waitFor(() => expect((propsOf("thinking-tab").clarifications as unknown[]).length).toBe(2));

    const rounds = propsOf("thinking-tab").clarifications as Array<{ round: number }>;
    expect(rounds.map((r) => r.round)).toEqual([1, 2]);
    expect(mockGetRunArtifacts).toHaveBeenCalledWith("test-token", "r1", { kind: "clarifications", includeContent: true });
    await waitFor(() => expect(propsOf("thinking-tab").clarificationsLoading).toBe(false));
  });

  it("falls back to no clarification rounds when the lookup fails", async () => {
    mockGetRunArtifacts.mockRejectedValue(new Error("nope"));
    const { user } = await openDetail(makeRun({ id: "r1", title: "Clarified" }));
    await user.click(screen.getByRole("button", { name: "Thinking" }));

    await waitFor(() => expect(propsOf("thinking-tab").clarificationsLoading).toBe(false));

    expect(propsOf("thinking-tab").clarifications).toEqual([]);
  });
});

// ─── Version switching ───────────────────────────────────────────────────────
describe("WorkflowHistory detail — switching versions", () => {
  const FAMILY_MEMBERS = [
    member({ id: "v1", revision_index: 1, title: "First" }),
    member({ id: "v2", revision_index: 2, title: "Second", parent_run_id: "v1" }),
  ];

  async function openFamilyRun(props: Partial<React.ComponentProps<typeof WorkflowHistory>> = {}) {
    const v1 = makeRun({ id: "v1", title: "First version", rootRunId: "v1", output: "<html>v1</html>", createdAt: new Date(Date.now() - 120_000).toISOString() });
    const v2 = makeRun({ id: "v2", title: "Second version", parentRunId: "v1", rootRunId: "v1", output: "<html>v2</html>" });
    mockGetWorkflows.mockResolvedValue({ runs: [v1, v2], total: 2 });
    mockGetWorkflow.mockImplementation(async (_t, id) => (id === "v1" ? v1 : v2));
    mockGetRunSummary.mockImplementation(async (_t, id) => summaryFor(id === "v1" ? v1 : v2, FAMILY_MEMBERS));
    const user = userEvent.setup();
    const view = renderWithProviders(<WorkflowHistory {...uiProps(props)} />, { preloadedState: catalogState() });
    await user.click(await screen.findByRole("button", { name: /^Open First version/ }));
    await screen.findByRole("heading", { level: 2 });
    return { user, ...view, v1, v2 };
  }

  it("loads the chosen version into the same detail surface", async () => {
    const { user } = await openFamilyRun();
    expect(await screen.findByRole("heading", { level: 2, name: "Second version" })).toBeInTheDocument();

    await user.click(await screen.findByRole("radio", { name: /^Version 1/ }));

    expect(await screen.findByRole("heading", { level: 2, name: "First version" })).toBeInTheDocument();
    expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "v1");
    expect(screen.getByTestId("prototype-preview")).toHaveTextContent("<html>v1</html>");
  });

  it("keeps the current version and logs when the version fetch fails", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { user } = await openFamilyRun();
    await screen.findByRole("heading", { level: 2, name: "Second version" });
    mockGetWorkflow.mockRejectedValue(new Error("gone"));

    await user.click(await screen.findByRole("radio", { name: /^Version 1/ }));

    await waitFor(() => expect(warn).toHaveBeenCalledWith("[revision-family] version fetch failed", expect.any(Error)));
    expect(screen.getByRole("heading", { level: 2, name: "Second version" })).toBeInTheDocument();
  });

  it("does nothing when the token is gone", async () => {
    const { user } = await openFamilyRun();
    const chip = await screen.findByRole("radio", { name: /^Version 1/ });
    mockGetWorkflow.mockClear();
    mockGetToken.mockReturnValue(null);

    await user.click(chip);

    expect(mockGetWorkflow).not.toHaveBeenCalled();
  });

  it("routes the switch through the shared run screen once onOpenRun is wired", async () => {
    const onOpenRun = vi.fn();
    const { user, rerender, v1 } = await openFamilyRun();
    const chip = await screen.findByRole("radio", { name: /^Version 1/ });
    rerender(<WorkflowHistory onBack={vi.fn()} onOpenRun={onOpenRun} />);

    await user.click(await screen.findByRole("radio", { name: /^Version 1/ }));

    await waitFor(() => expect(onOpenRun).toHaveBeenCalledWith(expect.objectContaining({ id: v1.id })));
    expect(chip).toBeDefined();
  });
});

// ─── Suggested next steps ────────────────────────────────────────────────────
describe("WorkflowHistory detail — suggested next steps", () => {
  const savedFlows: UserWorkflowSummary[] = [
    { id: "sw1", name: "My saved flow", base_pipeline_type: "user_stories", agent_ids: [] } as UserWorkflowSummary,
    { id: "sw2", name: "Unrelated flow", base_pipeline_type: "nothing_chains_here", agent_ids: [] } as UserWorkflowSummary,
  ];

  describe("revise", () => {
    it.each<[string, WorkflowRun["type"], keyof React.ComponentProps<typeof WorkflowHistory>, string]>([
      ["prototype", "prototype", "onRevisePrototype", "Revise Prototype"],
      ["presentation", "ppt", "onRevisePpt", "Revise Presentation"],
      ["user stories", "user_stories", "onReviseUserStory", "Revise User Stories"],
      ["app builder", "app_builder", "onReviseAppBuilder", "Revise App Blueprint"],
    ])("sends a %s revision with the instruction, output and source run id", async (_label, type, callbackName, buttonLabel) => {
      const callback = vi.fn();
      const { user } = await openDetail(
        makeRun({ id: "r9", title: "Revisable", type, output: "current output" }),
        { [callbackName]: callback },
      );

      await user.click(screen.getByRole("button", { name: new RegExp(buttonLabel) }));
      const box = screen.getByRole("textbox", { name: "Revision instructions" });
      expect(box).toHaveFocus();
      await user.type(box, "  make it blue  ");
      await user.click(screen.getByRole("button", { name: "Send" }));

      expect(callback).toHaveBeenCalledWith("make it blue", "current output", "r9");
      expect(screen.queryByRole("textbox", { name: "Revision instructions" })).not.toBeInTheDocument();
    });

    it("keeps Send disabled until there is a non-blank instruction", async () => {
      const callback = vi.fn();
      const { user } = await openDetail(makeRun({ id: "r1", title: "Revisable" }), { onRevisePrototype: callback });
      await user.click(screen.getByRole("button", { name: /Revise Prototype/ }));

      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      await user.type(screen.getByRole("textbox", { name: "Revision instructions" }), "   ");
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      expect(callback).not.toHaveBeenCalled();
    });

    it("sends with Ctrl+Enter and ignores a plain Enter or a blank instruction", async () => {
      const callback = vi.fn();
      const { user } = await openDetail(makeRun({ id: "r1", title: "Revisable" }), { onRevisePrototype: callback });
      await user.click(screen.getByRole("button", { name: /Revise Prototype/ }));
      const box = screen.getByRole("textbox", { name: "Revision instructions" });

      await user.keyboard("{Control>}{Enter}{/Control}");
      expect(callback).not.toHaveBeenCalled();

      await user.type(box, "darker");
      await user.keyboard("{Enter}");
      expect(callback).not.toHaveBeenCalled();

      await user.keyboard("{Control>}{Enter}{/Control}");
      expect(callback).toHaveBeenCalledWith("darker", "stored output", "r1");
    });

    it("offers no revise action when the matching handler is not supplied", async () => {
      await openDetail(makeRun({ id: "r1", title: "No handler", type: "ppt" }), { onRevisePrototype: vi.fn() });

      expect(screen.queryByRole("button", { name: /Revise/ })).not.toBeInTheDocument();
    });

    it("offers no revise action for a run that has no output", async () => {
      await openDetail(makeRun({ id: "r1", title: "No output", output: "" }), { onRevisePrototype: vi.fn() });

      expect(screen.queryByRole("button", { name: /Revise/ })).not.toBeInTheDocument();
    });

    it("hides the whole panel when a completed run has nothing to offer", async () => {
      await openDetail(makeRun({ id: "r1", title: "Custom run", type: "custom" }));

      expect(screen.queryByText("Suggested next steps")).not.toBeInTheDocument();
    });
  });

  describe("chaining", () => {
    it("chains a completed run into a built-in target and clears any stale source-status flag", async () => {
      sessionStorage.setItem(CHAIN_SOURCE_STATUS_KEY, "failed");
      const onChainPipeline = vi.fn();
      const run = makeRun({ id: "r1", title: "Deck", type: "ppt" });
      const { user } = await openDetail(run, { onChainPipeline });

      await user.click(screen.getByRole("button", { name: /User Stories/ }));

      expect(onChainPipeline).toHaveBeenCalledWith(expect.objectContaining({ id: "r1" }), "user_stories");
      expect(sessionStorage.getItem(CHAIN_SOURCE_STATUS_KEY)).toBeNull();
    });

    it("shows a beta target as unavailable and ignores clicks on it", async () => {
      const onChainPipeline = vi.fn();
      const { user } = await openDetail(makeRun({ id: "r1", title: "Deck", type: "ppt" }), { onChainPipeline });

      const beta = screen.getByRole("button", { name: /Prototype/ });
      expect(beta).toBeDisabled();
      expect(within(beta).getByText("Coming Soon")).toBeInTheDocument();
      await user.click(beta);

      expect(onChainPipeline).not.toHaveBeenCalled();
    });

    it("lists saved workflows whose base type is a chain target and chains with their id", async () => {
      const onChainPipeline = vi.fn();
      const { user } = await openDetail(
        makeRun({ id: "r1", title: "Deck", type: "ppt" }),
        { onChainPipeline, savedWorkflows: savedFlows },
      );

      expect(screen.queryByRole("button", { name: /Unrelated flow/ })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /My saved flow/ }));

      expect(onChainPipeline).toHaveBeenCalledWith(expect.objectContaining({ id: "r1" }), "user_stories", "sw1");
    });

    it("ignores saved workflows when no chain handler is supplied", async () => {
      await openDetail(
        makeRun({ id: "r1", title: "Deck", type: "ppt" }),
        { savedWorkflows: savedFlows, onRevisePpt: vi.fn() },
      );

      expect(screen.queryByRole("button", { name: /My saved flow/ })).not.toBeInTheDocument();
    });

    it("warns about partial output and records the source status for a chainable failed run", async () => {
      const onChainPipeline = vi.fn();
      const run = makeRun({ id: "r1", title: "Failed deck", type: "ppt", status: "failed", payloadChainable: true });
      const { user } = await openDetail(run, { onChainPipeline, savedWorkflows: savedFlows });

      expect(screen.getByText("This run failed — output may be incomplete")).toBeInTheDocument();
      expect(screen.getByText("Only partial output will be passed to the next pipeline.")).toBeInTheDocument();
      expect(screen.getByText("Chain this run's partial output into User Stories")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /^User Stories/ }));
      expect(sessionStorage.getItem(CHAIN_SOURCE_STATUS_KEY)).toBe("failed");
      expect(onChainPipeline).toHaveBeenLastCalledWith(expect.objectContaining({ id: "r1" }), "user_stories");

      sessionStorage.clear();
      await user.click(screen.getByRole("button", { name: /My saved flow/ }));
      expect(sessionStorage.getItem(CHAIN_SOURCE_STATUS_KEY)).toBe("failed");
      expect(onChainPipeline).toHaveBeenLastCalledWith(expect.objectContaining({ id: "r1" }), "user_stories", "sw1");
    });

    it("shows saved workflows as unavailable with the reason for a non-chainable source", async () => {
      const onChainPipeline = vi.fn();
      const run = makeRun({
        id: "r1", title: "Blocked deck", type: "ppt", status: "degraded",
        payloadChainable: false, nonChainableReason: "secret_scan_blocked",
      });
      const { user } = await openDetail(run, { onChainPipeline, savedWorkflows: savedFlows });

      const saved = screen.getByRole("button", { name: /My saved flow/ });
      expect(saved).toBeDisabled();
      expect(within(saved).getByText("secret_scan_blocked")).toBeInTheDocument();
      await user.click(saved);

      expect(onChainPipeline).not.toHaveBeenCalled();
    });

    it("falls back to a generic reason when none was recorded", async () => {
      const run = makeRun({ id: "r1", title: "Blocked deck", type: "ppt", status: "cancelled", payloadChainable: false });
      await openDetail(run, { onChainPipeline: vi.fn(), savedWorkflows: savedFlows });

      expect(within(screen.getByRole("button", { name: /My saved flow/ })).getByText("Output not available for chaining")).toBeInTheDocument();
    });

    it("offers no next steps for a failed run when chaining is not wired", async () => {
      await openDetail(makeRun({ id: "r1", title: "Failed deck", type: "ppt", status: "failed" }));

      expect(screen.queryByText("Suggested next steps")).not.toBeInTheDocument();
    });

    it("offers no next steps for an in-flight run", async () => {
      await openDetail(makeRun({ id: "r1", title: "Running deck", type: "ppt", status: "running" }), { onChainPipeline: vi.fn() });

      expect(screen.queryByText("Suggested next steps")).not.toBeInTheDocument();
    });
  });
});

// --- Heading title cleaning --------------------------------------------------
describe("WorkflowHistory detail — heading title", () => {
  it("strips a leaked 'Title: ' prefix", async () => {
    const run = makeRun({ id: "r1", title: "Title: Clean heading" });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetWorkflow.mockResolvedValue(run);
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
    const user = userEvent.setup();
    renderWithProviders(<WorkflowHistory {...uiProps()} />, { preloadedState: catalogState() });

    await user.click(await screen.findByRole("button", { name: /^Open Clean heading/ }));

    expect(await screen.findByRole("heading", { level: 2, name: "Clean heading" })).toBeInTheDocument();
  });

  it("derives the heading from the run input when the title is empty", async () => {
    mockGetWorkflows.mockResolvedValue({ runs: [], total: 0 });
    const run = makeRun({ id: "r1", title: "", input: "Title: Brief based heading\nmore", type: "prototype" });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetWorkflow.mockResolvedValue(run);
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
    const user = userEvent.setup();
    renderWithProviders(<WorkflowHistory {...uiProps()} />, { preloadedState: catalogState() });

    await user.click(await screen.findByRole("button", { name: /^Open/ }));

    expect(await screen.findByRole("heading", { level: 2, name: "Brief based heading" })).toBeInTheDocument();
  });

  it("falls back to the raw type when a polluted title has no usable input", async () => {
    const run = makeRun({ id: "r1", title: "=== EXISTING HTML ===", input: "", type: "prototype" });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetWorkflow.mockResolvedValue(run);
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
    const user = userEvent.setup();
    renderWithProviders(<WorkflowHistory {...uiProps()} />, { preloadedState: catalogState() });

    await user.click(await screen.findByRole("button", { name: /^Open/ }));

    expect(await screen.findByRole("heading", { level: 2, name: "prototype" })).toBeInTheDocument();
  });

  it("recovers the revision instruction embedded in a polluted title", async () => {
    const run = makeRun({ id: "r1", title: "Intro\n=== REVISION REQUEST ===\nShrink the logo", type: "prototype" });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetWorkflow.mockResolvedValue(run);
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
    const user = userEvent.setup();
    renderWithProviders(<WorkflowHistory {...uiProps()} />, { preloadedState: catalogState() });

    await user.click(await screen.findByRole("button", { name: /^Open/ }));

    expect(await screen.findByRole("heading", { level: 2, name: "Shrink the logo" })).toBeInTheDocument();
  });
});

// --- Agent output aggregation edge cases -------------------------------------
describe("WorkflowHistory detail — agent output aggregation edge cases", () => {
  it("sums repeated agents even when earlier entries carry no timing or token data", async () => {
    const agentOutputs = [
      { agent_id: "a1", name: "Builder", role: "Dev", icon: "", output: "one", duration: null },
      { agent_id: "a1", name: "Builder", role: "Dev", icon: "", output: "two", duration: 4, input_tokens: 2, output_tokens: 3, total_tokens: 5 },
    ];
    const { user } = await openDetail(
      makeRun({ id: "r1", title: "Builder run", agentOutputs: agentOutputs as unknown as WorkflowRun["agentOutputs"] }),
    );

    await user.click(screen.getByRole("button", { name: "Thinking" }));

    const [agent] = propsOf("thinking-tab").agents as Array<Record<string, unknown>>;
    expect(agent).toMatchObject({ duration: 4, output: "two" });
  });
});
