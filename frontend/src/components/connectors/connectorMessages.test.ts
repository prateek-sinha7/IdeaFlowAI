import { describe, expect, it } from "vitest";
import { CALLBACK_REASONS } from "@/lib/connectorPopup";
import type { ConnectorNotice } from "@/hooks/useConnectorAuthorization";
import {
  accountLabel,
  bannerFor,
  disconnectResultMessage,
  expiredMessage,
  formatConnectedDate,
  notConfiguredMessage,
  reasonMessage,
  statusLabel,
} from "./connectorMessages";

describe("statusLabel", () => {
  it.each([
    ["connected", "Connected"],
    ["not_connected", "Not connected"],
    ["expired", "Expired"],
    ["not_configured", "Not configured"],
  ] as const)("labels %s as %s", (status, label) => {
    expect(statusLabel(status)).toBe(label);
  });
});

describe("fixed card messages", () => {
  it("names the connector in the expired message", () => {
    expect(expiredMessage("Jira")).toBe("Your Jira connection expired. Reconnect to keep using its tools.");
  });

  it("names the connector in the not-configured message", () => {
    expect(notConfiguredMessage("Jira")).toBe("Jira is not configured on this server.");
  });
});

describe("accountLabel", () => {
  it("shows the display name and the login when both differ", () => {
    expect(accountLabel({ id: "1", display_name: "Jane Doe", login: "jane" })).toBe("Jane Doe (jane)");
  });

  it("shows one name when the display name equals the login", () => {
    expect(accountLabel({ id: "1", display_name: "jane", login: "jane" })).toBe("jane");
  });

  it("falls back to the login, then to the id", () => {
    expect(accountLabel({ id: "1", display_name: null, login: "jane" })).toBe("jane");
    expect(accountLabel({ id: "acct-7", display_name: null, login: null })).toBe("acct-7");
  });
});

describe("formatConnectedDate", () => {
  it("formats a valid timestamp as month, day and year", () => {
    expect(formatConnectedDate("2026-09-01T12:00:00Z")).toMatch(/^Sep \d{1,2}, 2026$/);
  });

  it.each([[null], [""], ["not a date"]])("returns null for %j", (value) => {
    expect(formatConnectedDate(value)).toBeNull();
  });
});

describe("reasonMessage", () => {
  it.each(CALLBACK_REASONS)("has a non-empty message for the %s reason", (reason) => {
    expect(reasonMessage(reason, "GitHub").length).toBeGreaterThan(10);
  });

  it("uses the connector name where the message mentions the provider", () => {
    expect(reasonMessage("token_exchange_failed", "Jira")).toBe("Jira did not accept the sign-in. Try again.");
  });

  it("never claims a verified sign-in for an issuer mismatch", () => {
    expect(reasonMessage("issuer_mismatch", "GitHub")).toContain("could not be verified");
  });
});

describe("disconnectResultMessage", () => {
  it("says the grant was revoked when the provider confirmed", () => {
    expect(disconnectResultMessage("revoked", "GitHub")).toContain("revoked at the provider");
  });

  it.each(["failed", "not_attempted"] as const)(
    "points to the provider's account settings when the revoke result is %s",
    (revocation) => {
      expect(disconnectResultMessage(revocation, "GitHub")).toContain("GitHub account settings");
    },
  );
});

describe("bannerFor", () => {
  const cases: Array<[string, ConnectorNotice, string, string]> = [
    ["connected", { kind: "connected", connector: "github" }, "success", "GitHub is connected."],
    ["cancelled", { kind: "cancelled", connector: "github" }, "info", "Sign-in to GitHub was cancelled."],
    ["timed out", { kind: "timed_out", connector: "github" }, "error", "Sign-in to GitHub timed out. Try again."],
    [
      "popup blocked",
      { kind: "popup_blocked", connector: "github", authorizationUrl: "https://example.test/a" },
      "info",
      "Your browser blocked the sign-in window.",
    ],
  ];

  it.each(cases)("describes a %s notice", (_label, notice, tone, text) => {
    expect(bannerFor(notice, "GitHub")).toEqual({ tone, text });
  });

  it("describes a disconnect through the revocation message", () => {
    const banner = bannerFor({ kind: "disconnected", connector: "github", providerRevocation: "failed" }, "GitHub");
    expect(banner.tone).toBe("success");
    expect(banner.text).toBe(disconnectResultMessage("failed", "GitHub"));
  });

  it("prefers the callback reason over free text for an error", () => {
    const banner = bannerFor(
      { kind: "error", connector: "github", reason: "access_denied", message: "ignored" },
      "GitHub",
    );
    expect(banner).toEqual({ tone: "error", text: reasonMessage("access_denied", "GitHub") });
  });

  it("uses the error message when there is no reason", () => {
    const banner = bannerFor({ kind: "error", connector: "github", reason: null, message: "Boom" }, "GitHub");
    expect(banner).toEqual({ tone: "error", text: "Boom" });
  });

  it("falls back to a generic error when there is neither a reason nor a message", () => {
    const banner = bannerFor({ kind: "error", connector: null, reason: null, message: null }, "the connector");
    expect(banner).toEqual({ tone: "error", text: "Could not connect the connector. Try again." });
  });
});
