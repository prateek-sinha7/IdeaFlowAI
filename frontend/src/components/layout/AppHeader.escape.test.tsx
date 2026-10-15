// ISS-928 (QA-KB-041): Escape must close the profile menu when the opening click did not
// focus the trigger. it.fails: red today by design; remove `.fails` when the fix lands.
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, fireEvent, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import { AppHeader } from "@/components/layout/AppHeader";

describe("ISS-928 AppHeader profile menu Escape", () => {
  it("ISS-928: Escape closes the menu after an unfocused click on the trigger", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppHeader currentPage="saved-workflows" onNavigate={vi.fn()} onLogout={vi.fn()}
        userEmail="qa@flowin.test" userTier="basic" />,
    );
    const trigger = screen.getByRole("button", { name: /account menu/i });
    fireEvent.click(trigger); // focus stays on BODY
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
