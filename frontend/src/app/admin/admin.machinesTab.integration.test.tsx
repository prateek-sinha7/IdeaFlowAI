/**
 * AdminPage — Users | Machines tabs, integrated with the REAL Tabs primitive,
 * CapacityMatrix component and useCapacityMatrix hook. Only the transport
 * (@/lib/api), router and animation shell are mocked.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { AdminCapacityHistory, AdminCapacityMatrix, AdminUser } from "@/lib/api";

const { routerObj, api } = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    detail: unknown;
    constructor(status: number, detail: unknown, message = "") {
      super(message);
      this.status = status;
      this.detail = detail;
    }
  }
  return {
    routerObj: { replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() },
    api: {
      ApiError,
      getToken: vi.fn((): string | null => "tok"),
      getMe: vi.fn(),
      logout: vi.fn(),
      adminListUsers: vi.fn(),
      adminUpdateTier: vi.fn(),
      adminCreateUser: vi.fn(),
      adminDeleteUser: vi.fn(),
      adminUpdateRole: vi.fn(),
      adminDisableUser: vi.fn(),
      adminEnableUser: vi.fn(),
      adminResetUserPassword: vi.fn(),
      adminListCapacity: vi.fn(),
      adminGetCapacityHistory: vi.fn(),
      onAdminMfaRequired: vi.fn((cb: (detail: { enroll_path: string }) => void): (() => void) => { void cb; return () => {}; }),
    },
  };
});

vi.mock("next/navigation", () => ({ useRouter: () => routerObj }));
vi.mock("@/lib/api", () => api);

// Stable component identity per tag (unlike a naive Proxy) so rows do not remount.
vi.mock("motion/react", () => {
  const STRIPPED = new Set([
    "initial", "animate", "exit", "transition", "whileHover", "whileTap",
    "whileFocus", "whileInView", "viewport", "layout", "layoutId", "drag",
    "dragConstraints", "variants", "custom",
  ]);
  const cache = new Map<string, React.ComponentType<Record<string, unknown>>>();
  return {
    motion: new Proxy({}, {
      get: (_t, tag: string) => {
        if (!cache.has(tag)) {
          cache.set(tag, ({ children, ...rest }: Record<string, unknown>) =>
            React.createElement(
              tag,
              Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))),
              children as React.ReactNode,
            ));
        }
        return cache.get(tag);
      },
    }),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

import AdminPage from "./page";

const ALICE: AdminUser = {
  id: "user-1",
  email: "alice@example.com",
  tier: "pro",
  is_admin: false,
  status: "active",
  created_at: "2026-01-15T12:00:00Z",
  workflow_run_count: 12,
};

const MATRIX: AdminCapacityMatrix = {
  collected_at: "2026-03-01T12:00:00Z",
  self_instance_id: "i-0abc",
  instance_source: "discovery",
  instances: [
    {
      instance_id: "i-0abc",
      instance_type: "m5.large",
      is_self: true,
      cpu_used_percent: 50,
      mem_used_percent: 40,
      cpu_user_percent: 30,
      cpu_system_percent: 10,
      cpu_iowait_percent: 10,
      reading_age_seconds: 5,
      stale: false,
    },
  ],
  gate: {
    enabled: true,
    state: "allowing",
    blind_reason: null,
    cpu_threshold_percent: 80,
    mem_threshold_percent: 85,
    signals: [],
    engaged_at: null,
    evaluated_at: "2026-03-01T12:00:00Z",
  },
};

const HISTORY: AdminCapacityHistory = {
  instance_id: "i-0abc",
  range: "3h",
  period_seconds: 60,
  allowed_periods: [60, 300, 900, 3600],
  start: "2026-03-01T09:00:00Z",
  end: "2026-03-01T09:03:00Z",
  fetched_at: "2026-03-01T09:03:05Z",
  cached: false,
  cpu_threshold_percent: 80,
  mem_threshold_percent: 85,
  series: [
    {
      key: "cpu_used",
      label: "Total",
      group: "cpu",
      unit: "percent",
      values: [10, 20, 30],
      summary: { latest: 30, min: 10, avg: 20, max: 30 },
      error: null,
    },
  ],
};

async function renderAdmin() {
  render(<AdminPage />);
  await screen.findByText("alice@example.com");
  return userEvent.setup();
}

const machinesTab = () => screen.getByRole("tab", { name: "Machines" });

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListUsers.mockResolvedValue([ALICE]);
  api.adminListCapacity.mockResolvedValue(MATRIX);
  api.adminGetCapacityHistory.mockResolvedValue(HISTORY);
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

describe("AdminPage — machines tab", () => {
  it("swaps the users view for the capacity matrix when the Machines tab is selected", async () => {
    const user = await renderAdmin();
    await user.click(machinesTab());

    expect(machinesTab()).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Users" })).toHaveAttribute("aria-selected", "false");
    expect(await screen.findByText("Admission gate")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show metrics history for i-0abc" })).toBeInTheDocument();
    expect(screen.getByText("This instance")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
    expect(screen.queryByText("alice@example.com")).toBeNull();
    expect(screen.queryByText("Total Users")).toBeNull();
  });

  it("charts this instance's metric history below the matrix", async () => {
    const user = await renderAdmin();
    await user.click(machinesTab());

    expect(await screen.findByRole("heading", { name: "Metrics history" })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /CPU utilization over the last 3h/ })).toBeInTheDocument();
    expect(api.adminGetCapacityHistory).toHaveBeenCalledWith("tok", "i-0abc", "3h", null);
    expect(screen.getByRole("button", { name: "Show metrics history for i-0abc" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("returns to the users view without refetching users when switching back", async () => {
    const user = await renderAdmin();
    await user.click(machinesTab());
    await screen.findByText("Admission gate");

    await user.click(screen.getByRole("tab", { name: "Users" }));

    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(api.adminListUsers).toHaveBeenCalledTimes(1);
  });

  it("shows the loading state while the capacity request is pending", async () => {
    api.adminListCapacity.mockReturnValue(new Promise(() => {}));
    const user = await renderAdmin();
    await user.click(machinesTab());
    expect(await screen.findByText("Loading capacity matrix...")).toBeInTheDocument();
  });

  it("shows the error message when the capacity request fails", async () => {
    api.adminListCapacity.mockRejectedValue(new Error("cap down"));
    const user = await renderAdmin();
    await user.click(machinesTab());
    expect(await screen.findByText("cap down")).toBeInTheDocument();
  });

  it("shows the empty state when no instances have been collected", async () => {
    api.adminListCapacity.mockResolvedValue({ ...MATRIX, instances: [] });
    const user = await renderAdmin();
    await user.click(machinesTab());
    expect(await screen.findByText("No instances collected yet")).toBeInTheDocument();
  });

  it("does not request capacity when there is no token", async () => {
    api.getToken.mockReturnValue(null);
    render(<AdminPage />);
    await act(async () => {});
    expect(routerObj.replace).toHaveBeenCalled();
    expect(api.adminListCapacity).not.toHaveBeenCalled();
  });

  it.each([
    ["Enter", "{Enter}"],
    ["Space", " "],
  ])("activates the Machines tab with the %s key when it has focus", async (_label, keys) => {
    const user = await renderAdmin();
    await act(async () => { machinesTab().focus(); });
    await user.keyboard(keys);

    await waitFor(() => expect(machinesTab()).toHaveAttribute("aria-selected", "true"));
    expect(await screen.findByText("Admission gate")).toBeInTheDocument();
  });
});
