/**
 * ISS-244 — the "New passwords do not match" banner must clear once the
 * Confirm new password field is edited to agree with New password again.
 *
 * Today `message` (AccountSettings.tsx:99) is written only inside
 * handleChangePassword; the New/Confirm password onChange handlers
 * (AccountSettings.tsx:296,306) never call setMessage(null), so the stale
 * mismatch banner survives a correcting edit. This test asserts the CORRECT
 * behaviour and is expected to fail (xfail, strict) until that is fixed.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockGetToken = vi.fn(() => "test-token");
const mockGetMe = vi.fn();
const mockGetPreferences = vi.fn();
const mockGetCapabilities = vi.fn();
const mockChangePassword = vi.fn();
const mockUpdatePreferences = vi.fn();
const mockGetMfaStatus = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getMe: (t: string) => mockGetMe(t),
  getPreferences: (t: string) => mockGetPreferences(t),
  getCapabilities: (t: string) => mockGetCapabilities(t),
  changePassword: (t: string, c: string, n: string) => mockChangePassword(t, c, n),
  updatePreferences: (t: string, m: string | null) => mockUpdatePreferences(t, m),
  getMfaStatus: (t: string) => mockGetMfaStatus(t),
  enableEmailMfa: vi.fn(),
  disableEmailMfa: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const mockRouter = { push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
}));

import { AccountSettings } from "./AccountSettings";

beforeEach(() => {
  vi.clearAllMocks();
  mockGetToken.mockReturnValue("test-token");
  mockGetMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "enterprise" });
  mockGetPreferences.mockResolvedValue({ preferred_model: null, available_models: [] });
  mockGetCapabilities.mockResolvedValue({ model_catalog: [] });
  mockChangePassword.mockResolvedValue({ message: "ok" });
  mockUpdatePreferences.mockResolvedValue({ preferred_model: null, available_models: [] });
  mockGetMfaStatus.mockResolvedValue({
    supported: true,
    enabled: false,
    required: false,
    email_available: true,
    factors: [],
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ content: "" }) }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AccountSettings — password mismatch banner (ISS-244)", () => {
  it(
    "clears the 'New passwords do not match' banner once Confirm is edited to agree",
    async () => {
      const user = userEvent.setup();
      render(<AccountSettings onBack={() => {}} />);
      await waitFor(() => expect(mockGetMe).toHaveBeenCalled());

      await user.type(screen.getByLabelText(/Current password/i), "current-pw-1");
      await user.type(screen.getByLabelText(/^New password$/i), "brand-new-pw");
      await user.type(screen.getByLabelText(/Confirm new password/i), "different-pw");
      await user.click(screen.getByRole("button", { name: /Change Password/i }));

      expect(await screen.findByText(/New passwords do not match/i)).toBeInTheDocument();

      // Correct the confirm field so it now agrees with New password.
      const confirmInput = screen.getByLabelText(/Confirm new password/i);
      await user.clear(confirmInput);
      await user.type(confirmInput, "brand-new-pw");

      // Expected: the stale mismatch banner is gone now that the fields agree.
      expect(screen.queryByText(/New passwords do not match/i)).toBeNull();
    },
  );
});
