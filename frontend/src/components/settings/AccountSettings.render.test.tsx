/**
 * B1-02 (Phase 35 Wave 2) — AccountSettings behavior-parity + fiction-guard.
 *
 * This is a RESKIN, not a static->real build: the mock's "static fields" are
 * mock fiction; the product controls are ALREADY real. This test PINS the four
 * already-wired sections so the token reskin cannot regress any endpoint call,
 * and encodes the scope boundary (no unbacked Full name / Role / Organization
 * inputs — INV-3, no new backend):
 *
 *   1. On mount the existing loaders fire: getMe / getPreferences /
 *      getCapabilities.
 *   2. The password form calls changePassword(token, current, new) with the
 *      pw>=8 client validation preserved.
 *   3. Saving a changed model calls updatePreferences(token, modelId).
 *   4. The constitution section reads /api/settings/constitution.
 *   5. Fiction guard: email renders read-only (a display, not an editable
 *      input) and NO Full name / Role / Organization field is rendered.
 *
 * Nav is queried role-agnostically (closest <button>) so the same assertions
 * hold before AND after the Task-2 reskin swaps the sidebar buttons for the
 * `Tabs` primitive (SC-001 — keyed on generic section labels, never a workflow
 * name). `@/lib/api` is mocked so no real network call is made; the
 * constitution `fetch` is stubbed on the global.
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

vi.mock("@/lib/api", () => ({
  // FR-015: the constitution section now calls lib/api's `authedFetch` (global
  // fetch + the shared 401 -> handleSessionExpiry() guard) instead of bare
  // fetch. Delegate to the stubbed global so the assertion below still checks
  // the same thing — that the section reads /api/settings/constitution with an
  // auth header — rather than weakening it to a mock-call count.
  authedFetch: (input: string, init?: RequestInit) => fetch(input, init),
  getToken: () => mockGetToken(),
  getMe: (t: string) => mockGetMe(t),
  getPreferences: (t: string) => mockGetPreferences(t),
  getCapabilities: (t: string) => mockGetCapabilities(t),
  changePassword: (t: string, c: string, n: string) => mockChangePassword(t, c, n),
  updatePreferences: (t: string, m: string | null) => mockUpdatePreferences(t, m),
}));

import { AccountSettings } from "./AccountSettings";
import { ENV } from "@/lib/env";

// Click a settings-section nav control by its visible label, resolving the
// enclosing <button> so this works whether the nav is a plain <button>
// (pre-reskin) or a `Tabs` <button role="tab"> (post-reskin).
async function clickNav(user: ReturnType<typeof userEvent.setup>, label: string) {
  const node = screen
    .getAllByText(label)
    .map((n) => n.closest("button"))
    .find((b): b is HTMLButtonElement => b !== null);
  if (!node) throw new Error(`No nav button found for "${label}"`);
  await user.click(node);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetToken.mockReturnValue("test-token");
  mockGetMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "pro" });
  mockGetPreferences.mockResolvedValue({
    preferred_model: null,
    available_models: [
      { id: "model-one", name: "Model One", description: "desc", tier: "fast" },
    ],
  });
  mockGetCapabilities.mockResolvedValue({ model_catalog: [] });
  mockChangePassword.mockResolvedValue({ message: "ok" });
  mockUpdatePreferences.mockResolvedValue({
    preferred_model: "model-one",
    available_models: [],
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ content: "" }) }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AccountSettings — behavior parity (wired sections preserved)", () => {
  it("invokes the existing loaders on mount", async () => {
    render(<AccountSettings onBack={() => {}} />);
    await waitFor(() => {
      expect(mockGetMe).toHaveBeenCalledWith("test-token");
      expect(mockGetPreferences).toHaveBeenCalledWith("test-token");
      expect(mockGetCapabilities).toHaveBeenCalledWith("test-token");
    });
  });

  it("submitting the password form invokes changePassword (pw>=8 preserved)", async () => {
    const user = userEvent.setup();
    render(<AccountSettings onBack={() => {}} />);
    await waitFor(() => expect(mockGetMe).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/enter current password/i), "oldpassword");
    await user.type(screen.getByPlaceholderText(/at least 8 characters/i), "newpassword1");
    await user.type(screen.getByPlaceholderText(/re-enter new password/i), "newpassword1");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() =>
      expect(mockChangePassword).toHaveBeenCalledWith("test-token", "oldpassword", "newpassword1"),
    );
  });

  it("saving a changed model invokes updatePreferences", async () => {
    const user = userEvent.setup();
    render(<AccountSettings onBack={() => {}} />);
    await waitFor(() => expect(mockGetPreferences).toHaveBeenCalled());

    await clickNav(user, "AI Model");
    const select = await screen.findByRole("combobox");
    await user.selectOptions(select, "model-one");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(mockUpdatePreferences).toHaveBeenCalledWith("test-token", "model-one"),
    );
  });

  it("the constitution section reads /api/settings/constitution", async () => {
    const user = userEvent.setup();
    render(<AccountSettings onBack={() => {}} />);
    await waitFor(() => expect(mockGetMe).toHaveBeenCalled());

    await clickNav(user, "Constitution");
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        `${ENV.API_URL}/api/settings/constitution`,
        expect.objectContaining({ headers: expect.anything() }),
      ),
    );
  });
});

describe("AccountSettings — fiction guard (no unbacked fields; INV-3)", () => {
  it("renders email read-only and NO Full name / Role / Organization inputs", async () => {
    render(<AccountSettings onBack={() => {}} />);
    // Email loads and is shown as a display, not an editable input.
    expect(await screen.findByText("user@example.com")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("user@example.com")).toBeNull();

    // No unbacked profile fields (mock fiction — there is no endpoint).
    expect(screen.queryByLabelText(/full name/i)).toBeNull();
    expect(screen.queryByLabelText(/organization/i)).toBeNull();
    expect(screen.queryByLabelText(/^role$/i)).toBeNull();
    expect(screen.queryByPlaceholderText(/full name/i)).toBeNull();
    expect(screen.queryByPlaceholderText(/organization/i)).toBeNull();
  });
});
