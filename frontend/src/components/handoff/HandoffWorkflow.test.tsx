/**
 * ISS-301 — a network-layer fetch failure on the handoff page must not be
 * rendered identically to a real 404. `HandoffWorkflow.fetchSession` collapses
 * both into the same `loadError` string, and the error branch always shows
 * "Handoff not found" (frontend/src/components/handoff/HandoffWorkflow.tsx:216-233).
 *
 * next/navigation, @/lib/api, @/lib/api-handoff and the WS hook are stubbed so
 * the component renders in jsdom with no live transport.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => "test-jwt",
}));

vi.mock("@/hooks/useHandoffSocket", () => ({
  useHandoffSocket: () => ({
    send: vi.fn(),
    connectionStatus: "disconnected",
    reconnect: vi.fn(),
  }),
}));

const { getHandoffMock } = vi.hoisted(() => ({
  getHandoffMock: vi.fn(),
}));
vi.mock("@/lib/api-handoff", () => ({
  getHandoff: getHandoffMock,
  startHandoff: vi.fn(),
}));

import { HandoffWorkflow } from "./HandoffWorkflow";

beforeEach(() => {
  getHandoffMock.mockReset();
});

describe("ISS-301 — handoff load-error surface", () => {
  it("shows Handoff not found for a genuine 404", async () => {
    getHandoffMock.mockRejectedValueOnce(new Error("HTTP 404"));

    render(<HandoffWorkflow token="nonexistent-token" />);

    await waitFor(() =>
      expect(screen.getByText("Handoff not found")).toBeInTheDocument()
    );
  });

  it("ISS-301 — does not render Handoff not found for a network-layer fetch failure on a real token", async () => {
    // Simulates the browser's own fetch rejection (offline/DNS/aborted
    // connection) — no HTTP response was ever received, unlike a real 404.
    getHandoffMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    render(<HandoffWorkflow token="real-owned-token" />);

    await waitFor(() => expect(getHandoffMock).toHaveBeenCalled());

    // A network failure must be distinguished from "this token doesn't
    // exist" — the card's expected behaviour is a retry-able connectivity
    // state, not the not-found copy.
    expect(screen.queryByText("Handoff not found")).not.toBeInTheDocument();
  });
});
