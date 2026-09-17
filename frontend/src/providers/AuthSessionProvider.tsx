"use client";

/**
 * AuthSessionProvider — app-wide owner of browser-session expiry.
 *
 * Cognito remains the credential authority: this provider only refreshes the
 * browser's short-lived access token before it expires and redirects after a
 * confirmed terminal refresh failure. It also subscribes to the API client's
 * terminal-bearer-failure signal so every authenticated request can end the
 * session through the same safe redirect path.
 */

import { useCallback, useEffect, useRef, type ReactNode } from "react";
import {
  expireSession,
  getToken,
  getTokenExpiryMs,
  onSessionExpired,
  onTokenChanged,
  refreshOnce,
  SESSION_REFRESH_SKEW_MS,
} from "@/lib/api";
import { buildLoginRedirect } from "@/lib/authRedirect";

export interface AuthSessionProviderProps {
  children: ReactNode;
}

export function AuthSessionProvider({
  children,
}: AuthSessionProviderProps): ReactNode {
  const isRedirectingRef = useRef(false);

  const redirectToLogin = useCallback(() => {
    if (typeof window === "undefined" || isRedirectingRef.current) return;
    if (window.location.pathname === "/login") return;

    isRedirectingRef.current = true;
    // Full navigation intentionally discards protected in-memory state after
    // the credential has been cleared. `buildLoginRedirect` permits only an
    // internal return path, preventing an open-redirect at this boundary.
    window.location.assign(buildLoginRedirect());
  }, []);

  useEffect(() => {
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;
    let isDisposed = false;

    const clearRefreshTimer = () => {
      if (refreshTimer !== null) {
        clearTimeout(refreshTimer);
        refreshTimer = null;
      }
    };

    function scheduleRefresh(): void {
      clearRefreshTimer();

      const token = getToken();
      const expiresAt = getTokenExpiryMs(token);
      if (!token || expiresAt === null) return;

      const delay = expiresAt - Date.now() - SESSION_REFRESH_SKEW_MS;
      if (delay <= 0) {
        void refreshOrExpire(expiresAt);
        return;
      }

      refreshTimer = setTimeout(() => {
        void refreshOrExpire(expiresAt);
      }, delay);
    }

    async function refreshOrExpire(expiresAt: number): Promise<void> {
      const refreshedToken = await refreshOnce();
      if (isDisposed) return;

      if (refreshedToken) {
        scheduleRefresh();
        return;
      }

      // A network failure before the access token expires must not sign the
      // user out early. Retry once at true expiry; if the provider session is
      // still unavailable then, terminate the browser session.
      const currentExpiry = getTokenExpiryMs(getToken());
      if (currentExpiry !== expiresAt) {
        scheduleRefresh();
        return;
      }

      const remainingLifetime = expiresAt - Date.now();
      if (remainingLifetime > 0) {
        refreshTimer = setTimeout(() => {
          void refreshOrExpire(expiresAt);
        }, remainingLifetime);
        return;
      }

      expireSession();
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") scheduleRefresh();
    };

    const unsubscribeTokenChanges = onTokenChanged(scheduleRefresh);
    const unsubscribeSessionExpiry = onSessionExpired(redirectToLogin);

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", scheduleRefresh);
    scheduleRefresh();

    return () => {
      isDisposed = true;
      clearRefreshTimer();
      unsubscribeTokenChanges();
      unsubscribeSessionExpiry();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("online", scheduleRefresh);
    };
  }, [redirectToLogin]);

  return children;
}
