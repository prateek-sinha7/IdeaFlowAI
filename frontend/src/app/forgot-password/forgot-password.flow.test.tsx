/**
 * forgot-password/page.tsx — gaps beyond forgot-password.test.tsx: request
 * step states, confirm-step rendering, validation boundaries, submit errors.
 * Boundaries mocked: next/navigation, @/lib/api transport (real ApiError kept),
 * motion/react (animation shell).
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { routerMock, forgotMock, confirmMock } = vi.hoisted(() => ({
  routerMock: { push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() },
  forgotMock: vi.fn(),
  confirmMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  forgotPassword: forgotMock,
  confirmForgotPassword: confirmMock,
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
import ForgotPasswordPage from "./page";

type User = ReturnType<typeof userEvent.setup>;

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

async function requestCode(user: User, message = "Code sent.") {
  forgotMock.mockResolvedValue({ message });
  render(<ForgotPasswordPage />);
  await user.type(screen.getByLabelText("Email"), "a@b.com");
  await user.click(screen.getByRole("button", { name: "Send reset code" }));
  await screen.findByRole("heading", { name: "Check your email" });
}

function confirmForm() {
  return screen.getByRole("button", { name: "Reset password" }).closest("form")!;
}

beforeEach(() => {
  routerMock.push.mockReset();
  forgotMock.mockReset();
  confirmMock.mockReset();
});

describe("ForgotPasswordPage — request step", () => {
  it("renders the labelled email field and submit button", () => {
    render(<ForgotPasswordPage />);
    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    const email = screen.getByLabelText("Email");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "email");
    expect(screen.getByRole("button", { name: "Send reset code" })).toBeInTheDocument();
  });

  it("navigates to /login from Back to sign in by click and by Enter", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);
    const back = screen.getByRole("button", { name: "Back to sign in" });
    await user.click(back);
    expect(routerMock.push).toHaveBeenCalledWith("/login");
    routerMock.push.mockClear();
    back.focus();
    await user.keyboard("{Enter}");
    expect(routerMock.push).toHaveBeenCalledWith("/login");
  });

  it("submits with Enter and sends the email exactly as typed", async () => {
    const user = userEvent.setup();
    forgotMock.mockResolvedValue({ message: "ok" });
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "Mixed@Case.com{Enter}");
    await waitFor(() => expect(forgotMock).toHaveBeenCalledWith("Mixed@Case.com"));
  });

  it("shows a disabled pending button and stays on the request step until resolved", async () => {
    const user = userEvent.setup();
    const d = deferred<{ message: string }>();
    forgotMock.mockReturnValue(d.promise);
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "Send reset code" }));
    expect(await screen.findByRole("button", { name: "Sending…" })).toBeDisabled();
    expect(screen.queryByLabelText("Reset code")).toBeNull();
    d.resolve({ message: "done" });
    expect(await screen.findByLabelText("Reset code")).toBeInTheDocument();
    expect(forgotMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    [new ApiError(409, "Ask an administrator"), "Ask an administrator"],
    [new ApiError(500, { x: 1 }), "An error occurred. Please try again."],
    [new Error("boom"), "An unexpected error occurred. Please try again."],
  ])("maps rejection %# and stays on the request step", async (err, message) => {
    const user = userEvent.setup();
    forgotMock.mockRejectedValue(err);
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "Send reset code" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send reset code" })).toBeEnabled();
    expect(screen.queryByLabelText("Reset code")).toBeNull();
  });

  it("clears the previous error when resubmitting", async () => {
    const user = userEvent.setup();
    const d = deferred<{ message: string }>();
    forgotMock.mockRejectedValueOnce(new ApiError(409, "First failure")).mockReturnValueOnce(d.promise);
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "Send reset code" }));
    await screen.findByText("First failure");
    await user.click(screen.getByRole("button", { name: "Send reset code" }));
    await screen.findByRole("button", { name: "Sending…" });
    expect(screen.queryByText("First failure")).toBeNull();
    d.resolve({ message: "ok" });
    await screen.findByLabelText("Reset code");
  });

  it("does not send twice when the pending (disabled) button is clicked again", async () => {
    const user = userEvent.setup();
    const d = deferred<{ message: string }>();
    forgotMock.mockReturnValue(d.promise);
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "Send reset code" }));
    await user.click(await screen.findByRole("button", { name: "Sending…" }));
    d.resolve({ message: "ok" });
    await screen.findByLabelText("Reset code");
    expect(forgotMock).toHaveBeenCalledTimes(1);
  });
});

describe("ForgotPasswordPage — confirm step render", () => {
  it("shows the server message as the subtitle", async () => {
    await requestCode(userEvent.setup(), "Code sent.");
    expect(screen.getByText("Code sent.")).toBeInTheDocument();
  });

  it("falls back to the default subtitle when the message is empty", async () => {
    await requestCode(userEvent.setup(), "");
    expect(
      screen.getByText("Enter the code we emailed you and choose a new password."),
    ).toBeInTheDocument();
  });

  it("exposes the field attributes", async () => {
    await requestCode(userEvent.setup());
    const code = screen.getByLabelText("Reset code");
    expect(code).toHaveAttribute("inputmode", "numeric");
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    const pw = screen.getByLabelText("New password");
    expect(pw).toHaveAttribute("autocomplete", "new-password");
    expect(pw).toHaveAttribute("minlength", "12");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("autocomplete", "new-password");
  });

  it("returns to the request step keeping the email and clearing errors", async () => {
    const user = userEvent.setup();
    await requestCode(user);
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "short" } });
    fireEvent.submit(confirmForm());
    await screen.findByText("New password must be at least 12 characters.");
    await user.click(screen.getByRole("button", { name: "Use a different email" }));
    expect(await screen.findByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("a@b.com");
    expect(screen.queryByText("New password must be at least 12 characters.")).toBeNull();
  });

  it("navigates to /login from Back to sign in on the confirm step", async () => {
    const user = userEvent.setup();
    await requestCode(user);
    await user.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(routerMock.push).toHaveBeenCalledWith("/login");
  });
});

describe("ForgotPasswordPage — confirm validation", () => {
  async function setup() {
    const user = userEvent.setup();
    await requestCode(user);
    return user;
  }

  // fireEvent.change/submit below: jsdom's required/minLength validation would
  // otherwise block the submit event before the handler's own checks run.
  function fill(code: string, pw: string, confirm: string) {
    fireEvent.change(screen.getByLabelText("Reset code"), { target: { value: code } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: pw } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: confirm } });
    fireEvent.submit(confirmForm());
  }

  it("rejects an 11-character password", async () => {
    await setup();
    fill("123456", "a".repeat(11), "a".repeat(11));
    expect(await screen.findByText("New password must be at least 12 characters.")).toBeInTheDocument();
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it("accepts exactly 12 matching characters", async () => {
    await setup();
    confirmMock.mockResolvedValue(undefined);
    fill("123456", "a".repeat(12), "a".repeat(12));
    await waitFor(() => expect(confirmMock).toHaveBeenCalledTimes(1));
  });

  it("rejects mismatched passwords", async () => {
    await setup();
    fill("123456", STRONG, STRONG + "x");
    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it("reports the length error before the mismatch error", async () => {
    await setup();
    fill("123456", "short", "other");
    expect(await screen.findByText("New password must be at least 12 characters.")).toBeInTheDocument();
    expect(screen.queryByText("Passwords do not match.")).toBeNull();
  });

  it("rejects a whitespace-only code", async () => {
    await setup();
    fill("   ", STRONG, STRONG);
    expect(await screen.findByText("Enter the 6-digit code we emailed you.")).toBeInTheDocument();
    expect(confirmMock).not.toHaveBeenCalled();
  });
});

describe("ForgotPasswordPage — confirm submit", () => {
  async function setup() {
    const user = userEvent.setup();
    await requestCode(user);
    await user.type(screen.getByLabelText("Reset code"), " 123456 ");
    await user.type(screen.getByLabelText("New password"), STRONG);
    await user.type(screen.getByLabelText("Confirm password"), STRONG);
    return user;
  }

  it("trims the code before confirming", async () => {
    const user = await setup();
    confirmMock.mockResolvedValue(undefined);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/login"));
    expect(confirmMock).toHaveBeenCalledWith("a@b.com", "123456", STRONG);
  });

  it("shows a disabled pending button without navigating", async () => {
    const user = await setup();
    const d = deferred<void>();
    confirmMock.mockReturnValue(d.promise);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByRole("button", { name: "Resetting…" })).toBeDisabled();
    expect(routerMock.push).not.toHaveBeenCalled();
    d.resolve();
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/login"));
  });

  it("shows the API detail on rejection, stays put, then recovers on retry", async () => {
    const user = await setup();
    confirmMock.mockRejectedValueOnce(new ApiError(400, "Invalid code")).mockResolvedValueOnce(undefined);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText("Invalid code")).toBeInTheDocument();
    expect(routerMock.push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Reset password" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("Invalid code")).toBeNull();
  });

  it("shows the generic message for a non-ApiError rejection", async () => {
    const user = await setup();
    confirmMock.mockRejectedValue(new Error("boom"));
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(
      await screen.findByText("An unexpected error occurred. Please try again."),
    ).toBeInTheDocument();
  });
});
