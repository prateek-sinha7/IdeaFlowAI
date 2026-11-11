/**
 * Pure helpers for the Connectors OAuth popup flow.
 *
 * Three parties share these rules: the Connectors page (opens the popup and
 * listens), the /connectors/oauth-complete landing page (posts the result) and
 * their tests. Everything read from a URL or a BroadcastChannel is untrusted,
 * so it is validated here before any code acts on it.
 */
import { CONNECTOR_KEY_PATTERN } from "@/types/connectors";

/** Popup window name prefix. The landing page uses it to know it runs in a popup. */
export const POPUP_NAME_PREFIX = "flowin-connect-";

/** BroadcastChannel the landing page posts on and the Connectors page listens to. */
export const CONNECTORS_CHANNEL = "flowin-connectors";

export const OAUTH_COMPLETE_TYPE = "oauth-complete";

/** Popup features: `window.open` returns the handle only without `noopener`. */
export const POPUP_FEATURES = "popup,width=600,height=720";

/** How often the page re-reads GET /api/connectors while an authorization is pending. */
export const AUTHORIZATION_POLL_MS = 2_000;

/** Server-side state TTL; the page stops polling when it passes. */
export const AUTHORIZATION_TTL_MS = 10 * 60 * 1000;

/** Reason codes the backend callback can put in `reason=`. Anything else is not shown. */
export const CALLBACK_REASONS = [
  "invalid_state",
  "access_denied",
  "provider_error",
  "missing_code",
  "issuer_missing",
  "issuer_mismatch",
  "token_exchange_failed",
  "account_lookup_failed",
  "no_accessible_sites",
  "not_configured",
  "server_error",
] as const;

export type CallbackReason = (typeof CALLBACK_REASONS)[number];

export type OAuthResult = "connected" | "error";

export interface OAuthCompleteMessage {
  type: typeof OAUTH_COMPLETE_TYPE;
  connector: string;
  result: OAuthResult;
  reason: CallbackReason | null;
}

export function popupNameFor(connectorKey: string): string {
  return `${POPUP_NAME_PREFIX}${connectorKey}`;
}

export function isConnectorPopupName(windowName: string): boolean {
  return windowName.startsWith(POPUP_NAME_PREFIX);
}

export function isCallbackReason(value: unknown): value is CallbackReason {
  return typeof value === "string" && (CALLBACK_REASONS as readonly string[]).includes(value);
}

export function isConnectorKey(value: unknown): value is string {
  return typeof value === "string" && CONNECTOR_KEY_PATTERN.test(value);
}

function isOAuthResult(value: unknown): value is OAuthResult {
  return value === "connected" || value === "error";
}

/** Type guard for a message received on the BroadcastChannel. */
export function isOAuthCompleteMessage(value: unknown): value is OAuthCompleteMessage {
  if (typeof value !== "object" || value === null) return false;
  const m = value as Record<string, unknown>;
  return (
    m.type === OAUTH_COMPLETE_TYPE &&
    isConnectorKey(m.connector) &&
    isOAuthResult(m.result) &&
    (m.reason === null || isCallbackReason(m.reason))
  );
}

/**
 * Build a message from the landing-page query. Returns null unless `connector`
 * and `result` are valid. An unknown or missing `reason` becomes null so the
 * page shows a generic message. A successful result never carries a reason.
 * The query is only a hint: page state always comes from GET /api/connectors.
 */
export function parseOAuthResult(params: {
  get(name: string): string | null;
}): OAuthCompleteMessage | null {
  const connector = params.get("connector");
  const result = params.get("result");
  if (!isConnectorKey(connector) || !isOAuthResult(result)) return null;
  const reason = params.get("reason");
  return {
    type: OAUTH_COMPLETE_TYPE,
    connector,
    result,
    reason: result === "error" && isCallbackReason(reason) ? reason : null,
  };
}

/**
 * True only for an https URL. The popup (or this tab) is navigated only after
 * this check, so a bad server response cannot send the user to javascript:,
 * data: or a plain-http address.
 */
export function isHttpsUrl(value: string): boolean {
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}
