"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowLeft } from "lucide-react";
import { routes } from "@/lib/routes";
import { Button } from "@/components/ui/Button";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen">
      {/* LEFT — dark brand panel (~46%); mirrors the login page idiom */}
      <aside
        data-testid="not-found-brand-panel"
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
            It happens
          </p>
          <h2 className="text-[32px] leading-[1.15] font-semibold tracking-tight text-white font-sans">
            Page not found.
          </h2>
          <p className="mt-4 text-[14px] leading-relaxed text-white/60">
            This URL doesn't exist. Let's get you back on track to shipping faster
            with your agent workforce.
          </p>
        </div>

        {/* Static decoration — supporting context (no interactive affordances) */}
        <div className="flex flex-wrap gap-2">
          {["Lost?", "Typo?", "Moved."].map((tag) => (
            <span
              key={tag}
              className="rounded-[var(--radius-pill)] border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-medium text-white/60"
            >
              {tag}
            </span>
          ))}
        </div>
      </aside>

      {/* RIGHT — action area */}
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
            <div className="mb-4 inline-flex items-center justify-center w-16 h-16 rounded-[var(--radius-card)] bg-surface-card border border-line-control">
              <span className="text-[28px] font-bold text-ink-400">404</span>
            </div>
            <h1 className="text-[36px] sm:text-[40px] font-semibold text-ink-900 leading-[1.1] tracking-tight font-sans">
              Not found
            </h1>
            <p className="mt-3 text-[13px] text-ink-500 leading-relaxed">
              The page you're looking for doesn't exist or has been moved.
            </p>
          </motion.div>

          {/* Card */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="rounded-[var(--radius-card)] border border-line-control bg-surface-card p-7 shadow-[var(--elevation-raised)]"
          >
            <div className="space-y-4">
              <p className="text-[13px] text-ink-600 leading-relaxed">
                Here are your options to get back on track:
              </p>

              <div className="space-y-3 pt-2">
                <Link href={routes.home()} className="block">
                  <Button
                    variant="primary"
                    className="w-full py-3 text-[13px]"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    Back to dashboard
                  </Button>
                </Link>

                <Link href={routes.create()} className="block">
                  <Button
                    variant="secondary"
                    className="w-full py-3 text-[13px]"
                  >
                    Create a workflow
                  </Button>
                </Link>

                <Link href={routes.login()} className="block">
                  <Button
                    variant="secondary"
                    className="w-full py-3 text-[13px]"
                  >
                    Sign in
                  </Button>
                </Link>
              </div>
            </div>
          </motion.div>

          {/* Footer note */}
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="mt-6 text-center text-[11px] text-ink-400 leading-relaxed"
          >
            If you believe this is an error, check the URL for typos or contact support.
          </motion.p>
        </motion.div>
      </div>
    </div>
  );
}
