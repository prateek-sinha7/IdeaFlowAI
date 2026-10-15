// ISS-930 (QA-KB-041): Escape must close the admin tier dropdown after an unfocused click.
// it.fails: red today by design; remove `.fails` when the fix lands.
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const { routerObj, api } = vi.hoisted(() => ({
  routerObj: { replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() },
  api: {
    getToken: vi.fn(() => "tok"), getMe: vi.fn(), logout: vi.fn(), adminListUsers: vi.fn(),
    adminUpdateTier: vi.fn(), adminCreateUser: vi.fn(), adminDeleteUser: vi.fn(), adminUpdateRole: vi.fn(),
    adminDisableUser: vi.fn(), adminEnableUser: vi.fn(), onAdminMfaRequired: vi.fn(() => () => {}),
  },
}));
vi.mock("next/navigation", () => ({ useRouter: () => routerObj }));
vi.mock("@/lib/api", () => api);

import AdminPage from "@/app/admin/page";

const USERS = [{
  id: "aaaa1111-2222-3333-4444-555566667777", email: "alice@example.com", tier: "pro" as const,
  is_admin: false, status: "active" as const, created_at: "2026-01-15T09:00:00Z", workflow_run_count: 12,
}];
beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListUsers.mockResolvedValue(USERS);
});
describe("ISS-930 admin TierDropdown Escape", () => {
  it("ISS-930: Escape closes the tier menu after an unfocused click on the trigger", async () => {
    render(<AdminPage />);
    await screen.findByText("alice@example.com");
    const user = userEvent.setup();
    const trigger = document.querySelector('[aria-haspopup="menu"]') as HTMLElement;
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
