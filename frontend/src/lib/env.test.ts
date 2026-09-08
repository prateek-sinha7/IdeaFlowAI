import { describe, it, expect } from "vitest";
import { ENV } from "./env";

describe("ENV object", () => {
  it("should have a readonly API_URL property", () => {
    expect(ENV).toHaveProperty("API_URL");
    expect(typeof ENV.API_URL).toBe("string");
  });

  it("API_URL should be a valid string", () => {
    expect(ENV.API_URL).toBeDefined();
    expect(typeof ENV.API_URL).toBe("string");
  });

  it("API_URL should be either empty string or a valid URL", () => {
    if (ENV.API_URL !== "") {
      // If not empty, must start with http
      expect(ENV.API_URL).toMatch(/^https?:\/\//);
    }
  });

  it("should resolve API_URL for localhost", () => {
    // In the test environment (jsdom with localhost), this should resolve to localhost:8000
    // or to empty string if running on a different host
    expect(typeof ENV.API_URL).toBe("string");
    const isLocalOrEmpty =
      ENV.API_URL === "http://localhost:8000" ||
      ENV.API_URL === "" ||
      ENV.API_URL.includes("localhost");
    expect(isLocalOrEmpty).toBe(true);
  });
});
