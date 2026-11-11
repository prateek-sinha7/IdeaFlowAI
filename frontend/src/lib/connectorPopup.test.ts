import { describe, it, expect } from "vitest";
import {
  CALLBACK_REASONS,
  CONNECTORS_CHANNEL,
  POPUP_NAME_PREFIX,
  isCallbackReason,
  isConnectorKey,
  isConnectorPopupName,
  isHttpsUrl,
  isOAuthCompleteMessage,
  parseOAuthResult,
  popupNameFor,
} from "./connectorPopup";

const params = (query: string) => new URLSearchParams(query);

describe("connectorPopup constants", () => {
  it("uses the names the landing page and the page agree on", () => {
    expect(POPUP_NAME_PREFIX).toBe("flowin-connect-");
    expect(CONNECTORS_CHANNEL).toBe("flowin-connectors");
  });

  it("allows exactly the eleven callback reasons the backend can send", () => {
    expect([...CALLBACK_REASONS].sort()).toEqual(
      [
        "access_denied",
        "account_lookup_failed",
        "invalid_state",
        "issuer_mismatch",
        "issuer_missing",
        "missing_code",
        "no_accessible_sites",
        "not_configured",
        "provider_error",
        "server_error",
        "token_exchange_failed",
      ].sort(),
    );
  });
});

describe("popupNameFor / isConnectorPopupName", () => {
  it("prefixes the connector key", () => {
    expect(popupNameFor("github")).toBe("flowin-connect-github");
  });

  it("recognises a popup name and rejects other window names", () => {
    expect(isConnectorPopupName("flowin-connect-jira")).toBe(true);
    expect(isConnectorPopupName("")).toBe(false);
    expect(isConnectorPopupName("other-flowin-connect-jira")).toBe(false);
  });
});

describe("isConnectorKey", () => {
  it.each(["github", "jira", "ab", "a1"])("accepts %s", (key) => {
    expect(isConnectorKey(key)).toBe(true);
  });

  it.each([
    ["uppercase", "GitHub"],
    ["leading digit", "1abc"],
    ["one character", "a"],
    ["path traversal", "../x"],
    ["too long", "a".repeat(33)],
    ["empty", ""],
  ])("rejects %s", (_label, key) => {
    expect(isConnectorKey(key)).toBe(false);
  });

  it("rejects non-strings", () => {
    expect(isConnectorKey(null)).toBe(false);
    expect(isConnectorKey(42)).toBe(false);
  });
});

describe("isCallbackReason", () => {
  it("accepts a listed reason and rejects anything else", () => {
    expect(isCallbackReason("access_denied")).toBe(true);
    expect(isCallbackReason("<script>alert(1)</script>")).toBe(false);
    expect(isCallbackReason(undefined)).toBe(false);
  });
});

describe("isOAuthCompleteMessage", () => {
  const valid = { type: "oauth-complete", connector: "github", result: "connected", reason: null };

  it("accepts a well-formed success message", () => {
    expect(isOAuthCompleteMessage(valid)).toBe(true);
  });

  it("accepts an error message with an allow-listed reason", () => {
    expect(isOAuthCompleteMessage({ ...valid, result: "error", reason: "access_denied" })).toBe(true);
  });

  it.each([
    ["null", null],
    ["a string", "oauth-complete"],
    ["an array", []],
    ["a wrong type tag", { ...valid, type: "other" }],
    ["a bad connector key", { ...valid, connector: "Git Hub" }],
    ["a bad result", { ...valid, result: "ok" }],
    ["an unlisted reason", { ...valid, result: "error", reason: "because" }],
    ["a missing reason field", { type: "oauth-complete", connector: "github", result: "connected" }],
  ])("rejects %s", (_label, value) => {
    expect(isOAuthCompleteMessage(value)).toBe(false);
  });
});

describe("parseOAuthResult", () => {
  it("builds a connected message and ignores any reason", () => {
    expect(parseOAuthResult(params("connector=jira&result=connected&reason=access_denied"))).toEqual({
      type: "oauth-complete",
      connector: "jira",
      result: "connected",
      reason: null,
    });
  });

  it("keeps an allow-listed reason on an error result", () => {
    expect(parseOAuthResult(params("connector=github&result=error&reason=issuer_mismatch"))).toEqual({
      type: "oauth-complete",
      connector: "github",
      result: "error",
      reason: "issuer_mismatch",
    });
  });

  it("drops an unknown reason but keeps the error result", () => {
    expect(parseOAuthResult(params("connector=github&result=error&reason=%3Cb%3E"))?.reason).toBeNull();
  });

  it("returns a reason of null when none is given on an error result", () => {
    expect(parseOAuthResult(params("connector=github&result=error"))?.reason).toBeNull();
  });

  it.each([
    ["no params", ""],
    ["a missing connector", "result=connected"],
    ["an invalid connector", "connector=..%2Fx&result=connected"],
    ["a missing result", "connector=github"],
    ["an invalid result", "connector=github&result=maybe"],
  ])("returns null for %s", (_label, query) => {
    expect(parseOAuthResult(params(query))).toBeNull();
  });
});

describe("isHttpsUrl", () => {
  it("accepts https", () => {
    expect(isHttpsUrl("https://github.com/login/oauth/authorize?x=1")).toBe(true);
  });

  it.each([
    ["http", "http://github.com/login"],
    ["javascript:", "javascript:alert(1)"],
    ["data:", "data:text/html,<b>x</b>"],
    ["a relative path", "/connectors"],
    ["protocol-relative", "//evil.example/path"],
    ["empty", ""],
    ["garbage", "not a url"],
  ])("rejects %s", (_label, value) => {
    expect(isHttpsUrl(value)).toBe(false);
  });
});
