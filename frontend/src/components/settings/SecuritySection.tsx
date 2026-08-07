"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { ShieldCheck, ShieldAlert, Mail, Smartphone, RefreshCw } from "lucide-react";
import {
  getToken,
  getMfaStatus,
  enableEmailMfa,
  disableEmailMfa,
  ApiError,
  type MfaStatus,
} from "@/lib/api";
import { buildLoginRedirect } from "@/lib/authRedirect";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

/**
 * Account security — second-factor management.
 *
 * Cognito migration Phase 6: the enrolment surface the backend's MFA endpoints
 * were always missing. Without it `ADMIN_MFA_REQUIRED` is a lockout switch
 * rather than a control, because the 403 it raises points at an endpoint no
 * screen calls.
 *
 * Lives as a TAB inside Account Settings rather than its own route: the
 * standalone `/settings/security` page duplicated the chrome (own back button,
 * own page title) that the settings surface already provides, and split account
 * concerns across two navigation models. This component therefore renders body
 * content only — the header, back affordance and tab strip are the parent's.
 *
 * Email OTP is a TOGGLE, not a wizard, and that asymmetry with TOTP is real
 * rather than a shortcut: Cognito provisions no secret for email codes (the
 * mailbox is already the pool's verified sign-in identifier), so there is
 * nothing to display, scan, or confirm. Enabling it is a single preference
 * write.
 */

/**
 * Discriminated union rather than parallel `loading`/`error`/`data` booleans, so
 * "loaded but also erroring" is not representable.
 */
type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; status: MfaStatus };

function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    // The backend's 409s carry the actionable copy (pool not configured for
    // email codes, admin must keep a factor). Prefer it over a generic string.
    if (typeof err.detail === "string") return err.detail;
    if (err.detail && typeof err.detail === "object" && "message" in err.detail) {
      const { message } = err.detail as { message?: unknown };
      if (typeof message === "string") return message;
    }
    return err.message || fallback;
  }
  return fallback;
}

export function SecuritySection() {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

  // Deliberately does NOT set the loading state itself. On first run the initial
  // state is already `loading`, so setting it again would be a redundant
  // synchronous setState inside the effect (and a cascading-render lint error).
  // The retry path sets it explicitly instead, where it genuinely is a
  // transition.
  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      router.replace(buildLoginRedirect());
      return;
    }
    try {
      const status = await getMfaStatus(token);
      setState({ kind: "ready", status });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace(buildLoginRedirect());
        return;
      }
      setState({
        kind: "error",
        message: describeError(err, "Could not load your security settings."),
      });
    }
  }, [router]);

  // react-hooks/set-state-in-effect warns here and cannot be satisfied without
  // changing the auth architecture: the bearer token lives in localStorage
  // (COGNITO-MIGRATION-PLAN Decision 3 defers cookie/BFF), so this data cannot be
  // fetched in a Server Component and any client fetch-on-mount necessarily ends
  // in a setState. The actual setState happens after an await, not synchronously.
  // Left un-suppressed so it disappears on its own once the token moves to a
  // cookie; the same warning already exists in RunConnectionProvider.
  useEffect(() => {
    void load();
  }, [load]);

  const retry = useCallback(() => {
    setState({ kind: "loading" });
    void load();
  }, [load]);

  const toggleEmailMfa = useCallback(
    async (enable: boolean) => {
      const token = getToken();
      if (!token) {
        router.replace(buildLoginRedirect());
        return;
      }
      setPending(true);
      setNotice(null);
      try {
        const result = enable ? await enableEmailMfa(token) : await disableEmailMfa(token);
        // Trust the server's returned factor list over an optimistic guess: the
        // write resolves against the account's real current state, so assuming
        // the outcome here could show a factor set that never existed.
        setState((prev) =>
          prev.kind === "ready"
            ? {
                kind: "ready",
                status: {
                  ...prev.status,
                  factors: result.factors,
                  enabled: result.factors.length > 0,
                },
              }
            : prev
        );
        setNotice({ tone: "ok", text: result.message });
      } catch (err) {
        setNotice({
          tone: "bad",
          text: describeError(err, "That change could not be saved. Please try again."),
        });
      } finally {
        setPending(false);
      }
    },
    [router]
  );

  return (
    <motion.div
      key="security"
      initial={{ opacity: 0, x: 8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      transition={{ duration: 0.15 }}
      className="pt-1"
    >
      <p className="text-[13px] text-ink-500 leading-relaxed mb-4 max-w-2xl">
        Add a second step to sign-in so a stolen password isn&apos;t enough on its own.
      </p>

      {/*
        aria-live so the outcome of a toggle is announced. Without it a
        screen-reader user gets no confirmation that anything happened —
        the only visible change is text further down the page.
      */}
      <div aria-live="polite" className="sr-only">
        {notice?.text ?? ""}
      </div>

      {state.kind === "loading" && <SecuritySkeleton />}

      {state.kind === "error" && (
        <Card className="p-[22px] shadow-[var(--elevation-raised)]">
          <div className="flex items-start gap-3">
            <ShieldAlert
              className="mt-0.5 h-5 w-5 flex-shrink-0 text-status-failed"
              aria-hidden="true"
            />
            <div>
              <p className="text-[14px] font-semibold text-ink-900">
                Couldn&apos;t load your settings
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-500">{state.message}</p>
              <Button variant="secondary" onClick={retry} className="mt-4">
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                Try again
              </Button>
            </div>
          </div>
        </Card>
      )}

      {state.kind === "ready" && (
        <SecurityPanel
          status={state.status}
          pending={pending}
          notice={notice}
          onToggleEmail={toggleEmailMfa}
        />
      )}
    </motion.div>
  );
}

function SecuritySkeleton() {
  return (
    <Card className="p-[22px] shadow-[var(--elevation-raised)]" aria-busy="true">
      {/* Fixed heights matching the loaded rows so nothing shifts on arrival (CLS). */}
      <div className="h-5 w-48 animate-pulse rounded bg-surface-warm" />
      <div className="mt-6 h-[72px] animate-pulse rounded-[var(--radius-button)] bg-surface-warm" />
      <div className="mt-3 h-[72px] animate-pulse rounded-[var(--radius-button)] bg-surface-warm" />
      <span className="sr-only">Loading your security settings…</span>
    </Card>
  );
}

function SecurityPanel({
  status,
  pending,
  notice,
  onToggleEmail,
}: {
  status: MfaStatus;
  pending: boolean;
  notice: { tone: "ok" | "bad"; text: string } | null;
  onToggleEmail: (enable: boolean) => void;
}) {
  // A break-glass/local account has no Cognito factors to manage. Say so
  // plainly instead of rendering controls that would 501.
  if (!status.supported) {
    return (
      <Card className="p-[22px] shadow-[var(--elevation-raised)]">
        <p className="text-[14px] font-semibold text-ink-900">Not available for this account</p>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-500">
          This account&apos;s credentials are managed outside the application, so
          two-factor authentication is configured separately.
        </p>
      </Card>
    );
  }

  const emailOn = status.factors.includes("EMAIL_OTP");
  const totpOn = status.factors.includes("SOFTWARE_TOKEN_MFA");

  return (
    <div className="space-y-3.5">
      <Card className="p-[22px] shadow-[var(--elevation-raised)]">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            {status.enabled ? (
              <ShieldCheck
                className="mt-0.5 h-5 w-5 flex-shrink-0 text-status-done"
                aria-hidden="true"
              />
            ) : (
              <ShieldAlert
                className="mt-0.5 h-5 w-5 flex-shrink-0 text-ink-400"
                aria-hidden="true"
              />
            )}
            <div>
              <h2 className="text-[15px] font-semibold text-ink-900">
                Two-factor authentication
              </h2>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-500">
                {status.enabled
                  ? "Active. You'll be asked for a code when you sign in."
                  : "Not set up. Your password is the only thing protecting this account."}
              </p>
            </div>
          </div>
          <Badge
            status={status.enabled ? "done" : "queued"}
            label={status.enabled ? "On" : "Off"}
          />
        </div>

        {status.required && (
          <p className="mt-5 rounded-[var(--radius-button)] border border-line-control bg-surface-warm px-4 py-3 text-[12px] leading-relaxed text-ink-600">
            Your role requires a second factor, so at least one method must stay
            switched on.
          </p>
        )}

        {notice && (
          <p
            className={[
              "mt-5 rounded-[var(--radius-button)] px-4 py-3 text-[13px] leading-relaxed",
              notice.tone === "ok"
                ? "border border-line-control bg-surface-warm text-ink-700"
                : "border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] text-status-failed",
            ].join(" ")}
          >
            {notice.text}
          </p>
        )}
      </Card>

      <Card className="divide-y divide-line-divider shadow-[var(--elevation-raised)]">
        {status.email_available && (
          <MethodRow
            icon={<Mail className="h-4 w-4 text-ink-500" aria-hidden="true" />}
            title="Email codes"
            description={
              emailOn
                ? "We email a 6-digit code each time you sign in."
                : "We'll email a 6-digit code each time you sign in. Nothing to install."
            }
            active={emailOn}
            action={
              <Button
                variant={emailOn ? "secondary" : "primary"}
                onClick={() => onToggleEmail(!emailOn)}
                disabled={pending}
                aria-describedby="email-mfa-description"
              >
                {pending ? "Saving…" : emailOn ? "Turn off" : "Turn on"}
              </Button>
            }
            descriptionId="email-mfa-description"
          />
        )}

        <MethodRow
          icon={<Smartphone className="h-4 w-4 text-ink-500" aria-hidden="true" />}
          title="Authenticator app"
          description={
            totpOn
              ? "A time-based code from your authenticator app."
              : "Codes from an app like Google Authenticator. Set-up is handled by your administrator."
          }
          active={totpOn}
          // Deliberately no control here. The TOTP enrolment endpoints exist
          // (/api/auth/mfa/totp/associate + /verify) but this screen does not
          // implement the QR ceremony, and rendering a button that goes nowhere
          // would be worse than stating where set-up happens.
          action={null}
          descriptionId="totp-mfa-description"
        />

        {!status.email_available && !totpOn && (
          <div className="px-6 py-5">
            <p className="text-[12px] leading-relaxed text-ink-500">
              No two-factor methods are enabled for this environment yet. Contact
              your administrator if you need one.
            </p>
          </div>
        )}
      </Card>

      {status.email_available && (
        <p className="px-1 text-[12px] leading-relaxed text-ink-400">
          Because sign-in codes go to your email address, password resets are
          handled by an administrator rather than by email.
        </p>
      )}
    </div>
  );
}

function MethodRow({
  icon,
  title,
  description,
  descriptionId,
  active,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  descriptionId: string;
  active: boolean;
  action: React.ReactNode | null;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-6 py-5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex-shrink-0">{icon}</span>
        <div>
          <div className="flex items-center gap-2">
            <p className="text-[14px] font-medium text-ink-900">{title}</p>
            {active && <Badge status="done" label="Active" />}
          </div>
          <p id={descriptionId} className="mt-1 text-[12.5px] leading-relaxed text-ink-500">
            {description}
          </p>
        </div>
      </div>
      {action}
    </div>
  );
}
