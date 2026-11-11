import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { buildConnectedConnector, buildConnector } from "@/test/connectorFixtures";
import type { ConnectorPending } from "@/hooks/useConnectorAuthorization";
import type { ConnectorSummary } from "@/types/connectors";
import { ConnectorCard } from "./ConnectorCard";

function setup(connector: ConnectorSummary, pending: ConnectorPending = "idle") {
  const handlers = {
    onConnect: vi.fn(),
    onReconnect: vi.fn(),
    onDisconnect: vi.fn(),
    onCancel: vi.fn(),
  };
  render(<ConnectorCard connector={connector} pending={pending} {...handlers} />);
  return handlers;
}

describe("ConnectorCard", () => {
  describe("not connected", () => {
    it("shows the description, the requested scopes and a Connect button", () => {
      setup(buildConnector({ requested_scopes: ["repo", "read:user"] }));
      const card = screen.getByRole("article", { name: "GitHub" });
      expect(within(card).getByText("Not connected")).toBeInTheDocument();
      expect(within(card).getByText("Read and change repositories, issues and pull requests.")).toBeInTheDocument();
      expect(within(card).getByText("repo")).toBeInTheDocument();
      expect(within(card).getByText("read:user")).toBeInTheDocument();
      expect(within(card).getByRole("button", { name: "Connect GitHub" })).toBeEnabled();
      expect(within(card).queryByRole("button", { name: /Disconnect|Reconnect/ })).not.toBeInTheDocument();
    });

    it("passes the connector to onConnect when Connect is clicked", async () => {
      const user = userEvent.setup();
      const connector = buildConnector();
      const { onConnect } = setup(connector);
      await user.click(screen.getByRole("button", { name: "Connect GitHub" }));
      expect(onConnect).toHaveBeenCalledExactlyOnceWith(connector);
    });
  });

  describe("not configured", () => {
    it("explains it and disables Connect", async () => {
      const user = userEvent.setup();
      const { onConnect } = setup(buildConnector({ status: "not_configured" }));
      expect(screen.getByText("Not configured")).toBeInTheDocument();
      expect(screen.getByText("GitHub is not configured on this server.")).toBeInTheDocument();
      const connect = screen.getByRole("button", { name: "Connect GitHub" });
      expect(connect).toBeDisabled();
      await user.click(connect);
      expect(onConnect).not.toHaveBeenCalled();
    });
  });

  describe("connected", () => {
    it("shows the account, the Jira sites, the granted scopes and the connected date", () => {
      setup(
        buildConnectedConnector({
          key: "jira",
          display_name: "Jira",
          sites: [
            { id: "s1", name: "Acme Cloud", url: "https://acme.example.test" },
            { id: "s2", name: "Beta Cloud", url: "https://beta.example.test" },
          ],
          granted_scopes: ["read:jira-work", "write:jira-work"],
        }),
      );
      const card = screen.getByRole("article", { name: "Jira" });
      expect(within(card).getByText("Connected as Jane Doe (jane)")).toBeInTheDocument();
      expect(within(card).getByText("Acme Cloud")).toBeInTheDocument();
      expect(within(card).getByText("Beta Cloud")).toBeInTheDocument();
      expect(within(card).getByText("read:jira-work")).toBeInTheDocument();
      expect(within(card).getByText("write:jira-work")).toBeInTheDocument();
      expect(within(card).getByText(/^Connected on Sep \d{1,2}, 2026$/)).toBeInTheDocument();
    });

    it("omits the Sites section when there are no sites", () => {
      setup(buildConnectedConnector({ sites: [] }));
      expect(screen.queryByText("Sites")).not.toBeInTheDocument();
    });

    it("offers Reconnect and Disconnect, not Connect", () => {
      setup(buildConnectedConnector());
      expect(screen.getByRole("button", { name: "Reconnect GitHub" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Disconnect GitHub" })).toBeEnabled();
      expect(screen.queryByRole("button", { name: "Connect GitHub" })).not.toBeInTheDocument();
    });

    it("passes the connector to onReconnect and onDisconnect", async () => {
      const user = userEvent.setup();
      const connector = buildConnectedConnector();
      const { onReconnect, onDisconnect } = setup(connector);
      await user.click(screen.getByRole("button", { name: "Reconnect GitHub" }));
      await user.click(screen.getByRole("button", { name: "Disconnect GitHub" }));
      expect(onReconnect).toHaveBeenCalledExactlyOnceWith(connector);
      expect(onDisconnect).toHaveBeenCalledExactlyOnceWith(connector);
    });

    it("renders provider text as plain text, never as markup", () => {
      setup(buildConnectedConnector({ account: { id: "1", display_name: "<img src=x onerror=alert(1)>", login: null } }));
      expect(screen.getByText("Connected as <img src=x onerror=alert(1)>")).toBeInTheDocument();
      expect(document.querySelector("img")).toBeNull();
    });
  });

  describe("expired", () => {
    it("tells the user to reconnect and offers Reconnect and Disconnect", () => {
      setup(buildConnectedConnector({ status: "expired" }));
      expect(screen.getByText("Expired")).toBeInTheDocument();
      expect(
        screen.getByText("Your GitHub connection expired. Reconnect to keep using its tools."),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Reconnect GitHub" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Disconnect GitHub" })).toBeEnabled();
    });
  });

  describe("authorizing", () => {
    it("shows a waiting message and only Cancel, which calls onCancel", async () => {
      const user = userEvent.setup();
      const connector = buildConnector();
      const { onCancel } = setup(connector, { kind: "authorizing", deadline: 1 });
      expect(screen.getByRole("status")).toHaveTextContent(
        "Waiting for you to finish signing in to GitHub in the pop-up window.",
      );
      expect(screen.queryByRole("button", { name: "Connect GitHub" })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Cancel sign-in to GitHub" }));
      expect(onCancel).toHaveBeenCalledExactlyOnceWith(connector);
    });

    it("shows Cancel and hides Disconnect when reconnecting a connected connector", () => {
      setup(buildConnectedConnector(), { kind: "authorizing", deadline: 1 });
      expect(screen.getByRole("button", { name: "Cancel sign-in to GitHub" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Disconnect GitHub" })).not.toBeInTheDocument();
    });
  });

  describe("disconnecting", () => {
    it("announces it and disables the actions", () => {
      setup(buildConnectedConnector(), { kind: "disconnecting" });
      expect(screen.getByRole("status")).toHaveTextContent("Disconnecting GitHub…");
      expect(screen.getByRole("button", { name: "Reconnect GitHub" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Disconnect GitHub" })).toBeDisabled();
    });
  });

  describe("documentation link", () => {
    it("opens an https docs URL in a new tab without opener access", () => {
      setup(buildConnector({ docs_url: "https://docs.example.test/github" }));
      const link = screen.getByRole("link", { name: "GitHub documentation (opens in a new tab)" });
      expect(link).toHaveAttribute("href", "https://docs.example.test/github");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });

    it.each([["javascript:alert(1)"], ["http://docs.example.test"], ["not a url"]])(
      "renders no link for the unsafe docs URL %s",
      (docsUrl) => {
        setup(buildConnector({ docs_url: docsUrl }));
        expect(screen.queryByRole("link")).not.toBeInTheDocument();
      },
    );
  });
});
