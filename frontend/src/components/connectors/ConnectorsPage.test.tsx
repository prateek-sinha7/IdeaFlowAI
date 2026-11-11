import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { buildConnectedConnector, buildConnector } from "@/test/connectorFixtures";
import type { ConnectorSummary } from "@/types/connectors";
import { ConnectorsPage } from "./ConnectorsPage";

const { list, authorize, disconnect, replace, nav } = vi.hoisted(() => ({
  list: vi.fn(),
  authorize: vi.fn(),
  disconnect: vi.fn(),
  replace: vi.fn(),
  nav: { search: new URLSearchParams() },
}));

// Boundaries only: the API client, the auth token and Next navigation. The hooks run for real.
vi.mock("@/store/api/connectors", () => ({ connectorsApi: { list, authorize, disconnect } }));
vi.mock("@/lib/api", () => ({ getToken: () => "test-token" }));
vi.mock("next/navigation", () => {
  const router = { replace };
  return { useRouter: () => router, useSearchParams: () => nav.search };
});

const AUTH_URL = "https://github.com/login/oauth/authorize?state=abc";

const jira = buildConnector({
  key: "jira",
  display_name: "Jira",
  description: "Search and update Jira issues.",
  status: "not_configured",
  requested_scopes: ["read:jira-work"],
});
const github = buildConnector();

/** BroadcastChannel stand-in: the test delivers the landing page's message by hand. */
class FakeChannel {
  static instances: FakeChannel[] = [];
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  constructor(public name: string) {
    FakeChannel.instances.push(this);
  }
  close() {}
  receive(data: unknown) {
    this.onmessage?.({ data } as MessageEvent<unknown>);
  }
}

function fakePopup() {
  return { opener: "original" as unknown, location: { href: "about:blank" }, close: vi.fn() };
}

function listReturns(connectors: ConnectorSummary[]) {
  list.mockResolvedValue({ connectors });
}

async function renderPage(onBack = vi.fn()) {
  render(<ConnectorsPage onBack={onBack} />);
  return { onBack };
}

describe("ConnectorsPage", () => {
  let popup: ReturnType<typeof fakePopup>;
  let openSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    nav.search = new URLSearchParams();
    (globalThis as unknown as { __r?: string[] }).__r = [];
    FakeChannel.instances = [];
    vi.stubGlobal("BroadcastChannel", FakeChannel);
    popup = fakePopup();
    openSpy = vi.fn(() => popup);
    vi.stubGlobal("open", openSpy);
    list.mockReset();
    authorize.mockReset();
    authorize.mockResolvedValue({ authorization_url: AUTH_URL, expires_at: "2099-01-01T00:00:00Z" });
    disconnect.mockReset();
    replace.mockReset();
    listReturns([github, jira]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("states", () => {
    it("shows a loading status while the list is being read", async () => {
      list.mockReturnValue(new Promise(() => {}));
      await renderPage();
      expect(screen.getByText("Loading connectors")).toBeInTheDocument();
      expect(screen.queryByRole("article")).not.toBeInTheDocument();
    });

    it("shows a card for each connector with its status", async () => {
      await renderPage();
      const githubCard = await screen.findByRole("article", { name: "GitHub" });
      const jiraCard = screen.getByRole("article", { name: "Jira" });
      expect(within(githubCard).getByText("Not connected")).toBeInTheDocument();
      expect(within(jiraCard).getByText("Not configured")).toBeInTheDocument();
      expect(within(jiraCard).getByRole("button", { name: "Connect Jira" })).toBeDisabled();
    });

    it("shows the empty message when no connector is available", async () => {
      listReturns([]);
      await renderPage();
      expect(await screen.findByText("No connectors are available.")).toBeInTheDocument();
    });

    it("shows the error with a Retry button that loads the list", async () => {
      const user = userEvent.setup();
      list.mockRejectedValueOnce(new Error("Backend is down"));
      await renderPage();
      expect(await screen.findByRole("alert")).toHaveTextContent("Backend is down");
      await user.click(screen.getByRole("button", { name: "Retry" }));
      expect(await screen.findByRole("article", { name: "GitHub" })).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("calls onBack from the Back button", async () => {
      const user = userEvent.setup();
      const { onBack } = await renderPage();
      await screen.findByRole("article", { name: "GitHub" });
      await user.click(screen.getByRole("button", { name: "Back" }));
      expect(onBack).toHaveBeenCalledOnce();
    });
  });

  describe("connecting", () => {
    it("opens the popup in the click, navigates it to the https URL and shows Cancel", async () => {
      const user = userEvent.setup();
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Connect GitHub" }));

      expect(openSpy).toHaveBeenCalledWith("", "flowin-connect-github", "popup,width=600,height=720");
      await waitFor(() => expect(popup.location.href).toBe(AUTH_URL));
      expect(popup.opener).toBeNull();
      expect(authorize).toHaveBeenCalledWith("github");
      expect(await screen.findByRole("button", { name: "Cancel sign-in to GitHub" })).toBeInTheDocument();
    });

    it("announces a cancelled sign-in and closes the popup", async () => {
      const user = userEvent.setup();
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Connect GitHub" }));
      await user.click(await screen.findByRole("button", { name: "Cancel sign-in to GitHub" }));

      expect(popup.close).toHaveBeenCalled();
      expect(await screen.findByText("Sign-in to GitHub was cancelled.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Connect GitHub" })).toBeInTheDocument();
    });

    it("refuses a non-https authorization URL and shows an error", async () => {
      const user = userEvent.setup();
      authorize.mockResolvedValue({ authorization_url: "http://github.com/login", expires_at: "2099-01-01T00:00:00Z" });
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Connect GitHub" }));

      expect(await screen.findByText("The sign-in address was not secure, so it was not opened.")).toBeInTheDocument();
      expect(popup.location.href).toBe("about:blank");
      expect(popup.close).toHaveBeenCalled();
    });

    it("shows the server's message when the authorization request fails", async () => {
      const user = userEvent.setup();
      authorize.mockRejectedValue(new Error("GitHub is not configured"));
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Connect GitHub" }));
      expect(await screen.findByText("GitHub is not configured")).toBeInTheDocument();
    });

    it("offers Continue in this tab when the browser blocks the popup", async () => {
      const user = userEvent.setup();
      const assign = vi.fn();
      vi.stubGlobal("location", { assign });
      openSpy.mockReturnValue(null);
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Connect GitHub" }));

      expect(await screen.findByText("Your browser blocked the sign-in window.")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Continue in this tab" }));
      expect(assign).toHaveBeenCalledExactlyOnceWith(AUTH_URL);
    });

    it("shows the connected banner and the account when the landing page reports success", async () => {
      const user = userEvent.setup();
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Connect GitHub" }));
      await screen.findByRole("button", { name: "Cancel sign-in to GitHub" });

      listReturns([buildConnectedConnector(), jira]);
      await act(async () => {
        FakeChannel.instances[0].receive({
          type: "oauth-complete",
          connector: "github",
          result: "connected",
          reason: null,
        });
      });

      expect(await screen.findByText("GitHub is connected.")).toBeInTheDocument();
      expect(screen.getByText("Connected as Jane Doe (jane)")).toBeInTheDocument();
    });

    it("shows the reason when the landing page reports an error", async () => {
      const user = userEvent.setup();
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Connect GitHub" }));
      await screen.findByRole("button", { name: "Cancel sign-in to GitHub" });

      await act(async () => {
        FakeChannel.instances[0].receive({
          type: "oauth-complete",
          connector: "github",
          result: "error",
          reason: "access_denied",
        });
      });

      expect(await screen.findByText("Access was declined, so nothing was connected.")).toBeInTheDocument();
    });
  });

  describe("result banner", () => {
    it("lives in a polite status region that exists before any message", async () => {
      await renderPage();
      await screen.findByRole("article", { name: "GitHub" });
      const regions = screen.getAllByRole("status");
      expect(regions.some((el) => el.getAttribute("aria-live") === "polite")).toBe(true);
    });

    it("is dismissed by the Dismiss button", async () => {
      const user = userEvent.setup();
      nav.search = new URLSearchParams("connector=github&result=error&reason=access_denied");
      await renderPage();
      expect(await screen.findByText("Access was declined, so nothing was connected.")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Dismiss" }));
      expect(screen.queryByText("Access was declined, so nothing was connected.")).not.toBeInTheDocument();
    });
  });

  describe("same-tab landing hint", () => {
    it("shows an error hint from the address and removes it from the URL", async () => {
      nav.search = new URLSearchParams("connector=github&result=error&reason=invalid_state");
      await renderPage();
      expect(
        await screen.findByText("The sign-in link expired or was already used. Try connecting again."),
      ).toBeInTheDocument();
      expect(replace).toHaveBeenCalledExactlyOnceWith("/connectors");
    });

    it("shows a generic error for an unknown reason", async () => {
      nav.search = new URLSearchParams("connector=github&result=error&reason=<script>");
      await renderPage();
      expect(await screen.findByText("Could not connect GitHub. Try again.")).toBeInTheDocument();
    });

    it("shows a success hint only when the server list agrees", async () => {
      nav.search = new URLSearchParams("connector=github&result=connected");
      listReturns([buildConnectedConnector(), jira]);
      await renderPage();
      expect(await screen.findByText("GitHub is connected.")).toBeInTheDocument();
    });

    it("ignores a success hint that the server list contradicts", async () => {
      nav.search = new URLSearchParams("connector=github&result=connected");
      await renderPage();
      await screen.findByRole("article", { name: "GitHub" });
      expect(screen.queryByText("GitHub is connected.")).not.toBeInTheDocument();
    });

    it("ignores a hint for an invalid connector key and leaves the URL alone", async () => {
      nav.search = new URLSearchParams("connector=GitHub%20Evil&result=error&reason=access_denied");
      await renderPage();
      await screen.findByRole("article", { name: "GitHub" });
      expect(screen.queryByText("Access was declined, so nothing was connected.")).not.toBeInTheDocument();
      expect(replace).not.toHaveBeenCalled();
    });

    it("does not touch the URL when there is no hint", async () => {
      await renderPage();
      await screen.findByRole("article", { name: "GitHub" });
      expect(replace).not.toHaveBeenCalled();
    });
  });

  describe("disconnecting", () => {
    beforeEach(() => {
      listReturns([buildConnectedConnector(), jira]);
    });

    it("confirms in a dialog, disconnects, shows the revoke result and refreshes the card", async () => {
      const user = userEvent.setup();
      disconnect.mockResolvedValue({ status: "disconnected", provider_revocation: "revoked" });
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Disconnect GitHub" }));

      listReturns([github, jira]);
      const dialog = await screen.findByRole("dialog", { name: "Disconnect GitHub?" });
      await user.click(within(dialog).getByRole("button", { name: "Disconnect" }));

      expect(disconnect).toHaveBeenCalledExactlyOnceWith("github");
      expect(await within(dialog).findByRole("status")).toHaveTextContent("revoked at the provider");
      await user.click(within(dialog).getByRole("button", { name: "Close" }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      const card = screen.getByRole("article", { name: "GitHub" });
      expect(within(card).getByText("Not connected")).toBeInTheDocument();
    });

    it("keeps the connection and disconnects nothing when the dialog is cancelled", async () => {
      const user = userEvent.setup();
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Disconnect GitHub" }));
      await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(disconnect).not.toHaveBeenCalled();
      expect(screen.getByText("Connected as Jane Doe (jane)")).toBeInTheDocument();
    });

    it("shows an error in the dialog when the disconnect fails", async () => {
      const user = userEvent.setup();
      disconnect.mockRejectedValue(new Error("Server error"));
      await renderPage();
      await user.click(await screen.findByRole("button", { name: "Disconnect GitHub" }));
      const dialog = await screen.findByRole("dialog");
      await user.click(within(dialog).getByRole("button", { name: "Disconnect" }));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent("Could not disconnect GitHub. Try again.");
      expect(screen.getByText("Connected as Jane Doe (jane)")).toBeInTheDocument();
    });
  });
});
