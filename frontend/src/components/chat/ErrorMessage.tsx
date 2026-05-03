"use client";

import { motion } from "motion/react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export interface ErrorMessageProps {
  message: string;
  code?: string;
  recoverable?: boolean;
  onRetry?: () => void;
}

/**
 * A compact error message component with left border accent.
 * Shows an AlertTriangle icon, the error message, and a "Try Again" button for recoverable errors.
 */
export function ErrorMessage({
  message,
  code,
  recoverable = true,
  onRetry,
}: ErrorMessageProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="relative flex gap-3 rounded-lg bg-red-950/20 px-4 py-3 my-6 ml-11 border-l-2 border-red-500/50"
    >
      <div className="flex-shrink-0 mt-0.5">
        <AlertTriangle className="h-4 w-4 text-red-400/80" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] text-red-200/90 leading-relaxed">{message}</p>
        {code && (
          <p className="mt-1 text-[11px] text-red-400/50 font-mono">
            {code}
          </p>
        )}
        {recoverable && onRetry && (
          <button
            onClick={onRetry}
            className="mt-2.5 inline-flex items-center gap-1.5 rounded-md bg-red-500/10 px-2.5 py-1 text-[11px] font-medium text-red-300/90 hover:bg-red-500/20 transition-colors duration-200"
          >
            <RefreshCw className="h-3 w-3" />
            Try Again
          </button>
        )}
        {!recoverable && (
          <p className="mt-2 text-[11px] text-red-400/60 leading-relaxed">
            {code === "api_key_missing"
              ? "The AI service needs to be configured by an administrator."
              : code === "auth_error"
              ? "The AI service credentials are invalid. Please contact support."
              : "This error cannot be resolved by retrying."}
          </p>
        )}
      </div>
    </motion.div>
  );
}
