"use client";

import { AlertCircle, X } from "lucide-react";

interface LaunchErrorBannerProps {
  message: string;
  onDismiss: () => void;
}

/**
 * A launch the server refused before any run existed (e.g. `uploads_missing`).
 * Fixed top-center overlay, so it causes no layout shift; announced as an alert.
 */
export function LaunchErrorBanner({ message, onDismiss }: LaunchErrorBannerProps) {
  return (
    <div
      role="alert"
      className="fixed left-1/2 top-4 z-50 flex max-w-[min(560px,calc(100vw-2rem))] -translate-x-1/2 items-start gap-2 rounded-[var(--radius-button)] border border-status-failed-border bg-status-failed-fill px-4 py-3 text-[12px] text-status-failed shadow-[var(--elevation-raised)]"
    >
      <AlertCircle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 flex-none" />
      <span className="flex-1">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="flex-none rounded-sm text-status-failed hover:text-status-failed-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
      >
        <X aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
