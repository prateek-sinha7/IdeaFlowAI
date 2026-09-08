"use client";

/**
 * ServiceBusyProvider — app-level owner of the "service is busy" modal
 * (specs/014). Modeled on `RunConnectionProvider`: a context with an inert
 * no-provider default (so `useServiceBusy()` is always safe to call) wrapping
 * a subscriber to a module-level pub/sub — here, `lib/api.ts`'s
 * `onCapacityRejected`, the single seam every 503 `host_capacity_exhausted`
 * rejection reaches regardless of which endpoint produced it (the backend
 * gate's REST twin sites, `RunConnectionProvider.sendCommand`'s launch
 * branch, and any future call site that throws `ApiError` all converge there
 * — see `lib/api.ts`'s `ApiError` constructor).
 *
 * Coalescing (specs/014 §4): this provider holds exactly ONE rejection in
 * state, so N rejections arriving while the modal is already open update
 * the SAME modal's contents rather than stacking N modals — there is only
 * ever one `Modal` mounted at a time by construction, not by extra logic.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { onCapacityRejected, type CapacityRejectionDetail } from "@/lib/api";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";

export interface ServiceBusyContextValue {
  /** Whether the busy modal is currently shown. */
  isBusy: boolean;
  /** The rejection that produced the current modal, or null when not busy. */
  lastRejection: CapacityRejectionDetail | null;
  /** Dismiss the modal programmatically (e.g. a caller retrying immediately). */
  dismiss: () => void;
}

/** Inert default so `useServiceBusy()` is safe outside the provider. */
const DEFAULT_VALUE: ServiceBusyContextValue = {
  isBusy: false,
  lastRejection: null,
  dismiss: () => {},
};

const ServiceBusyContext = createContext<ServiceBusyContextValue>(DEFAULT_VALUE);

/** Consume the app-level busy state. Safe outside the provider (inert). */
export function useServiceBusy(): ServiceBusyContextValue {
  return useContext(ServiceBusyContext);
}

// Human-readable label for a signal name — the backend sends the short,
// generic identifiers ("cpu" | "memory") it also uses internally
// (app/services/capacity_state.py's _SIGNAL_CPU / _SIGNAL_MEM); this is
// presentation-only and adds no new vocabulary on the wire.
const SIGNAL_LABELS: Record<string, string> = {
  cpu: "CPU",
  memory: "Memory",
};

function formatSignal(signal: CapacityRejectionDetail["signals"][number]): string {
  const label = SIGNAL_LABELS[signal.name] ?? signal.name;
  return `${label}: ${Math.round(signal.value)}% (threshold ${Math.round(signal.threshold)}%)`;
}

export interface ServiceBusyProviderProps {
  children: ReactNode;
}

export function ServiceBusyProvider({ children }: ServiceBusyProviderProps) {
  const [rejection, setRejection] = useState<CapacityRejectionDetail | null>(
    null,
  );
  const [secondsRemaining, setSecondsRemaining] = useState(0);

  const dismiss = useCallback(() => {
    setRejection(null);
  }, []);

  // The single subscription for the lifetime of the app. `onCapacityRejected`
  // fires synchronously from inside `ApiError`'s constructor, so this handler
  // never touches the network itself — it only reacts to a rejection some
  // other call site already received.
  useEffect(() => {
    return onCapacityRejected((detail) => {
      setRejection(detail);
      setSecondsRemaining(Math.max(0, Math.round(detail.retry_after_seconds)));
    });
  }, []);

  // Countdown ticker, purely presentational — nothing here auto-retries the
  // failed operation; it only tells the user when trying again is likely to
  // succeed. Re-armed whenever a NEW rejection object arrives (coalesced
  // repeats while already open restart the countdown from the fresh value).
  useEffect(() => {
    if (rejection === null) return;
    const timer = setInterval(() => {
      setSecondsRemaining((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [rejection]);

  const value = useMemo<ServiceBusyContextValue>(
    () => ({ isBusy: rejection !== null, lastRejection: rejection, dismiss }),
    [rejection, dismiss],
  );

  return (
    <ServiceBusyContext.Provider value={value}>
      {children}
      {rejection ? (
        <Modal onClose={dismiss} title="Service is busy" description={rejection.error}>
          <div className="space-y-3">
            <p className="text-[12px] text-ink-700">
              {secondsRemaining > 0
                ? `You can try again in about ${secondsRemaining}s.`
                : "You can try again now."}
            </p>
            {rejection.signals.length > 0 ? (
              <ul className="space-y-1 text-[11px] text-ink-500">
                {rejection.signals.map((signal) => (
                  <li key={signal.name}>{formatSignal(signal)}</li>
                ))}
              </ul>
            ) : null}
            <div className="flex justify-end pt-2">
              <Button size="sm" onClick={dismiss}>
                Got it
              </Button>
            </div>
          </div>
        </Modal>
      ) : null}
    </ServiceBusyContext.Provider>
  );
}
