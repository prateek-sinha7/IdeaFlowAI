/**
 * Shared axios instance for the new consolidated API client (frontend/src/store/api/).
 *
 * Reuses the existing token storage (getToken) and ApiError shape from
 * @/lib/api so error handling stays consistent while lib/api.ts is still
 * around. The JWT is auto-attached via a request interceptor so resource
 * modules don't need to thread a token through every call — callers that
 * need a different auth scheme (e.g. the Flowin API key on handoff/mcp
 * endpoints) can set their own `Authorization`/custom header explicitly and
 * the interceptor will leave it alone.
 */

import axios, { AxiosError, type AxiosRequestConfig } from "axios";
import { ApiError, getToken, handleSessionExpiry, isSessionExpiryExempt } from "@/lib/api";
import { ENV } from "@/lib/env";

export const http = axios.create({
  baseURL: ENV.API_URL,
});

http.interceptors.request.use((config) => {
  const hasAuthHeader = config.headers?.Authorization !== undefined;
  if (!hasAuthHeader) {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      // FR-015 — this axios instance is a second shared request path (Library's
      // agent/skill/hook fetches and everything else in store/api/ go through
      // it, bypassing lib/api.ts's fetchWithAuth entirely), so it needs its own
      // 401 -> session-expired redirect rather than relying on the fetch-based
      // path to cover it. Same exempt list as lib/api.ts so a failed login or
      // change-password 401 here (if ever wired up) shows its own inline error
      // instead of bouncing back to /login.
      const path = error.config?.url ?? "";
      if (error.response.status === 401 && !isSessionExpiryExempt(path)) {
        handleSessionExpiry();
      }
      const body = error.response.data as { detail?: unknown } | undefined;
      return Promise.reject(
        new ApiError(error.response.status, body?.detail ?? body ?? error.message)
      );
    }
    return Promise.reject(error);
  }
);

/** Build multipart/form-data headers config for file uploads. */
export function multipartConfig(): AxiosRequestConfig {
  return { headers: { "Content-Type": "multipart/form-data" } };
}
