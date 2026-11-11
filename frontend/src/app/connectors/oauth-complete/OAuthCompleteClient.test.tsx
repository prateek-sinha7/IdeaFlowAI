import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { OAuthCompleteClient } from "./OAuthCompleteClient";

const { replace, nav } = vi.hoisted(() => ({
  replace: vi.fn(),
  nav: { search: new URLSearchParams() },
}));

// Boundary only: Next navigation. The component and its parsing helpers run for real.
vi.mock("next/navigation", () => {
  const router = { replace };
  return { useRouter: () => router, useSearchParams: () => nav.search };
});

/** BroadcastChannel stand-in that records every message posted on it. */
class FakeChannel {
  static instances: FakeChannel[] = [];
  posted: unknown[] = [];
  closed = false;
  constructor(public name: string) {
    FakeChannel.instances.push(this);
  }
  postMessage(data: unknown) {
    this.posted.push(data);
  }
  close() {
    this.closed = true;
  }
}

function posted(): unknown[] {
  return FakeChannel.instances.flatMap((c) => c.posted);
}

describe("OAuthCompleteClient", () => {
  const closeSpy = vi.fn();

  beforeEach(() => {
    FakeChannel.instances = [];
    vi.stubGlobal("BroadcastChannel", FakeChannel);
    vi.spyOn(window, "close").mockImplementation(closeSpy);
    window.name = "";
    nav.search = new URLSearchParams();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    closeSpy.mockReset();
    replace.mockReset();
    window.name = "";
  });

  describe("in a popup", () => {
    beforeEach(() => {
      window.name = "flowin-connect-jira";
    });

    it("posts the hint on the connectors channel and closes the window when the result is connected", () => {
      nav.search = new URLSearchParams("connector=jira&result=connected");
      render(<OAuthCompleteClient />);

      expect(FakeChannel.instances[0]?.name).toBe("flowin-connectors");
      expect(posted()).toEqual([
        { type: "oauth-complete", connector: "jira", result: "connected", reason: null },
      ]);
      expect(FakeChannel.instances[0]?.closed).toBe(true);
      expect(closeSpy).toHaveBeenCalledTimes(1);
      expect(replace).not.toHaveBeenCalled();
      expect(screen.getByRole("heading", { name: "Connected" })).toBeInTheDocument();
      expect(screen.getByText(/You can close this window/)).toBeInTheDocument();
    });

    it("keeps a link back to Connectors visible in case the browser keeps the window open", () => {
      nav.search = new URLSearchParams("connector=jira&result=connected");
      render(<OAuthCompleteClient />);

      expect(screen.getByRole("link", { name: "Back to Connectors" })).toHaveAttribute(
        "href",
        "/connectors",
      );
    });

    it("shows the reason message and posts the reason when the result is an error", () => {
      nav.search = new URLSearchParams("connector=github&result=error&reason=access_denied");
      render(<OAuthCompleteClient />);

      expect(posted()).toEqual([
        { type: "oauth-complete", connector: "github", result: "error", reason: "access_denied" },
      ]);
      expect(screen.getByRole("heading", { name: "Connection failed" })).toBeInTheDocument();
      expect(screen.getByText(/Access was declined/)).toBeInTheDocument();
      expect(closeSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe("in a normal tab", () => {
    it("posts the hint and redirects to Connectors with the same result when connected", () => {
      nav.search = new URLSearchParams("connector=jira&result=connected");
      render(<OAuthCompleteClient />);

      expect(posted()).toHaveLength(1);
      expect(closeSpy).not.toHaveBeenCalled();
      expect(replace).toHaveBeenCalledWith("/connectors?connector=jira&result=connected");
    });

    it("forwards a known reason when the result is an error", () => {
      nav.search = new URLSearchParams("connector=jira&result=error&reason=invalid_state");
      render(<OAuthCompleteClient />);

      expect(replace).toHaveBeenCalledWith(
        "/connectors?connector=jira&result=error&reason=invalid_state",
      );
    });

    it("drops an unknown reason and shows the generic message when the reason is not on the allow-list", () => {
      nav.search = new URLSearchParams("connector=jira&result=error&reason=<script>x</script>");
      render(<OAuthCompleteClient />);

      expect(replace).toHaveBeenCalledWith("/connectors?connector=jira&result=error");
      expect(screen.getByText(/could not be completed/)).toBeInTheDocument();
      expect(document.body.innerHTML).not.toContain("<script>");
    });

    it("still redirects when BroadcastChannel is unavailable", () => {
      vi.stubGlobal("BroadcastChannel", undefined);
      nav.search = new URLSearchParams("connector=jira&result=connected");
      render(<OAuthCompleteClient />);

      expect(replace).toHaveBeenCalledTimes(1);
    });

    it("still redirects when the channel throws on construction", () => {
      vi.stubGlobal(
        "BroadcastChannel",
        class {
          constructor() {
            throw new Error("blocked");
          }
        },
      );
      nav.search = new URLSearchParams("connector=jira&result=connected");
      render(<OAuthCompleteClient />);

      expect(replace).toHaveBeenCalledTimes(1);
    });
  });

  describe.each([
    ["connector is missing", "result=connected"],
    ["connector is malformed", "connector=Jira%20Cloud&result=connected"],
    ["connector has a path in it", "connector=../admin&result=connected"],
    ["result is unknown", "connector=jira&result=pending"],
    ["result is missing", "connector=jira"],
    ["there is no query", ""],
  ])("when %s", (_label, query) => {
    it("ignores the values: nothing is posted, closed or redirected", () => {
      window.name = "flowin-connect-jira";
      nav.search = new URLSearchParams(query);
      render(<OAuthCompleteClient />);

      expect(posted()).toEqual([]);
      expect(closeSpy).not.toHaveBeenCalled();
      expect(replace).not.toHaveBeenCalled();
      expect(screen.getByRole("heading", { name: "This link is not valid" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Back to Connectors" })).toBeInTheDocument();
    });
  });

  it("does not call fetch", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    nav.search = new URLSearchParams("connector=jira&result=connected");
    render(<OAuthCompleteClient />);

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
