/**
 * Every user-visible string of the Connectors page that depends on data.
 *
 * Pure functions with no React, so the wording is one place to review and the
 * tests can pin each message. Nothing here names a provider: the connector's
 * own `display_name` is passed in, which keeps the page generic (SC-001 at the
 * UI layer). No message contains a token, code or state, and server text is
 * only used where the hook already treats it as displayable.
 */
import type { CallbackReason } from "@/lib/connectorPopup";
import type { ConnectorNotice } from "@/hooks/useConnectorAuthorization";
import type { ConnectorAccount, ConnectorStatus, ProviderRevocation } from "@/types/connectors";

export const PAGE_TITLE = "Connectors";
export const PAGE_SUBTITLE =
  "Connect your accounts so your custom workflows can use them. Tokens stay on the server.";
export const EMPTY_MESSAGE = "No connectors are available.";
export const LOADING_MESSAGE = "Loading connectors";
export const LOAD_ERROR_FALLBACK = "Connectors could not be loaded.";

const STATUS_LABELS: Record<ConnectorStatus, string> = {
  connected: "Connected",
  not_connected: "Not connected",
  expired: "Expired",
  not_configured: "Not configured",
};

export function statusLabel(status: ConnectorStatus): string {
  return STATUS_LABELS[status];
}

export function expiredMessage(name: string): string {
  return `Your ${name} connection expired. Reconnect to keep using its tools.`;
}

export function notConfiguredMessage(name: string): string {
  return `${name} is not configured on this server.`;
}

export function authorizingMessage(name: string): string {
  return `Waiting for you to finish signing in to ${name} in the pop-up window.`;
}

export function disconnectingMessage(name: string): string {
  return `Disconnecting ${name}…`;
}

/** "Connected as Jane Doe (@jane)": the display name first, the login when it adds something. */
export function accountLabel(account: ConnectorAccount): string {
  const { display_name: displayName, login, id } = account;
  if (displayName && login && displayName !== login) return `${displayName} (${login})`;
  return displayName || login || id;
}

/** "Sep 1, 2026" in the viewer's locale, or null when the server value is not a date. */
export function formatConnectedDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

const REASON_MESSAGES: Record<CallbackReason, (name: string) => string> = {
  invalid_state: () => "The sign-in link expired or was already used. Try connecting again.",
  access_denied: () => "Access was declined, so nothing was connected.",
  provider_error: (name) => `${name} reported an error during sign-in. Try again.`,
  missing_code: (name) => `${name} did not send back an authorization code. Try again.`,
  issuer_missing: () => "The sign-in response could not be verified, so it was rejected. Try again.",
  issuer_mismatch: () => "The sign-in response could not be verified, so it was rejected. Try again.",
  token_exchange_failed: (name) => `${name} did not accept the sign-in. Try again.`,
  account_lookup_failed: (name) =>
    `You signed in, but your ${name} account details could not be read. Try again.`,
  no_accessible_sites: (name) =>
    `Your ${name} account has no sites this app can use. Check your access, then try again.`,
  not_configured: (name) => notConfiguredMessage(name),
  server_error: () => "Something went wrong on our side. Try again in a moment.",
};

export function reasonMessage(reason: CallbackReason, name: string): string {
  return REASON_MESSAGES[reason](name);
}

export function disconnectResultMessage(revocation: ProviderRevocation, name: string): string {
  switch (revocation) {
    case "revoked":
      return `${name} is disconnected, and its access grant was revoked at the provider.`;
    case "failed":
      return `${name} is disconnected here, but the provider did not confirm the revoke. You can also remove the grant in your ${name} account settings.`;
    case "not_attempted":
      return `${name} is disconnected here. The grant could not be revoked automatically, so remove it in your ${name} account settings if you want.`;
  }
}

export function disconnectFailedMessage(name: string): string {
  return `Could not disconnect ${name}. Try again.`;
}

export function disconnectDialogTitle(name: string): string {
  return `Disconnect ${name}?`;
}

export function disconnectDialogBody(name: string): string {
  return `Flowin will delete the stored connection and ask ${name} to revoke the access it granted. Workflows that use ${name} tools will stop working until you connect again.`;
}

export type BannerTone = "success" | "info" | "error";

export interface Banner {
  tone: BannerTone;
  text: string;
}

/**
 * The text and tone of the result banner for a notice.
 * @param name Display name of the notice's connector (the key when it is unknown).
 */
export function bannerFor(notice: ConnectorNotice, name: string): Banner {
  switch (notice.kind) {
    case "connected":
      return { tone: "success", text: `${name} is connected.` };
    case "cancelled":
      return { tone: "info", text: `Sign-in to ${name} was cancelled.` };
    case "timed_out":
      return { tone: "error", text: `Sign-in to ${name} timed out. Try again.` };
    case "disconnected":
      return { tone: "success", text: disconnectResultMessage(notice.providerRevocation, name) };
    case "popup_blocked":
      return { tone: "info", text: "Your browser blocked the sign-in window." };
    case "error":
      if (notice.reason) return { tone: "error", text: reasonMessage(notice.reason, name) };
      return { tone: "error", text: notice.message || `Could not connect ${name}. Try again.` };
  }
}
