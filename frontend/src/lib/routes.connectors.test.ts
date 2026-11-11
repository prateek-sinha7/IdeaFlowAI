import { describe, it, expect } from "vitest";
import { routes, parseViewPath } from "./routes";

describe("routes.connectors", () => {
  it("returns the bare path when no params are given", () => {
    expect(routes.connectors()).toBe("/connectors");
  });

  it("appends only the params that have a value", () => {
    expect(routes.connectors({ connector: "github", result: "error", reason: undefined })).toBe(
      "/connectors?connector=github&result=error",
    );
  });

  it("percent-encodes a reason that contains reserved characters", () => {
    expect(routes.connectors({ reason: "a&b=c" })).toBe("/connectors?reason=a%26b%3Dc");
  });
});

describe("parseViewPath for /connectors", () => {
  it("parses /connectors as the connectors screen", () => {
    expect(parseViewPath(["connectors"])).toEqual({ screen: "connectors" });
  });

  it("round-trips the builder output", () => {
    const path = routes.connectors({ connector: "jira", result: "connected" });
    const segments = path.split("?")[0].split("/").filter(Boolean);
    expect(parseViewPath(segments)).toEqual({ screen: "connectors" });
  });

  it.each([
    ["a sub-path", ["connectors", "anything"]],
    ["the oauth-complete landing path, which is a static route", ["connectors", "oauth-complete"]],
  ])("treats %s as unknown", (_label, segments) => {
    expect(parseViewPath(segments)).toEqual({ screen: "unknown" });
  });
});
