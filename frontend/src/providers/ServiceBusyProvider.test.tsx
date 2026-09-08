/**
 * specs/014 — ServiceBusyProvider: the app-level owner of the "service is
 * busy" modal. Drives the real provider (no mocking of the provider itself)
 * and fires rejections through the REAL `onCapacityRejected` pub/sub in
 * `lib/api.ts` — this is the same seam any ApiError construction anywhere in
 * the app uses, so the test exercises the actual integration point rather
 * than a stand-in.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ServiceBusyProvider,
  useServiceBusy,
} from "./ServiceBusyProvider";
import type { CapacityRejectionDetail } from "@/lib/api";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function rejection(
  overrides: Partial<CapacityRejectionDetail> = {},
): CapacityRejectionDetail {
  return {
    error: "The service is busy right now. Please try again in a few minutes.",
    code: "host_capacity_exhausted",
    recoverable: true,
    retry_after_seconds: 120,
    signals: [{ name: "cpu", value: 91, threshold: 75 }],
    ...overrides,
  };
}

describe("useServiceBusy — inert default outside the provider", () => {
  it("is safe to call outside the provider and reports not-busy", () => {
    const { result } = renderHook(() => useServiceBusy());
    expect(result.current.isBusy).toBe(false);
    expect(result.current.lastRejection).toBeNull();
  });
});

describe("ServiceBusyProvider — modal lifecycle", () => {
  it("renders no modal before any rejection", () => {
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows the busy modal when a 503 host_capacity_exhausted ApiError is constructed anywhere", async () => {
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();

    // Import ApiError the same way production call sites do, and construct
    // one exactly as request()/postResume/etc. do on a real 503 — this is
    // what actually notifies the provider's subscription.
    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(503, rejection());
    });

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
    expect(screen.getByText("Service is busy")).toBeInTheDocument();
  });

  it("renders the rejection's error message and signal details", async () => {
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(
        503,
        rejection({
          error: "custom busy message",
          signals: [
            { name: "memory", value: 88, threshold: 75 },
            { name: "cpu", value: 91, threshold: 75 },
          ],
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText("custom busy message")).toBeInTheDocument();
    });
    expect(screen.getByText(/Memory: 88%/)).toBeInTheDocument();
    expect(screen.getByText(/CPU: 91%/)).toBeInTheDocument();
  });

  it("dismisses via the 'Got it' button", async () => {
    const user = userEvent.setup();
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(503, rejection());
    });
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("dismisses via Escape (the Modal primitive's own behavior)", async () => {
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(503, rejection());
    });
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    act(() => {
      const evt = new KeyboardEvent("keydown", { key: "Escape" });
      window.dispatchEvent(evt);
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a second rejection while already open COALESCES into the same modal (only one dialog ever mounted)", async () => {
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(503, rejection({ error: "first" }));
    });
    await waitFor(() => {
      expect(screen.getByText("first")).toBeInTheDocument();
    });

    act(() => {
      new ApiError(503, rejection({ error: "second" }));
    });
    await waitFor(() => {
      expect(screen.getByText("second")).toBeInTheDocument();
    });
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("does not react to a non-capacity ApiError (e.g. a 403)", async () => {
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(403, "Admin access required.");
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("ServiceBusyProvider — context value", () => {
  it("useServiceBusy reflects isBusy/lastRejection and exposes a working dismiss()", async () => {
    const { result } = renderHook(() => useServiceBusy(), {
      wrapper: ServiceBusyProvider,
    });
    expect(result.current.isBusy).toBe(false);

    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(503, rejection());
    });

    await waitFor(() => {
      expect(result.current.isBusy).toBe(true);
    });
    expect(result.current.lastRejection?.code).toBe("host_capacity_exhausted");

    act(() => {
      result.current.dismiss();
    });
    await waitFor(() => {
      expect(result.current.isBusy).toBe(false);
    });
    expect(result.current.lastRejection).toBeNull();
  });
});

describe("ServiceBusyProvider — retry countdown", () => {
  it("counts down from retry_after_seconds and reaches the 'try again now' state", async () => {
    vi.useFakeTimers();
    render(
      <ServiceBusyProvider>
        <div>app</div>
      </ServiceBusyProvider>,
    );
    const { ApiError } = await import("@/lib/api");
    act(() => {
      new ApiError(503, rejection({ retry_after_seconds: 2 }));
    });

    expect(screen.getByText(/try again in about 2s/i)).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText(/try again in about 1s/i)).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText(/you can try again now/i)).toBeInTheDocument();

    // Never goes negative.
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText(/you can try again now/i)).toBeInTheDocument();
  });
});
