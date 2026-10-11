/**
 * SecuritySection — second-factor management tab.
 *
 * Boundaries mocked: `@/lib/api` (token + MFA endpoints) and `next/navigation`
 * (router). Everything else — error-message selection, the load/error/ready
 * state machine, the toggle lock and the panel variants — runs for real.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const api = vi.hoisted(() => ({
  getToken: vi.fn(),
  getMfaStatus: vi.fn(),
  enableEmailMfa: vi.fn(),
  disableEmailMfa: vi.fn(),
}));

vi.mock("@/lib/api", () => {
  // Mirrors the real ApiError shape (status + detail + message) that
  // SecuritySection's describeError reads.
  class ApiError extends Error {
    status: number;
    detail: unknown;
    constructor(status: number, detail: unknown, message = "") {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  }
  return {
    ApiError,
    getToken: () => api.getToken(),
    getMfaStatus: (t: string) => api.getMfaStatus(t),
    enableEmailMfa: (t: string) => api.enableEmailMfa(t),
    disableEmailMfa: (t: string) => api.disableEmailMfa(t),
  };
});

// Stable singleton: a fresh router per render would re-create `load` and
// re-fire the fetch effect, which is a harness artifact (real identity is stable).
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { ApiError, type MfaStatus } from "@/lib/api";
import { SecuritySection } from "./SecuritySection";

const LOGIN_REDIRECT = "/login?redirect=%2F";

function mfaStatus(overrides: Partial<MfaStatus> = {}): MfaStatus {
  return {
    supported: true,
    enabled: false,
    required: false,
    email_available: true,
    factors: [],
    ...overrides,
  } as MfaStatus;
}

// ApiError is the mocked class above; widen its constructor for test use.
const MockApiError = ApiError as unknown as new (
  status: number,
  detail: unknown,
  message?: string,
) => Error;

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMfaStatus.mockResolvedValue(mfaStatus());
  api.enableEmailMfa.mockResolvedValue({ message: "Email codes are on.", factors: ["EMAIL_OTP"] });
  api.disableEmailMfa.mockResolvedValue({ message: "Email codes are off.", factors: [] });
});

describe("SecuritySection — loading and session handling", () => {
  it("shows a loading placeholder until MFA status resolves", async () => {
    let resolve!: (s: MfaStatus) => void;
    api.getMfaStatus.mockReturnValue(new Promise<MfaStatus>((r) => (resolve = r)));
    render(<SecuritySection />);

    expect(screen.getByText("Loading your security settings…")).toBeInTheDocument();

    await act(async () => resolve(mfaStatus()));

    expect(screen.queryByText("Loading your security settings…")).toBeNull();
    expect(await screen.findByText("Two-factor authentication")).toBeInTheDocument();
  });

  it("redirects to login without calling the API when there is no token", async () => {
    api.getToken.mockReturnValue(null);
    render(<SecuritySection />);

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(LOGIN_REDIRECT));
    expect(api.getMfaStatus).not.toHaveBeenCalled();
  });

  it("redirects to login when the status call returns 401", async () => {
    api.getMfaStatus.mockRejectedValue(new MockApiError(401, "expired"));
    render(<SecuritySection />);

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(LOGIN_REDIRECT));
    expect(screen.queryByText("Couldn't load your settings")).toBeNull();
  });
});

describe("SecuritySection — load errors", () => {
  it("shows the server's string detail when the status call fails", async () => {
    api.getMfaStatus.mockRejectedValue(new MockApiError(409, "Pool is not configured for MFA."));
    render(<SecuritySection />);

    expect(await screen.findByText("Couldn't load your settings")).toBeInTheDocument();
    expect(screen.getByText("Pool is not configured for MFA.")).toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("shows detail.message when the detail is an object with a string message", async () => {
    api.getMfaStatus.mockRejectedValue(new MockApiError(500, { message: "Upstream unavailable." }));
    render(<SecuritySection />);

    expect(await screen.findByText("Upstream unavailable.")).toBeInTheDocument();
  });

  it("falls back to the error's own message when detail has no usable message", async () => {
    api.getMfaStatus.mockRejectedValue(new MockApiError(500, { message: 42 }, "Request failed (500)"));
    render(<SecuritySection />);

    expect(await screen.findByText("Request failed (500)")).toBeInTheDocument();
  });

  it("falls back to the generic copy when an ApiError carries no message at all", async () => {
    api.getMfaStatus.mockRejectedValue(new MockApiError(500, null, ""));
    render(<SecuritySection />);

    expect(await screen.findByText("Could not load your security settings.")).toBeInTheDocument();
  });

  it("falls back to the generic copy for a non-ApiError failure", async () => {
    api.getMfaStatus.mockRejectedValue(new Error("network down"));
    render(<SecuritySection />);

    expect(await screen.findByText("Could not load your security settings.")).toBeInTheDocument();
    expect(screen.queryByText("network down")).toBeNull();
  });

  it("reloads and shows the panel when 'Try again' is pressed after a failure", async () => {
    const user = userEvent.setup();
    api.getMfaStatus.mockRejectedValueOnce(new Error("boom"));
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: /try again/i }));

    expect(await screen.findByText("Two-factor authentication")).toBeInTheDocument();
    expect(api.getMfaStatus).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Couldn't load your settings")).toBeNull();
  });

  it("returns to the loading state while a retry is in flight", async () => {
    const user = userEvent.setup();
    api.getMfaStatus.mockRejectedValueOnce(new Error("boom"));
    api.getMfaStatus.mockReturnValueOnce(new Promise(() => {}));
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: /try again/i }));

    expect(screen.getByText("Loading your security settings…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });
});

describe("SecuritySection — panel variants", () => {
  it("explains that a local account has no factors to manage", async () => {
    api.getMfaStatus.mockResolvedValue(mfaStatus({ supported: false }));
    render(<SecuritySection />);

    expect(await screen.findByText("Not available for this account")).toBeInTheDocument();
    expect(screen.getByText(/This is a local account/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /turn (on|off)/i })).toBeNull();
  });

  it("shows the off state with an enabled 'Turn on' control when nothing is enabled", async () => {
    render(<SecuritySection />);

    expect(await screen.findByText(/Not set up\. Your password is the only thing/)).toBeInTheDocument();
    expect(screen.getByText("Off")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn on" })).toBeEnabled();
    expect(screen.getByText(/We'll email a 6-digit code each time you sign in\. Nothing to install\./)).toBeInTheDocument();
    expect(screen.queryByText("Active")).toBeNull();
  });

  it("shows the active state with 'Turn off' and the required-role notice", async () => {
    api.getMfaStatus.mockResolvedValue(
      mfaStatus({ enabled: true, required: true, factors: ["EMAIL_OTP"] }),
    );
    render(<SecuritySection />);

    expect(await screen.findByText(/Active\. You'll be asked for a code/)).toBeInTheDocument();
    expect(screen.getByText("On")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn off" })).toBeInTheDocument();
    expect(screen.getByText("We email a 6-digit code each time you sign in.")).toBeInTheDocument();
    expect(screen.getByText(/Your role requires a second factor/)).toBeInTheDocument();
  });

  it("omits the required-role notice when a second factor is optional", async () => {
    render(<SecuritySection />);

    await screen.findByText("Two-factor authentication");
    expect(screen.queryByText(/Your role requires a second factor/)).toBeNull();
  });

  it("marks the authenticator app active and has no control for it when TOTP is enrolled", async () => {
    api.getMfaStatus.mockResolvedValue(
      mfaStatus({ enabled: true, factors: ["SOFTWARE_TOKEN_MFA"] }),
    );
    render(<SecuritySection />);

    expect(await screen.findByText("A time-based code from your authenticator app.")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    // Only the email toggle exists; the authenticator row is informational.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("tells the user set-up is administrator-managed when TOTP is not enrolled", async () => {
    render(<SecuritySection />);

    expect(
      await screen.findByText(/Set-up is handled by your administrator\./),
    ).toBeInTheDocument();
  });

  it("hides the email row and explains there is no method when email codes are unavailable and no TOTP", async () => {
    api.getMfaStatus.mockResolvedValue(mfaStatus({ email_available: false }));
    render(<SecuritySection />);

    expect(await screen.findByText(/No two-factor methods are enabled for this environment/)).toBeInTheDocument();
    expect(screen.queryByText("Email codes")).toBeNull();
    expect(screen.queryByRole("button", { name: /turn (on|off)/i })).toBeNull();
    expect(screen.queryByText(/password resets are handled by an administrator/)).toBeNull();
  });

  it("does not show the 'no methods' message when email is unavailable but TOTP is on", async () => {
    api.getMfaStatus.mockResolvedValue(
      mfaStatus({ email_available: false, enabled: true, factors: ["SOFTWARE_TOKEN_MFA"] }),
    );
    render(<SecuritySection />);

    await screen.findByText("Two-factor authentication");
    expect(screen.queryByText(/No two-factor methods are enabled/)).toBeNull();
  });

  it("adds the password-reset footnote when email codes are available", async () => {
    render(<SecuritySection />);

    expect(
      await screen.findByText(/password resets are handled by an administrator rather than by email/),
    ).toBeInTheDocument();
  });
});

describe("SecuritySection — toggling email codes", () => {
  it("enables email codes and shows the server's resulting factor state", async () => {
    const user = userEvent.setup();
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn on" }));

    expect(api.enableEmailMfa).toHaveBeenCalledWith("tok");
    expect(await screen.findByRole("button", { name: "Turn off" })).toBeInTheDocument();
    expect(screen.getByText("On")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(/Active\. You'll be asked for a code/)).toBeInTheDocument();
  });

  it("announces the outcome in the polite live region", async () => {
    const user = userEvent.setup();
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn on" }));
    await screen.findByRole("button", { name: "Turn off" });

    // Once in the visible banner and once in the sr-only aria-live announcer.
    expect(screen.getAllByText("Email codes are on.")).toHaveLength(2);
  });

  it("disables email codes and turns the account back to off when no factors remain", async () => {
    const user = userEvent.setup();
    api.getMfaStatus.mockResolvedValue(mfaStatus({ enabled: true, factors: ["EMAIL_OTP"] }));
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn off" }));

    expect(api.disableEmailMfa).toHaveBeenCalledWith("tok");
    expect(api.enableEmailMfa).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Turn on" })).toBeInTheDocument();
    expect(screen.getByText("Off")).toBeInTheDocument();
    expect(screen.getByText(/Not set up/)).toBeInTheDocument();
  });

  it("keeps the account 'on' when other factors remain after turning email off", async () => {
    const user = userEvent.setup();
    api.getMfaStatus.mockResolvedValue(
      mfaStatus({ enabled: true, factors: ["EMAIL_OTP", "SOFTWARE_TOKEN_MFA"] }),
    );
    api.disableEmailMfa.mockResolvedValue({
      message: "Email codes are off.",
      factors: ["SOFTWARE_TOKEN_MFA"],
    });
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn off" }));

    expect(await screen.findByRole("button", { name: "Turn on" })).toBeInTheDocument();
    expect(screen.getByText("On")).toBeInTheDocument();
  });

  it("disables the control and shows 'Saving…' while the write is in flight", async () => {
    const user = userEvent.setup();
    let resolve!: (v: { message: string; factors: string[] }) => void;
    api.enableEmailMfa.mockReturnValue(new Promise((r) => (resolve = r)));
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn on" }));

    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();

    await act(async () => resolve({ message: "Email codes are on.", factors: ["EMAIL_OTP"] }));

    expect(await screen.findByRole("button", { name: "Turn off" })).toBeEnabled();
  });

  it("ignores a second click that lands before React re-renders (ISS-354 lock)", async () => {
    let resolve!: (v: { message: string; factors: string[] }) => void;
    api.enableEmailMfa.mockReturnValue(new Promise((r) => (resolve = r)));
    render(<SecuritySection />);
    const button = await screen.findByRole("button", { name: "Turn on" });

    // user-event cannot express two clicks inside one un-flushed task; fireEvent
    // inside a single act() reproduces the pre-commit window the ref guards.
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });

    expect(api.enableEmailMfa).toHaveBeenCalledTimes(1);

    await act(async () => resolve({ message: "Email codes are on.", factors: ["EMAIL_OTP"] }));
  });

  it("allows another toggle after the first one completes", async () => {
    const user = userEvent.setup();
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn on" }));
    await user.click(await screen.findByRole("button", { name: "Turn off" }));

    expect(api.enableEmailMfa).toHaveBeenCalledTimes(1);
    expect(api.disableEmailMfa).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("button", { name: "Turn on" })).toBeInTheDocument();
  });

  it("shows the server's explanation and keeps the previous state when the write fails", async () => {
    const user = userEvent.setup();
    api.getMfaStatus.mockResolvedValue(mfaStatus({ enabled: true, required: true, factors: ["EMAIL_OTP"] }));
    api.disableEmailMfa.mockRejectedValue(
      new MockApiError(409, "An admin must keep at least one factor."),
    );
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn off" }));

    const notices = await screen.findAllByText("An admin must keep at least one factor.");
    expect(notices.length).toBeGreaterThan(0);
    // State is unchanged and the control is usable again for a retry.
    expect(screen.getByRole("button", { name: "Turn off" })).toBeEnabled();
    expect(screen.getByText("On")).toBeInTheDocument();
  });

  it("uses generic save-failure copy for a non-ApiError rejection", async () => {
    const user = userEvent.setup();
    api.enableEmailMfa.mockRejectedValue(new Error("socket hang up"));
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn on" }));

    expect((await screen.findAllByText("That change could not be saved. Please try again.")).length).toBeGreaterThan(0);
    expect(screen.queryByText("socket hang up")).toBeNull();
  });

  it("clears a previous notice when the next toggle starts", async () => {
    const user = userEvent.setup();
    api.enableEmailMfa.mockRejectedValueOnce(new Error("first fails"));
    render(<SecuritySection />);

    await user.click(await screen.findByRole("button", { name: "Turn on" }));
    await screen.findAllByText("That change could not be saved. Please try again.");

    await user.click(screen.getByRole("button", { name: "Turn on" }));
    await screen.findByRole("button", { name: "Turn off" });

    expect(screen.queryByText("That change could not be saved. Please try again.")).toBeNull();
  });

  it("redirects to login and does not write when the token has gone by the time of the toggle", async () => {
    const user = userEvent.setup();
    render(<SecuritySection />);
    const button = await screen.findByRole("button", { name: "Turn on" });

    api.getToken.mockReturnValue(null);
    await user.click(button);

    expect(router.replace).toHaveBeenCalledWith(LOGIN_REDIRECT);
    expect(api.enableEmailMfa).not.toHaveBeenCalled();

    // The lock was released: restoring the token lets the toggle work again.
    api.getToken.mockReturnValue("tok");
    await user.click(screen.getByRole("button", { name: "Turn on" }));
    expect(api.enableEmailMfa).toHaveBeenCalledWith("tok");
  });

  it("scopes the email description to the toggle for assistive technology", async () => {
    render(<SecuritySection />);

    const button = await screen.findByRole("button", { name: "Turn on" });

    expect(button).toHaveAccessibleDescription(/We'll email a 6-digit code each time you sign in/);
  });
});
