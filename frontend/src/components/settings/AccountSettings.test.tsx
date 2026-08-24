/**
 * 40-05 — Account Settings mock-fidelity restyle guards.
 *
 * Pins the Phase-40 fidelity contract for the Settings surface (the behavior
 * parity + fiction-guard for the four wired sections is separately pinned in
 * AccountSettings.render.test.tsx — this file is additive, not a replacement):
 *
 *   1. The "Limits" tab is relabelled "Usage & Limits" to match the mock, while
 *      the internal id / data-testid ("limits" / tab-limits) stays STABLE
 *      (the fidelity oracle navigates by /Limits/i, testids never move).
 *   2. The Profile form renders REAL user data only (email + plan/tier) — NONE
 *      of the mock's fabricated name / role / organization strings appear
 *      (ND-Y / SC-001 — never fabricate unpersisted data).
 *   3. The AI Model tab lists the LIVE available models from the preferences
 *      endpoint (ND-D), never a hardcoded model list.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

// Stable singleton, matching next/navigation's real identity (see the note in
// AccountSettings.render.test.tsx).
const mockRouter = { push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
}));

import { AccountSettings } from "./AccountSettings";

beforeEach(() => {
  vi.clearAllMocks();
  mockGetToken.mockReturnValue("test-token");
  mockGetMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "enterprise" });
  mockGetPreferences.mockResolvedValue({
    preferred_model: null,
    available_models: [
      { id: "live-model-x", name: "Live Model X", description: "a live model", tier: "fast" },
    ],
  });
  mockGetCapabilities.mockResolvedValue({ model_catalog: [] });
  mockChangePassword.mockResolvedValue({ message: "ok" });
  mockUpdatePreferences.mockResolvedValue({ preferred_model: "live-model-x", available_models: [] });
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

describe("AccountSettings — mock relabel (Usage & Limits, stable id)", () => {
  it('renders the tab labelled "Usage & Limits" (not a bare "Limits") with a stable testid', async () => {
    render(<AccountSettings onBack={() => {}} />);
    await waitFor(() => expect(mockGetMe).toHaveBeenCalled());

    // The relabelled tab is present…
    const tab = screen.getByRole("tab", { name: /Usage & Limits/i });
    expect(tab).toBeInTheDocument();
    // …and it is the SAME control as the stable "limits" id (testid unmoved).
    expect(screen.getByTestId("tab-limits")).toBe(tab);
    expect(screen.getByTestId("tab-limits")).toHaveTextContent("Usage & Limits");

    // No tab reads the bare pre-relabel label.
    expect(screen.queryByRole("tab", { name: /^Limits$/ })).toBeNull();
  });
});

describe("AccountSettings — tab order (Security last, after Constitution)", () => {
  it("renders the five section tabs in order with Security appended", async () => {
    render(<AccountSettings onBack={() => {}} />);
    await waitFor(() => expect(mockGetMe).toHaveBeenCalled());

    const labels = screen.getAllByRole("tab").map((t) => t.textContent?.trim());
    expect(labels).toEqual([
      "Profile",
      "AI Model",
      "Usage & Limits",
      "Constitution",
      "Security",
    ]);
    // Stable id for the relocated section, mirroring tab-limits.
    expect(screen.getByTestId("tab-security")).toBe(
      screen.getByRole("tab", { name: /^Security$/ }),
    );
  });
});

describe("AccountSettings — real-data profile only (ND-Y)", () => {
  it("shows email + plan and NONE of the mock's fabricated name/role/org fields", async () => {
    render(<AccountSettings onBack={() => {}} />);

    // Real fields render.
    expect(await screen.findByText("user@example.com")).toBeInTheDocument();
    expect(screen.getAllByText(/Enterprise/i).length).toBeGreaterThan(0);

    // The mock's fabricated profile strings are absent.
    for (const fiction of ["Ayesha Khan", "Product Engineer", "Hexaware Technologies"]) {
      expect(screen.queryByText(fiction)).toBeNull();
    }
    // No fabricated name / role / organization inputs or labels.
    expect(screen.queryByText(/Full name/i)).toBeNull();
    expect(screen.queryByText(/Organization/i)).toBeNull();
    expect(screen.queryByLabelText(/^role$/i)).toBeNull();
  });
});

describe("AccountSettings — live model list (ND-D)", () => {
  it("lists the live available model from the preferences endpoint", async () => {
    const user = userEvent.setup();
    render(<AccountSettings onBack={() => {}} />);
    await waitFor(() => expect(mockGetPreferences).toHaveBeenCalled());

    await user.click(screen.getByRole("tab", { name: /AI Model/i }));
    const select = await screen.findByRole("combobox");
    // The live model name (never a hardcoded mock model) is an option.
    expect(within(select).getByRole("option", { name: /Live Model X/i })).toBeInTheDocument();
  });
});
