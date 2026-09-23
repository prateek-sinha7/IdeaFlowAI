import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";

/**
 * BUG-20260828-041300-preview-fullscreen — AppBuilderPreview's file-explorer
 * search filters only leaf files (`FileTreeNode`'s `matchesSearch` guard sits
 * in the `file` branch only, ~line 203). The `folder` branch renders
 * unconditionally, so a folder with zero matching descendants stays visible
 * and expandable. The sidebar footer (~line 556) reads the raw, unfiltered
 * `files` prop and never reflects the active search.
 *
 * No pytest-equivalent `issue`/xfail marker exists in this vitest suite;
 * `it.fails` is vitest's xfail(strict=True) — it must fail now (unfixed) and
 * vitest fails the run if it ever starts passing unmarked.
 */

function makeFiles(): ParsedFile[] {
  return [
    { path: "index.html", name: "index.html", ext: "html", content: "<html></html>", language: "html" },
    { path: "src/app.js", name: "app.js", ext: "js", content: "console.log('app')", language: "javascript" },
    { path: "src/styles/main.css", name: "main.css", ext: "css", content: "body{}", language: "css" },
    { path: "src/utils/helper.js", name: "helper.js", ext: "js", content: "export const h = 1;", language: "javascript" },
  ];
}

describe("AppBuilderPreview — file-explorer search (ISS-332)", () => {
  it("ISS-332 — a folder with zero matching descendants is hidden by an active search", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={makeFiles()} projectName="SearchTestProject" />);

    // "src" is already auto-expanded on mount (top-level folders start open);
    // expand the nested subfolders so their (non-matching) rows would be visible.
    await user.click(screen.getByText("styles"));
    await user.click(screen.getByText("utils"));

    await user.type(screen.getByLabelText("Search files"), "app");

    // "app" matches only src/app.js. Neither "styles" nor "utils" contains a
    // matching file, so correct behaviour hides both folder rows.
    expect(screen.queryByText("styles")).not.toBeInTheDocument();
    expect(screen.queryByText("utils")).not.toBeInTheDocument();
    expect(screen.getByText("app.js")).toBeInTheDocument();
  });

  it("ISS-332 — the footer file count reflects the active search filter", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={makeFiles()} projectName="SearchTestProject" />);

    await user.type(screen.getByLabelText("Search files"), "app");

    // Only 1 of 4 files matches "app" (src/app.js) — the footer must say so,
    // not the unfiltered total.
    expect(screen.getByText(/^1 files? ·/)).toBeInTheDocument();
    expect(screen.queryByText(/^4 files ·/)).not.toBeInTheDocument();
  });

  it("ISS-501 — search surfaces a match nested inside a collapsed non-top-level folder", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={makeFiles()} projectName="SearchTestProject" />);

    // Do NOT manually expand "utils" first — only the top-level "src" folder
    // is auto-expanded on mount. "utils" starts collapsed.
    await user.type(screen.getByLabelText("Search files"), "helper");

    // helper.js lives inside src/utils, which is collapsed by default.
    // Correct behaviour surfaces the match anyway (e.g. by auto-expanding
    // its containing folder).
    expect(screen.getByText("helper.js")).toBeInTheDocument();
  });

  it("ISS-502 — a zero-match query shows an empty-state message, not a stack of dead folders", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={makeFiles()} projectName="SearchTestProject" />);

    await user.type(screen.getByLabelText("Search files"), "zzzznomatch");

    // Every folder row should disappear along with the (already-filtered)
    // files, and some empty-state affordance should replace them.
    expect(screen.queryByText("src")).not.toBeInTheDocument();
    expect(screen.queryByText("styles")).not.toBeInTheDocument();
    expect(screen.queryByText("utils")).not.toBeInTheDocument();
    expect(screen.getByText(/no files match/i)).toBeInTheDocument();
  });
});
