import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

const { replaceMock, getTokenMock } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  getTokenMock: vi.fn<() => string | null>(),
}));

// Stable router object for the whole test: `useEffect` depends on `router`, so
// a fresh object per render would re-run the redirect effect.
const router = { replace: replaceMock };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("@/lib/api", () => ({
  getToken: getTokenMock,
}));

import Home from "./page";

describe("Home (root redirect page)", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    getTokenMock.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to the dashboard when a session token is present", () => {
    getTokenMock.mockReturnValue("jwt-token");

    render(<Home />);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/dashboard");
  });

  it("redirects to the login page when no session token is stored", () => {
    getTokenMock.mockReturnValue(null);

    render(<Home />);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("redirects to the login page when the stored token is an empty string", () => {
    getTokenMock.mockReturnValue("");

    render(<Home />);

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("renders no visible content while redirecting", () => {
    getTokenMock.mockReturnValue(null);

    const { container } = render(<Home />);

    expect(container).toBeEmptyDOMElement();
  });

  it("does not redirect a second time when re-rendered with the same router", () => {
    getTokenMock.mockReturnValue("jwt-token");

    const { rerender } = render(<Home />);
    rerender(<Home />);

    expect(replaceMock).toHaveBeenCalledTimes(1);
  });
});
