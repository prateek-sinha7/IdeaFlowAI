import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { replaceMock, router } = vi.hoisted(() => {
  const replaceMock = vi.fn();
  return { replaceMock, router: { replace: replaceMock } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));
// Stub: the real preview pulls CodeMirror/iframes and has its own tests.
// A test id is used because the stub has no semantic role.
vi.mock("@/components/preview/AppBuilderPreview", () => ({
  AppBuilderPreview: ({
    files,
    projectName,
  }: {
    files: { path: string }[];
    projectName: string;
  }) => (
    <div data-testid="app-preview" data-project-name={projectName}>
      <ul>
        {files.map((f) => (
          <li key={f.path}>{f.path}</li>
        ))}
      </ul>
    </div>
  ),
}));

import PreviewFullscreenPage from "./page";

const KEY = "__app_preview__";
const FILE = { path: "src/a.ts", name: "a.ts", ext: "ts", content: "x", language: "typescript" };
const validPayload = (projectName = "Acme") => JSON.stringify({ files: [FILE], projectName });

function setUrl(search: string) {
  window.history.replaceState(null, "", `/preview-fullscreen${search}`);
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("PreviewFullscreenPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    sessionStorage.clear();
    setUrl("");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    window.history.replaceState(null, "", "/");
  });

  it("redirects to the run preview route when runId is present", async () => {
    setUrl("?runId=run-123");
    const { container } = render(<PreviewFullscreenPage />);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/runs/run-123/preview/full");
    await advance(1000);
    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Loading preview...")).not.toBeInTheDocument();
  });

  it("shows the loading state before the delay elapses", async () => {
    render(<PreviewFullscreenPage />);

    expect(screen.getByText("Loading preview...")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
    await advance(99);
    expect(screen.getByText("Loading preview...")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
    await advance(1);
    expect(replaceMock).toHaveBeenCalledWith("/runs");
  });

  it("renders the preview when a valid payload is stored", async () => {
    sessionStorage.setItem(KEY, validPayload("Acme"));
    render(<PreviewFullscreenPage />);
    await advance(100);

    const preview = screen.getByTestId("app-preview");
    expect(preview).toHaveAttribute("data-project-name", "Acme");
    expect(screen.getByText("src/a.ts")).toBeInTheDocument();
    expect(document.title).toBe("Acme — IDE Preview");
    expect(screen.queryByText("Loading preview...")).not.toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("falls back to a generic title when projectName is empty", async () => {
    sessionStorage.setItem(KEY, validPayload(""));
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(screen.getByTestId("app-preview")).toBeInTheDocument();
    expect(document.title).toBe("Project — IDE Preview");
  });

  it("redirects to run history when nothing is stored", async () => {
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/runs");
  });

  it.each([
    ["files missing", '{"projectName":"x"}'],
    ["files empty", '{"files":[],"projectName":"x"}'],
    ["JSON null", "null"],
  ])("redirects to run history when the payload has no files (%s)", async (_label, raw) => {
    sessionStorage.setItem(KEY, raw);
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/runs");
    expect(screen.queryByTestId("app-preview")).not.toBeInTheDocument();
  });

  it("redirects to run history when the stored payload is not valid JSON", async () => {
    sessionStorage.setItem(KEY, "{not json");
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(replaceMock).toHaveBeenCalledWith("/runs");
  });

  it("shows the too-large dead end when error=quota and nothing usable is stored", async () => {
    setUrl("?error=quota");
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(screen.getByText("Project too large for full screen")).toBeInTheDocument();
    expect(screen.getByText(/Download ZIP/)).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("app-preview")).not.toBeInTheDocument();
  });

  it("shows the too-large dead end when error=quota and the payload is malformed", async () => {
    setUrl("?error=quota");
    sessionStorage.setItem(KEY, "{not json");
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(screen.getByText("Project too large for full screen")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("still renders a valid payload when error=quota", async () => {
    setUrl("?error=quota");
    sessionStorage.setItem(KEY, validPayload());
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(screen.getByTestId("app-preview")).toBeInTheDocument();
    expect(screen.queryByText("Project too large for full screen")).not.toBeInTheDocument();
  });

  it("ignores an unrelated error value", async () => {
    setUrl("?error=other");
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(replaceMock).toHaveBeenCalledWith("/runs");
    expect(screen.queryByText("Project too large for full screen")).not.toBeInTheDocument();
  });

  it("lets runId win over quota and a stored payload", async () => {
    setUrl("?runId=r1&error=quota");
    sessionStorage.setItem(KEY, validPayload());
    render(<PreviewFullscreenPage />);
    await advance(200);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/runs/r1/preview/full");
    expect(screen.queryByTestId("app-preview")).not.toBeInTheDocument();
  });

  it("falls through to the stored payload when runId is empty", async () => {
    setUrl("?runId=");
    sessionStorage.setItem(KEY, validPayload());
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(screen.getByTestId("app-preview")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("redirects to run history when sessionStorage access throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    render(<PreviewFullscreenPage />);
    await advance(100);

    expect(replaceMock).toHaveBeenCalledWith("/runs");
  });

  it("does not redirect after unmount", async () => {
    const { unmount } = render(<PreviewFullscreenPage />);
    unmount();
    await advance(1000);

    expect(replaceMock).not.toHaveBeenCalled();
  });
});
