"use client";

/**
 * MachinesPanel — the admin "Machines" tab body: the live capacity table
 * (`CapacityMatrix`, 15s poll) above the selected instance's metric history
 * (`CapacityHistoryPanel`, ADR-0056).
 *
 * Owns the instance selection and the chart view options so both survive the
 * history panel unmounting while the table is loading or erroring. The effective
 * selection is derived during render: the clicked instance while it is still in
 * the table, otherwise this instance, otherwise the first row.
 */

import { useState } from "react";
import type { AdminCapacityInstance } from "@/lib/api";
import type { CapacityMatrixState } from "@/hooks/useCapacityMatrix";
import { CapacityMatrix } from "./CapacityMatrix";
import { CapacityHistoryPanel, DEFAULT_HISTORY_VIEW } from "./CapacityHistoryPanel";
import type { HistoryViewOptions } from "./CapacityHistoryPanel";

export function resolveSelectedInstance(
  instances: readonly AdminCapacityInstance[],
  selectedId: string | null,
): string | null {
  if (selectedId && instances.some((inst) => inst.instance_id === selectedId)) {
    return selectedId;
  }
  return (instances.find((inst) => inst.is_self) ?? instances[0])?.instance_id ?? null;
}

export interface MachinesPanelProps {
  state: CapacityMatrixState;
  token: string | null;
}

export function MachinesPanel({ state, token }: MachinesPanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viewOptions, setViewOptions] = useState<HistoryViewOptions>(DEFAULT_HISTORY_VIEW);

  const instances = state.status === "ready" ? state.matrix.instances : [];
  const effectiveId = resolveSelectedInstance(instances, selectedId);

  return (
    <div className="space-y-4">
      <CapacityMatrix
        state={state}
        selectedInstanceId={effectiveId}
        onSelectInstance={setSelectedId}
      />
      {effectiveId && (
        <CapacityHistoryPanel
          token={token}
          instanceId={effectiveId}
          options={viewOptions}
          onOptionsChange={setViewOptions}
        />
      )}
    </div>
  );
}

export default MachinesPanel;
