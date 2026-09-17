/**
 * T2b — TOTP enrolment view + the admin 403 -> enrolment redirect.
 *
 * The behaviours worth pinning are the two that a user actually depends on and
 * that are easy to regress silently:
 *
 *   1. A blocked admin is MOVED to enrolment rather than left staring at a
 *      "Failed to load users" toast on a page that can never load.
 *   2. After verifying, the page tells the user their CURRENT session still is
 *      not verified. Without that line the obvious next move is to go straight
 *      back to /admin and hit the same 403, which reads as a broken enrolment.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const { routerObj, api } = vi.hoisted(() => {
  class ApiError extends Error {
    constructor(
      public status: number,
      public detail: unknown,
    ) {
      super(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
  }
  return {
    routerObj: { replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() },
    api: {
      getToken: vi.fn(() => "tok"),
      associateTotp: vi.fn(),
      verifyTotp: vi.fn(),
      ApiError,
    },
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => routerObj,
}));

vi.mock("@/lib/api", () => api);

import SecuritySettingsPage from "./page";

const ASSOCIATION = {
  secret: "ABCDEFGHIJKLMNOP",
  issuer: "Flowin",
  account: "admin-user@flowinqa.com",
  otpauth_uri:
    "otpauth://totp/Flowin:admin-user@flowinqa.com?secret=ABCDEFGHIJKLMNOP&issuer=Flowin",
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
});

describe("SecuritySettingsPage", () => {
  it("shows the setup key and link from associate", async () => {
    api.associateTotp.mockResolvedValue(ASSOCIATION);

    render(<SecuritySettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("totp-secret")).toHaveTextContent(
        ASSOCIATION.secret,
      );
    });
    expect(screen.getByTestId("totp-otpauth-uri")).toHaveTextContent(
      "otpauth://totp/Flowin:admin-user@flowinqa.com",
    );
  });

  it("verifies the code and then tells the user to sign in again", async () => {
    api.associateTotp.mockResolvedValue(ASSOCIATION);
    api.verifyTotp.mockResolvedValue({
      message: "Two-factor authentication enabled.",
    });

    render(<SecuritySettingsPage />);
    await waitFor(() => expect(screen.getByTestId("totp-secret")).toBeTruthy());

    await userEvent.type(screen.getByLabelText(/verification code/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /verify and enable/i }));

    await waitFor(() => {
      expect(api.verifyTotp).toHaveBeenCalledWith("tok", "123456");
    });

    expect(
      await screen.findByText(/two-factor authentication is on/i),
    ).toBeTruthy();
    // The whole point of the success copy: enrolling does not retro-verify the
    // token already in the browser.
    expect(screen.getByText(/sign in again/i)).toBeTruthy();
  });

  it("surfaces the server's message when the code is rejected", async () => {
    api.associateTotp.mockResolvedValue(ASSOCIATION);
    api.verifyTotp.mockRejectedValue(
      new api.ApiError(400, "Could not verify that code. Try the current code from your app."),
    );

    render(<SecuritySettingsPage />);
    await waitFor(() => expect(screen.getByTestId("totp-secret")).toBeTruthy());

    await userEvent.type(screen.getByLabelText(/verification code/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /verify and enable/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/try the current code/i);
    // Still on the form, not falsely reporting success.
    expect(screen.queryByText(/two-factor authentication is on/i)).toBeNull();
  });
});
