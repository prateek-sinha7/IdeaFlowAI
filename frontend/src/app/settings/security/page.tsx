"use client";

/**
 * Account security — TOTP enrolment.
 *
 * This page exists because Cognito provides no enrolment UI without the hosted
 * UI, and because `require_admin` refuses an admin who holds no second factor.
 * It is the destination the backend names in that 403's `enroll_path`, so it
 * must be reachable by any authenticated user — an admin arriving here is, by
 * definition, currently blocked from every `/api/admin/*` route.
 *
 * The ceremony is two steps because Cognito's is: associate provisions a secret,
 * verify proves possession. Nothing is enrolled until the second step returns.
 */

import { useCallback, useEffect, useState } from "react";
import { getToken, associateTotp, verifyTotp, ApiError } from "@/lib/api";
import type { TotpAssociation } from "@/lib/api";

type Stage =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; association: TotpAssociation }
  | { kind: "enrolled" };

export default function SecuritySettingsPage() {
  // A discriminated union rather than several booleans: "loading and errored"
  // and "ready with no association" are not states this page can be in, so they
  // are made unrepresentable instead of guarded against.
  const [stage, setStage] = useState<Stage>({ kind: "loading" });
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [codeError, setCodeError] = useState<string | null>(null);

  const begin = useCallback(async () => {
    setStage({ kind: "loading" });
    const token = getToken();
    if (!token) {
      setStage({ kind: "error", message: "Please sign in again to continue." });
      return;
    }
    try {
      const association = await associateTotp(token);
      setStage({ kind: "ready", association });
    } catch (err: unknown) {
      setStage({
        kind: "error",
        message:
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : "Could not start enrolment. Please try again.",
      });
    }
  }, []);

  useEffect(() => {
    const start = window.setTimeout(() => {
      void begin();
    }, 0);
    return () => window.clearTimeout(start);
  }, [begin]);

  async function onVerify(event: React.FormEvent) {
    event.preventDefault();
    const token = getToken();
    if (!token || stage.kind !== "ready") return;

    setSubmitting(true);
    setCodeError(null);
    try {
      await verifyTotp(token, code.trim());
      setStage({ kind: "enrolled" });
    } catch (err: unknown) {
      // The backend's 400 message names the actual problem (usually a code that
      // rolled over while being typed), so it is shown verbatim rather than
      // replaced with a generic failure.
      setCodeError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not verify that code. Try the current code from your app.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-slate-100">
          Two-factor authentication
        </h1>
        <p className="text-sm text-slate-400">
          Admin access requires a second factor. Set up an authenticator app to
          continue.
        </p>
      </header>

      {stage.kind === "loading" && (
        <p role="status" className="text-sm text-slate-400">
          Preparing your enrolment…
        </p>
      )}

      {stage.kind === "error" && (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm text-red-400">
            {stage.message}
          </p>
          <button
            type="button"
            onClick={() => void begin()}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            Try again
          </button>
        </div>
      )}

      {stage.kind === "ready" && (
        <>
          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-slate-200">
              1. Add this account to your authenticator app
            </h2>
            <p className="text-sm text-slate-400">
              Scan the setup link, or enter the key by hand if you cannot scan.
            </p>
            {/* Rendered as text rather than an image: drawing a QR code would
                mean adding a rendering dependency, and every authenticator app
                accepts a manually-entered key. The otpauth URI is included so a
                client that can render one already has everything it needs. */}
            <dl className="flex flex-col gap-2 rounded-md border border-slate-800 bg-slate-900/60 p-3 text-sm">
              <div className="flex flex-col gap-0.5">
                <dt className="text-xs uppercase tracking-wide text-slate-500">
                  Account
                </dt>
                <dd className="text-slate-200">{stage.association.account}</dd>
              </div>
              <div className="flex flex-col gap-0.5">
                <dt className="text-xs uppercase tracking-wide text-slate-500">
                  Setup key
                </dt>
                <dd
                  data-testid="totp-secret"
                  className="break-all font-mono text-slate-100"
                >
                  {stage.association.secret}
                </dd>
              </div>
              <div className="flex flex-col gap-0.5">
                <dt className="text-xs uppercase tracking-wide text-slate-500">
                  Setup link
                </dt>
                <dd
                  data-testid="totp-otpauth-uri"
                  className="break-all font-mono text-xs text-slate-400"
                >
                  {stage.association.otpauth_uri}
                </dd>
              </div>
            </dl>
            <p className="text-xs text-slate-500">
              This key is shown once and is not stored. If you leave this page
              before finishing, start again.
            </p>
          </section>

          <form onSubmit={onVerify} className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-slate-200">
              2. Enter the 6-digit code from your app
            </h2>
            <label htmlFor="totp-code" className="text-sm text-slate-400">
              Verification code
            </label>
            <input
              id="totp-code"
              name="totp-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              aria-invalid={codeError ? true : undefined}
              aria-describedby={codeError ? "totp-code-error" : undefined}
              className="w-40 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-slate-100"
            />
            {codeError && (
              <p id="totp-code-error" role="alert" className="text-sm text-red-400">
                {codeError}
              </p>
            )}
            <button
              type="submit"
              disabled={submitting || code.trim().length === 0}
              className="w-fit rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {submitting ? "Verifying…" : "Verify and enable"}
            </button>
          </form>
        </>
      )}

      {stage.kind === "enrolled" && (
        <div role="status" className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-emerald-400">
            Two-factor authentication is on.
          </h2>
          {/* Not optional politeness: the admin gate compares this session's
              token `iat` against `mfa_verified_at`. The token in the browser
              right now was minted BEFORE this enrolment, so it cannot carry the
              proof and admin routes will keep returning 403 until a new sign-in
              mints a token that does. */}
          <p className="text-sm text-slate-400">
            Sign out and sign back in to finish. Your current session was started
            before you enrolled, so it does not yet count as verified — admin
            pages will keep refusing until you sign in again.
          </p>
        </div>
      )}
    </main>
  );
}
