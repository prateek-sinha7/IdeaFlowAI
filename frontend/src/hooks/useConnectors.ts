"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectorsApi } from "@/store/api/connectors";
import { saveErrorMessage } from "@/lib/saveError";
import type { ConnectorSummary } from "@/types/connectors";

/**
 * Connectors list state. A discriminated union so the page never has to reason
 * about impossible combinations such as "error" with stale data lying around.
 */
export type ConnectorsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "empty" }
  | { status: "ready"; connectors: ConnectorSummary[] };

export interface UseConnectors {
  state: ConnectorsState;
  /**
   * Re-read GET /api/connectors. Resolves with the connectors on success, or
   * null when the request failed or a newer request superseded it. A failed
   * refresh keeps data that is already on screen and only turns an empty or
   * loading page into an error. Retry from the error state shows "loading".
   */
  refresh: () => Promise<ConnectorSummary[] | null>;
}

function toState(connectors: ConnectorSummary[]): ConnectorsState {
  return connectors.length === 0 ? { status: "empty" } : { status: "ready", connectors };
}

/**
 * @param token Bearer token. The shared axios client attaches the JWT itself;
 *   the token only gates the request so nothing is fired before auth resolves.
 *   A changed token resets to "loading" and refetches.
 *
 * It refetches when the window regains focus (the user may have connected in
 * another tab or changed the grant at the provider) and never polls by itself.
 * The authorization hook polls through `refresh` while a sign-in is pending.
 */
export function useConnectors(token: string | null): UseConnectors {
  const [state, setState] = useState<ConnectorsState>({ status: "loading" });
  // A slow response from an earlier request must not overwrite a newer one.
  const requestIdRef = useRef(0);

  const load = useCallback(
    async (reset: boolean): Promise<ConnectorSummary[] | null> => {
      if (!token) return null;
      const requestId = ++requestIdRef.current;
      setState((prev) => (reset || prev.status === "error" ? { status: "loading" } : prev));
      try {
        const { connectors } = await connectorsApi.list();
        if (requestId !== requestIdRef.current) return null;
        setState(toState(connectors));
        return connectors;
      } catch (err) {
        if (requestId !== requestIdRef.current) return null;
        const message = saveErrorMessage(err, "Failed to load connectors");
        setState((prev) =>
          prev.status === "ready" || prev.status === "empty" ? prev : { status: "error", message },
        );
        return null;
      }
    },
    [token],
  );

  const refresh = useCallback(() => load(false), [load]);

  useEffect(() => {
    if (!token) return;
    // Fetch on mount and on token change. The state update happens in the
    // request's own callbacks, the same shape as useCapacityMatrix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(true);
    const onFocus = () => {
      void load(false);
    };
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      // Invalidate in-flight requests so nothing lands after unmount or a token change.
      requestIdRef.current += 1;
    };
  }, [token, load]);

  return { state, refresh };
}

export default useConnectors;
