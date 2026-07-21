"use client";

// ─────────────────────────────────────────────────────────────────────────────
// ReadOnlyVersionBanner — the amber "Viewing v{k} (read-only)" strip shown under
// the run header while an older version is on screen (B3 / POR §5 D5). Cloned
// from the ReviewGatePanel amber notice (ReviewGatePanel.tsx:398-403).
//
// Phase 39 (RUNUI-06/07): the interactive version affordance (the retired v{n} ▾
// pill + dropdown) has moved into the mock's RunHeader Version menu — one version
// control (INV-3/INV-12). This file now hosts ONLY the read-only banner, which
// the mock does not depict but which surfaces the real older-version-viewing
// behaviour (ND-D live data).
// ─────────────────────────────────────────────────────────────────────────────

import { AlertTriangle } from "lucide-react";

export function ReadOnlyVersionBanner({
  versionNumber,
  onBackToLatest,
}: {
  versionNumber: number;
  onBackToLatest: () => void;
}) {
  return (
    <div
      role="status"
      className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[10px] text-amber-700"
    >
      <AlertTriangle aria-hidden className="h-3.5 w-3.5 text-amber-600 flex-shrink-0" />
      <span>Viewing v{versionNumber} (read-only)</span>
      <button
        onClick={onBackToLatest}
        className="ml-auto text-amber-700 font-medium hover:underline"
      >
        Back to latest →
      </button>
    </div>
  );
}
