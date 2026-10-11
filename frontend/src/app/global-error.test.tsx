import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render as rtlRender, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";

const { usePathnameMock } = vi.hoisted(() => ({
  usePathnameMock: vi.fn<() => string>(),
}));

vi.mock("next/navigation", () => ({
  usePathname: usePathnameMock,
}));

import GlobalErrorPage from "./global-error";

type BoundaryError = Error & { digest?: string };

function makeError(message = "database password leaked: hunter2", digest?: string): BoundaryError {
  const error: BoundaryError = new Error(message);
  error.stack = "Error: internal\n    at secretInternalFunction (/srv/app/internal.ts:42:7)";
  if (digest !== undefined) error.digest = digest;
  return error;
}

// GlobalErrorPage renders its own <html>/<body>. Mounting that inside RTL's
// default <div> container would nest <html> in a <div> and never reach
// `document.documentElement`, so the root is mounted on `document` itself,
// which is where Next.js mounts it. (No React nesting warning was observed in
// either mode with this React/jsdom pair, so none is asserted.)
function render(ui: ReactElement) {
  return rtlRender(ui, { container: document, baseElement: document.body });
}

describe("GlobalErrorPage (root error boundary)", () => {
  const originalLocation = window.location;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    usePathnameMock.mockReturnValue("/dashboard");
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    // jsdom cannot navigate on `location.href = ...`; replace it with a plain
    // mutable object so the assigned destination can be observed.
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: { href: "http://localhost/current" } as unknown as Location,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
    vi.restoreAllMocks();
    usePathnameMock.mockReset();
  });

  describe("document shell", () => {
    it("renders its own English-language <html> element", () => {
      render(<GlobalErrorPage error={makeError()} reset={vi.fn()} />);

      expect(document.documentElement).toHaveAttribute("lang", "en");
    });

    it("renders the page content inside the <body>", () => {
      render(<GlobalErrorPage error={makeError()} reset={vi.fn()} />);

      expect(document.body).toContainElement(
        screen.getByRole("heading", { level: 1, name: "Something went wrong" }),
      );
    });
  });

  describe("content", () => {
    it("renders the generic failure heading, notice, and 500 code", () => {
      render(<GlobalErrorPage error={makeError()} reset={vi.fn()} />);

      expect(screen.getByRole("heading", { level: 1, name: "Something went wrong" })).toBeInTheDocument();
      expect(
        screen.getByText("An unexpected error occurred. Our team has been notified."),
      ).toBeInTheDocument();
      expect(screen.getByText("500")).toBeInTheDocument();
      expect(
        screen.getByText("If this problem persists, contact your administrator."),
      ).toBeInTheDocument();
    });

    it("offers three recovery buttons by accessible name", () => {
      render(<GlobalErrorPage error={makeError()} reset={vi.fn()} />);

      expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Back to dashboard" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Back to login" })).toBeInTheDocument();
      expect(screen.getAllByRole("button")).toHaveLength(3);
    });

    it("does not leak the error message, stack, or digest to the user", () => {
      render(
        <GlobalErrorPage error={makeError("database password leaked: hunter2", "digest-8841")} reset={vi.fn()} />,
      );

      expect(document.body).not.toHaveTextContent("hunter2");
      expect(document.body).not.toHaveTextContent("secretInternalFunction");
      expect(document.body).not.toHaveTextContent("digest-8841");
    });
  });

  describe("interactions", () => {
    it("calls reset once when 'Try again' is clicked", async () => {
      const user = userEvent.setup();
      const reset = vi.fn();
      render(<GlobalErrorPage error={makeError()} reset={reset} />);

      await user.click(screen.getByRole("button", { name: "Try again" }));

      expect(reset).toHaveBeenCalledTimes(1);
      expect(reset).toHaveBeenCalledWith();
    });

    it("does not call reset or navigate on first render", () => {
      const reset = vi.fn();
      render(<GlobalErrorPage error={makeError()} reset={reset} />);

      expect(reset).not.toHaveBeenCalled();
      expect(window.location.href).toBe("http://localhost/current");
    });

    it("hard-navigates to the dashboard when 'Back to dashboard' is clicked", async () => {
      const user = userEvent.setup();
      const reset = vi.fn();
      render(<GlobalErrorPage error={makeError()} reset={reset} />);

      await user.click(screen.getByRole("button", { name: "Back to dashboard" }));

      expect(window.location.href).toBe("/dashboard");
      expect(reset).not.toHaveBeenCalled();
    });

    it("hard-navigates to the login page when 'Back to login' is clicked", async () => {
      const user = userEvent.setup();
      const reset = vi.fn();
      render(<GlobalErrorPage error={makeError()} reset={reset} />);

      await user.click(screen.getByRole("button", { name: "Back to login" }));

      expect(window.location.href).toBe("/login");
      expect(reset).not.toHaveBeenCalled();
    });

    it("activates 'Try again' from the keyboard", async () => {
      const user = userEvent.setup();
      const reset = vi.fn();
      render(<GlobalErrorPage error={makeError()} reset={reset} />);

      screen.getByRole("button", { name: "Try again" }).focus();
      await user.keyboard("{Enter}");

      expect(reset).toHaveBeenCalledTimes(1);
    });
  });

  describe("error logging", () => {
    function globalBoundaryLogs() {
      return consoleErrorSpy.mock.calls.filter((call: unknown[]) =>
        String(call[0]).includes("Global error boundary caught:"),
      );
    }

    it("logs the caught error tagged with the current screen", () => {
      const error = makeError("boom", "digest-1");
      usePathnameMock.mockReturnValue("/dashboard");

      render(<GlobalErrorPage error={error} reset={vi.fn()} />);

      expect(globalBoundaryLogs()).toEqual([["[home] Global error boundary caught:", error]]);
    });

    it.each([
      { pathname: "/", label: "home" },
      { pathname: "/runs/run-42", label: "run-detail" },
      { pathname: "/runs/run-42/steps", label: "run-steps" },
      { pathname: "/settings/security", label: "settings-security" },
      { pathname: "/library/agents/some-agent", label: "library-agent" },
      { pathname: "/does/not/exist", label: "unknown" },
    ])("tags the log with '$label' when the pathname is $pathname", ({ pathname, label }) => {
      const error = makeError("boom");
      usePathnameMock.mockReturnValue(pathname);

      render(<GlobalErrorPage error={error} reset={vi.fn()} />);

      expect(globalBoundaryLogs()).toEqual([[`[${label}] Global error boundary caught:`, error]]);
    });

    it("logs again when the boundary receives a different error", () => {
      const first = makeError("first");
      const second = makeError("second");

      const { rerender } = render(<GlobalErrorPage error={first} reset={vi.fn()} />);
      rerender(<GlobalErrorPage error={second} reset={vi.fn()} />);

      expect(globalBoundaryLogs()).toEqual([
        ["[home] Global error boundary caught:", first],
        ["[home] Global error boundary caught:", second],
      ]);
    });

    it("logs again with the new screen tag when the pathname changes", () => {
      const error = makeError("boom");
      usePathnameMock.mockReturnValue("/dashboard");
      const { rerender } = render(<GlobalErrorPage error={error} reset={vi.fn()} />);

      usePathnameMock.mockReturnValue("/runs/run-42");
      rerender(<GlobalErrorPage error={error} reset={vi.fn()} />);

      expect(globalBoundaryLogs()).toEqual([
        ["[home] Global error boundary caught:", error],
        ["[run-detail] Global error boundary caught:", error],
      ]);
    });

    it("does not log again when re-rendered with the same error and pathname", () => {
      const error = makeError("boom");
      const { rerender } = render(<GlobalErrorPage error={error} reset={vi.fn()} />);

      rerender(<GlobalErrorPage error={error} reset={vi.fn()} />);

      expect(globalBoundaryLogs()).toHaveLength(1);
    });
  });
});
