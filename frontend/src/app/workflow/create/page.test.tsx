import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { replaceMock, router, searchState } = vi.hoisted(() => {
  const replaceMock = vi.fn();
  return {
    replaceMock,
    // Stable router object: a fresh one per render would re-run the redirect effect.
    router: { replace: replaceMock },
    // `suspendOn` lets a test make useSearchParams suspend, to exercise the Suspense fallback.
    searchState: {
      mode: null as string | null,
      suspendOn: null as Promise<void> | null,
    },
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => {
    if (searchState.suspendOn) throw searchState.suspendOn;
    const params = new URLSearchParams();
    if (searchState.mode !== null) params.set("mode", searchState.mode);
    return params;
  },
}));

// Stub: the real wizard owns auth, network I/O and has its own tests.
// A test id is used because the stub has no semantic role.
vi.mock("@/components/workflow/LaunchWizard", () => ({
  LaunchWizard: ({ initialMode }: { initialMode: string }) => (
    <div data-testid="launch-wizard-stub" data-initial-mode={initialMode} />
  ),
}));

import CreatePage from "./page";

describe("CreatePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchState.mode = null;
    searchState.suspendOn = null;
  });

  it("renders the wizard in prototype mode when no mode param is present", () => {
    render(<CreatePage />);

    expect(screen.getByTestId("launch-wizard-stub")).toHaveAttribute("data-initial-mode", "prototype");
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it.each(["prototype", "ppt", "ppt_v2"])("passes mode=%s through to the wizard without redirecting", (mode) => {
    searchState.mode = mode;
    render(<CreatePage />);

    expect(screen.getByTestId("launch-wizard-stub")).toHaveAttribute("data-initial-mode", mode);
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it.each([
    ["an unknown value", "banana"],
    ["an empty string", ""],
    ["a legacy v2 prototype value the route does not accept", "prototype_v2"],
    ["a differently-cased known value", "PPT"],
    ["a script-injection attempt", "<script>alert(1)</script>"],
  ])("renders nothing and canonicalizes the URL when mode is %s", async (_label, mode) => {
    searchState.mode = mode;
    const { container } = render(<CreatePage />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("launch-wizard-stub")).not.toBeInTheDocument();
    await waitFor(() => expect(replaceMock).toHaveBeenCalledTimes(1));
    // The redirect target is a fixed literal; the untrusted value is never echoed into it.
    expect(replaceMock).toHaveBeenCalledWith("/create?mode=prototype");
  });

  it("shows the loading fallback while search params are suspended, then the wizard", async () => {
    let release: () => void = () => {};
    searchState.suspendOn = new Promise<void>((resolve) => {
      release = resolve;
    });
    searchState.mode = "ppt";
    render(<CreatePage />);

    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(screen.queryByTestId("launch-wizard-stub")).not.toBeInTheDocument();

    searchState.suspendOn = null;
    release();

    expect(await screen.findByTestId("launch-wizard-stub")).toHaveAttribute("data-initial-mode", "ppt");
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  });
});
