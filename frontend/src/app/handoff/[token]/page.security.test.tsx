/**
 * Security-oriented client behavior of the handoff token route: invalid / expired token UX,
 * unauthenticated access, adversarial token and error text, and no leakage of secrets.
 *
 * This is client UX only. It does not replace backend token-enforcement / IDOR tests.
 *
 * The real page and real HandoffWorkflow run; only the system boundaries are controlled:
 * next/navigation, @/lib/api (session token), @/lib/env, @/lib/api-handoff, and the socket hook.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { HandoffSessionView } from "@/lib/api-handoff";

type SocketConfig = { url?: string; token: string | null };

const { getHandoffMock, getTokenMock, replaceMock, routerStub, paramsState, useHandoffSocketMock } =
  vi.hoisted(() => {
    const replace = vi.fn();
    return {
      getHandoffMock: vi.fn(),
      getTokenMock: vi.fn(),
      replaceMock: replace,
      // Stable router object: a fresh one per render would re-run the auth effect.
      routerStub: { replace, push: vi.fn() },
      paramsState: { value: { token: "tok-1" } as { token?: string } },
      useHandoffSocketMock: vi.fn<(config: SocketConfig) => unknown>(),
    };
  });

vi.mock("next/navigation", () => ({
  useRouter: () => routerStub,
  useParams: () => paramsState.value,
}));
vi.mock("@/lib/api", () => ({ getToken: () => getTokenMock() }));
vi.mock("@/lib/env", () => ({ ENV: { API_URL: "https://api.example.test" } }));
vi.mock("@/hooks/useHandoffSocket", () => ({
  useHandoffSocket: (config: SocketConfig) => useHandoffSocketMock(config),
}));
vi.mock("@/lib/api-handoff", () => ({
  getHandoff: getHandoffMock,
  startHandoff: vi.fn(),
  getGithubPatStatus: vi.fn(),
  listApiKeys: vi.fn(),
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
  saveGithubPat: vi.fn(),
  deleteGithubPat: vi.fn(),
}));

import HandoffPage from "./page";

const AUTH_JWT = "jwt-super-secret-value";

function makeSession(overrides: Partial<HandoffSessionView> = {}): HandoffSessionView {
  return {
    id: "s-1",
    token: "tok-1",
    task_description: "Add retry to uploader",
    repo_url: "https://github.com/acme/app",
    mode: "auto",
    resolved_mode: null,
    status: "pending",
    source_client: "claude-code",
    source_branch: null,
    created_at: "2030-01-01T00:00:00",
    started_at: null,
    completed_at: null,
    expires_at: "2999-01-01T00:00:00",
    pr_url: null,
    pr_number: null,
    branch_name: null,
    pipeline_output: null,
    error: null,
    issuer_email: null,
    has_github_pat: true,
    ...overrides,
  };
}

describe("HandoffPage security", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsState.value = { token: "tok-1" };
    getTokenMock.mockReturnValue(AUTH_JWT);
  });

  it("redirects to /login and never requests the handoff when the user is unauthenticated", async () => {
    getTokenMock.mockReturnValue(null);
    render(<HandoffPage />);

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(getHandoffMock).not.toHaveBeenCalled();
    expect(screen.queryByText("Add retry to uploader")).not.toBeInTheDocument();
  });

  it("makes no request and renders nothing when the route has no token", () => {
    paramsState.value = {};
    const { container } = render(<HandoffPage />);

    expect(container).toBeEmptyDOMElement();
    expect(getHandoffMock).not.toHaveBeenCalled();
  });

  it("shows a not-found state with a dashboard link and no retry when the server rejects the token", async () => {
    getHandoffMock.mockRejectedValue(Object.assign(new Error("Handoff not found"), { status: 404 }));
    render(<HandoffPage />);

    expect(await screen.findByRole("heading", { name: "Handoff not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start pipeline/i })).not.toBeInTheDocument();
  });

  it("requests the handoff with the session token and the raw route token", async () => {
    paramsState.value = { token: "tok-xyz" };
    getHandoffMock.mockResolvedValue(makeSession({ token: "tok-xyz" }));
    render(<HandoffPage />);

    expect(await screen.findByText("Add retry to uploader")).toBeInTheDocument();
    expect(getHandoffMock).toHaveBeenCalledWith(AUTH_JWT, "tok-xyz");
  });

  it("does not leak the session token or route token into the not-found view", async () => {
    paramsState.value = { token: "handoff-token-value" };
    getHandoffMock.mockRejectedValue(new Error("Handoff not found"));
    const { container } = render(<HandoffPage />);

    await screen.findByRole("heading", { name: "Handoff not found" });
    expect(container).not.toHaveTextContent(AUTH_JWT);
    expect(container).not.toHaveTextContent("handoff-token-value");
  });

  it("renders a hostile server error message as inert text, not markup", async () => {
    getHandoffMock.mockRejectedValue(new Error('<img src=x onerror="alert(1)">'));
    const { container } = render(<HandoffPage />);

    expect(await screen.findByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows the offline state, not a not-found claim, and retries successfully when the request never reached the server", async () => {
    const user = userEvent.setup();
    getHandoffMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    getHandoffMock.mockResolvedValueOnce(makeSession());
    render(<HandoffPage />);

    expect(await screen.findByRole("heading", { name: "Couldn't reach VelocityAI" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Handoff not found" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Add retry to uploader")).toBeInTheDocument();
    expect(getHandoffMock).toHaveBeenCalledTimes(2);
  });

  it("treats an ApiError-style status 0 failure as offline", async () => {
    getHandoffMock.mockRejectedValue(Object.assign(new Error("Network error"), { status: 0 }));
    render(<HandoffPage />);

    expect(await screen.findByRole("heading", { name: "Couldn't reach VelocityAI" })).toBeInTheDocument();
  });

  it("falls back to a generic message when the rejection is not an Error", async () => {
    getHandoffMock.mockRejectedValue("boom");
    render(<HandoffPage />);

    expect(await screen.findByText("Failed to load handoff")).toBeInTheDocument();
    expect(screen.queryByText("boom")).not.toBeInTheDocument();
  });

  it("shows the expired state and offers no way to start when the expiry time has passed", async () => {
    getHandoffMock.mockResolvedValue(makeSession({ expires_at: "2000-01-01T00:00:00" }));
    render(<HandoffPage />);

    expect(await screen.findByRole("heading", { name: "This handoff has expired" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start pipeline/i })).not.toBeInTheDocument();
  });

  it("shows the expired state when the server marks the session expired even if the clock says otherwise", async () => {
    getHandoffMock.mockResolvedValue(makeSession({ status: "expired" }));
    render(<HandoffPage />);

    expect(await screen.findByRole("heading", { name: "This handoff has expired" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start pipeline/i })).not.toBeInTheDocument();
  });

  it("does not open the live socket for an expired session", async () => {
    getHandoffMock.mockResolvedValue(makeSession({ status: "expired" }));
    render(<HandoffPage />);

    await screen.findByRole("heading", { name: "This handoff has expired" });
    expect(useHandoffSocketMock).toHaveBeenCalled();
    for (const [config] of useHandoffSocketMock.mock.calls) {
      expect(config.token).toBeNull();
    }
  });

  it("URL-encodes a hostile token in the socket URL and only authenticates it for a running session", async () => {
    paramsState.value = { token: "../a b?x=1#frag" };
    getHandoffMock.mockResolvedValue(makeSession({ status: "running" }));
    render(<HandoffPage />);

    await screen.findByText("Add retry to uploader");
    await waitFor(() => {
      const last = useHandoffSocketMock.mock.calls.at(-1)?.[0];
      expect(last?.token).toBe(AUTH_JWT);
    });
    const last = useHandoffSocketMock.mock.calls.at(-1)?.[0];
    expect(last?.url).toBe("wss://api.example.test/ws/handoff/..%2Fa%20b%3Fx%3D1%23frag");
  });
});
