/**
 * API client utility for communicating with the backend.
 * Uses the fetch API with JWT-based authentication.
 */

import type {
  AuthResponse,
  ChatMessage,
  ChatSession,
  User,
} from "@/types/index";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "auth_token";

// --- Token management ---

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// --- HTTP helpers ---

class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    const message =
      typeof detail === "string" ? detail : JSON.stringify(detail);
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, options);

  if (!response.ok) {
    const body = await response.json().catch(() => ({
      detail: response.statusText,
    }));
    throw new ApiError(response.status, body.detail ?? body);
  }

  return response.json() as Promise<T>;
}

function authHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

// --- Auth API ---

export async function register(
  email: string,
  password: string
): Promise<AuthResponse> {
  const data = await request<AuthResponse>("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  setToken(data.token);
  return data;
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  const data = await request<AuthResponse>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  setToken(data.token);
  return data;
}

export async function getMe(token: string): Promise<User> {
  return request<User>("/api/auth/me", {
    method: "GET",
    headers: authHeaders(token),
  });
}

// --- Chat API ---

/** Raw message shape from the backend (snake_case fields) */
export interface RawMessageResponse {
  id: string;
  chat_session_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface ChatDetailResponse {
  id: string;
  title: string;
  last_activity: string;
  created_at: string;
  messages: RawMessageResponse[];
  final_output: string | null;
}

export async function createChat(
  token: string,
  title?: string
): Promise<ChatSession> {
  return request<ChatSession>("/api/chats", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ title: title ?? null }),
  });
}

export async function getChats(token: string): Promise<ChatSession[]> {
  return request<ChatSession[]>("/api/chats", {
    method: "GET",
    headers: authHeaders(token),
  });
}

export async function getChat(
  token: string,
  id: string
): Promise<ChatDetailResponse> {
  return request<ChatDetailResponse>(`/api/chats/${id}`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

export async function addMessage(
  token: string,
  chatId: string,
  content: string,
  role: string = "user"
): Promise<ChatMessage> {
  return request<ChatMessage>(`/api/chats/${chatId}/messages`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify({ content, role }),
  });
}

export { ApiError };
