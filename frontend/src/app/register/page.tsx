"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "motion/react";
import { Mail, Lock, Sparkles } from "lucide-react";
import { register, ApiError } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);

  function validatePassword(value: string): string {
    if (value.length > 0 && value.length < 8) {
      return "Password must be at least 8 characters.";
    }
    return "";
  }

  function handlePasswordChange(value: string) {
    setPassword(value);
    const passwordError = validatePassword(value);
    setFieldErrors((prev) => ({
      ...prev,
      password: passwordError,
    }));
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setFieldErrors({});

    // Client-side validation
    if (password.length < 8) {
      setFieldErrors({ password: "Password must be at least 8 characters." });
      return;
    }

    setIsLoading(true);

    try {
      await register(email, password);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setFieldErrors({ email: "An account with this email already exists." });
      } else if (err instanceof ApiError && err.status === 422) {
        const detail = err.detail;
        if (Array.isArray(detail)) {
          const errors: Record<string, string> = {};
          for (const item of detail) {
            const field = item.field || item.loc?.[item.loc.length - 1] || "general";
            errors[field] = item.message || item.msg || "Invalid value";
          }
          setFieldErrors(errors);
        } else if (typeof detail === "string") {
          setError(detail);
        } else {
          setError("Validation failed. Please check your input.");
        }
      } else if (err instanceof ApiError) {
        setError(
          typeof err.detail === "string"
            ? err.detail
            : "An error occurred. Please try again."
        );
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 gradient-radial" style={{ backgroundColor: 'var(--theme-bg)' }}>
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="w-full max-w-md"
      >
        {/* Branding */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="flex items-center justify-center gap-2.5 mb-8"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-navy border border-grey/20">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <h2 className="text-xl font-semibold text-white tracking-tight">
            IdeaFlow AI
          </h2>
        </motion.div>

        {/* Card */}
        <div className="rounded-2xl border border-grey/20 backdrop-blur-md p-8 shadow-2xl shadow-navy/20" style={{ backgroundColor: 'var(--theme-surface)', opacity: 0.85 }}>
          <h1 className="mb-6 text-center text-2xl font-semibold text-white">
            Create Account
          </h1>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
            >
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-grey"
              >
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-grey/50" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  className="w-full rounded-xl border border-grey/20 bg-black/50 pl-10 pr-3 py-2.5 text-white text-sm placeholder-grey/40 focus:border-grey/50 focus:outline-none focus:ring-1 focus:ring-grey/30 transition-colors"
                  placeholder="you@example.com"
                />
              </div>
              {fieldErrors.email && (
                <p className="mt-1.5 text-sm text-red-400">{fieldErrors.email}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-grey"
              >
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-grey/50" />
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => handlePasswordChange(e.target.value)}
                  required
                  autoComplete="new-password"
                  className="w-full rounded-xl border border-grey/20 bg-black/50 pl-10 pr-3 py-2.5 text-white text-sm placeholder-grey/40 focus:border-grey/50 focus:outline-none focus:ring-1 focus:ring-grey/30 transition-colors"
                  placeholder="••••••••"
                />
              </div>
              {fieldErrors.password && (
                <p className="mt-1.5 text-sm text-red-400">
                  {fieldErrors.password}
                </p>
              )}
            </div>

            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              type="submit"
              disabled={isLoading}
              className="w-full rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? "Creating account..." : "Create Account"}
            </motion.button>
          </form>

          <p className="mt-6 text-center text-sm text-grey">
            Already have an account?{" "}
            <Link
              href="/login"
              className="text-white underline underline-offset-2 hover:opacity-80 transition-opacity"
            >
              Sign in
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
