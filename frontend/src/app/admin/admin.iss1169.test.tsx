// ISS-1169 (QA-KB-109 sibling): a refused tier change must put the row's badge back on the tier the
// server still holds. Another user's row with the PATCH rejected, so the test does not depend on the
// own-row guard. No motion mock: real motion keeps the row mounted, the repo's Proxy mock remounts it
// and would reset the badge by itself.
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

const ALICE = {
  id: "aaaa1111-2222-3333-4444-555566667777", email: "alice@example.com", tier: "pro" as const,
  is_admin: false, status: "active" as const, created_at: "2026-01-15T09:00:00Z", workflow_run_count: 12,
};
beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListUsers.mockResolvedValue([ALICE]);
  api.adminUpdateTier.mockRejectedValue(new Error("Identity provider unavailable"));
});
describe("ISS-1169 admin TierDropdown after a refused change", () => {
  it("ISS-1169: the badge returns to the server's tier when the tier change is refused", async () => {
    render(<AdminPage />);
    await screen.findByText(ALICE.email);
    const user = userEvent.setup();
    const row = screen.getByText(ALICE.email).closest("tr") as HTMLElement;
    const trigger = row.querySelector('[aria-haspopup="menu"]') as HTMLElement;
    expect(trigger).toHaveTextContent("Pro");

    await user.click(trigger);
    await user.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: /basic/i }));

    await screen.findByText("Identity provider unavailable");
    expect(api.adminUpdateTier).toHaveBeenCalledWith("tok", ALICE.id, "basic");
    await waitFor(() => expect(trigger).toHaveTextContent("Pro"));
  });
});
