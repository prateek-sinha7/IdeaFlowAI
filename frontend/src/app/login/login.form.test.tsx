/**
 * LoginForm branch of login/page.tsx: mount guard, expired banner, redirect
 * safety, error mapping, loading / double-submit, canonical email, keyboard.
 * Boundaries mocked: next/navigation, @/lib/api (transport only; real
 * ApiError + isAuthChallenge kept), motion/react (animation shell).
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { routerMock, mockSearchParams, getTokenMock, loginMock } = vi.hoisted(() => ({
  routerMock: { push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() },
  mockSearchParams: { current: new URLSearchParams() },
  getTokenMock: vi.fn(),
  loginMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  useSearchParams: () => mockSearchParams.current,
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: getTokenMock,
  login: loginMock,
}));

const STRIPPED = new Set(["initial", "animate", "exit", "transition"]);
vi.mock("motion/react", () => {
  // Components are cached per tag: a fresh component type per access would
  // remount the subtree on every render and drop typed input / focus.
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

const OK = { token: "tok", user: { id: "1", email: "a@b.com", tier: "basic", is_admin: false } };

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function fillCredentials(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Email"), "a@b.com");
  await user.type(screen.getByLabelText("Password"), "secret123");
}

async function signIn(user: ReturnType<typeof userEvent.setup>) {
  await fillCredentials(user);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

beforeEach(() => {
  routerMock.push.mockReset();
  routerMock.replace.mockReset();
  loginMock.mockReset();
  getTokenMock.mockReset();
  getTokenMock.mockReturnValue(null);
  mockSearchParams.current = new URLSearchParams();
});

describe("LoginPage — mount guard", () => {
  it("renders nothing and replaces to /dashboard when already signed in", async () => {
    getTokenMock.mockReturnValue("tok");
    render(<LoginPage />);
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByRole("heading", { name: "Welcome back" })).toBeNull();
  });

  it("replaces to a safe internal ?redirect= when already signed in", async () => {
    getTokenMock.mockReturnValue("tok");
    mockSearchParams.current = new URLSearchParams("redirect=%2Fworkflow%2Fcreate%3Fmode%3Dppt");
    render(<LoginPage />);
    await waitFor(() =>
      expect(routerMock.replace).toHaveBeenCalledWith("/workflow/create?mode=ppt"),
    );
  });

  it.each(["//evil.com", "https://evil.com"])(
    "falls back to /dashboard for unsafe ?redirect=%s when already signed in",
    async (target) => {
      getTokenMock.mockReturnValue("tok");
      mockSearchParams.current = new URLSearchParams({ redirect: target });
      render(<LoginPage />);
      await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith("/dashboard"));
    },
  );

  it("renders the form and does not replace when anonymous", async () => {
    render(<LoginPage />);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });
});

describe("LoginPage — expired banner", () => {
  it("shows the session-expired alert when ?expired=true", async () => {
    mockSearchParams.current = new URLSearchParams("expired=true");
    render(<LoginPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your session expired. Please sign in again.",
    );
  });

  it.each(["", "expired=false", "expired=1"])("shows no banner for '%s'", async (qs) => {
    mockSearchParams.current = new URLSearchParams(qs);
    render(<LoginPage />);
    await screen.findByRole("heading", { name: "Welcome back" });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("LoginPage — redirect after login", () => {
  it.each(["//evil.com", "/\\evil.com"])("falls back to /dashboard for %s", async (target) => {
    const user = userEvent.setup();
    mockSearchParams.current = new URLSearchParams({ redirect: target });
    loginMock.mockResolvedValue(OK);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await signIn(user);
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/dashboard"));
  });

  it("does not navigate when login rejects", async () => {
    const user = userEvent.setup();
    loginMock.mockRejectedValue(new ApiError(401, null));
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await signIn(user);
    await screen.findByRole("alert");
    expect(routerMock.push).not.toHaveBeenCalled();
  });
});

describe("LoginPage — error mapping", () => {
  it.each([
    [new ApiError(401, "anything"), "Invalid email or password."],
    [new ApiError(500, "Database unavailable"), "Database unavailable"],
    [new ApiError(500, { code: 1 }), "An error occurred. Please try again."],
    [new Error("boom"), "An unexpected error occurred. Please try again."],
  ])("shows the mapped message for %#", async (err, message) => {
    const user = userEvent.setup();
    loginMock.mockRejectedValue(err);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await signIn(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("clears the previous error while a new submit is pending", async () => {
    const user = userEvent.setup();
    const second = deferred<typeof OK>();
    loginMock.mockRejectedValueOnce(new ApiError(401, null)).mockReturnValueOnce(second.promise);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await signIn(user);
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("button", { name: "Signing in…" });
    expect(screen.queryByRole("alert")).toBeNull();
    second.resolve(OK);
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/dashboard"));
  });
});

describe("LoginPage — loading and double submit", () => {
  it("disables the button with a pending name, then navigates once on success", async () => {
    const user = userEvent.setup();
    const d = deferred<typeof OK>();
    loginMock.mockReturnValue(d.promise);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await signIn(user);
    const pending = await screen.findByRole("button", { name: "Signing in…" });
    expect(pending).toBeDisabled();
    d.resolve(OK);
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledTimes(1));
    expect(loginMock).toHaveBeenCalledTimes(1);
  });

  it("re-enables the button after rejection", async () => {
    const user = userEvent.setup();
    const d = deferred<typeof OK>();
    loginMock.mockReturnValue(d.promise);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await signIn(user);
    await screen.findByRole("button", { name: "Signing in…" });
    d.reject(new ApiError(401, null));
    const button = await screen.findByRole("button", { name: "Sign in" });
    expect(button).toBeEnabled();
  });

  it("ignores a second same-task submit while the first is in flight", async () => {
    const user = userEvent.setup();
    const d = deferred<typeof OK>();
    loginMock.mockReturnValue(d.promise);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await fillCredentials(user);
    const form = screen.getByRole("button", { name: "Sign in" }).closest("form")!;
    // fireEvent: user-event cannot dispatch two submits within one task, which
    // is exactly the window the ref guard (not `disabled`) closes.
    fireEvent.submit(form);
    fireEvent.submit(form);
    d.resolve(OK);
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledTimes(1));
    expect(loginMock).toHaveBeenCalledTimes(1);
  });

  it("allows a re-submit after the first request settled", async () => {
    const user = userEvent.setup();
    loginMock.mockRejectedValueOnce(new ApiError(401, null)).mockResolvedValueOnce(OK);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await signIn(user);
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(routerMock.push).toHaveBeenCalledWith("/dashboard"));
    expect(loginMock).toHaveBeenCalledTimes(2);
  });
});

describe("LoginPage — email canonicalization", () => {
  it("submits the canonical email and writes it back to the field", async () => {
    const user = userEvent.setup();
    loginMock.mockRejectedValue(new ApiError(401, null));
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await user.type(screen.getByLabelText("Email"), "Foo@Bar.COM");
    await user.type(screen.getByLabelText("Password"), "secret123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("alert");
    expect(loginMock).toHaveBeenCalledWith("foo@bar.com", "secret123");
    expect(screen.getByLabelText("Email")).toHaveValue("foo@bar.com");
  });
});

describe("LoginPage — keyboard and accessibility", () => {
  it("exposes autocomplete hints on the labelled fields", async () => {
    render(<LoginPage />);
    const email = await screen.findByLabelText("Email");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "email");
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
  });

  it("tabs Email → Forgot password? → Password → Show password → Sign in", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await user.tab();
    expect(screen.getByLabelText("Email")).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Forgot password?" })).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Password")).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Show password" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Sign in" })).toHaveFocus();
  });

  it("submits with Enter from the password field", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue(OK);
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Password"), "secret123{Enter}");
    await waitFor(() => expect(loginMock).toHaveBeenCalledWith("a@b.com", "secret123"));
  });

  it("activates Forgot password? with Enter", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    screen.getByRole("button", { name: "Forgot password?" }).focus();
    await user.keyboard("{Enter}");
    expect(routerMock.push).toHaveBeenCalledWith("/forgot-password");
  });

  it("toggles password visibility and the toggle name", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await screen.findByLabelText("Email");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });
});
