"use client";

import { AlertTriangle, CheckCircle2, Circle, MinusCircle, type LucideIcon } from "lucide-react";
import type { ConnectorStatus } from "@/types/connectors";
import { statusLabel } from "./connectorMessages";

// Colour never carries the meaning alone: every status has a text label and its own icon.
const STATUS_STYLE: Record<ConnectorStatus, { icon: LucideIcon; className: string }> = {
  connected: {
    icon: CheckCircle2,
    className: "text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]",
  },
  expired: {
    icon: AlertTriangle,
    className: "text-status-amber bg-[var(--status-amber-fill)] border-[var(--status-amber-border)]",
  },
  not_connected: {
    icon: Circle,
    className: "text-status-queued bg-[var(--status-queued-fill)] border-[var(--status-queued-border)]",
  },
  not_configured: {
    icon: MinusCircle,
    className: "text-status-queued bg-[var(--status-queued-fill)] border-[var(--status-queued-border)]",
  },
};

export interface ConnectorStatusBadgeProps {
  status: ConnectorStatus;
}

export function ConnectorStatusBadge({ status }: ConnectorStatusBadgeProps) {
  const { icon: Icon, className } = STATUS_STYLE[status];
  return (
    <span
      className={[
        "inline-flex items-center gap-1 border rounded-[var(--radius-tag)] px-2 py-1 font-sans text-[11px] font-semibold leading-none",
        className,
      ].join(" ")}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}

export default ConnectorStatusBadge;
