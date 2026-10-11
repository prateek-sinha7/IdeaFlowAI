import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { replaceMock, getTokenMock, router } = vi.hoisted(() => {
  const replaceMock = vi.fn();
  return { replaceMock, getTokenMock: vi.fn(), router: { replace: replaceMock } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", () => ({ getToken: getTokenMock }));
// Stub: the real card does its own network I/O and has its own tests.
// A test id is used because the stub has no semantic role.
vi.mock("@/components/handoff/IntegrationsCard", () => ({
  IntegrationsCard: () => <div data-testid="integrations-card-stub" />,
}));

import HandoffSettingsPage from "./page";

describe("HandoffSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to /login and renders nothing when no token", () => {
    getTokenMock.mockReturnValue(null);
    const { container } = render(<HandoffSettingsPage />);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.queryByTestId("integrations-card-stub")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("treats an empty-string token as unauthenticated", () => {
    getTokenMock.mockReturnValue("");
    const { container } = render(<HandoffSettingsPage />);

    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.queryByTestId("integrations-card-stub")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the integrations card when a token exists", async () => {
    getTokenMock.mockReturnValue("jwt");
    render(<HandoffSettingsPage />);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Handoff integrations" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Install the slash command, save your GitHub PAT, manage VelocityAI API keys."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("integrations-card-stub")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("links back to the dashboard", () => {
    getTokenMock.mockReturnValue("jwt");
    render(<HandoffSettingsPage />);

    // Suspected a11y defect: this icon-only link has no accessible name,
    // so it is queried by role only and no name is asserted.
    expect(screen.getByRole("link")).toHaveAttribute("href", "/dashboard");
  });

  it("does not redirect again on rerender with the same router", () => {
    getTokenMock.mockReturnValue(null);
    const { rerender } = render(<HandoffSettingsPage />);
    rerender(<HandoffSettingsPage />);

    expect(replaceMock).toHaveBeenCalledTimes(1);
  });
});
