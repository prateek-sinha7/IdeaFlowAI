"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { getToken } from "@/lib/api";
import { parseOAuthResult } from "@/lib/connectorPopup";
import { routes } from "@/lib/routes";
import { useConnectors } from "@/hooks/useConnectors";
import { useConnectorAuthorization, type ConnectorNotice } from "@/hooks/useConnectorAuthorization";
import type { ConnectorSummary } from "@/types/connectors";
import { ConnectorCard } from "./ConnectorCard";
import { DisconnectDialog } from "./DisconnectDialog";
import {
  EMPTY_MESSAGE,
  LOADING_MESSAGE,
  PAGE_SUBTITLE,
  PAGE_TITLE,
  bannerFor,
  type BannerTone,
} from "./connectorMessages";

export interface ConnectorsPageProps {
  onBack: () => void;
}

const BANNER_TONE_CLASS: Record<BannerTone, string> = {
  success: "text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]",
  info: "text-ink-700 bg-surface-warm border-line-control",
  error: "text-status-failed bg-[var(--status-failed-fill)] border-[var(--status-failed-border)]",
};

function LoadingSkeleton() {
  return (
    <div role="status" aria-busy="true" className="grid gap-4 md:grid-cols-2">
      <span className="sr-only">{LOADING_MESSAGE}</span>
      {[0, 1].map((index) => (
        <div
          key={index}
          aria-hidden="true"
          className="min-h-[220px] rounded-[var(--radius-card)] border border-line-border bg-surface-card motion-safe:animate-pulse"
        />
      ))}
    </div>
  );
}

/**
 * The Connectors page: the user's connected accounts and the sign-in flow.
 * The server list is the single source of truth. The `?connector=&result=`
 * query that the landing page leaves after a same-tab sign-in is only a hint:
 * an error hint is shown as given, a success hint only once the list agrees.
 */
export function ConnectorsPage({ onBack }: ConnectorsPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { state, refresh } = useConnectors(getToken());
  const authorization = useConnectorAuthorization({ refresh });
  const [landingHint, setLandingHint] = useState(() => parseOAuthResult(searchParams));
  const [disconnectTarget, setDisconnectTarget] = useState<ConnectorSummary | null>(null);
  const hasLandingHint = landingHint !== null;

  // Take the hint off the address bar so a reload does not show it again.
  useEffect(() => {
    if (hasLandingHint) router.replace(routes.connectors());
  }, [hasLandingHint, router]);

  const connectors = state.status === "ready" ? state.connectors : [];
  const displayNameOf = (key: string | null): string =>
    connectors.find((c) => c.key === key)?.display_name ?? key ?? "the connector";

  let landingNotice: ConnectorNotice | null = null;
  if (landingHint?.result === "error") {
    landingNotice = {
      kind: "error",
      connector: landingHint.connector,
      reason: landingHint.reason,
      message: null,
    };
  } else if (
    landingHint?.result === "connected" &&
    connectors.some((c) => c.key === landingHint.connector && c.status === "connected")
  ) {
    landingNotice = { kind: "connected", connector: landingHint.connector };
  }

  const notice = authorization.notice ?? landingNotice;
  const banner = notice ? bannerFor(notice, displayNameOf(notice.connector)) : null;

  const dismissNotice = () => {
    authorization.clearNotice();
    setLandingHint(null);
  };

  const startSignIn = (connector: ConnectorSummary) => {
    setLandingHint(null);
    void authorization.start(connector.key);
  };

  const pendingFor = (key: string) => authorization.pending[key] ?? "idle";

  return (
    <div className="h-full flex flex-col overflow-y-auto bg-surface-paper">
      <div className="mx-auto w-full max-w-[1040px] px-10 pb-16 pt-6">
        <div className="mb-[22px] flex flex-wrap items-center gap-3.5">
          <button
            type="button"
            onClick={onBack}
            aria-label="Back"
            className="grid h-9 w-9 flex-none place-items-center rounded-[9px] border border-line-control bg-surface-card text-ink-700 transition-colors hover:border-line-faint"
          >
            <ChevronLeft className="h-[17px] w-[17px]" aria-hidden="true" />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="font-serif text-[26px] font-normal italic leading-none tracking-tight text-ink-900">
              {PAGE_TITLE}
            </h1>
            <p className="mt-1.5 text-[12.5px] text-ink-400">{PAGE_SUBTITLE}</p>
          </div>
        </div>

        {/* Always mounted, so a screen reader announces the text that appears in it. */}
        <div role="status" aria-live="polite" className="empty:hidden">
          {banner && notice ? (
            <div
              className={[
                "mb-4 flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border px-4 py-3 text-[12.5px]",
                BANNER_TONE_CLASS[banner.tone],
              ].join(" ")}
            >
              <p className="min-w-0 flex-1">{banner.text}</p>
              {notice.kind === "popup_blocked" ? (
                <Button size="sm" onClick={authorization.continueInThisTab}>
                  Continue in this tab
                </Button>
              ) : null}
              <Button size="sm" variant="secondary" onClick={dismissNotice}>
                Dismiss
              </Button>
            </div>
          ) : null}
        </div>

        {state.status === "loading" ? <LoadingSkeleton /> : null}
        {state.status === "error" ? (
          <div role="alert" className="flex flex-wrap items-center gap-3 text-[12.5px] text-status-failed">
            <p>{state.message}</p>
            <Button variant="secondary" size="sm" onClick={() => void refresh()}>
              Retry
            </Button>
          </div>
        ) : null}
        {state.status === "empty" ? <p className="text-[12.5px] text-ink-500">{EMPTY_MESSAGE}</p> : null}
        {state.status === "ready" ? (
          <ul aria-label="Connectors" className="grid gap-4 md:grid-cols-2">
            {state.connectors.map((connector) => (
              <li key={connector.key} className="flex [&>article]:flex-1">
                <ConnectorCard
                  connector={connector}
                  pending={pendingFor(connector.key)}
                  onConnect={startSignIn}
                  onReconnect={startSignIn}
                  onDisconnect={setDisconnectTarget}
                  onCancel={(c) => authorization.cancel(c.key)}
                />
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {disconnectTarget ? (
        <DisconnectDialog
          connector={disconnectTarget}
          onConfirm={(c) => authorization.disconnect(c.key)}
          onClose={() => setDisconnectTarget(null)}
        />
      ) : null}
    </div>
  );
}

export default ConnectorsPage;
