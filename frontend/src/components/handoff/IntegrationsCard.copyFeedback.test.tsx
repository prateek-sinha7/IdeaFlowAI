/**
 * ISS-561 — the Handoff Integrations page's install-command Copy button
 * (IntegrationsCard.tsx:73-78, `.then()` with no `.catch()`) is silent on a
 * rejected clipboard write, and its API-key "copy now" button
 * (IntegrationsCard.tsx:316-323, `.then(() => {})`) gives no feedback at
 * all — success or failure. Two distinct call sites named by the card,
 * two tests.
 *
 * @/lib/api and @/lib/api-handoff are stubbed so the component renders
 * with no live transport, following HandoffWorkflow.test.tsx's pattern.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  getToken: () => "test-jwt",
}));

const { getGithubPatStatusMock, listApiKeysMock, createApiKeyMock } = vi.hoisted(() => ({
  getGithubPatStatusMock: vi.fn(),
  listApiKeysMock: vi.fn(),
  createApiKeyMock: vi.fn(),
}));
vi.mock("@/lib/api-handoff", () => ({
  getGithubPatStatus: getGithubPatStatusMock,
  listApiKeys: listApiKeysMock,
  createApiKey: createApiKeyMock,
  revokeApiKey: vi.fn(),
  saveGithubPat: vi.fn(),
  deleteGithubPat: vi.fn(),
}));

import { IntegrationsCard } from "./IntegrationsCard";

beforeEach(() => {
  getGithubPatStatusMock.mockReset().mockResolvedValue(null);
  listApiKeysMock.mockReset().mockResolvedValue([]);
  createApiKeyMock.mockReset();
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
  });
});

// The defect this card asserts IS an unhandled promise rejection (both
// call sites' `.then()` chains have no `.catch()`) — that is exactly what
// makes them silent. Swallow the process-level event so the real
// assertion below decides pass/fail instead of the test runner.
let restoreUnhandledRejection: (() => void) | undefined;
beforeEach(() => {
  const noop = () => {};
  process.on("unhandledRejection", noop);
  restoreUnhandledRejection = () => process.off("unhandledRejection", noop);
});
afterEach(() => {
  restoreUnhandledRejection?.();
});

describe("IntegrationsCard install-command Copy button — ISS-561", () => {
  it("shows a failure state when the clipboard write rejects, instead of staying silent", async () => {
    render(<IntegrationsCard />);

    fireEvent.click(await screen.findByRole("button", { name: /^Copy$/ }));
    // findByText retries until the async state update completes, eliminating the race.
    await expect(screen.findByText(/copy failed/i)).resolves.toBeInTheDocument();
  });
});

describe("IntegrationsCard API-key 'copy now' button — ISS-561", () => {
  it("shows SOME feedback after clicking the newly-minted-key copy button", async () => {
    createApiKeyMock.mockResolvedValue({
      id: "k1",
      name: "Default",
      expires_at: null,
      token_prefix: "vai_abc",
      last_used_at: null,
      token: "vai_abc123secret",
    });

    render(<IntegrationsCard />);

    fireEvent.change(screen.getByLabelText("API key name"), { target: { value: "Laptop" } });
    fireEvent.click(screen.getByRole("button", { name: /Create key/i }));

    // Wait for the banner with "New key — copy now" to appear
    await waitFor(() => expect(screen.getByText("New key — copy now")).toBeInTheDocument());

    // Find all buttons in the banner container and click the copy button (usually the last one)
    const keyBanner = screen.getByText("New key — copy now").closest("div") || screen.getByText("New key — copy now").parentElement;
    const buttons = keyBanner?.querySelectorAll("button") || [];
    const copyBtn = Array.from(buttons).pop();
    
    if (copyBtn) {
      fireEvent.click(copyBtn);
      // findByText retries until the async state update completes, eliminating the race.
      await expect(screen.findByText(/copy failed|copied/i)).resolves.toBeInTheDocument();
    }
  });
});
