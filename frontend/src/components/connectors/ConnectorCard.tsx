"use client";

import { useId } from "react";
import { Button } from "@/components/ui/Button";
import { isHttpsUrl } from "@/lib/connectorPopup";
import type { ConnectorPending } from "@/hooks/useConnectorAuthorization";
import type { ConnectorSummary } from "@/types/connectors";
import { ConnectorStatusBadge } from "./ConnectorStatusBadge";
import {
  accountLabel,
  authorizingMessage,
  disconnectingMessage,
  expiredMessage,
  formatConnectedDate,
  notConfiguredMessage,
} from "./connectorMessages";

export interface ConnectorCardProps {
  connector: ConnectorSummary;
  pending: ConnectorPending;
  onConnect: (connector: ConnectorSummary) => void;
  onReconnect: (connector: ConnectorSummary) => void;
  onDisconnect: (connector: ConnectorSummary) => void;
  onCancel: (connector: ConnectorSummary) => void;
}

function ScopeList({ label, scopes }: { label: string; scopes: string[] }) {
  if (scopes.length === 0) return null;
  return (
    <div>
      <p className="text-[11px] font-semibold text-ink-500">{label}</p>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {scopes.map((scope) => (
          <li
            key={scope}
            className="rounded-[var(--radius-tag)] border border-line-control bg-surface-white px-1.5 py-0.5 font-mono text-[11px] text-ink-700"
          >
            {scope}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * One connector. Presentational: the page owns the data and the OAuth flow.
 * Provider text (name, description, scopes, site names) renders as plain text.
 */
export function ConnectorCard({
  connector,
  pending,
  onConnect,
  onReconnect,
  onDisconnect,
  onCancel,
}: ConnectorCardProps) {
  const headingId = useId();
  const { display_name: name, status } = connector;
  const authorizing = pending !== "idle" && pending.kind === "authorizing";
  const disconnecting = pending !== "idle" && pending.kind === "disconnecting";
  const busy = authorizing || disconnecting;
  const connectedOn = formatConnectedDate(connector.connected_at);

  return (
    <article
      aria-labelledby={headingId}
      className="flex min-h-[220px] flex-col gap-3 rounded-[var(--radius-card)] border border-line-border bg-surface-card p-5"
    >
      <header className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid h-10 w-10 flex-none place-items-center rounded-[10px] border border-line-control bg-surface-white font-serif text-[18px] text-ink-900"
        >
          {name.charAt(0).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={headingId} className="truncate text-[15px] font-semibold text-ink-900">
            {name}
          </h2>
          <div className="mt-1.5">
            <ConnectorStatusBadge status={status} />
          </div>
        </div>
        {isHttpsUrl(connector.docs_url) ? (
          <a
            href={connector.docs_url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${name} documentation (opens in a new tab)`}
            className="text-[12px] text-ink-500 underline underline-offset-2 hover:text-ink-700"
          >
            Docs
          </a>
        ) : null}
      </header>

      <div className="flex flex-1 flex-col gap-2.5 text-[12.5px] text-ink-700">
        {status === "connected" ? (
          <>
            {connector.account ? <p>Connected as {accountLabel(connector.account)}</p> : <p>Connected</p>}
            {connector.sites.length > 0 ? (
              <div>
                <p className="text-[11px] font-semibold text-ink-500">Sites</p>
                <ul className="mt-1 list-disc pl-4">
                  {connector.sites.map((site) => (
                    <li key={site.id}>{site.name}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <ScopeList label="Permissions granted" scopes={connector.granted_scopes} />
            {connectedOn ? <p className="text-ink-500">Connected on {connectedOn}</p> : null}
          </>
        ) : null}
        {status === "expired" ? <p>{expiredMessage(name)}</p> : null}
        {status === "not_connected" ? (
          <>
            <p>{connector.description}</p>
            <ScopeList label="Permissions requested" scopes={connector.requested_scopes} />
          </>
        ) : null}
        {status === "not_configured" ? <p>{notConfiguredMessage(name)}</p> : null}
        {authorizing ? (
          <p role="status" className="text-ink-500">
            {authorizingMessage(name)}
          </p>
        ) : null}
        {disconnecting ? (
          <p role="status" className="text-ink-500">
            {disconnectingMessage(name)}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        {authorizing ? (
          <Button variant="secondary" aria-label={`Cancel sign-in to ${name}`} onClick={() => onCancel(connector)}>
            Cancel
          </Button>
        ) : null}
        {!authorizing && status === "not_connected" ? (
          <Button aria-label={`Connect ${name}`} disabled={busy} onClick={() => onConnect(connector)}>
            Connect
          </Button>
        ) : null}
        {!authorizing && status === "not_configured" ? (
          <Button aria-label={`Connect ${name}`} disabled>
            Connect
          </Button>
        ) : null}
        {!authorizing && (status === "expired" || status === "connected") ? (
          <Button
            variant={status === "expired" ? "primary" : "secondary"}
            aria-label={`Reconnect ${name}`}
            disabled={busy}
            onClick={() => onReconnect(connector)}
          >
            Reconnect
          </Button>
        ) : null}
        {!authorizing && (status === "expired" || status === "connected") ? (
          <Button
            variant="secondary"
            aria-label={`Disconnect ${name}`}
            disabled={busy}
            onClick={() => onDisconnect(connector)}
          >
            Disconnect
          </Button>
        ) : null}
      </div>
    </article>
  );
}

export default ConnectorCard;
