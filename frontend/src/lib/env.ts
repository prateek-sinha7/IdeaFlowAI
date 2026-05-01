/**
 * Environment configuration for the frontend application.
 * Uses NEXT_PUBLIC_ prefixed variables for client-side access.
 */

export const ENV = {
  /** Base URL for REST API calls */
  API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  /** Base URL for WebSocket connections */
  WS_URL: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/chat",
} as const;
