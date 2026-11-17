"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { reasonMessage } from "@/components/connectors/connectorMessages";
import {
  CONNECTORS_CHANNEL,
  isConnectorPopupName,
  parseOAuthResult,
  type OAuthCompleteMessage,
} from "@/lib/connectorPopup";
import { routes } from "@/lib/routes";

/** "jira" -> "Jira". The page makes no API call, so the key is all it knows of the connector. */
function nameFromKey(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/** Tell other tabs (the Connectors page) to re-read the list. Never throws. */
function announce(message: OAuthCompleteMessage): void {
  if (typeof BroadcastChannel === "undefined") return;
  try {
    const channel = new BroadcastChannel(CONNECTORS_CHANNEL);
    channel.postMessage(message);
    channel.close();
  } catch {
    // The poll on the Connectors page still picks the result up.
  }
}

// window.name does not change while the page is open, so there is nothing to subscribe to.
const subscribeNever = () => () => {};
const readIsPopup = () => isConnectorPopupName(window.name);
// The server has no window. React also uses this snapshot while hydrating, so the first
// client render matches the server HTML and the real value is applied right after.
const readIsPopupOnServer = () => false;

/** True when this page was opened by the Connectors page as an OAuth popup. Hydration-safe. */
function useIsConnectorPopup(): boolean {
  return useSyncExternalStore(subscribeNever, readIsPopup, readIsPopupOnServer);
}

/**
 * Shows the outcome of the provider sign-in and hands control back.
 *
 * Reads only `connector`, `result` and `reason` from the URL, each validated by
 * parseOAuthResult. In a popup it closes itself after announcing the result; in a
 * normal tab it forwards to the Connectors page. No API calls, no tokens.
 */
export function OAuthCompleteClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const outcome = useMemo(() => parseOAuthResult(searchParams), [searchParams]);
  const isPopup = useIsConnectorPopup();

  useEffect(() => {
    if (!outcome) return;
    announce(outcome);
    if (isConnectorPopupName(window.name)) {
      window.close();
      return;
    }
    router.replace(
      routes.connectors({
        connector: outcome.connector,
        result: outcome.result,
        reason: outcome.reason ?? undefined,
      }),
    );
  }, [outcome, router]);

  let heading: string;
  let detail: string;
  if (!outcome) {
    heading = "This link is not valid";
    detail = "There is nothing to finish here. Open Connectors to see your accounts.";
  } else if (outcome.result === "connected") {
    heading = "Connected";
    detail = isPopup
      ? "You can close this window and return to Connectors."
      : "Taking you back to Connectors.";
  } else {
    heading = "Connection failed";
    detail = outcome.reason
      ? reasonMessage(outcome.reason, nameFromKey(outcome.connector))
      : "The connection could not be completed. Try again from Connectors.";
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface-paper px-4 py-12">
      <section
        role="status"
        aria-live="polite"
        className="w-full max-w-md rounded-[var(--radius-card)] border border-line-control bg-surface-card p-7 shadow-[var(--elevation-raised)]"
      >
        <h1 className="text-[24px] font-semibold tracking-tight text-ink-900 font-sans">
          {heading}
        </h1>
        <p className="mt-3 text-[13px] leading-relaxed text-ink-600">{detail}</p>
        <Link
          href={routes.connectors()}
          className="mt-5 inline-block text-[13px] font-medium text-ink-900 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          Back to Connectors
        </Link>
      </section>
    </main>
  );
}
