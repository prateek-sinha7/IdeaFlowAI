"use client";

import { Suspense, useState, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import { Mail, Lock } from "lucide-react";
import { login, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { resolveRedirectTarget } from "@/lib/authRedirect";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      await login(email, password);
      // Every user — including admins — lands on the main application by
      // default. If the user was bounced here from a specific protected page
      // (?redirect=...), return them there instead; the target is validated
      // against the internal-path allowlist to prevent an open redirect.
      // The admin dashboard is reached separately via its nav link/menu item.
      router.push(resolveRedirectTarget(searchParams.get("redirect")));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid email or password.");
      } else if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : "An error occurred. Please try again.");
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
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

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
