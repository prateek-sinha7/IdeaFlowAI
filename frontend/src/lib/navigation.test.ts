import { afterEach, describe, expect, it, vi } from "vitest";
import { backToOrigin, readBackOrigin, rememberBackOrigin } from "./navigation";

describe("backToOrigin — a run's Back returns to the list it came from", () => {
  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("defaults to the dashboard when no list recorded itself", () => {
    const push = vi.fn();
    backToOrigin({ push });
    expect(readBackOrigin().label).toBe("dashboard");
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("pops every entry pushed since the Runs list (tabs, wizard) instead of one", () => {
    vi.spyOn(window.history, "length", "get").mockReturnValue(3);
    rememberBackOrigin("runs", "/runs?type=backlog");
    vi.spyOn(window.history, "length", "get").mockReturnValue(7); // run + 3 tab switches
    const go = vi.spyOn(window.history, "go").mockImplementation(() => {});
    const push = vi.fn();
    backToOrigin({ push });
    expect(go).toHaveBeenCalledWith(-4);
    expect(push).not.toHaveBeenCalled();
    expect(readBackOrigin().label).toBe("runs");
  });

  it("pushes the list when history holds nothing past it (shared link)", () => {
    vi.spyOn(window.history, "length", "get").mockReturnValue(5);
    rememberBackOrigin("runs", "/runs");
    const push = vi.fn();
    backToOrigin({ push });
    expect(push).toHaveBeenCalledWith("/runs");
  });
});
