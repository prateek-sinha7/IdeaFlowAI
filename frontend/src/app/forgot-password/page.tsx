"use client";

import { Suspense, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { Mail, Lock, KeyRound } from "lucide-react";
import { forgotPassword, confirmForgotPassword, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";

/**
 * Self-service password reset (Cognito migration Phase 5, over the existing
 * backend flow — Decision 8 / `POST /api/auth/forgot-password[/confirm]`).
 *
 * Two steps, one page: request a code, then submit it with a new password.
 * `forgotPassword()` always resolves (the backend returns a generic 202
 * whether or not the address exists — Cognito's own account-enumeration
 * defense), so the UI always advances to step two on submit; it never
 * reveals whether an account exists.
 *
 * The one case that does NOT advance silently is a 409: this deployment has
 * email OTP configured as a second factor, which disqualifies email as a
 * recovery channel too (an AWS constraint — see `cognito.forgot_password`'s
 * docstring). That message names the actual situation ("ask an
 * administrator") rather than sending the user through a code-entry step
 * that could never work.
 */
function ForgotPasswordForm() {
  const router = useRouter();
  const [step, setStep] = useState<"request" | "confirm">("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  function describeApiError(err: unknown): string {
    if (err instanceof ApiError) {
      return typeof err.detail === "string"
        ? err.detail
        : "An error occurred. Please try again.";
    }
    return "An unexpected error occurred. Please try again.";
  }

  async function handleRequestSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const result = await forgotPassword(email);
      setInfo(result.message);
      setStep("confirm");
    } catch (err) {
      // Only a 409 (self-service reset unavailable in this deployment) should
      // ever land here — every other outcome resolves normally above.
      setError(describeApiError(err));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleConfirmSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");

    if (newPassword.length < 12) {
      setError("New password must be at least 12 characters.");
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (!code.trim()) {
      setError("Enter the 6-digit code we emailed you.");
      return;
    }

    setIsLoading(true);
    try {
      await confirmForgotPassword(email, code.trim(), newPassword);
      router.push("/login");
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-paper px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="w-full max-w-md"
      >
        <div className="mb-8">
          <h1 className="text-[36px] sm:text-[40px] font-semibold text-ink-900 leading-[1.1] tracking-tight font-sans">
            {step === "request" ? "Reset your password" : "Check your email"}
          </h1>
          <p className="mt-3 text-[13px] text-ink-500 leading-relaxed">
            {step === "request"
              ? "Enter your email and we'll send you a reset code, if an account exists."
              : info || "Enter the code we emailed you and choose a new password."}
          </p>
        </div>

        <div className="rounded-[var(--radius-card)] border border-line-control bg-surface-card p-7 shadow-[var(--elevation-raised)]">
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 rounded-[var(--radius-button)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-4 py-3 text-sm text-status-failed"
            >
              {error}
            </motion.div>
          )}

          {step === "request" ? (
            <form onSubmit={handleRequestSubmit} className="space-y-5">
              <div>
                <label htmlFor="email" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                  Email
                </label>
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

              <Button variant="primary" type="submit" disabled={isLoading} className="w-full py-3 text-[13px]">
                {isLoading ? "Sending…" : "Send reset code"}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleConfirmSubmit} className="space-y-5">
              <div>
                <label htmlFor="code" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                  Reset code
                </label>
                <div className="input-focus relative rounded-[var(--radius-button)] border border-line-control bg-surface-card transition-colors">
                  <KeyRound className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-400" />
                  <input
                    id="code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    required
                    className="w-full rounded-[var(--radius-button)] bg-transparent pl-10 pr-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none tracking-widest"
                    placeholder="123456"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="new-password" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                  New password
                </label>
                <div className="input-focus relative rounded-[var(--radius-button)] border border-line-control bg-surface-card transition-colors">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-400" />
                  <input
                    id="new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    minLength={12}
                    className="w-full rounded-[var(--radius-button)] bg-transparent pl-10 pr-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none"
                    placeholder="At least 12 characters"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="confirm-new-password" className="mb-1.5 block text-[11px] font-semibold text-ink-600 uppercase tracking-wider">
                  Confirm password
                </label>
                <div className="input-focus relative rounded-[var(--radius-button)] border border-line-control bg-surface-card transition-colors">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-400" />
                  <input
                    id="confirm-new-password"
                    type="password"
                    value={confirmNewPassword}
                    onChange={(e) => setConfirmNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    className="w-full rounded-[var(--radius-button)] bg-transparent pl-10 pr-3.5 py-2.5 text-ink-900 text-[14px] placeholder-ink-400 focus:border-brand focus:outline-none"
                    placeholder="Re-enter your new password"
                  />
                </div>
              </div>

              <Button variant="primary" type="submit" disabled={isLoading} className="w-full py-3 text-[13px]">
                {isLoading ? "Resetting…" : "Reset password"}
              </Button>
              <button
                type="button"
                onClick={() => { setStep("request"); setError(""); }}
                className="w-full text-center text-[12px] text-ink-400 hover:text-ink-700"
              >
                Use a different email
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-[11px] text-ink-400 leading-relaxed">
          <button
            type="button"
            onClick={() => router.push("/login")}
            className="hover:text-ink-700 hover:underline"
          >
            Back to sign in
          </button>
        </p>
      </motion.div>
    </div>
  );
}

export default function ForgotPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ForgotPasswordForm />
    </Suspense>
  );
}
