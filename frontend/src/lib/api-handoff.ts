/**
 * API client functions for the /flowin-handoff feature.
 *
 * Split from lib/api.ts to keep the surface for the new feature
 * isolated. All calls go through the same fetch helper as the rest of
 * the app and use the JWT in localStorage via the existing Bearer
 * header pattern.
 */

import { ENV } from "@/lib/env";
import { ApiError, errorMessageFromDetail, handleSessionExpiry } from "@/lib/api";

const BASE_URL = ENV.API_URL;

export interface HandoffSessionView {
  id: string;
  token: string;
  task_description: string;
  repo_url: string;
  mode: "auto" | "coding" | "test";
  resolved_mode: string | null;
  status: "pending" | "running" | "completed" | "failed" | "expired";
  source_client: string | null;
  source_branch: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  expires_at: string;
  pr_url: string | null;
  pr_number: number | null;
  branch_name: string | null;
  pipeline_output: Record<string, unknown> | null;
  error: string | null;
  issuer_email: string | null;
  has_github_pat: boolean;
}

export interface GithubPatStatus {
  github_username: string | null;
  scopes: string | null;
  last_4: string;
  created_at: string;
  updated_at: string;
}

export interface ApiKeySummary {
  id: string;
  name: string;
  /** ISO timestamp, or null for a key minted before expiry existed (never expires). */
  expires_at?: string | null;
  token_prefix: string;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKeySummary {
  token: string;
}

async function authedJson<T>(
  token: string,
  path: string,
  init: RequestInit = {}
): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.headers || {}),
      },
    });
  } catch (err) {
    // ISS-301 — a network-layer rejection (offline, DNS failure, aborted
    // connection, backend unreachable) never reached the server, so it says
    // nothing about whether the resource exists. Re-throw it as ApiError(0) —
    // lib/api.ts's own marker for "no HTTP response was received" (see its
    // abort path) — so every handoff call site can branch on `status` instead
    // of guessing from the message text.
    throw new ApiError(
      0,
      err instanceof Error ? err.message : "Network request failed"
    );
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  const body = await resp.json().catch(() => ({ detail: resp.statusText }));
  if (!resp.ok) {
    // FR-015 — mirror useRunStream.ts's handleAuthExpiry: a 401 here means the
    // token in localStorage is stale/invalid, so route through the shared
    // clear+redirect helper instead of surfacing a generic inline error that
    // strands the user on a dead handoff page.
    if (resp.status === 401) {
      handleSessionExpiry();
    }
    // ISS-224 — a 422's list-shaped `detail` embeds the rejected value in
    // `input`; stringifying the body rendered a submitted PAT back on-page.
    const message = errorMessageFromDetail(body?.detail) ?? JSON.stringify(body);
    // ISS-301 — carry the HTTP status on the error. A bare Error left every
    // caller unable to tell a real 404 apart from any other failure.
    throw new ApiError(resp.status, message || `HTTP ${resp.status}`);
  }
  return body as T;
}

// --- Handoff ----------------------------------------------------------

export function getHandoff(
  token: string,
  handoffToken: string
): Promise<HandoffSessionView> {
  return authedJson<HandoffSessionView>(
    token,
    `/api/handoff/${encodeURIComponent(handoffToken)}`,
    { method: "GET" }
  );
}

export function startHandoff(
  token: string,
  handoffToken: string
): Promise<{ status: string; started_at: string }> {
  return authedJson(
    token,
    `/api/handoff/${encodeURIComponent(handoffToken)}/start`,
    { method: "POST" }
  );
}

// --- GitHub PAT --------------------------------------------------------

export function getGithubPatStatus(
  token: string
): Promise<GithubPatStatus | null> {
  return authedJson<GithubPatStatus | null>(token, "/api/settings/github-pat", {
    method: "GET",
  });
}

export function saveGithubPat(
  token: string,
  pat: string
): Promise<GithubPatStatus> {
  return authedJson<GithubPatStatus>(token, "/api/settings/github-pat", {
    method: "PUT",
    body: JSON.stringify({ pat }),
  });
}

export function deleteGithubPat(token: string): Promise<void> {
  return authedJson<void>(token, "/api/settings/github-pat", {
    method: "DELETE",
  });
}

// --- API keys ---------------------------------------------------------

export function listApiKeys(token: string): Promise<ApiKeySummary[]> {
  return authedJson<ApiKeySummary[]>(token, "/api/settings/api-keys", {
    method: "GET",
  });
}

export function createApiKey(
  token: string,
  name: string
): Promise<ApiKeyCreated> {
  return authedJson<ApiKeyCreated>(token, "/api/settings/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function revokeApiKey(token: string, keyId: string): Promise<void> {
  return authedJson<void>(
    token,
    `/api/settings/api-keys/${encodeURIComponent(keyId)}`,
    { method: "DELETE" }
  );
}
