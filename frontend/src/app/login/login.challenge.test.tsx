/**
 * ChallengeForm + challenge handler of login/page.tsx, driven through
 * LoginPage: login() resolves a challenge, then the challenge step is used.
 * Boundaries mocked: next/navigation, @/lib/api transport (real ApiError and
 * isAuthChallenge kept), motion/react (animation shell).
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { routerMock, mockSearchParams, getTokenMock, loginMock, respondMock } = vi.hoisted(() => ({
  routerMock: { push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() },
  mockSearchParams: { current: new URLSearchParams() },
  getTokenMock: vi.fn(),
  loginMock: vi.fn(),
  respondMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  useSearchParams: () => mockSearchParams.current,
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: getTokenMock,
  login: loginMock,
  respondToLoginChallenge: respondMock,
}));

const STRIPPED = new Set(["initial", "animate", "exit", "transition"]);
vi.mock("motion/react", () => {
  // Cached per tag so re-renders do not remount the subtree.
  const cache = new Map<string, React.ComponentType<Record<string, unknown>>>();
  return {
    motion: new Proxy(
      {},
      {
        get: (_t, prop: string) => {
          if (!cache.has(prop)) {
            cache.set(prop, ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
              React.createElement(
                prop,
                Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))),
                children,
              ),
            );
          }
          return cache.get(prop);
        },
      },
    ),
  };
});

import { ApiError } from "@/lib/api";
import LoginPage from "./page";

type User = ReturnType<typeof userEvent.setup>;

const OK = { token: "tok", user: { id: "1", email: "a@b.com", tier: "basic", is_admin: false } };
const STRONG = "a-long-password-1";

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function reachChallenge(user: User, challenge: Record<string, unknown>) {
  loginMock.mockResolvedValue({ session: "sess-1", ...challenge });
  render(<LoginPage />);
  await screen.findByLabelText("Email");
  await user.type(screen.getByLabelText("Email"), "Foo@Bar.com");
  await user.type(screen.getByLabelText("Password"), "secret123");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByRole("button", { name: "Back to sign in" });
}

function challengeForm() {
  return screen.getByRole("button", { name: "Back to sign in" }).closest("form")!;
}

beforeEach(() => {
  routerMock.push.mockReset();
  routerMock.replace.mockReset();
  loginMock.mockReset();
  respondMock.mockReset();
  getTokenMock.mockReset();
  getTokenMock.mockReturnValue(null);
  mockSearchParams.current = new URLSearchParams();
});

describe("ChallengeForm — copy", () => {
  it.each([
    ["NEW_PASSWORD_REQUIRED", "Set a new password"],
    ["SOFTWARE_TOKEN_MFA", "Enter your authentication code"],
    ["EMAIL_OTP", "Check your email"],
    ["SELECT_MFA_TYPE", "Choose a verification method"],
    ["MFA_SETUP", "Two-factor setup required"],
  ])("shows the %s heading", async (kind, heading) => {
    await reachChallenge(userEvent.setup(), { challenge: kind });
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("labels the code field per factor", async () => {
    await reachChallenge(userEvent.setup(), { challenge: "SOFTWARE_TOKEN_MFA" });
    expect(screen.getByLabelText("Authentication code")).toBeInTheDocument();
  });

  it("names the masked mailbox for EMAIL_OTP when delivery is provided", async () => {
    await reachChallenge(userEvent.setup(), { challenge: "EMAIL_OTP", delivery: "j***@e***.com" });
    expect(screen.getByText(/We sent a 6-digit code to j\*\*\*@e\*\*\*\.com/)).toBeInTheDocument();
  });

  it("uses the generic EMAIL_OTP subtitle without delivery", async () => {
    await reachChallenge(userEvent.setup(), { challenge: "EMAIL_OTP" });
    expect(
      screen.getByText("We sent you a 6-digit code. Enter it below to finish signing in."),
    ).toBeInTheDocument();
  });

  it("falls back to generic copy for an unknown challenge kind", async () => {
    await reachChallenge(userEvent.setup(), { challenge: "SOMETHING_NEW" });
    expect(
      screen.getByRole("heading", { name: "Additional verification required" }),
    ).toBeInTheDocument();
  });
});

describe("ChallengeForm — NEW_PASSWORD_REQUIRED", () => {
  async function setup() {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "NEW_PASSWORD_REQUIRED" });
    return user;
  }

  it("rejects an 11-character password", async () => {
    await setup();
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a".repeat(11) } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "a".repeat(11) } });
    // fireEvent: jsdom's minLength constraint validation would pre-empt the handler.
    fireEvent.submit(challengeForm());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "New password must be at least 12 characters.",
    );
    expect(respondMock).not.toHaveBeenCalled();
  });

  it("accepts exactly 12 matching characters and redirects", async () => {
    const user = await setup();
    respondMock.mockResolvedValue(OK);
    const pw = "a".repeat(12);
    await user.type(screen.getByLabelText("New password"), pw);
    await user.type(screen.getByLabelText("Confirm password"), pw);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/dashboard"));
    expect(respondMock).toHaveBeenCalledWith("foo@bar.com", "sess-1", "NEW_PASSWORD_REQUIRED", {
      newPassword: pw,
      mfaCode: undefined,
      selectedFactor: undefined,
    });
  });

  it("rejects mismatched passwords", async () => {
    const user = await setup();
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm password"), STRONG + "x");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(respondMock).not.toHaveBeenCalled();
  });

  it("reports the length error before the mismatch error", async () => {
    await setup();
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "other" } });
    fireEvent.submit(challengeForm());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "New password must be at least 12 characters.",
    );
  });

  it("honors a safe ?redirect= after challenge success", async () => {
    mockSearchParams.current = new URLSearchParams("redirect=%2Fhistory");
    const user = await setup();
    respondMock.mockResolvedValue(OK);
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm password"), STRONG);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/history"));
  });

  it("falls back to /dashboard for an unsafe ?redirect= after challenge success", async () => {
    mockSearchParams.current = new URLSearchParams({ redirect: "//evil.com" });
    const user = await setup();
    respondMock.mockResolvedValue(OK);
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm password"), STRONG);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/dashboard"));
  });

  it("clears a stale validation banner when either field is edited", async () => {
    const user = await setup();
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm password"), "different-value-1");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("alert");
    await user.type(screen.getByLabelText("Confirm password"), "x");
    expect(screen.queryByRole("alert")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("alert");
    await user.type(screen.getByLabelText("New password"), "y");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("gives both password fields a labelled visibility toggle", async () => {
    const user = await setup();
    const toggles = screen.getAllByRole("button", { name: "Show password" });
    expect(toggles).toHaveLength(2);
    await user.click(toggles[0]);
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("type", "password");
  });
});

describe("ChallengeForm — code challenges", () => {
  it.each([
    ["EMAIL_OTP", "Email code", "Enter the 6-digit code we emailed you."],
    ["SOFTWARE_TOKEN_MFA", "Authentication code", "Enter the 6-digit code from your authenticator app."],
  ])("%s rejects a whitespace-only code with a specific message", async (kind, label, message) => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: kind });
    await user.type(screen.getByLabelText(label), "   ");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(respondMock).not.toHaveBeenCalled();
  });

  it("passes the code as mfaCode only", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "SOFTWARE_TOKEN_MFA" });
    respondMock.mockResolvedValue(OK);
    await user.type(screen.getByLabelText("Authentication code"), "654321");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/dashboard"));
    expect(respondMock).toHaveBeenCalledWith("foo@bar.com", "sess-1", "SOFTWARE_TOKEN_MFA", {
      newPassword: undefined,
      mfaCode: "654321",
      selectedFactor: undefined,
    });
  });

  it("marks the code field for numeric one-time-code entry", async () => {
    await reachChallenge(userEvent.setup(), { challenge: "EMAIL_OTP" });
    const field = screen.getByLabelText("Email code");
    expect(field).toHaveAttribute("inputmode", "numeric");
    expect(field).toHaveAttribute("autocomplete", "one-time-code");
  });
});

describe("ChallengeForm — SELECT_MFA_TYPE", () => {
  it("renders only the offered factor", async () => {
    await reachChallenge(userEvent.setup(), {
      challenge: "SELECT_MFA_TYPE",
      available_factors: ["SOFTWARE_TOKEN_MFA"],
    });
    expect(screen.getByRole("radio", { name: "Use my authenticator app" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Email me a code" })).toBeNull();
  });

  it.each([[null], [undefined], [[]]])("renders both factors when available_factors is %j", async (factors) => {
    await reachChallenge(userEvent.setup(), { challenge: "SELECT_MFA_TYPE", available_factors: factors });
    expect(screen.getByRole("radio", { name: "Email me a code" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Use my authenticator app" })).toBeInTheDocument();
  });

  it("groups the radios under a legend", async () => {
    await reachChallenge(userEvent.setup(), { challenge: "SELECT_MFA_TYPE" });
    expect(screen.getByRole("group", { name: "Verification method" })).toBeInTheDocument();
  });

  it("requires a selection before continuing", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "SELECT_MFA_TYPE" });
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose how you'd like to receive your code.",
    );
    expect(respondMock).not.toHaveBeenCalled();
  });

  it.each([
    ["Email me a code", "EMAIL_MFA"],
    ["Use my authenticator app", "SOFTWARE_TOKEN_MFA"],
  ])("sends %s as %s", async (label, value) => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "SELECT_MFA_TYPE" });
    respondMock.mockResolvedValue(OK);
    await user.click(screen.getByRole("radio", { name: label }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(respondMock).toHaveBeenCalledTimes(1));
    expect(respondMock).toHaveBeenCalledWith("foo@bar.com", "sess-1", "SELECT_MFA_TYPE", {
      newPassword: undefined,
      mfaCode: undefined,
      selectedFactor: value,
    });
  });

  it("selects a radio with the keyboard", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "SELECT_MFA_TYPE" });
    screen.getByRole("radio", { name: "Email me a code" }).focus();
    await user.keyboard(" ");
    expect(screen.getByRole("radio", { name: "Email me a code" })).toBeChecked();
  });
});

describe("ChallengeForm — MFA_SETUP dead end", () => {
  it("explains the situation without a Continue button", async () => {
    await reachChallenge(userEvent.setup(), { challenge: "MFA_SETUP" });
    expect(screen.getByText(/Contact your administrator to finish setup/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
    expect(screen.getByRole("button", { name: "Back to sign in" })).toBeInTheDocument();
  });
});

describe("ChallengeForm — chaining", () => {
  it("shows the next challenge with empty fields and no stale error", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "NEW_PASSWORD_REQUIRED" });
    respondMock.mockResolvedValue({ challenge: "EMAIL_OTP", session: "sess-2" });
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm password"), STRONG);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    const code = await screen.findByLabelText("Email code");
    expect(code).toHaveValue("");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(routerMock.push).not.toHaveBeenCalled();

    respondMock.mockResolvedValue(OK);
    await user.type(code, "111222");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/dashboard"));
    expect(respondMock).toHaveBeenLastCalledWith("foo@bar.com", "sess-2", "EMAIL_OTP", {
      newPassword: undefined,
      mfaCode: "111222",
      selectedFactor: undefined,
    });
  });

  it("clears a previously typed code on the next challenge", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "EMAIL_OTP" });
    respondMock.mockResolvedValue({ challenge: "SOFTWARE_TOKEN_MFA", session: "sess-2" });
    await user.type(screen.getByLabelText("Email code"), "111111");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByLabelText("Authentication code")).toHaveValue("");
  });

  it("clears a previously chosen factor on the next challenge", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "SELECT_MFA_TYPE" });
    respondMock.mockResolvedValue({ challenge: "SELECT_MFA_TYPE", session: "sess-2" });
    await user.click(screen.getByRole("radio", { name: "Email me a code" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(respondMock).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "Email me a code" })).not.toBeChecked(),
    );
  });
});

describe("ChallengeForm — errors and loading", () => {
  it.each([
    [new ApiError(401, null), "Invalid email or password."],
    [new ApiError(400, "Code mismatch"), "Code mismatch"],
    [new Error("boom"), "An unexpected error occurred. Please try again."],
  ])("maps rejection %#", async (err, message) => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "EMAIL_OTP" });
    respondMock.mockRejectedValue(err);
    await user.type(screen.getByLabelText("Email code"), "123456");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    expect(routerMock.push).not.toHaveBeenCalled();
  });

  it("disables the button while verifying", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "EMAIL_OTP" });
    const d = deferred<typeof OK>();
    respondMock.mockReturnValue(d.promise);
    await user.type(screen.getByLabelText("Email code"), "123456");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("button", { name: "Verifying…" })).toBeDisabled();
    d.reject(new ApiError(400, "nope"));
    expect(await screen.findByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("ignores a second same-task submit while verifying", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "EMAIL_OTP" });
    const d = deferred<typeof OK>();
    respondMock.mockReturnValue(d.promise);
    await user.type(screen.getByLabelText("Email code"), "123456");
    // fireEvent: two submits within one task, which only the ref guard can stop.
    fireEvent.submit(challengeForm());
    fireEvent.submit(challengeForm());
    d.resolve(OK);
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledTimes(1));
    expect(respondMock).toHaveBeenCalledTimes(1);
  });
});

describe("ChallengeForm — cancel", () => {
  it("returns to the sign-in form, clears the error and keeps the email", async () => {
    const user = userEvent.setup();
    await reachChallenge(user, { challenge: "EMAIL_OTP" });
    // whitespace satisfies `required` but not the handler's trim check
    await user.type(screen.getByLabelText("Email code"), " ");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByLabelText("Email")).toHaveValue("foo@bar.com");
    expect(respondMock).not.toHaveBeenCalled();
  });
});
