/**
 * AccountSettings — coverage for the Profile, AI Model and Usage & Limits tabs
 * plus the tab strip / back affordance.
 *
 * Complements AccountSettings.render.test.tsx (loader + happy-path parity),
 * AccountSettings.test.tsx (tab labels / live model list) and
 * AccountSettings.password-mismatch.test.tsx. This file owns the error paths,
 * validation branches, tier variants and model-selection state transitions.
 *
 * Boundaries mocked: `@/lib/api` and `next/navigation`. The Constitution tab is
 * covered in AccountSettings.constitution.test.tsx.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

const api = vi.hoisted(() => ({
  getToken: vi.fn(),
  getMe: vi.fn(),
  getPreferences: vi.fn(),
  getCapabilities: vi.fn(),
  changePassword: vi.fn(),
  updatePreferences: vi.fn(),
  getMfaStatus: vi.fn(),
  getConstitution: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  authedFetch: vi.fn(),
  getToken: () => api.getToken(),
  getMe: (t: string) => api.getMe(t),
  getPreferences: (t: string) => api.getPreferences(t),
  getCapabilities: (t: string) => api.getCapabilities(t),
  changePassword: (t: string, c: string, n: string) => api.changePassword(t, c, n),
  updatePreferences: (t: string, m: string | null) => api.updatePreferences(t, m),
  getMfaStatus: (t: string) => api.getMfaStatus(t),
  getConstitution: (t: string) => api.getConstitution(t),
  enableEmailMfa: vi.fn(),
  disableEmailMfa: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

// Stable singleton, matching next/navigation's real identity.
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { AccountSettings, type SettingsSection } from "./AccountSettings";

const MODELS = [
  { id: "fast-1", name: "Fast One", description: "Quick everyday model", tier: "fast" },
  { id: "locked-1", name: "Locked One", description: "Needs a higher plan", tier: "powerful", allowed: false },
  { id: "odd-1", name: "Odd One", description: "Uncategorised model", tier: "experimental" },
];

function renderSettings(props: { initialSection?: SettingsSection; onBack?: () => void } = {}) {
  return renderWithProviders(<AccountSettings onBack={props.onBack ?? (() => {})} initialSection={props.initialSection} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "pro" });
  api.getPreferences.mockResolvedValue({ preferred_model: null, available_models: MODELS });
  api.getCapabilities.mockResolvedValue({
    model_catalog: [
      { id: "fast-1", context_window: 200_000 },
      { id: "odd-1", context_window: 2_000_000 },
    ],
  });
  api.changePassword.mockResolvedValue({ message: "ok" });
  api.updatePreferences.mockResolvedValue({ preferred_model: "fast-1", available_models: [] });
  api.getMfaStatus.mockResolvedValue({
    supported: true,
    enabled: false,
    required: false,
    email_available: true,
    factors: [],
  });
  api.getConstitution.mockResolvedValue({ content: "" });
});

describe("AccountSettings — navigation chrome", () => {
  it("calls onBack when the back button is pressed", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    renderSettings({ onBack });
    await screen.findByText("user@example.com");

    // The back control is an icon-only button with no accessible name (see the
    // evidence notes), so the only semantic handle is its position: first button.
    await user.click(screen.getAllByRole("button")[0]);

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["AI Model", "/settings/ai-model"],
    ["Usage & Limits", "/settings/usage"],
    ["Constitution", "/settings/constitution"],
    ["Security", "/settings/security"],
  ])("selecting the %s tab updates the URL to %s", async (label, route) => {
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText("user@example.com");

    await user.click(screen.getByRole("tab", { name: label }));

    expect(router.replace).toHaveBeenCalledWith(route);
    expect(screen.getByRole("tab", { name: label })).toHaveAttribute("aria-selected", "true");
  });

  it("returns to the Profile tab and URL from another tab", async () => {
    const user = userEvent.setup();
    renderSettings({ initialSection: "limits" });
    await screen.findByText("Deliverable access");

    await user.click(screen.getByRole("tab", { name: "Profile" }));

    expect(router.replace).toHaveBeenCalledWith("/settings/profile");
    expect(await screen.findByLabelText("Current password")).toBeInTheDocument();
  });
});

describe("AccountSettings — loading the account", () => {
  it("does not call any loader when there is no session token", async () => {
    api.getToken.mockReturnValue(null);
    renderSettings();

    // Profile card is on screen but nothing was fetched and no email is shown.
    expect(await screen.findByText("Basic plan")).toBeInTheDocument();
    expect(api.getMe).not.toHaveBeenCalled();
    expect(api.getPreferences).not.toHaveBeenCalled();
    expect(screen.queryByText("user@example.com")).toBeNull();
  });

  it("shows the email and initials derived from it once loaded", async () => {
    renderSettings();

    expect(await screen.findByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByText("US")).toBeInTheDocument();
    expect(screen.getByText("Pro plan")).toBeInTheDocument();
  });

  it("falls back to the Basic plan when the user record has no tier", async () => {
    api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "" });
    renderSettings();

    expect(await screen.findByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByText("Basic plan")).toBeInTheDocument();
  });

  it("stops loading and keeps defaults when the account loaders fail", async () => {
    api.getMe.mockRejectedValue(new Error("down"));
    renderSettings({ initialSection: "model" });

    // The select only renders once loading has finished.
    const select = await screen.findByRole("combobox", { name: "Select model" });
    expect(select).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Fast One/ })).toBeNull();
  });

  it("still loads the account when only the capabilities call fails", async () => {
    api.getCapabilities.mockRejectedValue(new Error("no palette"));
    const user = userEvent.setup();
    renderSettings({ initialSection: "model" });

    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    expect(screen.getByText("Quick everyday model")).toBeInTheDocument();
    // Without the capability catalog there is no context-window chip.
    expect(screen.queryByText(/ctx/)).toBeNull();
  });
});

describe("AccountSettings — change password", () => {
  async function fillPasswords(
    user: ReturnType<typeof userEvent.setup>,
    values: { current?: string; next?: string; confirm?: string },
  ) {
    if (values.current) await user.type(screen.getByLabelText("Current password"), values.current);
    if (values.next) await user.type(screen.getByLabelText("New password"), values.next);
    if (values.confirm) await user.type(screen.getByLabelText("Confirm new password"), values.confirm);
  }

  it("keeps Change Password disabled until all three fields are filled", async () => {
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText("user@example.com");
    const submit = screen.getByRole("button", { name: "Change Password" });

    expect(submit).toBeDisabled();
    await fillPasswords(user, { current: "old-password" });
    expect(submit).toBeDisabled();
    await fillPasswords(user, { next: "new-password-1" });
    expect(submit).toBeDisabled();
    await fillPasswords(user, { confirm: "new-password-1" });
    expect(submit).toBeEnabled();
  });

  it("rejects a new password shorter than 8 characters without calling the API", async () => {
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText("user@example.com");

    await fillPasswords(user, { current: "old-password", next: "short", confirm: "short" });
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(await screen.findByText("New password must be at least 8 characters")).toBeInTheDocument();
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it("clears the validation error as soon as a field is edited", async () => {
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText("user@example.com");
    await fillPasswords(user, { current: "old-password", next: "short", confirm: "short" });
    await user.click(screen.getByRole("button", { name: "Change Password" }));
    await screen.findByText("New password must be at least 8 characters");

    await user.type(screen.getByLabelText("Current password"), "x");

    expect(screen.queryByText("New password must be at least 8 characters")).toBeNull();
  });

  it("reports success and empties all three fields after a successful change", async () => {
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText("user@example.com");

    await fillPasswords(user, { current: "old-password", next: "new-password-1", confirm: "new-password-1" });
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(await screen.findByText("Password changed successfully")).toBeInTheDocument();
    expect(api.changePassword).toHaveBeenCalledWith("tok", "old-password", "new-password-1");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
    expect(screen.getByLabelText("Confirm new password")).toHaveValue("");
  });

  it("shows 'Changing...' and disables the button while the request is pending", async () => {
    const user = userEvent.setup();
    let resolve!: (v: unknown) => void;
    api.changePassword.mockReturnValue(new Promise((r) => (resolve = r)));
    renderSettings();
    await screen.findByText("user@example.com");
    await fillPasswords(user, { current: "old-password", next: "new-password-1", confirm: "new-password-1" });

    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(screen.getByRole("button", { name: "Changing..." })).toBeDisabled();
    await act(async () => resolve({ message: "ok" }));
    expect(await screen.findByText("Password changed successfully")).toBeInTheDocument();
  });

  it("shows the server's error message and keeps the typed values when the change fails", async () => {
    const user = userEvent.setup();
    api.changePassword.mockRejectedValue(new Error("Current password is incorrect"));
    renderSettings();
    await screen.findByText("user@example.com");

    await fillPasswords(user, { current: "old-password", next: "new-password-1", confirm: "new-password-1" });
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(await screen.findByText("Current password is incorrect")).toBeInTheDocument();
    expect(screen.getByLabelText("Current password")).toHaveValue("old-password");
  });

  it("uses generic copy when the failure is not an Error instance", async () => {
    const user = userEvent.setup();
    api.changePassword.mockRejectedValue("nope");
    renderSettings();
    await screen.findByText("user@example.com");

    await fillPasswords(user, { current: "old-password", next: "new-password-1", confirm: "new-password-1" });
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(await screen.findByText("Failed to change password")).toBeInTheDocument();
  });

  it("does nothing when the session token is gone at submit time", async () => {
    const user = userEvent.setup();
    renderSettings();
    await screen.findByText("user@example.com");
    await fillPasswords(user, { current: "old-password", next: "new-password-1", confirm: "new-password-1" });

    api.getToken.mockReturnValue(null);
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(api.changePassword).not.toHaveBeenCalled();
    expect(screen.queryByText("Password changed successfully")).toBeNull();
  });
});

describe("AccountSettings — AI Model tab", () => {
  it("shows a placeholder instead of the selector while preferences are loading", async () => {
    let resolve!: (v: unknown) => void;
    api.getPreferences.mockReturnValue(new Promise((r) => (resolve = r)));
    renderSettings({ initialSection: "model" });

    expect(screen.getByText("Pipeline model")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();

    await act(async () =>
      resolve({ preferred_model: null, available_models: MODELS }),
    );
    expect(await screen.findByRole("combobox", { name: "Select model" })).toBeInTheDocument();
  });

  it("starts on the system default with the default hint and Save disabled", async () => {
    renderSettings({ initialSection: "model" });

    const select = await screen.findByRole("combobox", { name: "Select model" });
    expect(select).toHaveValue("");
    expect(screen.getByText(/Fastest and most cost-efficient/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.queryByText(/Unsaved/)).toBeNull();
  });

  it("marks models the plan cannot use as disabled with a lock", async () => {
    renderSettings({ initialSection: "model" });
    await screen.findByRole("combobox", { name: "Select model" });

    expect(screen.getByRole("option", { name: "🔒 Locked One" })).toBeDisabled();
    expect(screen.getByRole("option", { name: "Fast One" })).toBeEnabled();
  });

  it("shows description, tier and context window (K) for a selected model and flags the change as unsaved", async () => {
    const user = userEvent.setup();
    renderSettings({ initialSection: "model" });

    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    expect(screen.getByText("Quick everyday model")).toBeInTheDocument();
    expect(screen.getByText("fast")).toBeInTheDocument();
    expect(screen.getByText("200K ctx")).toBeInTheDocument();
    expect(screen.getByText(/Unsaved — currently using/)).toHaveTextContent("System Default");
    expect(screen.queryByText(/Fastest and most cost-efficient/)).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("formats context windows of a million tokens or more in M and keeps unknown tiers readable", async () => {
    const user = userEvent.setup();
    renderSettings({ initialSection: "model" });

    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "odd-1");

    expect(screen.getByText("2M ctx")).toBeInTheDocument();
    expect(screen.getByText("experimental")).toBeInTheDocument();
    expect(screen.getByText("Uncategorised model")).toBeInTheDocument();
  });

  it("omits the context chip when the capability catalog has no entry for the model", async () => {
    const user = userEvent.setup();
    api.getCapabilities.mockResolvedValue({ model_catalog: [] });
    renderSettings({ initialSection: "model" });

    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    expect(screen.getByText("Quick everyday model")).toBeInTheDocument();
    expect(screen.queryByText(/ctx/)).toBeNull();
  });

  it("returns to the default hint and a clean state when the system default is re-selected", async () => {
    const user = userEvent.setup();
    renderSettings({ initialSection: "model" });
    const select = await screen.findByRole("combobox", { name: "Select model" });

    await user.selectOptions(select, "fast-1");
    await user.selectOptions(select, "");

    expect(screen.getByText(/Fastest and most cost-efficient/)).toBeInTheDocument();
    expect(screen.queryByText(/Unsaved/)).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("names the saved model in the unsaved notice when the preference is changed away from it", async () => {
    const user = userEvent.setup();
    api.getPreferences.mockResolvedValue({ preferred_model: "fast-1", available_models: MODELS });
    renderSettings({ initialSection: "model" });
    const select = await screen.findByRole("combobox", { name: "Select model" });
    expect(select).toHaveValue("fast-1");
    expect(screen.queryByText(/Unsaved/)).toBeNull();

    await user.selectOptions(select, "");

    expect(screen.getByText(/Unsaved — currently using/)).toHaveTextContent("Fast One");
  });

  it("falls back to the raw id in the unsaved notice when the saved model is no longer offered", async () => {
    const user = userEvent.setup();
    api.getPreferences.mockResolvedValue({ preferred_model: "retired-model", available_models: MODELS });
    renderSettings({ initialSection: "model" });
    const select = await screen.findByRole("combobox", { name: "Select model" });
    // No description block is rendered for a model that is not in the list.
    expect(screen.queryByText("Quick everyday model")).toBeNull();

    await user.selectOptions(select, "fast-1");

    expect(screen.getByText(/Unsaved — currently using/)).toHaveTextContent("retired-model");
  });

  it("saves the chosen model, confirms it and clears the unsaved state", async () => {
    const user = userEvent.setup();
    renderSettings({ initialSection: "model" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Model preference saved")).toBeInTheDocument();
    expect(api.updatePreferences).toHaveBeenCalledWith("tok", "fast-1");
    expect(screen.queryByText(/Unsaved/)).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("saves null when the system default is chosen over a stored preference", async () => {
    const user = userEvent.setup();
    api.getPreferences.mockResolvedValue({ preferred_model: "fast-1", available_models: MODELS });
    renderSettings({ initialSection: "model" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "");

    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.updatePreferences).toHaveBeenCalledWith("tok", null));
  });

  it("shows 'Saving…' and disables Save while the request is pending", async () => {
    const user = userEvent.setup();
    let resolve!: (v: unknown) => void;
    api.updatePreferences.mockReturnValue(new Promise((r) => (resolve = r)));
    renderSettings({ initialSection: "model" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    await act(async () => resolve({}));
    expect(await screen.findByText("Model preference saved")).toBeInTheDocument();
  });

  it("shows the error message and keeps the change unsaved when saving fails", async () => {
    const user = userEvent.setup();
    api.updatePreferences.mockRejectedValue(new Error("Model not permitted for this plan"));
    renderSettings({ initialSection: "model" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Model not permitted for this plan")).toBeInTheDocument();
    expect(screen.getByText(/Unsaved — currently using/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("uses generic copy when the save failure is not an Error instance", async () => {
    const user = userEvent.setup();
    api.updatePreferences.mockRejectedValue("boom");
    renderSettings({ initialSection: "model" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Failed to save preference")).toBeInTheDocument();
  });

  it("clears a previous save error when a different model is chosen", async () => {
    const user = userEvent.setup();
    api.updatePreferences.mockRejectedValue(new Error("Model not permitted for this plan"));
    renderSettings({ initialSection: "model" });
    const select = await screen.findByRole("combobox", { name: "Select model" });
    await user.selectOptions(select, "fast-1");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Model not permitted for this plan");

    await user.selectOptions(select, "odd-1");

    expect(screen.queryByText("Model not permitted for this plan")).toBeNull();
  });

  it("does not call the API when the token is gone at save time", async () => {
    const user = userEvent.setup();
    renderSettings({ initialSection: "model" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Select model" }), "fast-1");

    api.getToken.mockReturnValue(null);
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(api.updatePreferences).not.toHaveBeenCalled();
    expect(screen.queryByText("Model preference saved")).toBeNull();
  });
});

describe("AccountSettings — Usage & Limits tab", () => {
  it("lists the deliverables entitled to a basic plan and no others", async () => {
    api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "basic" });
    renderSettings({ initialSection: "limits" });

    expect(await screen.findByText("Product Requirements")).toBeInTheDocument();
    expect(screen.getByText("Presentation")).toBeInTheDocument();
    expect(screen.queryByText("Interactive Prototype")).toBeNull();
    expect(screen.queryByText("App Builder")).toBeNull();
    expect(screen.getByText("Basic plan")).toBeInTheDocument();
  });

  it("lists every displayable deliverable for an enterprise plan", async () => {
    api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "enterprise" });
    renderSettings({ initialSection: "limits" });

    for (const label of [
      "Product Requirements",
      "Presentation",
      "Interactive Prototype",
      "App Builder",
      "Custom Workflow",
      "Platform Workflows",
      "Mulesoft Migration",
      ".NET Migration",
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
  });

  it("shows the prototype deliverable but not presentations for the hexaware plan", async () => {
    api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "hexaware" });
    renderSettings({ initialSection: "limits" });

    expect(await screen.findByText("Interactive Prototype")).toBeInTheDocument();
    expect(screen.queryByText("Presentation")).toBeNull();
  });

  it("opens the upgrade dialog from 'Manage plan' and closes it again", async () => {
    const user = userEvent.setup();
    api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "basic" });
    renderSettings({ initialSection: "limits" });
    await screen.findByText("Product Requirements");

    await user.click(screen.getByRole("button", { name: "Manage plan" }));
    const dialog = await screen.findByRole("dialog", { name: "Upgrade your plan" });
    expect(dialog).toHaveTextContent("The Pro plan unlocks");

    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the highest-plan dialog for an enterprise account", async () => {
    const user = userEvent.setup();
    api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "enterprise" });
    renderSettings({ initialSection: "limits" });
    await screen.findByText("Custom Workflow");

    await user.click(screen.getByRole("button", { name: "Manage plan" }));

    expect(await screen.findByRole("dialog", { name: "Manage plan" })).toHaveTextContent(
      "Enterprise is the highest plan",
    );
  });
});
