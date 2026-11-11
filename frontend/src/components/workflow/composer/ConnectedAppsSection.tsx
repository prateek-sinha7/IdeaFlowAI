"use client";

import { useMemo, useState } from "react";
import { ChevronDown, Plug } from "lucide-react";
import { getToken } from "@/lib/api";
import { routes } from "@/lib/routes";
import { useConnectedApps, type ConnectorToolsState } from "@/hooks/useConnectedApps";
import { statusLabel } from "@/components/connectors/connectorMessages";
import { withConnectorTools, type StepSelection } from "../AgentsPopup";
import type { AgentToolGrants } from "@/types/index";
import type { ConnectorSummary, ConnectorTool } from "@/types/connectors";
import { Toggle } from "./Toggle";

/** Where a Canvas can use connected apps. Built-in canvases and override rows
 *  cannot (design 4.4); the server refuses their grants too. */
export type ConnectedAppsAvailability = "available" | "builtin" | "override";

/** The server's limit on connected-app tools per step. */
export const MAX_CONNECTOR_TOOLS = 64;

export const NOT_AVAILABLE_NOTE = "Connected apps work in your own workflows. Save a copy to use them.";
export const LIMIT_NOTE = `A step can use up to ${MAX_CONNECTOR_TOOLS} connected-app tools. Turn one off to add another.`;

export interface ConnectedAppsSectionProps {
  sel: StepSelection | undefined;
  availability: ConnectedAppsAvailability;
  /** Receives the step's whole next `tools` object (built by `withConnectorTools`). */
  onToolsChange: (tools: AgentToolGrants) => void;
}

/** Tool names carry their connector: `<connector_key>__<tool_name>`. */
function belongsTo(connectorKey: string, toolName: string): boolean {
  return toolName.startsWith(`${connectorKey}__`);
}

function SkeletonRows() {
  return (
    <div role="status" aria-label="Loading connected apps" className="space-y-1.5">
      {[0, 1].map((i) => (
        <div key={i} className="h-[58px] animate-pulse rounded-lg border border-line-faint-row bg-surface-warm" />
      ))}
    </div>
  );
}

function ErrorRow({ message, onRetry, what }: { message: string; onRetry: () => void; what: string }) {
  return (
    <div role="alert" className="rounded-lg border border-line-faint-row bg-surface-warm px-3 py-2">
      <p className="font-sans text-[11px] text-ink-700">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        aria-label={`Retry loading ${what}`}
        className="mt-1.5 rounded-md border border-line-control bg-surface-white px-2 py-1 font-sans text-[11px] font-semibold text-ink-900 hover:bg-surface-warm"
      >
        Retry
      </button>
    </div>
  );
}

function ToolRow({
  tool,
  on,
  disabled,
  onToggle,
}: {
  tool: ConnectorTool;
  on: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  const label = tool.title || tool.name;
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-line-faint-row bg-surface-warm px-3 py-2">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-1.5 font-sans text-[11px] font-semibold text-ink-900">
          {label}
          {tool.write_capable && (
            <span className="rounded-[var(--radius-tag)] border border-status-amber px-1.5 py-px font-sans text-[10px] font-semibold text-ink-700">
              Can change data
            </span>
          )}
        </p>
        {/* Provider text is rendered as text, never as HTML; the full text is in the tooltip. */}
        {tool.description && (
          <p
            title={tool.description}
            className="line-clamp-2 font-serif text-[10px] leading-relaxed text-ink-300"
          >
            {tool.description}
          </p>
        )}
      </div>
      <Toggle on={on} label={label} disabled={disabled} onToggle={onToggle} />
    </li>
  );
}

/** A tool that is on for the step but cannot be switched from the list. */
function LeftoverRow({
  name,
  reason,
  disabled,
  onTurnOff,
}: {
  name: string;
  reason: string;
  disabled: boolean;
  onTurnOff: () => void;
}) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-line-faint-row bg-surface-warm px-3 py-2">
      <div className="min-w-0">
        <p className="truncate font-mono text-[11px] text-ink-900">{name}</p>
        <p className="font-serif text-[10px] text-ink-300">{reason}</p>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={onTurnOff}
        aria-label={`Turn off ${name}`}
        className="flex-none rounded-md border border-line-control bg-surface-white px-2 py-1 font-sans text-[11px] font-semibold text-ink-900 hover:bg-surface-warm disabled:opacity-40"
      >
        Turn off
      </button>
    </li>
  );
}

function ConnectedTools({
  connector,
  tools,
  selected,
  editable,
  onChange,
}: {
  connector: ConnectorSummary;
  tools: ConnectorTool[];
  selected: string[];
  editable: boolean;
  onChange: (names: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const atLimit = selected.length >= MAX_CONNECTOR_TOOLS;
  const needle = query.trim().toLowerCase();
  const shown = useMemo(
    () =>
      needle
        ? tools.filter((t) =>
            `${t.title} ${t.name} ${t.description}`.toLowerCase().includes(needle),
          )
        : tools,
    [tools, needle],
  );
  const listed = new Set(tools.map((t) => t.name));
  const leftovers = selected.filter((n) => belongsTo(connector.key, n) && !listed.has(n));

  return (
    <div className="mt-2 space-y-2">
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label={`Search ${connector.display_name} tools`}
        placeholder="Search tools"
        className="w-full rounded-md border border-line-control bg-surface-white px-2 py-1.5 font-sans text-[12px] text-ink-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      />
      {shown.length === 0 && tools.length > 0 && (
        <p className="font-serif text-[11px] text-ink-300">No tools match your search.</p>
      )}
      {tools.length === 0 && (
        <p className="font-serif text-[11px] text-ink-300">This app offers no tools.</p>
      )}
      <ul className="space-y-1.5">
        {shown.map((tool) => {
          const on = selected.includes(tool.name);
          return (
            <ToolRow
              key={tool.name}
              tool={tool}
              on={on}
              disabled={!editable || (!on && atLimit)}
              onToggle={() =>
                onChange(on ? selected.filter((n) => n !== tool.name) : [...selected, tool.name])
              }
            />
          );
        })}
        {leftovers.map((name) => (
          <LeftoverRow
            key={name}
            name={name}
            reason="On, but this app no longer offers it"
            disabled={!editable}
            onTurnOff={() => onChange(selected.filter((n) => n !== name))}
          />
        ))}
      </ul>
    </div>
  );
}

function ConnectedAppGroup({
  connector,
  selected,
  toolsState,
  editable,
  onExpand,
  onRetryTools,
  onChange,
}: {
  connector: ConnectorSummary;
  /** Every connected-app tool name the step has on, across connectors. */
  selected: string[];
  toolsState: ConnectorToolsState;
  editable: boolean;
  onExpand: () => void;
  onRetryTools: () => void;
  onChange: (names: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const { key, display_name: name, status } = connector;
  const mine = selected.filter((n) => belongsTo(key, n));
  const needsConnection = status === "not_connected" || status === "expired";

  const toggleOpen = () => {
    if (!open) onExpand();
    setOpen(!open);
  };

  const summary =
    toolsState.status === "ready"
      ? `${mine.filter((n) => toolsState.tools.some((t) => t.name === n)).length} of ${toolsState.tools.length} on`
      : `${mine.length} on`;

  return (
    <fieldset className="rounded-lg border border-line-faint-row p-3">
      <legend className="flex items-center gap-2 px-1 font-sans text-[11px] font-semibold text-ink-900">
        {name}
        <span className="font-serif text-[10px] font-normal text-ink-300">{statusLabel(status)}</span>
      </legend>

      {status === "not_configured" && (
        <p className="font-serif text-[11px] text-ink-400">Not configured on this server</p>
      )}

      {needsConnection && (
        <div className="space-y-2">
          <p className="font-serif text-[11px] text-ink-400">
            {status === "expired"
              ? `Your ${name} connection expired.`
              : `${name} is not connected.`}{" "}
            <a
              href={routes.connectors({ connector: key })}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-brand underline"
            >
              {status === "expired" ? "Reconnect in Connectors" : "Connect in Connectors"}
            </a>
          </p>
          {mine.length > 0 && (
            <ul className="space-y-1.5">
              {mine.map((toolName) => (
                <LeftoverRow
                  key={toolName}
                  name={toolName}
                  reason="On, needs a connection"
                  disabled={!editable}
                  onTurnOff={() => onChange(selected.filter((n) => n !== toolName))}
                />
              ))}
            </ul>
          )}
        </div>
      )}

      {status === "connected" && (
        <div>
          <button
            type="button"
            aria-expanded={open}
            aria-label={`${open ? "Hide" : "Show"} ${name} tools`}
            onClick={toggleOpen}
            className="flex w-full items-center justify-between gap-2 rounded-md px-1 py-1 font-sans text-[11px] font-semibold text-ink-700 hover:text-ink-900 focus-visible:outline-2 focus-visible:outline-brand"
          >
            <span>{summary}</span>
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
          </button>
          {open && toolsState.status === "loading" && (
            <div role="status" aria-label={`Loading ${name} tools`} className="mt-2 space-y-1.5">
              {[0, 1].map((i) => (
                <div key={i} className="h-[46px] animate-pulse rounded-lg border border-line-faint-row bg-surface-warm" />
              ))}
            </div>
          )}
          {open && toolsState.status === "error" && (
            <div className="mt-2">
              <ErrorRow message={toolsState.message} onRetry={onRetryTools} what={`${name} tools`} />
            </div>
          )}
          {open && toolsState.status === "ready" && toolsState.connection !== "connected" && (
            <p className="mt-2 font-serif text-[11px] text-ink-400">
              {name} is no longer connected. Reconnect it in Connectors to see its tools.
            </p>
          )}
          {open && toolsState.status === "ready" && toolsState.connection === "connected" && (
            <ConnectedTools
              connector={connector}
              tools={toolsState.tools}
              selected={selected}
              editable={editable}
              onChange={onChange}
            />
          )}
        </div>
      )}
    </fieldset>
  );
}

/**
 * The Tools tab's "Connected Apps" block (design 4.4). Tools are off until the
 * user turns them on; the choice is saved as the step's `tools.connectors`.
 * Every write goes through `withConnectorTools`, so the step's other grant keys
 * survive (ISS-912 class). Presentational for the grant: it reports the next
 * `tools` object and never saves anything itself.
 */
export function ConnectedAppsSection({ sel, availability, onToolsChange }: ConnectedAppsSectionProps) {
  const { state, retry, toolsFor, loadTools } = useConnectedApps(getToken());
  const selected = sel?.tools?.connectors ?? [];
  const editable = availability === "available";
  const change = (names: string[]) => onToolsChange(withConnectorTools(sel, names));

  return (
    <section aria-label="Connected apps" className="mt-5">
      <div className="mb-2.5 flex items-center gap-2">
        <Plug className="h-3.5 w-3.5 text-ink-300" aria-hidden="true" />
        <h3 className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
          Connected apps
        </h3>
      </div>

      {!editable && <p className="mb-2 font-serif text-[11px] text-ink-400">{NOT_AVAILABLE_NOTE}</p>}
      {editable && selected.length >= MAX_CONNECTOR_TOOLS && (
        <p role="status" className="mb-2 font-serif text-[11px] text-ink-400">
          {LIMIT_NOTE}
        </p>
      )}

      {state.status === "loading" && <SkeletonRows />}
      {state.status === "error" && (
        <ErrorRow message={state.message} onRetry={retry} what="connected apps" />
      )}
      {state.status === "ready" && state.connectors.length === 0 && (
        <p className="font-serif text-[11px] text-ink-300">No connectors are available.</p>
      )}
      {state.status === "ready" && state.connectors.length > 0 && (
        <div className="space-y-2">
          {state.connectors.map((connector) => (
            <ConnectedAppGroup
              key={connector.key}
              connector={connector}
              selected={selected}
              toolsState={toolsFor(connector.key)}
              editable={editable}
              onExpand={() => loadTools(connector.key)}
              onRetryTools={() => loadTools(connector.key, true)}
              onChange={change}
            />
          ))}
        </div>
      )}
    </section>
  );
}
