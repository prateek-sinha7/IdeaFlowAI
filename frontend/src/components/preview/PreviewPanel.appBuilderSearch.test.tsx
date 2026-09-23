import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { PreviewPanel } from "./PreviewPanel";

/**
 * ISS-500 — AppBuilderPreview's file-explorer search/folder-filter defect
 * (ISS-332) is entirely inside the shared `AppBuilderPreview.tsx` component,
 * with no per-caller prop that could suppress it, so it reproduces
 * unmodified at every mount point — including the embedded "Preview" tab
 * this file drives via the real (unmocked) `AppBuilderIDEPreview` wrapper
 * inside `PreviewPanel.tsx`.
 *
 * Unlike PreviewPanel.test.tsx and friends, `AppBuilderPreview` is
 * deliberately NOT mocked here — the whole point of this test is to
 * exercise the real component through this second, independent mount path.
 *
 * No pytest-equivalent `issue`/xfail marker exists in this vitest suite;
 * `it.fails` is vitest's xfail(strict=True) — it must fail now (unfixed)
 * and vitest fails the run if it ever starts passing unmarked.
 */

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
import { vi } from "vitest";
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

const markdown = [
  "```filename: src/app.js",
  "console.log('app')",
  "```",
  "```filename: src/styles/main.css",
  "body{}",
  "```",
  "```filename: src/utils/helper.js",
  "export const h = 1;",
  "```",
].join("\n");

describe("PreviewPanel — app_builder embedded Preview tab search (ISS-500)", () => {
  it.fails("ISS-500 — a folder with zero matching descendants is hidden by an active search in the embedded IDE tab, same as ISS-332", async () => {
    const user = userEvent.setup();
    render(<PreviewPanel workflowType="app_builder" userStoryContent={markdown} />);

    // The embedded IDE mounts the real AppBuilderPreview — confirm it rendered
    // (not the mocked stub other PreviewPanel tests use).
    expect(screen.getByLabelText("Search files")).toBeInTheDocument();

    // "src" is already auto-expanded on mount (top-level folders start open);
    // expand the nested subfolders so their (non-matching) rows would be visible.
    await user.click(screen.getByText("styles"));
    await user.click(screen.getByText("utils"));

    await user.type(screen.getByLabelText("Search files"), "app");

    // "app" matches only src/app.js. "styles" (zero matches) should be hidden.
    expect(screen.queryByText("styles")).not.toBeInTheDocument();
    // ISS-596: src/app.js is files[0] so it is also auto-opened as an editor
    // tab — "app.js" appears twice (tree row + tab label). getAllByText avoids
    // the TestingLibraryElementError that getByText throws on multiple matches.
    expect(screen.getAllByText("app.js").length).toBeGreaterThan(0);
  });
});
