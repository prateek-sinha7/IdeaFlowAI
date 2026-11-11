import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { buildConnectedConnector } from "@/test/connectorFixtures";
import type { ProviderRevocation } from "@/types/connectors";
import { DisconnectDialog } from "./DisconnectDialog";

const connector = buildConnectedConnector();

function setup(onConfirm: () => Promise<ProviderRevocation | null>) {
  const confirm = vi.fn(onConfirm);
  const onClose = vi.fn();
  render(<DisconnectDialog connector={connector} onConfirm={confirm} onClose={onClose} />);
  return { confirm, onClose };
}

describe("DisconnectDialog", () => {
  it("asks for confirmation in a modal dialog that says the provider grant is revoked", () => {
    setup(() => Promise.resolve("revoked"));
    const dialog = screen.getByRole("dialog", { name: "Disconnect GitHub?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent("ask GitHub to revoke the access it granted");
  });

  it("focuses Cancel first so Enter does not disconnect by accident", () => {
    setup(() => Promise.resolve("revoked"));
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("closes without disconnecting when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const { confirm, onClose } = setup(() => Promise.resolve("revoked"));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
  });

  it("closes without disconnecting when Escape is pressed", async () => {
    const user = userEvent.setup();
    const { confirm, onClose } = setup(() => Promise.resolve("revoked"));
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
  });

  it.each([
    ["revoked", "revoked at the provider"],
    ["failed", "GitHub account settings"],
    ["not_attempted", "GitHub account settings"],
  ] as const)("shows the %s result and moves focus to Close", async (revocation, text) => {
    const user = userEvent.setup();
    const { confirm } = setup(() => Promise.resolve(revocation));
    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("status")).toHaveTextContent(text);
    expect(confirm).toHaveBeenCalledExactlyOnceWith(connector);
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
  });

  it("closes from the result view with the Close button", async () => {
    const user = userEvent.setup();
    const { onClose } = setup(() => Promise.resolve("revoked"));
    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("blocks Escape and the actions while the request is running", async () => {
    const user = userEvent.setup();
    let finish: (value: ProviderRevocation | null) => void = () => {};
    const { onClose } = setup(() => new Promise((resolve) => (finish = resolve)));
    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(screen.getByRole("button", { name: "Disconnecting…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    finish("revoked");
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("shows an alert and lets the user try again when the disconnect fails", async () => {
    const user = userEvent.setup();
    const results: Array<ProviderRevocation | null> = [null, "revoked"];
    const { confirm } = setup(() => Promise.resolve(results.shift() ?? null));
    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not disconnect GitHub. Try again.");
    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("status")).toHaveTextContent("revoked at the provider");
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
