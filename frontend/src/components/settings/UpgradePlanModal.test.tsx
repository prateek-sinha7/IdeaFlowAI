/**
 * UpgradePlanModal — the single plan-management affordance (ISS-291).
 *
 * Covers the two copy branches (a next tier exists vs. already on the top
 * plan) and the three ways a user can dismiss it (Close button, Escape,
 * backdrop click) while clicks inside the dialog must NOT dismiss it.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { UpgradePlanModal } from "./UpgradePlanModal";

describe("UpgradePlanModal", () => {
  it("offers the next tier and states the current plan when an upgrade path exists", () => {
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={() => {}} />);

    const dialog = screen.getByRole("dialog", { name: "Upgrade your plan" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("You are on the Basic plan")).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/The Pro plan unlocks \d+ more deliverable types\./);
    expect(dialog).toHaveTextContent(/contact them to move this account to Pro/);
  });

  it("follows the configured path for other tiers (pro -> Enterprise)", () => {
    renderWithProviders(<UpgradePlanModal tier="pro" onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Upgrade your plan" })).toHaveTextContent(
      /The Enterprise plan unlocks \d+ more deliverable types\./,
    );
  });

  it("says the account is on the highest plan when there is no next tier", () => {
    renderWithProviders(<UpgradePlanModal tier="enterprise" onClose={() => {}} />);

    const dialog = screen.getByRole("dialog", { name: "Manage plan" });
    expect(screen.getByText("You are on the Enterprise plan")).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/Enterprise is the highest plan/);
    expect(dialog).not.toHaveTextContent(/unlocks/);
    expect(screen.queryByRole("heading", { name: "Upgrade your plan" })).toBeNull();
  });

  it("renders into document.body so a header stacking context cannot trap it", () => {
    const { container } = renderWithProviders(<UpgradePlanModal tier="basic" onClose={() => {}} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("focuses the Close button when it opens", () => {
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={() => {}} />);

    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("calls onClose when Close is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape is pressed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={onClose} />);

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores keys other than Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={onClose} />);

    await user.keyboard("a{Tab}{ArrowDown}");

    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={onClose} />);

    // The backdrop is the dialog's role="presentation" wrapper.
    await user.click(screen.getByRole("presentation"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close when the dialog body itself is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={onClose} />);

    await user.click(screen.getByRole("heading", { name: "Upgrade your plan" }));

    expect(onClose).not.toHaveBeenCalled();
  });

  it("stops listening for Escape after it unmounts", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { unmount } = renderWithProviders(<UpgradePlanModal tier="basic" onClose={onClose} />);

    unmount();
    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
  });
});
