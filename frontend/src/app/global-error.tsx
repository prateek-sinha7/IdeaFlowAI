"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { motion } from "motion/react";
import { AlertCircle } from "lucide-react";
import { routes, parseViewPath, screenLabel } from "@/lib/routes";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export default function GlobalErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const pathname = usePathname();

  useEffect(() => {
    // Log the error to an error reporting service
    // FR-012/SC-006 (015-frontend-routing, T28): tag with the screen that was
    // showing when the error fired, so error tracking can be broken down by screen.
    const screen = screenLabel(parseViewPath(pathname.split("/").filter(Boolean)));
    console.error(`[${screen}] Global error boundary caught:`, error);
  }, [error, pathname]);

  return (
    <html lang="en">
      <body className="bg-surface-paper">
        <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="w-full max-w-md"
          >
            {/* Icon + status code */}
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, delay: 0.1 }}
              className="mb-6 flex justify-center"
            >
              <div className="rounded-full bg-surface-card border border-line-control p-4">
                <AlertCircle className="h-8 w-8 text-status-failed" />
              </div>
            </motion.div>

            {/* Heading */}
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="mb-8 text-center"
            >
              <h1 className="text-[36px] sm:text-[40px] font-semibold text-ink-900 leading-[1.1] tracking-tight font-sans">
                Something went wrong
              </h1>
              <p className="mt-3 text-[13px] text-ink-500 leading-relaxed">
                An unexpected error occurred. Our team has been notified.
              </p>
            </motion.div>

            {/* Content card */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.3 }}
            >
              <Card className="p-8 text-center">
                <p className="mb-6 text-[13px] text-ink-600">
                  Error code: <span className="font-semibold text-ink-900">500</span>
                </p>

                {/* Actions */}
                <div className="space-y-3">
                  <Button
                    variant="primary"
                    onClick={() => reset()}
                    className="w-full py-3 text-[13px]"
                  >
                    Try again
                  </Button>

                  <Button
                    variant="secondary"
                    // Same reason as error.tsx: this boundary replaces the whole
                    // <html>, so the app's router context may itself be broken —
                    // a hard navigation is the only reliable way out.
                    onClick={() => { window.location.href = routes.home(); }}
                    className="w-full py-3 text-[13px]"
                  >
                    Back to dashboard
                  </Button>

                  <Button
                    variant="secondary"
                    onClick={() => { window.location.href = routes.login(); }}
                    className="w-full py-3 text-[13px]"
                  >
                    Back to login
                  </Button>
                </div>
              </Card>
            </motion.div>

            {/* Help footer */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.4 }}
              className="mt-6 text-center text-[11px] text-ink-400 leading-relaxed"
            >
              If this problem persists, contact your administrator.
            </motion.p>
          </motion.div>
        </div>
      </body>
    </html>
  );
}
