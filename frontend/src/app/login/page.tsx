"use client";

import { Suspense, useState, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import { Mail, Lock } from "lucide-react";
import {
  login,
  respondToLoginChallenge,
  isAuthChallenge,
  ApiError,
  type AuthChallengeResponse,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { resolveRedirectTarget } from "@/lib/authRedirect";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isExpired = searchParams.get("expired") === "true";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Cognito migration (Phase 4): when login() returns a challenge instead of
  // a token, the form switches to the matching challenge step. `session` is
  // Cognito's opaque continuation token — echoed back verbatim.
  const [challenge, setChallenge] = useState<AuthChallengeResponse | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  // SELECT_MFA_TYPE only. Should not normally appear — the backend always names
  // a preferred factor — but a preference changed out of band (AWS console) can
  // still produce it, and a dead end at the login screen is the worst place for
  // one.
  const [selectedFactor, setSelectedFactor] = useState("");

  function goToDestination() {
    // Every user — including admins — lands on the main application by
    // default. If the user was bounced here from a specific protected page
    // (?redirect=...), return them there instead; the target is validated
    // against the internal-path allowlist to prevent an open redirect.
    // The admin dashboard is reached separately via its nav link/menu item.
    router.push(resolveRedirectTarget(searchParams.get("redirect")));
  }

  function describeApiError(err: unknown): string {
    if (err instanceof ApiError && err.status === 401) {
      return "Invalid email or password.";
    }
    if (err instanceof ApiError) {
      return typeof err.detail === "string" ? err.detail : "An error occurred. Please try again.";
    }
    return "An unexpected error occurred. Please try again.";
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const result = await login(email, password);
      if (isAuthChallenge(result)) {
        setChallenge(result);
        return;
      }
      goToDestination();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleChallengeSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!challenge) return;
    setError("");

    if (challenge.challenge === "NEW_PASSWORD_REQUIRED") {
      if (newPassword.length < 12) {
        setError("New password must be at least 12 characters.");
        return;
      }
      if (newPassword !== confirmNewPassword) {
        setError("Passwords do not match.");
        return;
      }
    } else if (challenge.challenge === "SELECT_MFA_TYPE") {
      if (!selectedFactor) {
        setError("Choose how you'd like to receive your code.");
        return;
      }
    } else if (!mfaCode.trim()) {
      setError(
        challenge.challenge === "EMAIL_OTP"
          ? "Enter the 6-digit code we emailed you."
          : "Enter the 6-digit code from your authenticator app."
      );
      return;
    }

    setIsLoading(true);
    try {
      const result = await respondToLoginChallenge(email, challenge.session, challenge.challenge, {
        newPassword: challenge.challenge === "NEW_PASSWORD_REQUIRED" ? newPassword : undefined,
        mfaCode:
          challenge.challenge === "SOFTWARE_TOKEN_MFA" || challenge.challenge === "EMAIL_OTP"
            ? mfaCode
            : undefined,
        selectedFactor:
          challenge.challenge === "SELECT_MFA_TYPE" ? selectedFactor : undefined,
      });
      if (isAuthChallenge(result)) {
        // A second challenge — ordinary, not exotic: a first login with a
        // temporary password produces NEW_PASSWORD_REQUIRED and then a code
        // prompt for a user who holds a factor. Clear the step-specific fields
        // so the next step starts empty.
        setChallenge(result);
        setNewPassword("");
        setConfirmNewPassword("");
        setMfaCode("");
        setSelectedFactor("");
        return;
      }
      goToDestination();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setIsLoading(false);
    }
  }

  if (challenge) {
    return (
      <ChallengeForm
        challenge={challenge}
        error={error}
        isLoading={isLoading}
        newPassword={newPassword}
        setNewPassword={setNewPassword}
        confirmNewPassword={confirmNewPassword}
        setConfirmNewPassword={setConfirmNewPassword}
        mfaCode={mfaCode}
        setMfaCode={setMfaCode}
        selectedFactor={selectedFactor}
        setSelectedFactor={setSelectedFactor}
        onSubmit={handleChallengeSubmit}
        onCancel={() => {
          setChallenge(null);
          setError("");
          setSelectedFactor("");
        }}
      />
    );
  }

  return (
    <div className="flex min-h-screen">
      {/* LEFT — dark brand panel (~46%); mirrors the 35-01 near-black shell idiom */}
      <aside
        data-testid="login-brand-panel"
        className="hidden lg:flex lg:w-[46%] flex-col justify-between bg-surface-near-black px-12 py-14 border-r border-white/10"
      >
        {/* Hexaware logo + VelocityAI wordmark */}
        <div className="flex items-center gap-2.5">
          <img
            src="/hexaware-logo.png"
            alt="Hexaware"
            className="h-10 w-10 rounded-[8px] flex-shrink-0"
          />
          <span className="text-base font-semibold tracking-tight text-white font-sans">
            VelocityAI
          </span>
        </div>

        {/* Brand statement */}
        <div className="max-w-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-brand-on-dark mb-4 font-sans">
            AI delivery, orchestrated
          </p>
          <h2 className="text-[32px] leading-[1.15] font-semibold tracking-tight text-white font-sans">
            Ship faster with your agent workforce.
          </h2>
          <p className="mt-4 text-[14px] leading-relaxed text-white/60">
            Compose, run, and review delivery workflows — every step traceable,
            every artifact yours.
          </p>
        </div>

        {/* Static decoration — value props (no wiring, no identity affordances) */}
        <div className="flex flex-wrap gap-2">
          {["Audit trail", "Role-based access", "Invitation-only"].map((tag) => (
            <span
              key={tag}
              className="rounded-[var(--radius-pill)] border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-medium text-white/60"
            >
              {tag}
            </span>
          ))}
        </div>
      </aside>

      {/* RIGHT — the wired form column */}
      <div className="flex flex-1 items-center justify-center bg-surface-paper px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="w-full max-w-md"
        >
          {/* Heading */}
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mb-8"
          >
            <h1 className="text-[36px] sm:text-[40px] font-semibold text-ink-900 leading-[1.1] tracking-tight font-sans">
              Welcome back
            </h1>
            <p className="mt-3 text-[13px] text-ink-500 leading-relaxed">
              Sign in to continue building with your AI delivery agents.
            </p>
          </motion.div>

          {/* Card */}
          <div className="rounded-[var(--radius-card)] border border-line-control bg-surface-card p-7 shadow-[var(--elevation-raised)]">
            {isExpired && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-5 rounded-[var(--radius-button)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-4 py-3 text-sm text-status-failed"
              >
                Your session expired. Please sign in again.
              </motion.div>
            )}

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-5 rounded-[var(--radius-button)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-4 py-3 text-sm text-status-failed"
              >
                {error}
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label htmlFor="email" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">Email</label>
                <div className="input-focus relative rounded-[var(--radius-button)] border border-line-control bg-surface-card transition-colors">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-400" />
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                    className="w-full rounded-[var(--radius-button)] bg-transparent pl-10 pr-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none"
                    placeholder="you@example.com"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="password" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">Password</label>
                <div className="input-focus relative rounded-[var(--radius-button)] border border-line-control bg-surface-card transition-colors">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-400" />
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    className="w-full rounded-[var(--radius-button)] bg-transparent pl-10 pr-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none"
                    placeholder="••••••••"
                  />
                </div>
              </div>

              <Button
                variant="primary"
                type="submit"
                disabled={isLoading}
                className="w-full py-3 text-[13px]"
              >
                {isLoading ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </div>

          {/* Quiet footer — no self-register; contact admin */}
          <p className="mt-6 text-center text-[11px] text-ink-400 leading-relaxed">
            Access is by invitation. Contact your administrator for an account.
          </p>
        </motion.div>
      </div>
    </div>
  );
}

/** Copy per challenge kind. Kept as one table so the strings are comparable
 *  side by side rather than scattered through nested ternaries. */
const CHALLENGE_COPY: Record<
  AuthChallengeResponse["challenge"],
  { title: string; subtitle: string }
> = {
  NEW_PASSWORD_REQUIRED: {
    title: "Set a new password",
    subtitle: "This is your first sign-in. Choose a permanent password to continue.",
  },
  SOFTWARE_TOKEN_MFA: {
    title: "Enter your authentication code",
    subtitle: "Enter the 6-digit code from your authenticator app.",
  },
  EMAIL_OTP: {
    title: "Check your email",
    subtitle: "We sent you a 6-digit code. Enter it below to finish signing in.",
  },
  SELECT_MFA_TYPE: {
    title: "Choose a verification method",
    subtitle: "How would you like to receive your code?",
  },
  MFA_SETUP: {
    title: "Two-factor setup required",
    subtitle:
      "This account needs two-factor authentication set up before it can sign in. Contact your administrator to finish setup.",
  },
};

/** SELECT_MFA_TYPE answers. `EMAIL_MFA` is Cognito's own asymmetry — the factor
 *  is `EMAIL_OTP` everywhere else but the selection answer is `EMAIL_MFA`. */
const FACTOR_CHOICES: { value: string; label: string }[] = [
  { value: "EMAIL_MFA", label: "Email me a code" },
  { value: "SOFTWARE_TOKEN_MFA", label: "Use my authenticator app" },
];

/**
 * Cognito migration (Phase 4): the first-login "set a new password" step and the
 * MFA code prompts. Reuses the same shell as the main login form so a challenge
 * never looks like a different app.
 */
function ChallengeForm({
  challenge,
  error,
  isLoading,
  newPassword,
  setNewPassword,
  confirmNewPassword,
  setConfirmNewPassword,
  mfaCode,
  setMfaCode,
  selectedFactor,
  setSelectedFactor,
  onSubmit,
  onCancel,
}: {
  challenge: AuthChallengeResponse;
  error: string;
  isLoading: boolean;
  newPassword: string;
  setNewPassword: (v: string) => void;
  confirmNewPassword: string;
  setConfirmNewPassword: (v: string) => void;
  mfaCode: string;
  setMfaCode: (v: string) => void;
  selectedFactor: string;
  setSelectedFactor: (v: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
}) {
  const kind = challenge.challenge;
  const isNewPassword = kind === "NEW_PASSWORD_REQUIRED";
  const isCode = kind === "SOFTWARE_TOKEN_MFA" || kind === "EMAIL_OTP";
  const isSelect = kind === "SELECT_MFA_TYPE";
  // MFA_SETUP cannot be completed here: it needs a three-call Cognito session
  // chain the single-shot /login/challenge endpoint can't express, and the
  // backend answers 501. Render the explanation instead of a code field that
  // would collect a code and then fail.
  const isDeadEnd = kind === "MFA_SETUP";

  const copy = CHALLENGE_COPY[kind] ?? {
    title: "Additional verification required",
    subtitle: "Follow the prompt below to finish signing in.",
  };
  const { title } = copy;
  // For EMAIL_OTP, name the mailbox Cognito actually sent to when it told us.
  // "Check your email" is unhelpful when the address on file isn't the one the
  // user expected; the value is already masked by AWS.
  const subtitle =
    kind === "EMAIL_OTP" && challenge.delivery
      ? `We sent a 6-digit code to ${challenge.delivery}. Enter it below to finish signing in.`
      : copy.subtitle;

  const choices =
    challenge.available_factors && challenge.available_factors.length > 0
      ? FACTOR_CHOICES.filter((c) => challenge.available_factors?.includes(c.value))
      : FACTOR_CHOICES;

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-paper px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8">
          <h1 className="text-[32px] font-semibold text-ink-900 leading-[1.1] tracking-tight font-sans">
            {title}
          </h1>
          <p className="mt-3 text-[13px] text-ink-500 leading-relaxed">{subtitle}</p>
        </div>

        <div className="rounded-[var(--radius-card)] border border-line-control bg-surface-card p-7 shadow-[var(--elevation-raised)]">
          {error && (
            <div className="mb-5 rounded-[var(--radius-button)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-4 py-3 text-sm text-status-failed">
              {error}
            </div>
          )}

          <form onSubmit={onSubmit} className="space-y-5">
            {isNewPassword ? (
              <>
                <div>
                  <label htmlFor="new-password" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                    New password
                  </label>
                  <input
                    id="new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    minLength={12}
                    className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-card px-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none"
                    placeholder="At least 12 characters"
                  />
                </div>
                <div>
                  <label htmlFor="confirm-new-password" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                    Confirm password
                  </label>
                  <input
                    id="confirm-new-password"
                    type="password"
                    value={confirmNewPassword}
                    onChange={(e) => setConfirmNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-card px-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none"
                    placeholder="Re-enter your new password"
                  />
                </div>
              </>
            ) : isSelect ? (
              <fieldset>
                <legend className="mb-2 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                  Verification method
                </legend>
                <div className="space-y-2">
                  {choices.map((choice) => (
                    <label
                      key={choice.value}
                      htmlFor={`factor-${choice.value}`}
                      className="flex cursor-pointer items-center gap-3 rounded-[var(--radius-button)] border border-line-control bg-surface-card px-3.5 py-3 text-[14px] text-ink-900 hover:bg-surface-warm has-[:focus-visible]:border-brand"
                    >
                      <input
                        id={`factor-${choice.value}`}
                        type="radio"
                        name="mfa-factor"
                        value={choice.value}
                        checked={selectedFactor === choice.value}
                        onChange={(e) => setSelectedFactor(e.target.value)}
                        className="h-4 w-4 accent-brand"
                      />
                      {choice.label}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : isCode ? (
              <div>
                <label htmlFor="mfa-code" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                  {kind === "EMAIL_OTP" ? "Email code" : "Authentication code"}
                </label>
                <input
                  id="mfa-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  required
                  className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-card px-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none tracking-widest"
                  placeholder="123456"
                />
              </div>
            ) : null}

            {/* MFA_SETUP has nothing actionable, so it gets no submit control —
                offering "Continue" would just produce a 501. */}
            {!isDeadEnd && (
              <Button variant="primary" type="submit" disabled={isLoading} className="w-full py-3 text-[13px]">
                {isLoading ? "Verifying…" : "Continue"}
              </Button>
            )}
            <button
              type="button"
              onClick={onCancel}
              className="w-full text-center text-[12px] text-ink-400 hover:text-ink-700"
            >
              Back to sign in
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
