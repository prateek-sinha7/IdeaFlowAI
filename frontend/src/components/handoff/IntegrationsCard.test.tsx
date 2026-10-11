import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const m = vi.hoisted(() => ({
  getToken: vi.fn(),
  getGithubPatStatus: vi.fn(),
  listApiKeys: vi.fn(),
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
  saveGithubPat: vi.fn(),
  deleteGithubPat: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ getToken: m.getToken }));
vi.mock("@/lib/api-handoff", () => ({
  getGithubPatStatus: m.getGithubPatStatus,
  listApiKeys: m.listApiKeys,
  createApiKey: m.createApiKey,
  revokeApiKey: m.revokeApiKey,
  saveGithubPat: m.saveGithubPat,
  deleteGithubPat: m.deleteGithubPat,
}));

import { IntegrationsCard } from "./IntegrationsCard";

const PAT = {
  github_username: "octocat",
  last_4: "abcd",
  scopes: "repo",
};
const KEY = {
  id: "k1",
  name: "Laptop",
  token_prefix: "vai_abc",
  last_used_at: null,
  revoked_at: null,
};

beforeEach(() => {
  Object.values(m).forEach((f) => f.mockReset());
  m.getToken.mockReturnValue("jwt");
  m.getGithubPatStatus.mockResolvedValue(null);
  m.listApiKeys.mockResolvedValue([]);
});

describe("IntegrationsCard loading", () => {
  it("shows empty states when no PAT and no keys exist", async () => {
    render(<IntegrationsCard compact />);
    expect(await screen.findByText(/No API keys yet/)).toBeInTheDocument();
    expect(screen.getByText(/No GitHub token saved yet/)).toBeInTheDocument();
  });

  it("does not call the API when there is no auth token", async () => {
    m.getToken.mockReturnValue(null);
    render(<IntegrationsCard />);
    await screen.findByText(/No API keys yet/);
    expect(m.getGithubPatStatus).not.toHaveBeenCalled();
  });

  it("renders saved PAT and keys including revoked and last-used", async () => {
    m.getGithubPatStatus.mockResolvedValue({ ...PAT, scopes: null, github_username: null });
    m.listApiKeys.mockResolvedValue([
      KEY,
      { ...KEY, id: "k2", name: "Old", revoked_at: "2024-01-01T00:00:00Z", last_used_at: "2024-01-02T00:00:00Z" },
    ]);
    render(<IntegrationsCard />);
    expect(await screen.findByText("unknown")).toBeInTheDocument();
    expect(screen.getByText(/never used/)).toBeInTheDocument();
    expect(screen.getByText(/last used/)).toBeInTheDocument();
    expect(screen.getByText("revoked")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Revoke/ })).toHaveLength(1);
  });

  it("shows scopes when present", async () => {
    m.getGithubPatStatus.mockResolvedValue(PAT);
    render(<IntegrationsCard />);
    expect(await screen.findByText(/scopes: repo/)).toBeInTheDocument();
  });

  it("shows offline notice for TypeError and retries successfully", async () => {
    const user = userEvent.setup();
    m.getGithubPatStatus.mockRejectedValueOnce(new TypeError("fail"));
    render(<IntegrationsCard />);
    expect(await screen.findByText(/check your connection/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByText(/check your connection/)).not.toBeInTheDocument());
  });

  it("shows offline notice for status 0 errors", async () => {
    m.getGithubPatStatus.mockRejectedValueOnce({ status: 0 });
    render(<IntegrationsCard />);
    expect(await screen.findByText(/check your connection/)).toBeInTheDocument();
  });

  it("shows generic load error for other failures", async () => {
    m.getGithubPatStatus.mockRejectedValueOnce(new Error("500"));
    render(<IntegrationsCard />);
    expect(await screen.findByText(/Couldn't load your saved credentials/)).toBeInTheDocument();
  });
});

describe("IntegrationsCard install command", () => {
  it("copies the install command and shows Copied", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: "Copy" }));
    expect(await screen.findByText("Copied")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/^curl -fsSL .*\/install\/flowin-handoff \| bash$/));
  });
});

describe("IntegrationsCard GitHub PAT", () => {
  it("disables save for short tokens and toggles visibility", async () => {
    const user = userEvent.setup();
    render(<IntegrationsCard />);
    const input = await screen.findByLabelText("GitHub personal access token");
    expect(input).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    const toggle = input.parentElement!.querySelector("button")!;
    await user.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    await user.click(toggle);
    expect(input).toHaveAttribute("type", "password");
  });

  it("saves a PAT and shows success message with username", async () => {
    const user = userEvent.setup();
    m.saveGithubPat.mockResolvedValue(PAT);
    render(<IntegrationsCard />);
    await user.type(await screen.findByLabelText("GitHub personal access token"), "github_pat_1234567");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved for octocat")).toBeInTheDocument();
    expect(m.saveGithubPat).toHaveBeenCalledWith("jwt", "github_pat_1234567");
    expect(screen.getByLabelText("GitHub personal access token")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Replace" })).toBeInTheDocument();
  });

  it("falls back to 'unknown user' when username is null", async () => {
    const user = userEvent.setup();
    m.saveGithubPat.mockResolvedValue({ ...PAT, github_username: null });
    render(<IntegrationsCard />);
    await user.type(await screen.findByLabelText("GitHub personal access token"), "github_pat_1234567");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved for unknown user")).toBeInTheDocument();
  });

  it("shows the error message when save fails with Error", async () => {
    const user = userEvent.setup();
    m.saveGithubPat.mockRejectedValue(new Error("bad token"));
    render(<IntegrationsCard />);
    await user.type(await screen.findByLabelText("GitHub personal access token"), "github_pat_1234567");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("bad token")).toBeInTheDocument();
  });

  it("shows fallback error when save rejects with non-Error", async () => {
    const user = userEvent.setup();
    m.saveGithubPat.mockRejectedValue("nope");
    render(<IntegrationsCard />);
    await user.type(await screen.findByLabelText("GitHub personal access token"), "github_pat_1234567");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Failed to save PAT")).toBeInTheDocument();
  });

  it("asks for confirmation and removes the PAT", async () => {
    const user = userEvent.setup();
    m.getGithubPatStatus.mockResolvedValue(PAT);
    m.deleteGithubPat.mockResolvedValue(undefined);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: "Remove" }));
    const dialog = screen.getByRole("dialog", { name: "Remove GitHub token?" });
    expect(m.deleteGithubPat).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(await screen.findByText("PAT removed")).toBeInTheDocument();
    expect(m.deleteGithubPat).toHaveBeenCalledWith("jwt");
    expect(screen.getByText(/No GitHub token saved yet/)).toBeInTheDocument();
  });

  it("keeps the PAT when removal is cancelled via button or backdrop", async () => {
    const user = userEvent.setup();
    m.getGithubPatStatus.mockResolvedValue(PAT);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Keep token" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("dialog"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(m.deleteGithubPat).not.toHaveBeenCalled();
  });

  it.each([
    [new Error("denied"), "denied"],
    ["x", "Failed to delete PAT"],
  ])("shows delete error for %s", async (rejection, text) => {
    const user = userEvent.setup();
    m.getGithubPatStatus.mockResolvedValue(PAT);
    m.deleteGithubPat.mockRejectedValue(rejection);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: "Remove" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }));
    expect(await screen.findByText(text)).toBeInTheDocument();
  });
});

describe("IntegrationsCard API keys", () => {
  const minted = { ...KEY, id: "k9", token: "vai_secret_token" };

  it("creates a key, shows the plaintext, copies it and dismisses", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    m.createApiKey.mockResolvedValue(minted);
    render(<IntegrationsCard />);
    const name = await screen.findByLabelText("API key name");
    await user.clear(name);
    await user.type(name, "  Work  ");
    await user.click(screen.getByRole("button", { name: /Create key/ }));
    expect(await screen.findByText("vai_secret_token")).toBeInTheDocument();
    expect(m.createApiKey).toHaveBeenCalledWith("jwt", "Work");
    expect(name).toHaveValue("Default");
    const banner = screen.getByText("New key — copy now").parentElement!;
    const [copyBtn] = within(banner).getAllByRole("button");
    await user.click(copyBtn);
    expect(await within(banner).findByText("Copied")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith("vai_secret_token");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("vai_secret_token")).not.toBeInTheDocument();
  });

  it("uses 'Default' when the name is blank", async () => {
    const user = userEvent.setup();
    m.createApiKey.mockResolvedValue(minted);
    render(<IntegrationsCard />);
    const name = await screen.findByLabelText("API key name");
    await user.clear(name);
    await user.click(screen.getByRole("button", { name: /Create key/ }));
    await screen.findByText("vai_secret_token");
    expect(m.createApiKey).toHaveBeenCalledWith("jwt", "Default");
  });

  it.each([
    [new Error("quota"), "quota"],
    [1, "Failed to create key"],
  ])("shows create error for %s", async (rejection, text) => {
    const user = userEvent.setup();
    m.createApiKey.mockRejectedValue(rejection);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: /Create key/ }));
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("confirms then revokes a key and refreshes", async () => {
    const user = userEvent.setup();
    m.listApiKeys.mockResolvedValue([KEY]);
    m.revokeApiKey.mockResolvedValue(undefined);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: /Revoke/ }));
    const dialog = screen.getByRole("dialog", { name: "Revoke this API key?" });
    await user.click(within(dialog).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(m.revokeApiKey).toHaveBeenCalledWith("jwt", "k1"));
    await waitFor(() => expect(m.listApiKeys).toHaveBeenCalledTimes(2));
  });

  it("does not revoke when cancelled via button or backdrop", async () => {
    const user = userEvent.setup();
    m.listApiKeys.mockResolvedValue([KEY]);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: /Revoke/ }));
    await user.click(screen.getByRole("button", { name: "Keep key" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Revoke/ }));
    await user.click(screen.getByRole("dialog"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(m.revokeApiKey).not.toHaveBeenCalled();
  });

  it.each([
    [new Error("locked"), "locked"],
    [null, "Failed to revoke key"],
  ])("shows revoke error for %s", async (rejection, text) => {
    const user = userEvent.setup();
    m.listApiKeys.mockResolvedValue([KEY]);
    m.revokeApiKey.mockRejectedValue(rejection);
    render(<IntegrationsCard />);
    await user.click(await screen.findByRole("button", { name: /Revoke/ }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Revoke" }));
    expect(await screen.findByText(text)).toBeInTheDocument();
  });
});
