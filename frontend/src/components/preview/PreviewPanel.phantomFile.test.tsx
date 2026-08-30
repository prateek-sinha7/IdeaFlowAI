import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// ISS-323 — the App Builder IDE preview's `parseAppBuilderFilesForIDE` regex
// (Format 2, PreviewPanel.tsx:92) matches ANY `### heading` whose text merely
// contains a dot-plus-word-chars substring, not just a real file path. A
// documentation subheading like `### Via Node.js` (library name + version-like
// dot) immediately followed by a fenced code sample is indistinguishable from
// a real `### src/app.js` heading to this regex, so it is parsed as a phantom
// project "file" — shown in the Explorer, counted in the footer, downloadable.
//
// Unlike PreviewPanel.test.tsx, AppBuilderPreview is left UNMOCKED here so the
// real file tree renders and the phantom entry (or its absence) is observable.
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflow: vi.fn(),
  getRunFamily: vi.fn(),
  getRunSandbox: vi.fn(),
  getRunSandboxFileBlob: vi.fn(),
}));

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

vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
// NOTE: ./AppBuilderPreview is intentionally NOT mocked — the real Explorer
// tree must render for this test to observe the phantom entry.
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  downloadBlob: vi.fn(),
  deriveDeliverableFilename: () => "project.zip",
}));

import { PreviewPanel } from "./PreviewPanel";

// The real README excerpt from the round-2 hunt (bug-hunter evidence notes.md):
// a genuine "### Via Node.js" subsection with a fenced JS sample, no real path.
// Plus one REAL "### src/app.js" file heading — the hunted deliverable listed
// three genuine files alongside the phantom ("4 files" in the footer), so the
// Explorer must still render, and the guard must not reject real path headings.
const README_WITH_PHANTOM_SUBHEADING = `# hello-world-app

### src/app.js

\`\`\`javascript
const app = "real file";
\`\`\`

## Usage

### Via Node.js

\`\`\`javascript
const http = require("http");
http.createServer((req, res) => res.end("hello")).listen(3000);
\`\`\`
`;

describe("ISS-323 — App Builder IDE preview must not parse a markdown subheading as a file", () => {
  it("does not list a documentation subheading like 'Via Node.js' as an Explorer file", () => {
    render(
      <PreviewPanel
        workflowType="app_builder"
        userStoryContent={README_WITH_PHANTOM_SUBHEADING}
      />,
    );

    // The real Explorer renders (AppBuilderPreview is unmocked for this test).
    expect(screen.getByText(/files$/)).toBeInTheDocument();

    // The bug: "Via Node.js" — a prose heading, not a file path (contains a
    // space, no real extension) — is added as a standalone Explorer entry
    // (it appears both in the sidebar tree and as an open editor tab).
    expect(screen.queryAllByText("Via Node.js")).toHaveLength(0);
  });
});
