/**
 * Phase 35 plan-01 (B1-01) — NotificationPanel bell a11y contract (RED-first).
 *
 * Encodes the notifications-bell a11y invariant the reskin must satisfy: the
 * bell advertises aria-haspopup=dialog + a toggling aria-expanded, the open
 * dropdown carries role=dialog (a notification popup is a dialog, not a menu —
 * its rows are notifications, not menuitem commands), Escape closes it and
 * refocuses the bell, and the existing aria-label="Notifications" is preserved.
 * the reskin turns them GREEN. CHROME ONLY — no feed/data assertions
 * (live feed is Phase 38).
 *
 * Mirrors the render-test conventions in ReviewGatesSection.test.tsx.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { NotificationPanel } from "./NotificationPanel";

type PanelOverrides = Partial<React.ComponentProps<typeof NotificationPanel>>;

function setup(overrides: PanelOverrides = {}) {
  const onMarkAllRead = vi.fn();
  render(
    <NotificationPanel
      notifications={[]}
      unreadCount={0}
      onMarkAllRead={onMarkAllRead}
      onClearAll={vi.fn()}
      onGoToPipeline={vi.fn()}
      onViewResults={vi.fn()}
      {...overrides}
    />,
  );
  return { onMarkAllRead };
}

describe("NotificationPanel — bell a11y", () => {
  it("preserves the accessible aria-label='Notifications'", () => {
    setup();
    expect(
      screen.getByRole("button", { name: /notifications/i }),
    ).toBeInTheDocument();
  });

  it("bell advertises aria-haspopup=dialog and toggles aria-expanded on open", async () => {
    const user = userEvent.setup();
    setup();
    const bell = screen.getByRole("button", { name: /notifications/i });
    expect(bell).toHaveAttribute("aria-haspopup", "dialog");
    expect(bell).toHaveAttribute("aria-expanded", "false");
    await user.click(bell);
    expect(bell).toHaveAttribute("aria-expanded", "true");
  });

  it("open dropdown carries role=dialog", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /notifications/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("Escape closes the dropdown and returns focus to the bell", async () => {
    const user = userEvent.setup();
    setup();
    const bell = screen.getByRole("button", { name: /notifications/i });
    await user.click(bell);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(bell).toHaveFocus();
  });
});
