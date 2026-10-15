// ISS-929 (QA-KB-041): Escape must close the bell panel when the opening click did not
// focus the bell. it.fails: red today by design; remove `.fails` when the fix lands.
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, fireEvent, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import { NotificationPanel } from "@/components/ui/NotificationPanel";

describe("ISS-929 NotificationPanel Escape", () => {
  it("ISS-929: Escape closes the panel after an unfocused click on the bell", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <NotificationPanel notifications={[]} unreadCount={0} onMarkAllRead={vi.fn()} onClearAll={vi.fn()}
        onGoToPipeline={vi.fn()} onViewResults={vi.fn()} />,
    );
    const bell = screen.getByRole("button", { name: /notifications/i });
    fireEvent.click(bell);
    expect(bell).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(bell).toHaveAttribute("aria-expanded", "false");
  });
});
