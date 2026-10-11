/**
 * AccountSettings — Constitution tab (FR-012) and the unsaved-changes guard
 * (ISS-482 / ISS-622) that protects it when switching tabs.
 *
 * Boundaries mocked: `@/lib/api` (token, constitution GET, authed PUT/DELETE)
 * and `next/navigation`. The editor, dialogs and dirty-tracking run for real.
 */

import { StrictMode } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const api = vi.hoisted(() => ({
  getToken: vi.fn(),
  getMe: vi.fn(),
  getPreferences: vi.fn(),
  getCapabilities: vi.fn(),
  getConstitution: vi.fn(),
  authedFetch: vi.fn(),
  getMfaStatus: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  authedFetch: (url: string, init?: RequestInit) => api.authedFetch(url, init),
  getToken: () => api.getToken(),
  getMe: (t: string) => api.getMe(t),
  getPreferences: (t: string) => api.getPreferences(t),
  getCapabilities: (t: string) => api.getCapabilities(t),
  getConstitution: (t: string) => api.getConstitution(t),
  getMfaStatus: (t: string) => api.getMfaStatus(t),
  changePassword: vi.fn(),
  updatePreferences: vi.fn(),
  enableEmailMfa: vi.fn(),
  disableEmailMfa: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { AccountSettings } from "./AccountSettings";

const CONSTITUTION_URL = /\/api\/settings\/constitution$/;

function renderConstitution() {
  return render(<AccountSettings onBack={() => {}} initialSection="constitution" />);
}

function okResponse(ok = true) {
  return { ok } as Response;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ id: "u1", email: "user@example.com", tier: "pro" });
  api.getPreferences.mockResolvedValue({ preferred_model: null, available_models: [] });
  api.getCapabilities.mockResolvedValue({ model_catalog: [] });
  api.getConstitution.mockResolvedValue({ content: "" });
  api.authedFetch.mockResolvedValue(okResponse());
  api.getMfaStatus.mockResolvedValue({
    supported: true,
    enabled: false,
    required: false,
    email_available: true,
    factors: [],
  });
});

describe("AccountSettings — constitution loading", () => {
  it("loads the saved constitution into the editor and shows its length", async () => {
    api.getConstitution.mockResolvedValue({ content: "Be concise." });
    renderConstitution();

    expect(await screen.findByRole("textbox", { name: "Constitution content" })).toHaveValue("Be concise.");
    expect(screen.getByText("11 / 4000 chars")).toBeInTheDocument();
    expect(api.getConstitution).toHaveBeenCalledWith("tok");
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
  });

  it("starts empty with Save disabled and no Clear button when nothing is saved", async () => {
    renderConstitution();

    expect(await screen.findByRole("textbox", { name: "Constitution content" })).toHaveValue("");
    expect(screen.getByText("0 / 4000 chars")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save constitution" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();
  });

  it("treats a null content field as an empty constitution", async () => {
    api.getConstitution.mockResolvedValue({ content: null });
    renderConstitution();

    expect(await screen.findByRole("textbox", { name: "Constitution content" })).toHaveValue("");
  });

  it("shows an editable empty editor when the load fails", async () => {
    const user = userEvent.setup();
    api.getConstitution.mockRejectedValue(new Error("500"));
    renderConstitution();

    const editor = await screen.findByRole("textbox", { name: "Constitution content" });
    await user.type(editor, "Mine");

    expect(editor).toHaveValue("Mine");
  });

  it("skips the request and shows the editor when there is no session token", async () => {
    api.getToken.mockReturnValue(null);
    renderConstitution();

    expect(await screen.findByRole("textbox", { name: "Constitution content" })).toHaveValue("");
    expect(api.getConstitution).not.toHaveBeenCalled();
  });

  it("limits the editor to 4000 characters", async () => {
    renderConstitution();

    expect(await screen.findByRole("textbox", { name: "Constitution content" })).toHaveAttribute(
      "maxlength",
      "4000",
    );
  });

  it("does not let a late duplicate response overwrite what the user is typing (ISS-581)", async () => {
    const user = userEvent.setup();
    let resolveSecond!: (v: { content: string }) => void;
    // StrictMode runs the mount effect twice; the second GET resolves late.
    api.getConstitution
      .mockResolvedValueOnce({ content: "" })
      .mockReturnValueOnce(new Promise((r) => (resolveSecond = r)));
    render(
      <StrictMode>
        <AccountSettings onBack={() => {}} initialSection="constitution" />
      </StrictMode>,
    );
    const editor = await screen.findByRole("textbox", { name: "Constitution content" });

    await user.type(editor, "my draft");
    await act(async () => resolveSecond({ content: "stale server copy" }));

    expect(screen.getByRole("textbox", { name: "Constitution content" })).toHaveValue("my draft");
  });
});

describe("AccountSettings — saving the constitution", () => {
  it("only enables Save for non-blank content", async () => {
    const user = userEvent.setup();
    renderConstitution();
    const editor = await screen.findByRole("textbox", { name: "Constitution content" });
    const save = screen.getByRole("button", { name: "Save constitution" });

    await user.type(editor, "   ");
    expect(save).toBeDisabled();

    await user.type(editor, "rule");
    expect(save).toBeEnabled();
  });

  it("PUTs the trimmed content with auth and confirms the save", async () => {
    const user = userEvent.setup();
    renderConstitution();
    await user.type(await screen.findByRole("textbox", { name: "Constitution content" }), "  Be kind.  ");

    await user.click(screen.getByRole("button", { name: "Save constitution" }));

    expect(await screen.findByText(/Constitution saved — active on all future runs\./)).toBeInTheDocument();
    expect(api.authedFetch).toHaveBeenCalledTimes(1);
    const [url, init] = api.authedFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(CONSTITUTION_URL);
    expect(init.method).toBe("PUT");
    expect(init.headers).toMatchObject({ Authorization: "Bearer tok", "Content-Type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({ content: "Be kind." });
  });

  it("shows 'Saving…' and disables Save while the request is pending", async () => {
    const user = userEvent.setup();
    let resolve!: (v: Response) => void;
    api.authedFetch.mockReturnValue(new Promise((r) => (resolve = r)));
    renderConstitution();
    await user.type(await screen.findByRole("textbox", { name: "Constitution content" }), "rule");

    await user.click(screen.getByRole("button", { name: "Save constitution" }));

    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    await act(async () => resolve(okResponse()));
    expect(await screen.findByText(/Constitution saved/)).toBeInTheDocument();
  });

  it("shows a failure message when the server rejects the save", async () => {
    const user = userEvent.setup();
    api.authedFetch.mockResolvedValue(okResponse(false));
    renderConstitution();
    await user.type(await screen.findByRole("textbox", { name: "Constitution content" }), "rule");

    await user.click(screen.getByRole("button", { name: "Save constitution" }));

    expect(await screen.findByText(/Failed to save\. Please try again\./)).toBeInTheDocument();
    expect(screen.queryByText(/Constitution saved/)).toBeNull();
  });

  it("shows a failure message when the request itself throws", async () => {
    const user = userEvent.setup();
    api.authedFetch.mockRejectedValue(new Error("offline"));
    renderConstitution();
    await user.type(await screen.findByRole("textbox", { name: "Constitution content" }), "rule");

    await user.click(screen.getByRole("button", { name: "Save constitution" }));

    expect(await screen.findByText(/Failed to save\. Please try again\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save constitution" })).toBeEnabled();
  });

  it("clears the status banner when the user edits again", async () => {
    const user = userEvent.setup();
    renderConstitution();
    const editor = await screen.findByRole("textbox", { name: "Constitution content" });
    await user.type(editor, "rule");
    await user.click(screen.getByRole("button", { name: "Save constitution" }));
    await screen.findByText(/Constitution saved/);

    await user.type(editor, "s");

    expect(screen.queryByText(/Constitution saved/)).toBeNull();
  });

  it("does not send a request when the token is gone at save time", async () => {
    const user = userEvent.setup();
    renderConstitution();
    await user.type(await screen.findByRole("textbox", { name: "Constitution content" }), "rule");

    api.getToken.mockReturnValue(null);
    await user.click(screen.getByRole("button", { name: "Save constitution" }));

    expect(api.authedFetch).not.toHaveBeenCalled();
    expect(screen.queryByText(/Constitution saved/)).toBeNull();
  });
});

describe("AccountSettings — clearing the constitution", () => {
  beforeEach(() => {
    api.getConstitution.mockResolvedValue({ content: "Existing rules" });
  });

  async function openClearDialog(user: ReturnType<typeof userEvent.setup>) {
    renderConstitution();
    await screen.findByDisplayValue("Existing rules");
    await user.click(screen.getByRole("button", { name: "Clear" }));
    return screen.findByRole("dialog", { name: "Clear your constitution?" });
  }

  it("asks for confirmation before deleting and sends nothing yet", async () => {
    const user = userEvent.setup();

    const dialog = await openClearDialog(user);

    expect(dialog).toHaveTextContent(/permanently deletes the saved instructions/);
    expect(api.authedFetch).not.toHaveBeenCalled();
  });

  it("keeps the constitution when the user chooses 'Keep constitution'", async () => {
    const user = userEvent.setup();
    const dialog = await openClearDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Keep constitution" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("textbox", { name: "Constitution content" })).toHaveValue("Existing rules");
    expect(api.authedFetch).not.toHaveBeenCalled();
  });

  it("dismisses the dialog when the backdrop is clicked but not when its body is", async () => {
    const user = userEvent.setup();
    const dialog = await openClearDialog(user);

    await user.click(within(dialog).getByRole("heading", { name: "Clear your constitution?" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(dialog);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.authedFetch).not.toHaveBeenCalled();
  });

  it("DELETEs with auth, empties the editor and reports that it was cleared", async () => {
    const user = userEvent.setup();
    const dialog = await openClearDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Clear" }));

    expect(await screen.findByText("Constitution cleared.")).toBeInTheDocument();
    const [url, init] = api.authedFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(CONSTITUTION_URL);
    expect(init.method).toBe("DELETE");
    expect(init.headers).toMatchObject({ Authorization: "Bearer tok" });
    expect(screen.getByRole("textbox", { name: "Constitution content" })).toHaveValue("");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();
  });

  it("shows 'Clearing…' while the delete is pending", async () => {
    const user = userEvent.setup();
    let resolve!: (v: Response) => void;
    api.authedFetch.mockReturnValue(new Promise((r) => (resolve = r)));
    const dialog = await openClearDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Clear" }));

    expect(screen.getByRole("button", { name: "Clearing…" })).toBeDisabled();
    await act(async () => resolve(okResponse()));
    expect(await screen.findByText("Constitution cleared.")).toBeInTheDocument();
  });

  it("keeps the content and shows an error when the server refuses the delete", async () => {
    const user = userEvent.setup();
    api.authedFetch.mockResolvedValue(okResponse(false));
    const dialog = await openClearDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Clear" }));

    expect(await screen.findByText(/Failed to save\. Please try again\./)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Constitution content" })).toHaveValue("Existing rules");
  });

  it("keeps the content and shows an error when the delete request throws", async () => {
    const user = userEvent.setup();
    api.authedFetch.mockRejectedValue(new Error("offline"));
    const dialog = await openClearDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Clear" }));

    expect(await screen.findByText(/Failed to save\. Please try again\./)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Constitution content" })).toHaveValue("Existing rules");
  });

  it("closes the dialog without a request when the token is gone at confirm time", async () => {
    const user = userEvent.setup();
    const dialog = await openClearDialog(user);

    api.getToken.mockReturnValue(null);
    await user.click(within(dialog).getByRole("button", { name: "Clear" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.authedFetch).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Constitution content" })).toHaveValue("Existing rules");
  });
});

describe("AccountSettings — unsaved constitution guard on tab switch", () => {
  beforeEach(() => {
    api.getConstitution.mockResolvedValue({ content: "Saved rules" });
  });

  async function makeDirty(user: ReturnType<typeof userEvent.setup>) {
    renderConstitution();
    const editor = await screen.findByDisplayValue("Saved rules");
    await user.type(editor, " plus edits");
    return editor;
  }

  it("switches tabs immediately when the draft matches what was loaded", async () => {
    const user = userEvent.setup();
    renderConstitution();
    await screen.findByDisplayValue("Saved rules");

    await user.click(screen.getByRole("tab", { name: "Profile" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.replace).toHaveBeenCalledWith("/settings/profile");
  });

  it("asks before leaving with unsaved edits and does not navigate yet", async () => {
    const user = userEvent.setup();
    await makeDirty(user);

    await user.click(screen.getByRole("tab", { name: "Profile" }));

    expect(await screen.findByRole("dialog", { name: "Discard unsaved changes?" })).toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("stays on the Constitution tab with the draft intact when the user keeps editing", async () => {
    const user = userEvent.setup();
    await makeDirty(user);
    await user.click(screen.getByRole("tab", { name: "Profile" }));
    const dialog = await screen.findByRole("dialog", { name: "Discard unsaved changes?" });

    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Constitution content" })).toHaveValue("Saved rules plus edits");
  });

  it("stays put when the backdrop of the discard dialog is clicked", async () => {
    const user = userEvent.setup();
    await makeDirty(user);
    await user.click(screen.getByRole("tab", { name: "Profile" }));
    const dialog = await screen.findByRole("dialog", { name: "Discard unsaved changes?" });

    await user.click(dialog);

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("leaves for the requested tab and updates the URL when the user discards", async () => {
    const user = userEvent.setup();
    await makeDirty(user);
    await user.click(screen.getByRole("tab", { name: "AI Model" }));
    const dialog = await screen.findByRole("dialog", { name: "Discard unsaved changes?" });

    await user.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(router.replace).toHaveBeenCalledWith("/settings/ai-model");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByRole("combobox", { name: "Select model" })).toBeInTheDocument();
  });

  it("does not prompt after the edits have been saved", async () => {
    const user = userEvent.setup();
    await makeDirty(user);
    await user.click(screen.getByRole("button", { name: "Save constitution" }));
    await screen.findByText(/Constitution saved/);

    await user.click(screen.getByRole("tab", { name: "Profile" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.replace).toHaveBeenCalledWith("/settings/profile");
  });

  it("does not prompt after the constitution has been cleared", async () => {
    const user = userEvent.setup();
    renderConstitution();
    await screen.findByDisplayValue("Saved rules");
    await user.click(screen.getByRole("button", { name: "Clear" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Clear" }));
    await screen.findByText("Constitution cleared.");

    await user.click(screen.getByRole("tab", { name: "Usage & Limits" }));

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/settings/usage"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
