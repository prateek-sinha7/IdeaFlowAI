/**
 * REST client of the AI Workflow Builder (`/api/workflow-builder`, design 3.2.1).
 *
 * Every call goes through `authedFetch`, so a 401 reaches session expiry. A
 * non-ok response throws `ApiError`, whose constructor is the single seam that
 * hands a 503 `host_capacity_exhausted` body to `ServiceBusyProvider`.
 *
 * The Session_Stream (`GET /sessions/{id}/events`) is not here: it is read
 * incrementally by `useBuilderSessionStream`.
 */

import { ApiError, authedFetch } from "@/lib/api";
import { ENV } from "@/lib/env";
import type {
  BuilderModelsResponse,
  CreateSessionRequest,
  DraftRevisionOut,
  LinkRequest,
  SendMessageRequest,
  SessionDetail,
  SessionPage,
  SessionSummary,
  TurnAccepted,
  UndoRequest,
} from "@/types/workflowBuilder";

const BASE_PATH = "/api/workflow-builder";

/** Same fail-fast bound as the shared REST client (BUG-013 Part B). */
const REQUEST_TIMEOUT_MS = 30_000;

/** Largest page the server allows (design 3.2.1). */
export const SESSION_PAGE_MAX = 50;

/**
 * A fresh idempotency key for one user message. It matches the server's
 * `^[A-Za-z0-9_-]{8,64}$`. Keep the value and pass it again when re-sending
 * the same message after a network failure: a repeated id never starts a
 * second turn.
 */
export function newClientMessageId(): string {
  return crypto.randomUUID();
}

function sessionPath(sessionId: string): string {
  return `${BASE_PATH}/sessions/${encodeURIComponent(sessionId)}`;
}

/** Build the request init: bearer token and, when there is a body, JSON. */
function init(
  token: string,
  method: "GET" | "POST" | "DELETE",
  body?: unknown,
): RequestInit {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return {
    method,
    headers,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
}

/** Send one request; throw `ApiError` on a timeout or a non-ok response. */
async function send(path: string, options: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await authedFetch(`${ENV.API_URL}${path}`, {
      ...options,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `Request timeout after ${REQUEST_TIMEOUT_MS}ms (aborted)`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const body: unknown = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(response.status, detail);
  }
  return response;
}

async function requestJson<T>(path: string, options: RequestInit): Promise<T> {
  const response = await send(path, options);
  return (await response.json()) as T;
}

/** Chat_List for this user. Also the availability probe for the AI button. */
export function getBuilderModels(token: string): Promise<BuilderModelsResponse> {
  return requestJson(`${BASE_PATH}/models`, init(token, "GET"));
}

/** Create a session (create or edit mode). */
export function createSession(
  token: string,
  body: CreateSessionRequest,
): Promise<SessionDetail> {
  return requestJson(`${BASE_PATH}/sessions`, init(token, "POST", body));
}

/**
 * List own sessions, newest activity first. `workflowId` narrows the list to
 * the sessions linked to that saved workflow.
 */
export function listSessions(
  token: string,
  params: { cursor?: string | null; limit?: number; workflowId?: string | null } = {},
): Promise<SessionPage> {
  const query = new URLSearchParams();
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.workflowId) query.set("workflow_id", params.workflowId);
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  return requestJson(`${BASE_PATH}/sessions${suffix}`, init(token, "GET"));
}

/** Metadata, transcript, latest draft and running-turn snapshot. */
export function getSession(token: string, sessionId: string): Promise<SessionDetail> {
  return requestJson(sessionPath(sessionId), init(token, "GET"));
}

/** Cancel any running turn and delete the session. */
export async function deleteSession(token: string, sessionId: string): Promise<void> {
  await send(sessionPath(sessionId), init(token, "DELETE"));
}

/**
 * Send a message. Pass `clientMessageId` again when re-sending the same
 * message after a failure; leave it out for a new message.
 */
export function sendMessage(
  token: string,
  sessionId: string,
  message: Omit<SendMessageRequest, "client_message_id">,
  clientMessageId: string = newClientMessageId(),
): Promise<TurnAccepted> {
  const body: SendMessageRequest = { ...message, client_message_id: clientMessageId };
  return requestJson(`${sessionPath(sessionId)}/messages`, init(token, "POST", body));
}

/** Retry the latest failed turn without a second user message. */
export function retryTurn(
  token: string,
  sessionId: string,
  turnId: string,
): Promise<TurnAccepted> {
  return requestJson(
    `${sessionPath(sessionId)}/turns/${encodeURIComponent(turnId)}/retry`,
    init(token, "POST"),
  );
}

/** Cancel the running turn. The server answers 200 or 202; the body is unused. */
export async function cancelTurn(
  token: string,
  sessionId: string,
  turnId: string,
): Promise<void> {
  await send(
    `${sessionPath(sessionId)}/turns/${encodeURIComponent(turnId)}/cancel`,
    init(token, "POST"),
  );
}

/** Restore the canvas state that started the latest AI change. */
export function undoLastChange(
  token: string,
  sessionId: string,
  body: UndoRequest,
): Promise<DraftRevisionOut> {
  return requestJson(`${sessionPath(sessionId)}/undo`, init(token, "POST", body));
}

/** Link the session to a saved workflow the user owns. */
export function linkSession(
  token: string,
  sessionId: string,
  body: LinkRequest,
): Promise<SessionSummary> {
  return requestJson(`${sessionPath(sessionId)}/link`, init(token, "POST", body));
}
