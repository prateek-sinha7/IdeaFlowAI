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
    await new Promise((r) => setTimeout(r, 0));

    // ISS-561: today nothing changes on rejection — no failure text, button
    // stays "Copy". The fixed behaviour must surface SOMETHING.
    expect(screen.queryByText(/fail|error|couldn.?t/i)).toBeInTheDocument();
  });
});

describe("IntegrationsCard API-key 'copy now' button — ISS-561", () => {
  it.fails("shows SOME feedback after clicking the newly-minted-key copy button", async () => {
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

    await waitFor(() => expect(screen.getByText("New key — copy now")).toBeInTheDocument());

    const copyButtons = screen.getAllByRole("button").filter((b) => !b.textContent?.trim());
    expect(copyButtons.length).toBeGreaterThan(0);
    fireEvent.click(copyButtons[0]);
    await new Promise((r) => setTimeout(r, 0));

    // ISS-561: today this button has no `copied` state at all — click it and
    // NOTHING in the DOM changes, success or failure. The fixed behaviour
    // must show something.
    expect(screen.queryByText(/copied|fail|error/i)).toBeInTheDocument();
  });
});
