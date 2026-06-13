/**
 * Shared constants for the Flowin E2E suite.
 * The app's defaults point REST → http://localhost:8000 and WS →
 * ws://localhost:8000/ws/chat (see frontend/src/lib/env.ts). In mocked mode
 * Playwright intercepts BOTH from the browser, so no backend is required and no
 * NEXT_PUBLIC_* env wiring is needed — the Next app is served on :3000 and its
 * calls to :8000 are routed by our fixtures.
 */

export const APP_ORIGIN = "http://localhost:3000";
export const TOKEN_KEY = "auth_token"; // localStorage key — frontend/src/lib/api.ts
export const TEST_JWT = "e2e.test.jwt-token"; // any non-empty string; the backend never sees it in mocked mode

/** Regex that matches the WS endpoint regardless of host/port. */
export const WS_URL_RE = /\/ws\/chat(\?|$)/;

/** The 5 catalog models surfaced by GET /api/capabilities → model_catalog.
 *  Mirrors backend agents/capabilities/model_catalog.py (user_allowed filtered
 *  by the AgentModelPicker). Use this in mocked mode; in live mode the real
 *  endpoint is hit. */
export const MODEL_CATALOG = [
  { id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0", label: "Haiku 4.5", description: "Fast, low-cost", tier: "fast", cost_class: "low", provider: "bedrock", context_window: 200000, user_allowed: true },
  { id: "eu.anthropic.claude-sonnet-4-5-20250101-v1:0", label: "Sonnet 4.5", description: "Balanced", tier: "balanced", cost_class: "medium", provider: "bedrock", context_window: 200000, user_allowed: true },
  { id: "eu.anthropic.claude-sonnet-4-6-20251101-v1:0", label: "Sonnet 4.6", description: "Balanced+", tier: "balanced", cost_class: "medium", provider: "bedrock", context_window: 200000, user_allowed: true },
  { id: "eu.anthropic.claude-opus-4-5-20250201-v1:0", label: "Opus 4.5", description: "Most capable", tier: "powerful", cost_class: "high", provider: "bedrock", context_window: 200000, user_allowed: true },
  { id: "eu.anthropic.claude-opus-4-6-20251201-v1:0", label: "Opus 4.6", description: "Most capable+", tier: "powerful", cost_class: "high", provider: "bedrock", context_window: 200000, user_allowed: false },
] as const;

/** A representative capability palette (the FE only consumes model_catalog today,
 *  but /api/capabilities returns both). */
export const CAPABILITIES = [
  { kind: "strategy", name: "single_shot", user_allowed: false, config_schema: {} },
  { kind: "strategy", name: "task_loop", user_allowed: true, config_schema: {} },
  { kind: "strategy", name: "fanout_batch", user_allowed: true, config_schema: {} },
  { kind: "strategy", name: "wave_scheduler", user_allowed: true, config_schema: {} },
  { kind: "validator", name: "html_static", user_allowed: true, config_schema: {} },
  { kind: "deliverable", name: "single_file", user_allowed: true, config_schema: {} },
  { kind: "gate", name: "human", user_allowed: true, config_schema: {} },
] as const;
