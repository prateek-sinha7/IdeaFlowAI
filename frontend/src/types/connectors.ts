/**
 * Connectors API types and runtime type guards.
 *
 * The shapes mirror `backend/app/api/connectors.py`. TypeScript types are not
 * validated at runtime, so every response is checked by the guards below at the
 * API boundary (store/api/connectors.ts). Unknown extra fields are tolerated so
 * the backend can add fields without breaking the page. A response never
 * contains a token, code, state or verifier.
 */

export const CONNECTOR_STATUSES = ["connected", "not_connected", "expired", "not_configured"] as const;
export type ConnectorStatus = (typeof CONNECTOR_STATUSES)[number];

export const CONNECTOR_MODES = ["remote_mcp", "native_api"] as const;
export type ConnectorMode = (typeof CONNECTOR_MODES)[number];

/** Same rule as the backend path validation for `{key}`. */
export const CONNECTOR_KEY_PATTERN = /^[a-z][a-z0-9]{1,31}$/;

export interface ConnectorAccount {
  id: string;
  display_name: string | null;
  login: string | null;
}

export interface ConnectorSite {
  id: string;
  name: string;
  url: string;
}

export interface ConnectorSummary {
  key: string;
  display_name: string;
  description: string;
  icon: string;
  docs_url: string;
  mode: ConnectorMode;
  status: ConnectorStatus;
  account: ConnectorAccount | null;
  requested_scopes: string[];
  granted_scopes: string[];
  sites: ConnectorSite[];
  connected_at: string | null;
  last_refreshed_at: string | null;
}

export interface ConnectorListResponse {
  connectors: ConnectorSummary[];
}

export interface AuthorizeResponse {
  authorization_url: string;
  expires_at: string;
}

export type ProviderRevocation = "revoked" | "failed" | "not_attempted";

export interface DisconnectResponse {
  status: "disconnected";
  provider_revocation: ProviderRevocation;
}

export interface ConnectorTool {
  name: string;
  source_name: string;
  title: string;
  description: string;
  write_capable: boolean;
}

export type ConnectorToolsStatus = "connected" | "not_connected" | "expired";

export interface ConnectorToolsResponse {
  connector: string;
  status: ConnectorToolsStatus;
  tools: ConnectorTool[];
  listed_at: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isOneOf<T extends string>(allowed: readonly T[], value: unknown): value is T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value);
}

export function isConnectorAccount(value: unknown): value is ConnectorAccount {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isNullableString(value.display_name) &&
    isNullableString(value.login)
  );
}

export function isConnectorSite(value: unknown): value is ConnectorSite {
  return isRecord(value) && isString(value.id) && isString(value.name) && isString(value.url);
}

export function isConnectorSummary(value: unknown): value is ConnectorSummary {
  return (
    isRecord(value) &&
    isString(value.key) &&
    CONNECTOR_KEY_PATTERN.test(value.key) &&
    isString(value.display_name) &&
    isString(value.description) &&
    isString(value.icon) &&
    isString(value.docs_url) &&
    isOneOf(CONNECTOR_MODES, value.mode) &&
    isOneOf(CONNECTOR_STATUSES, value.status) &&
    (value.account === null || isConnectorAccount(value.account)) &&
    isStringArray(value.requested_scopes) &&
    isStringArray(value.granted_scopes) &&
    Array.isArray(value.sites) &&
    value.sites.every(isConnectorSite) &&
    isNullableString(value.connected_at) &&
    isNullableString(value.last_refreshed_at)
  );
}

export function isConnectorListResponse(value: unknown): value is ConnectorListResponse {
  return isRecord(value) && Array.isArray(value.connectors) && value.connectors.every(isConnectorSummary);
}

export function isAuthorizeResponse(value: unknown): value is AuthorizeResponse {
  return isRecord(value) && isString(value.authorization_url) && isString(value.expires_at);
}

export function isDisconnectResponse(value: unknown): value is DisconnectResponse {
  return (
    isRecord(value) &&
    value.status === "disconnected" &&
    isOneOf(["revoked", "failed", "not_attempted"] as const, value.provider_revocation)
  );
}

export function isConnectorTool(value: unknown): value is ConnectorTool {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isString(value.source_name) &&
    isString(value.title) &&
    isString(value.description) &&
    typeof value.write_capable === "boolean"
  );
}

export function isConnectorToolsResponse(value: unknown): value is ConnectorToolsResponse {
  return (
    isRecord(value) &&
    isString(value.connector) &&
    isOneOf(["connected", "not_connected", "expired"] as const, value.status) &&
    Array.isArray(value.tools) &&
    value.tools.every(isConnectorTool) &&
    isNullableString(value.listed_at)
  );
}
