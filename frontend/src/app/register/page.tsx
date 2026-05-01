"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
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
        // Handle field-level validation errors
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
    <div className="flex min-h-screen items-center justify-center bg-black px-4">
      <div className="w-full max-w-md rounded-lg border border-grey/30 bg-navy p-8 shadow-lg">
        <h1 className="mb-6 text-center text-2xl font-semibold text-white">
          Create Account
        </h1>

        {error && (
          <div className="mb-4 rounded border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label
              htmlFor="email"
              className="mb-1 block text-sm font-medium text-grey"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full rounded border border-grey/30 bg-black px-3 py-2 text-white placeholder-grey/50 focus:border-white focus:outline-none focus:ring-1 focus:ring-white"
              placeholder="you@example.com"
            />
            {fieldErrors.email && (
              <p className="mt-1 text-sm text-red-400">{fieldErrors.email}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-sm font-medium text-grey"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => handlePasswordChange(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full rounded border border-grey/30 bg-black px-3 py-2 text-white placeholder-grey/50 focus:border-white focus:outline-none focus:ring-1 focus:ring-white"
              placeholder="••••••••"
            />
            {fieldErrors.password && (
              <p className="mt-1 text-sm text-red-400">
                {fieldErrors.password}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded bg-white px-4 py-2 font-medium text-black transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-grey">
          Already have an account?{" "}
          <Link
            href="/login"
            className="text-white underline hover:opacity-85"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
