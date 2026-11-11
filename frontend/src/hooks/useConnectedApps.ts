"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectorsApi } from "@/store/api/connectors";
import { saveErrorMessage } from "@/lib/saveError";
import type { ConnectorSummary, ConnectorTool, ConnectorToolsStatus } from "@/types/connectors";

/**
 * Connected Apps data for the Canvas rail's Tools tab (design 4.4).
 *
 * Server state (the connector list and each connector's tool list) is read
 * through `connectorsApi` and shared through one in-memory cache for the page
 * session, so switching between steps does not refetch. The cache is dropped
 * when the token changes. Nothing here writes: the selected tool names live in
 * the step's `tools.connectors` and are changed by the caller.
 */

/** How long a cached list or tool list is served without asking the server. */
export const CONNECTED_APPS_CACHE_TTL_MS = 60_000;

export type ConnectedAppsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; connectors: ConnectorSummary[] };

export type ConnectorToolsState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; connection: ConnectorToolsStatus; tools: ConnectorTool[] };

export interface UseConnectedApps {
  state: ConnectedAppsState;
  /** Re-read the connector list from the server (the error state's Retry). */
  retry: () => void;
  /** The tool list state of one connector; "idle" until `loadTools(key)` ran. */
  toolsFor: (key: string) => ConnectorToolsState;
  /** Load one connector's tools (cache first). `force` skips the cache (Retry). */
  loadTools: (key: string, force?: boolean) => void;
}

interface Timed<T> {
  value: T;
  at: number;
}

interface ToolsResult {
  connection: ConnectorToolsStatus;
  tools: ConnectorTool[];
}

const cache = {
  token: null as string | null,
  list: null as Timed<ConnectorSummary[]> | null,
  tools: new Map<string, Timed<ToolsResult>>(),
  listInflight: null as Promise<ConnectorSummary[]> | null,
  toolsInflight: new Map<string, Promise<ToolsResult>>(),
};

/** Drop every cached value. Exported for tests; the hook calls it on token change. */
export function resetConnectedAppsCache(): void {
  cache.token = null;
  cache.list = null;
  cache.tools.clear();
  cache.listInflight = null;
  cache.toolsInflight.clear();
}

function scopeCacheTo(token: string): void {
  if (cache.token === token) return;
  resetConnectedAppsCache();
  cache.token = token;
}

function isFresh<T>(entry: Timed<T> | null | undefined): entry is Timed<T> {
  return !!entry && Date.now() - entry.at < CONNECTED_APPS_CACHE_TTL_MS;
}

function peekList(token: string | null): ConnectorSummary[] | null {
  if (!token || cache.token !== token || !isFresh(cache.list)) return null;
  return cache.list.value;
}

function peekTools(token: string, key: string): ToolsResult | null {
  const entry = cache.tools.get(key);
  if (cache.token !== token || !isFresh(entry)) return null;
  return entry.value;
}

function fetchList(token: string, force: boolean): Promise<ConnectorSummary[]> {
  scopeCacheTo(token);
  const cached = peekList(token);
  if (cached && !force) return Promise.resolve(cached);
  if (cache.listInflight) return cache.listInflight;
  const request = connectorsApi
    .list()
    .then(({ connectors }) => {
      if (cache.token === token) {
        // A connector whose status changed (connected in another tab, expired)
        // may list different tools now, so its cached tool list is dropped.
        const previous = cache.list?.value ?? [];
        for (const next of connectors) {
          const before = previous.find((c) => c.key === next.key);
          if (before && before.status !== next.status) cache.tools.delete(next.key);
        }
        cache.list = { value: connectors, at: Date.now() };
      }
      return connectors;
    })
    .finally(() => {
      if (cache.listInflight === request) cache.listInflight = null;
    });
  cache.listInflight = request;
  return request;
}

function fetchTools(token: string, key: string, force: boolean): Promise<ToolsResult> {
  scopeCacheTo(token);
  const cached = peekTools(token, key);
  if (cached && !force) return Promise.resolve(cached);
  const pending = cache.toolsInflight.get(key);
  if (pending) return pending;
  const request = connectorsApi
    .tools(key)
    .then((response) => {
      const result: ToolsResult = { connection: response.status, tools: response.tools };
      if (cache.token === token) cache.tools.set(key, { value: result, at: Date.now() });
      return result;
    })
    .finally(() => {
      if (cache.toolsInflight.get(key) === request) cache.toolsInflight.delete(key);
    });
  cache.toolsInflight.set(key, request);
  return request;
}

function messageOf(err: unknown, fallback: string): string {
  return saveErrorMessage(err, fallback);
}

interface Loaded<T> {
  token: string | null;
  value: T;
}

/**
 * @param token Bearer token. The shared axios client attaches the JWT itself;
 *   the token gates the requests and scopes the cache. A changed token starts
 *   again from "loading" with an empty cache.
 *
 * The list is refetched when the window regains focus (the user may have
 * connected in another tab through the "Connect in Connectors" link). It never
 * polls.
 */
export function useConnectedApps(token: string | null): UseConnectedApps {
  const [loaded, setLoaded] = useState<Loaded<ConnectedAppsState>>(() => {
    const cached = peekList(token);
    return {
      token,
      value: cached ? { status: "ready", connectors: cached } : { status: "loading" },
    };
  });
  const [toolsLoaded, setToolsLoaded] = useState<Loaded<Record<string, ConnectorToolsState>>>({
    token,
    value: {},
  });
  // A response from an earlier request must not overwrite a newer one.
  const listRequestRef = useRef(0);
  const toolsRequestRef = useRef<Record<string, number>>({});
  const aliveRef = useRef(false);

  // Both states are tagged with the token they were loaded for, so a token
  // change reads as "loading" / "idle" without an effect that resets them.
  const state: ConnectedAppsState =
    loaded.token === token ? loaded.value : { status: "loading" };

  const load = useCallback(
    (force: boolean) => {
      if (!token) return;
      const requestId = ++listRequestRef.current;
      fetchList(token, force).then(
        (connectors) => {
          if (!aliveRef.current || requestId !== listRequestRef.current) return;
          setLoaded({ token, value: { status: "ready", connectors } });
        },
        (err: unknown) => {
          if (!aliveRef.current || requestId !== listRequestRef.current) return;
          const message = messageOf(err, "Connected apps could not be loaded.");
          // A failed refresh keeps a list that is already on screen.
          setLoaded((prev) =>
            prev.token === token && prev.value.status === "ready"
              ? prev
              : { token, value: { status: "error", message } },
          );
        },
      );
    },
    [token],
  );

  useEffect(() => {
    aliveRef.current = true;
    const requests = toolsRequestRef.current;
    load(false);
    const onFocus = () => load(true);
    window.addEventListener("focus", onFocus);
    return () => {
      aliveRef.current = false;
      window.removeEventListener("focus", onFocus);
      // Invalidate in-flight requests so nothing lands after unmount.
      listRequestRef.current += 1;
      for (const key of Object.keys(requests)) requests[key] += 1;
    };
  }, [load]);

  const retry = useCallback(() => {
    if (!token) return;
    setLoaded({ token, value: { status: "loading" } });
    load(true);
  }, [token, load]);

  const setTools = useCallback(
    (key: string, value: ConnectorToolsState) => {
      setToolsLoaded((prev) => ({
        token,
        value: { ...(prev.token === token ? prev.value : {}), [key]: value },
      }));
    },
    [token],
  );

  const loadTools = useCallback(
    (key: string, force = false) => {
      if (!token) return;
      const requestId = (toolsRequestRef.current[key] ?? 0) + 1;
      toolsRequestRef.current[key] = requestId;
      const cached = force ? null : peekTools(token, key);
      if (cached) {
        setTools(key, { status: "ready", ...cached });
        return;
      }
      setTools(key, { status: "loading" });
      fetchTools(token, key, force).then(
        (result) => {
          if (!aliveRef.current || toolsRequestRef.current[key] !== requestId) return;
          setTools(key, { status: "ready", ...result });
        },
        (err: unknown) => {
          if (!aliveRef.current || toolsRequestRef.current[key] !== requestId) return;
          setTools(key, { status: "error", message: messageOf(err, "Tools could not be loaded.") });
        },
      );
    },
    [token, setTools],
  );

  const toolsFor = useCallback(
    (key: string): ConnectorToolsState =>
      (toolsLoaded.token === token ? toolsLoaded.value[key] : undefined) ?? { status: "idle" },
    [toolsLoaded, token],
  );

  return { state, retry, toolsFor, loadTools };
}

export default useConnectedApps;
