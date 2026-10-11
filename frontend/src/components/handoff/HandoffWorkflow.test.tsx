/**
 * ISS-301 — a network-layer fetch failure on the handoff page must not be
 * rendered identically to a real 404. `HandoffWorkflow.fetchSession` collapses
 * both into the same `loadError` string, and the error branch always shows
 * "Handoff not found" (frontend/src/components/handoff/HandoffWorkflow.tsx:216-233).
 *
 * next/navigation, @/lib/api, @/lib/env, @/lib/api-handoff and the WS hook are
 * stubbed so the component renders in jsdom with no live transport. The real
 * pipeline reducer, agent/preview panels, diff/report views and
 * IntegrationsCard run unmocked.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

import type { HandoffSessionView } from "@/lib/api-handoff";
import type { StreamMessage } from "@/types/index";

type SocketConfig = {
  url?: string;
  token: string | null;
  onMessage: (msg: StreamMessage) => void;
};

const {
  getHandoffMock,
  startHandoffMock,
  getTokenMock,
  replaceMock,
  routerStub,
  useHandoffSocketMock,
  getGithubPatStatusMock,
  listApiKeysMock,
} = vi.hoisted(() => {
  const replace = vi.fn();
  return {
    getHandoffMock: vi.fn(),
    startHandoffMock: vi.fn(),
    getTokenMock: vi.fn(),
    replaceMock: replace,
    // Stable router object: a fresh one per render would re-run the auth effect.
    routerStub: { replace, push: vi.fn() },
    useHandoffSocketMock: vi.fn<(config: SocketConfig) => unknown>(),
    getGithubPatStatusMock: vi.fn(),
    listApiKeysMock: vi.fn(),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => routerStub,
}));

vi.mock("@/lib/api", () => ({
  getToken: () => getTokenMock(),
}));

// Fixed base URL so the derived WebSocket URL has an independent literal.
vi.mock("@/lib/env", () => ({
  ENV: { API_URL: "https://api.example.test" },
}));

vi.mock("@/hooks/useHandoffSocket", () => ({
  useHandoffSocket: (config: SocketConfig) => useHandoffSocketMock(config),
}));

vi.mock("@/lib/api-handoff", () => ({
  getHandoff: getHandoffMock,
  startHandoff: startHandoffMock,
  // Used by the real IntegrationsCard rendered in the onboarding state.
  getGithubPatStatus: getGithubPatStatusMock,
  listApiKeys: listApiKeysMock,
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
  saveGithubPat: vi.fn(),
  deleteGithubPat: vi.fn(),
}));

import { HandoffWorkflow } from "./HandoffWorkflow";

const FUTURE_EXPIRY = "2999-01-01T00:00:00";
const PAST_EXPIRY = "2000-01-01T00:00:00";
const TASK = "Add retry to uploader";
const REPO = "https://github.com/acme/app";
const ORIGINAL_TZ = process.env.TZ;

function makeSession(overrides: Partial<HandoffSessionView> = {}): HandoffSessionView {
  return {
    id: "s-1",
    token: "tok-1",
    task_description: TASK,
    repo_url: REPO,
    mode: "auto",
    resolved_mode: null,
    status: "pending",
    source_client: "claude-code",
    source_branch: null,
    created_at: "2030-01-01T00:00:00",
    started_at: null,
    completed_at: null,
    expires_at: FUTURE_EXPIRY,
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

const CODING_SUMMARY = {
  summary: "Added retry with backoff",
  rationale: "Transient 503s",
  edit_count: 1,
  edits: [
    {
      path: "src/upload.py",
      operation: "modify",
      old_string: "send(x)",
      new_string: "retry(send, x)",
    },
  ],
  tests_added: ["tests/test_upload.py"],
  follow_ups: ["Add jitter to the backoff"],
};
const EDIT_RESULTS = [{ path: "src/upload.py", operation: "modify", status: "applied" }];
const TEST_REPORT = {
  verdict: "concerns",
  summary: "Gaps in error paths",
  missing_coverage: [{ area: "Upload timeout", suggested_test: "covers a 504 response" }],
};
const COMPLIANCE_REPORT = {
  verdict: "approve_with_changes",
  summary: "Mostly compliant",
  findings: [
    {
      category: "security",
      severity: "high",
      location: "src/upload.py:10",
      issue: "Token logged in plaintext",
      recommendation: "Redact before logging",
    },
  ],
  positives: ["Small, focused diff"],
};

function completedSession(output: Record<string, unknown> | null): HandoffSessionView {
  return makeSession({ status: "completed", pipeline_output: output });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function lastSocketConfig(): SocketConfig {
  const call = useHandoffSocketMock.mock.calls.at(-1);
  if (!call) throw new Error("useHandoffSocket was never called");
  return call[0];
}

/**
 * Render with `getHandoff` resolving `session`, then wait until the page is
 * stable. A finished (completed/failed) session replays its output, which
 * flips `state.done` and triggers exactly one automatic re-fetch; wait for it
 * so later assertions do not race the loading spinner.
 */
async function renderHandoff(session: HandoffSessionView, token = "tok-1") {
  getHandoffMock.mockResolvedValue(session);
  const utils = render(<HandoffWorkflow token={token} />);
  if (session.status === "completed" || session.status === "failed") {
    await waitFor(() => expect(getHandoffMock).toHaveBeenCalledTimes(2));
  }
  await screen.findByText(session.task_description);
  return utils;
}

beforeEach(() => {
  getHandoffMock.mockReset();
  startHandoffMock
    .mockReset()
    .mockResolvedValue({ status: "running", started_at: "2030-01-01T00:00:00Z" });
  getTokenMock.mockReset().mockReturnValue("test-jwt");
  replaceMock.mockReset();
  useHandoffSocketMock.mockReset().mockReturnValue({
    send: vi.fn(),
    connectionStatus: "disconnected",
    reconnect: vi.fn(),
  });
  getGithubPatStatusMock.mockReset().mockResolvedValue(null);
  listApiKeysMock.mockReset().mockResolvedValue([]);
});

afterEach(() => {
  vi.useRealTimers();
  if (ORIGINAL_TZ === undefined) {
    delete process.env.TZ;
  } else {
    process.env.TZ = ORIGINAL_TZ;
  }
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

describe("HandoffWorkflow auth gate and loading", () => {
  it("redirects to login without fetching when no auth token exists", () => {
    getTokenMock.mockReturnValue(null);

    render(<HandoffWorkflow token="tok-1" />);

    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(getHandoffMock).not.toHaveBeenCalled();
  });

  it("fetches the session with the auth and handoff tokens without redirecting when a token exists", async () => {
    await renderHandoff(makeSession());

    expect(replaceMock).not.toHaveBeenCalled();
    expect(getHandoffMock).toHaveBeenCalledWith("test-jwt", "tok-1");
  });

  it("skips fetching and gives the socket no URL when the handoff token is empty", () => {
    render(<HandoffWorkflow token="" />);

    expect(getHandoffMock).not.toHaveBeenCalled();
    expect(lastSocketConfig().url).toBeUndefined();
  });

  it("shows neither session nor error content while the session is loading", async () => {
    const pending = deferred<HandoffSessionView>();
    getHandoffMock.mockReturnValue(pending.promise);

    render(<HandoffWorkflow token="tok-1" />);
    await waitFor(() => expect(getHandoffMock).toHaveBeenCalledTimes(1));

    expect(screen.queryByText(TASK)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Handoff not found" })).not.toBeInTheDocument();

    await act(async () => {
      pending.resolve(makeSession());
    });
    expect(await screen.findByText(TASK)).toBeInTheDocument();
  });
});

describe("HandoffWorkflow load failures", () => {
  it("explains the server was unreachable and offers Retry when the fetch throws a TypeError", async () => {
    getHandoffMock.mockRejectedValue(new TypeError("Failed to fetch"));

    render(<HandoffWorkflow token="tok-1" />);

    expect(
      await screen.findByRole("heading", { name: "Couldn't reach VelocityAI" })
    ).toBeInTheDocument();
    expect(screen.getByText(/The request never reached the server/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to dashboard" })).toHaveAttribute(
      "href",
      "/dashboard"
    );
  });

  it("treats an error carrying status 0 as offline", async () => {
    // api-handoff's authedJson labels a network failure as ApiError(status 0).
    getHandoffMock.mockRejectedValue(
      Object.assign(new Error("Network request failed"), { status: 0 })
    );

    render(<HandoffWorkflow token="tok-1" />);

    expect(
      await screen.findByRole("heading", { name: "Couldn't reach VelocityAI" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows the server message and no Retry button when the failure has an HTTP status", async () => {
    getHandoffMock.mockRejectedValue(
      Object.assign(new Error("Handoff token has expired"), { status: 404 })
    );

    render(<HandoffWorkflow token="tok-1" />);

    expect(await screen.findByRole("heading", { name: "Handoff not found" })).toBeInTheDocument();
    expect(screen.getByText("Handoff token has expired")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it.each([
    ["a non-Error string", "boom"],
    ["null", null],
  ])("shows the default load message when the rejection is %s", async (_label, reason) => {
    getHandoffMock.mockRejectedValue(reason);

    render(<HandoffWorkflow token="tok-1" />);

    expect(await screen.findByRole("heading", { name: "Handoff not found" })).toBeInTheDocument();
    expect(screen.getByText("Failed to load handoff")).toBeInTheDocument();
  });

  it("re-fetches and renders the session when Retry is clicked after an offline failure", async () => {
    const user = userEvent.setup();
    getHandoffMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(makeSession());

    render(<HandoffWorkflow token="tok-1" />);
    await user.click(await screen.findByRole("button", { name: "Retry" }));

    expect(await screen.findByText(TASK)).toBeInTheDocument();
    expect(getHandoffMock).toHaveBeenCalledTimes(2);
    expect(
      screen.queryByRole("heading", { name: "Couldn't reach VelocityAI" })
    ).not.toBeInTheDocument();
  });

  it("keeps the loaded view and shows an offline notice when a refresh fails", async () => {
    getHandoffMock
      .mockResolvedValueOnce(makeSession({ status: "running" }))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));

    render(<HandoffWorkflow token="tok-1" />);
    await screen.findByText(TASK);
    // pipeline_complete flips `done`, which triggers the refresh that fails.
    await act(async () => {
      lastSocketConfig().onMessage({ type: "pipeline_complete", data: {} });
    });

    expect(
      await screen.findByText(/Couldn't reach VelocityAI to refresh this handoff/)
    ).toBeInTheDocument();
    expect(screen.getByText(TASK)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Couldn't reach VelocityAI" })
    ).not.toBeInTheDocument();
  });

  it("keeps the loaded view and shows the server message when a refresh fails with an HTTP error", async () => {
    getHandoffMock
      .mockResolvedValueOnce(makeSession({ status: "running" }))
      .mockRejectedValueOnce(Object.assign(new Error("HTTP 503"), { status: 503 }));

    render(<HandoffWorkflow token="tok-1" />);
    await screen.findByText(TASK);
    await act(async () => {
      lastSocketConfig().onMessage({ type: "pipeline_complete", data: {} });
    });

    expect(await screen.findByText("HTTP 503")).toBeInTheDocument();
    expect(screen.getByText(TASK)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Handoff not found" })).not.toBeInTheDocument();
  });
});

describe("HandoffWorkflow header", () => {
  it("shows the client, mode, task, repository and an Integrations link", async () => {
    await renderHandoff(makeSession());

    expect(screen.getByText("Handoff workflow · claude-code · auto")).toBeInTheDocument();
    expect(screen.getByText(TASK)).toBeInTheDocument();
    expect(screen.getByText(REPO)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Integrations" })).toHaveAttribute(
      "href",
      "/handoff/settings"
    );
  });

  it("shows unknown client, the resolved mode and the source branch when present", async () => {
    await renderHandoff(
      makeSession({ source_client: null, resolved_mode: "coding", source_branch: "main" })
    );

    expect(screen.getByText("Handoff workflow · unknown · auto → coding")).toBeInTheDocument();
    expect(screen.getByText(`${REPO} · main`)).toBeInTheDocument();
  });

  it("links the back control to the dashboard", async () => {
    await renderHandoff(makeSession());

    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/dashboard");
  });

  it.each([
    ["pending", "Pipeline pending"],
    ["running", "Pipeline running"],
  ] as const)("labels the pipeline as %s in the agent panel", async (status, label) => {
    await renderHandoff(makeSession({ status }));

    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

describe("HandoffWorkflow start pipeline", () => {
  it("shows an enabled Start pipeline button for a pending session with a GitHub PAT", async () => {
    await renderHandoff(makeSession());

    expect(screen.getByRole("button", { name: "Start pipeline" })).toBeEnabled();
  });

  it("starts the pipeline with both tokens and shows the running state when Start pipeline is clicked", async () => {
    const user = userEvent.setup();
    await renderHandoff(makeSession());
    getHandoffMock.mockResolvedValueOnce(makeSession({ status: "running" }));

    await user.click(screen.getByRole("button", { name: "Start pipeline" }));

    expect(await screen.findByText("Pipeline running")).toBeInTheDocument();
    expect(startHandoffMock).toHaveBeenCalledWith("test-jwt", "tok-1");
    expect(screen.queryByRole("button", { name: /Start pipeline|Retry pipeline/ })).not.toBeInTheDocument();
  });

  it("disables the button and labels it Starting... while the start request is pending", async () => {
    const user = userEvent.setup();
    const pending = deferred<{ status: string; started_at: string }>();
    startHandoffMock.mockReturnValue(pending.promise);
    await renderHandoff(makeSession());
    getHandoffMock.mockResolvedValueOnce(makeSession({ status: "running" }));

    await user.click(screen.getByRole("button", { name: "Start pipeline" }));

    expect(await screen.findByRole("button", { name: "Starting..." })).toBeDisabled();

    await act(async () => {
      pending.resolve({ status: "running", started_at: "2030-01-01T00:00:00Z" });
    });
    expect(await screen.findByText("Pipeline running")).toBeInTheDocument();
  });

  it("shows the error and re-enables the button without re-fetching when starting fails", async () => {
    const user = userEvent.setup();
    startHandoffMock.mockRejectedValue(new Error("GitHub rate limited"));
    await renderHandoff(makeSession());

    await user.click(screen.getByRole("button", { name: "Start pipeline" }));

    expect(await screen.findByText("GitHub rate limited")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Start pipeline" })).toBeEnabled());
    expect(getHandoffMock).toHaveBeenCalledTimes(1);
  });

  it("shows the default start error when the rejection is not an Error", async () => {
    const user = userEvent.setup();
    startHandoffMock.mockRejectedValue("nope");
    await renderHandoff(makeSession());

    await user.click(screen.getByRole("button", { name: "Start pipeline" }));

    expect(await screen.findByText("Failed to start pipeline")).toBeInTheDocument();
  });

  it("offers Retry pipeline for a failed session and restarts it when clicked", async () => {
    const user = userEvent.setup();
    await renderHandoff(makeSession({ status: "failed" }));
    getHandoffMock.mockResolvedValueOnce(makeSession({ status: "running" }));

    await user.click(screen.getByRole("button", { name: "Retry pipeline" }));

    expect(await screen.findByText("Pipeline running")).toBeInTheDocument();
    expect(startHandoffMock).toHaveBeenCalledWith("test-jwt", "tok-1");
  });

  it.each(["running", "completed"] as const)(
    "offers no start control when the session is %s",
    async (status) => {
      await renderHandoff(makeSession({ status }));

      expect(
        screen.queryByRole("button", { name: /Start pipeline|Retry pipeline/ })
      ).not.toBeInTheDocument();
    }
  );
});

describe("HandoffWorkflow onboarding and expiry", () => {
  it("shows GitHub PAT onboarding with the integrations card and no pipeline or start control when no PAT is saved", async () => {
    await renderHandoff(makeSession({ has_github_pat: false }));

    expect(
      screen.getByRole("heading", { name: "One more step before this can run" })
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "GitHub access token" })).toBeInTheDocument();
    expect(await screen.findByText("No GitHub token saved yet.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Handoff pipeline" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start pipeline" })).not.toBeInTheDocument();
  });

  it("shows the expired notice and no start control when the status is expired", async () => {
    await renderHandoff(makeSession({ status: "expired" }));

    expect(screen.getByRole("heading", { name: "This handoff has expired" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start pipeline" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Handoff pipeline" })).not.toBeInTheDocument();
  });

  it("shows the expired notice when a Z-suffixed expires_at is in the past", async () => {
    await renderHandoff(makeSession({ expires_at: `${PAST_EXPIRY}Z` }));

    expect(screen.getByRole("heading", { name: "This handoff has expired" })).toBeInTheDocument();
  });

  it("shows the expired notice instead of onboarding when no PAT is saved and expires_at is in the past", async () => {
    await renderHandoff(makeSession({ has_github_pat: false, expires_at: PAST_EXPIRY }));

    expect(screen.getByRole("heading", { name: "This handoff has expired" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "One more step before this can run" })
    ).not.toBeInTheDocument();
  });

  it("treats a timezone-less expires_at as UTC when deciding expiry", async () => {
    // Auckland is UTC+13 in January: read as LOCAL time, 13:00 would already be
    // past (00:00Z) at the fixed "now"; read as UTC it is still 30 minutes away.
    process.env.TZ = "Pacific/Auckland";
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2030-01-01T12:30:00Z"));

    await renderHandoff(makeSession({ expires_at: "2030-01-01T13:00:00" }));

    expect(screen.getByRole("heading", { name: "Handoff pipeline" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "This handoff has expired" })
    ).not.toBeInTheDocument();
  });
});

describe("HandoffWorkflow persisted-output hydration", () => {
  it("replays the coding summary and applied edit into the Diff tab for a completed handoff", async () => {
    await renderHandoff(
      completedSession({ coding_summary: CODING_SUMMARY, edit_results: EDIT_RESULTS })
    );

    expect(screen.getByText("Added retry with backoff")).toBeInTheDocument();
    expect(screen.getByText("Proposed file changes (1)")).toBeInTheDocument();
    expect(screen.getByText("src/upload.py")).toBeInTheDocument();
    expect(screen.getByText("APPLIED")).toBeInTheDocument();
    expect(screen.getByText("tests/test_upload.py")).toBeInTheDocument();
    expect(screen.getByText("Add jitter to the backoff")).toBeInTheDocument();
  });

  it("marks edits as PROPOSED when persisted edit_results is not an array", async () => {
    await renderHandoff(
      completedSession({ coding_summary: CODING_SUMMARY, edit_results: "bogus" })
    );

    expect(screen.getByText("PROPOSED")).toBeInTheDocument();
    expect(screen.queryByText("APPLIED")).not.toBeInTheDocument();
  });

  it("completes the coding agent with empty defaults when the persisted summary has no fields", async () => {
    await renderHandoff(completedSession({ coding_summary: {} }));

    expect(screen.getByText("DONE")).toBeInTheDocument();
    expect(screen.getByText(/No file edits proposed yet/)).toBeInTheDocument();
  });

  it("leaves every agent queued when the persisted coding_summary is not an object", async () => {
    await renderHandoff(completedSession({ coding_summary: "not-an-object" }));

    expect(screen.getAllByText("Waiting...")).toHaveLength(3);
  });

  it("shows the persisted test report", async () => {
    await renderHandoff(completedSession({ test_report: TEST_REPORT }));

    expect(screen.getByRole("heading", { name: "Test coverage report" })).toBeInTheDocument();
    expect(screen.getByText("concerns")).toBeInTheDocument();
    expect(screen.getByText("Missing coverage (1)")).toBeInTheDocument();
    expect(screen.getByText("Upload timeout")).toBeInTheDocument();
  });

  it("shows the persisted compliance report", async () => {
    await renderHandoff(completedSession({ compliance_report: COMPLIANCE_REPORT }));

    expect(screen.getByRole("heading", { name: "Compliance review" })).toBeInTheDocument();
    expect(screen.getByText("approve with changes")).toBeInTheDocument();
    expect(screen.getByText("Findings (1)")).toBeInTheDocument();
    expect(screen.getByText("Token logged in plaintext")).toBeInTheDocument();
    expect(screen.getByText("Small, focused diff")).toBeInTheDocument();
  });

  it("shows the pull request strip with branch and link from persisted PR data", async () => {
    await renderHandoff(
      completedSession({
        pr_url: "https://github.com/acme/app/pull/42",
        pr_number: 42,
        branch_name: "flowin/retry-upload",
        resolved_mode: "coding",
      })
    );

    expect(screen.getByText("Draft pull request opened")).toBeInTheDocument();
    expect(screen.getByText("flowin/retry-upload")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View PR #42/ })).toHaveAttribute(
      "href",
      "https://github.com/acme/app/pull/42"
    );
  });

  it.each([
    ["only a PR url", { pr_url: "https://github.com/acme/app/pull/42" }],
    ["only a PR number", { pr_number: 42 }],
  ])("shows no pull request strip when persisted output has %s", async (_label, output) => {
    await renderHandoff(completedSession(output));

    expect(screen.queryByText("Draft pull request opened")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /View PR/ })).not.toBeInTheDocument();
  });

  it("labels the pipeline complete with no finished agents when a completed session has no output", async () => {
    await renderHandoff(completedSession(null));

    expect(screen.getByText("Pipeline complete")).toBeInTheDocument();
    expect(screen.getByText("0/3")).toBeInTheDocument();
  });

  it("labels the pipeline failed and offers Retry pipeline when a failed session has persisted output", async () => {
    await renderHandoff(
      makeSession({ status: "failed", pipeline_output: { coding_summary: CODING_SUMMARY } })
    );

    expect(screen.getByText("Pipeline failed")).toBeInTheDocument();
    expect(screen.getByText("Added retry with backoff")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry pipeline" })).toBeEnabled();
  });

  it("re-fetches a finished session exactly once after replaying its output", async () => {
    await renderHandoff(completedSession({ coding_summary: CODING_SUMMARY }));

    expect(getHandoffMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText(TASK)).toBeInTheDocument();
  });
});

describe("HandoffWorkflow preview selection", () => {
  const fullOutput = {
    coding_summary: CODING_SUMMARY,
    edit_results: EDIT_RESULTS,
    test_report: TEST_REPORT,
    compliance_report: COMPLIANCE_REPORT,
  };

  it("auto-follows to the compliance report when every agent has finished", async () => {
    await renderHandoff(completedSession(fullOutput));

    expect(screen.getByRole("heading", { name: "Compliance review" })).toBeInTheDocument();
  });

  it("switches the preview to the test report when the Test analysis agent card is clicked", async () => {
    const user = userEvent.setup();
    await renderHandoff(completedSession(fullOutput));

    await user.click(screen.getByRole("button", { name: /Test analysis/ }));

    expect(screen.getByRole("heading", { name: "Test coverage report" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Compliance review" })).not.toBeInTheDocument();
  });

  it("switches the preview to the Diff when the Diff tab is clicked", async () => {
    const user = userEvent.setup();
    await renderHandoff(completedSession(fullOutput));

    await user.click(screen.getByRole("button", { name: "Diff" }));

    expect(screen.getByText("Proposed file changes (1)")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Compliance review" })).not.toBeInTheDocument();
  });
});

describe("HandoffWorkflow live socket", () => {
  it("connects to the encoded handoff socket URL with the auth token while the session is running", async () => {
    await renderHandoff(makeSession({ status: "running" }), "a/b c");

    expect(lastSocketConfig().url).toBe("wss://api.example.test/ws/handoff/a%2Fb%20c");
    expect(lastSocketConfig().token).toBe("test-jwt");
  });

  it.each(["pending", "failed"] as const)(
    "gives the socket no token when the session is %s",
    async (status) => {
      await renderHandoff(makeSession({ status }));

      expect(lastSocketConfig().token).toBeNull();
    }
  );

  it("shows the thinking agent as RUNNING when the socket delivers agent_thinking", async () => {
    getHandoffMock.mockResolvedValue(makeSession({ status: "running" }));
    render(<HandoffWorkflow token="tok-1" />);
    await screen.findByText(TASK);

    await act(async () => {
      lastSocketConfig().onMessage({
        type: "agent_thinking",
        data: { agent_id: "coding_agent", thinking: "Reading the repo" },
      });
    });

    expect(screen.getByText("RUNNING")).toBeInTheDocument();
    expect(screen.getByText("Reading the repo")).toBeInTheDocument();
  });

  it("logs a phase when the socket delivers a message without data", async () => {
    getHandoffMock.mockResolvedValue(makeSession({ status: "running" }));
    render(<HandoffWorkflow token="tok-1" />);
    await screen.findByText(TASK);

    await act(async () => {
      lastSocketConfig().onMessage({ type: "phase_start", section: "clone_repo" });
    });

    expect(screen.getByText("clone_repo")).toBeInTheDocument();
  });

  it("shows the PR strip and drops the socket token when the socket reports pipeline_complete", async () => {
    getHandoffMock.mockResolvedValue(makeSession({ status: "running" }));
    render(<HandoffWorkflow token="tok-1" />);
    await screen.findByText(TASK);

    await act(async () => {
      lastSocketConfig().onMessage({
        type: "pipeline_complete",
        data: {
          resolved_mode: "coding",
          branch_name: "flowin/retry-upload",
          pr_url: "https://github.com/acme/app/pull/7",
          pr_number: 7,
        },
      });
    });

    expect(await screen.findByRole("link", { name: /View PR #7/ })).toHaveAttribute(
      "href",
      "https://github.com/acme/app/pull/7"
    );
    expect(lastSocketConfig().token).toBeNull();
  });

  it("shows the pipeline error when the socket reports handoff_error", async () => {
    getHandoffMock
      .mockResolvedValueOnce(makeSession({ status: "running" }))
      .mockResolvedValueOnce(makeSession({ status: "failed" }));
    render(<HandoffWorkflow token="tok-1" />);
    await screen.findByText(TASK);

    await act(async () => {
      // handoff_error is emitted by the backend but is not in the shared
      // StreamMessage union, so it needs an explicit cast here.
      lastSocketConfig().onMessage({
        type: "handoff_error" as unknown as StreamMessage["type"],
        data: { message: "Clone failed" },
      });
    });
    await waitFor(() => expect(getHandoffMock).toHaveBeenCalledTimes(2));

    expect((await screen.findAllByText("Clone failed")).length).toBeGreaterThan(0);
  });
});
