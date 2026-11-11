"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import type { ConnectorSummary, ProviderRevocation } from "@/types/connectors";
import {
  disconnectDialogBody,
  disconnectDialogTitle,
  disconnectFailedMessage,
  disconnectResultMessage,
} from "./connectorMessages";

export interface DisconnectDialogProps {
  connector: ConnectorSummary;
  /** Runs the disconnect. Resolves with the provider revocation result, or null on failure. */
  onConfirm: (connector: ConnectorSummary) => Promise<ProviderRevocation | null>;
  onClose: () => void;
}

type Phase =
  | { kind: "confirm"; failed: boolean }
  | { kind: "working" }
  | { kind: "done"; revocation: ProviderRevocation };

/**
 * Confirms a disconnect, says that the provider grant is revoked too, and then
 * shows how the revoke went. Escape and the backdrop cancel, except while the
 * request is running.
 */
export function DisconnectDialog({ connector, onConfirm, onClose }: DisconnectDialogProps) {
  const [phase, setPhase] = useState<Phase>({ kind: "confirm", failed: false });
  const footerRef = useRef<HTMLDivElement>(null);
  const name = connector.display_name;
  const working = phase.kind === "working";
  const done = phase.kind === "done";

  // The confirm buttons unmount when the result shows, so move focus to Close.
  useEffect(() => {
    if (done) footerRef.current?.querySelector("button")?.focus();
  }, [done]);

  const confirm = async () => {
    setPhase({ kind: "working" });
    const revocation = await onConfirm(connector);
    setPhase(revocation ? { kind: "done", revocation } : { kind: "confirm", failed: true });
  };

  return (
    <Modal
      onClose={() => {
        if (!working) onClose();
      }}
      title={disconnectDialogTitle(name)}
      hideCloseButton
      closeOnBackdropClick={!working}
    >
      {phase.kind === "done" ? (
        <p role="status" className="text-[12.5px] text-ink-700">
          {disconnectResultMessage(phase.revocation, name)}
        </p>
      ) : (
        <p className="text-[12.5px] text-ink-700">{disconnectDialogBody(name)}</p>
      )}
      {phase.kind === "confirm" && phase.failed ? (
        <p role="alert" className="mt-3 text-[12.5px] text-status-failed">
          {disconnectFailedMessage(name)}
        </p>
      ) : null}
      <div ref={footerRef} className="mt-5 flex justify-end gap-3">
        {phase.kind === "done" ? (
          <Button onClick={onClose}>
            Close
          </Button>
        ) : (
          <>
            <Button variant="secondary" disabled={working} onClick={onClose}>
              Cancel
            </Button>
            <Button disabled={working} onClick={() => void confirm()}>
              {working ? "Disconnecting…" : "Disconnect"}
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}

export default DisconnectDialog;
