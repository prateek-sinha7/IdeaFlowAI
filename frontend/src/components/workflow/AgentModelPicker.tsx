"use client";

/**
 * AgentModelPicker — per-agent model picker populated from the live
 * capability-registry model catalog (the `model_catalog` kind, API-02 /
 * MODEL-04 / D-11).
 *
 * Home (ISS-014): this is the PRIMARY model-selection surface inside the
 * AgentsPopup Agents tab. The legacy WorkflowComposer/CapabilityPalette that
 * once hosted it were deleted; there is no composer to look for.
 *
 * Fetches the live `/api/capabilities` model catalog on mount and lets the user
 * pick a model PER AGENT. The selection is reported upward via `onChange`
 * (agentId -> modelId) so it feeds the existing per-run `model_overrides` path —
 * an unselected agent simply keeps the run default (no override emitted).
 *
 * Models come from the live registry catalog (id/label/tier), never a hardcoded
 * list; only `user_allowed` models are offered.
 */

import { useEffect, useState } from "react";
import { Cpu, AlertCircle } from "lucide-react";
import {
  getCapabilities,
  getToken,
  type CapabilityModelEntry,
} from "@/lib/api";

export interface AgentModelPickerProps {
  /** The agents (id + display name) the user can assign a model to. */
  agents: { id: string; name: string }[];
  /** Reports the per-agent model overrides (agentId -> modelId). */
  onChange?: (modelOverrides: Record<string, string>) => void;
  /** Optional token override (defaults to the stored JWT). */
  token?: string | null;
}

export function AgentModelPicker({
  agents,
  onChange,
  token,
}: AgentModelPickerProps) {
  const [models, setModels] = useState<CapabilityModelEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    const jwt = token ?? getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getCapabilities(jwt)
      .then((palette) => {
        if (cancelled) return;
        // Only offer user-allowed models in the picker.
        setModels(palette.model_catalog.filter((m) => m.user_allowed));
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load models.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const setAgentModel = (agentId: string, modelId: string) => {
    setOverrides((prev) => {
      const next = { ...prev };
      if (modelId) {
        next[agentId] = modelId;
      } else {
        // Empty selection = use the run default (no override emitted).
        delete next[agentId];
      }
      onChange?.(next);
      return next;
    });
  };

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5 mb-2">
        <Cpu className="h-3.5 w-3.5 text-[#1B2A4A]" />
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Per-Agent Model
        </p>
      </div>

      {loading && (
        <p className="text-[11px] text-gray-400 py-2">Loading model catalog…</p>
      )}

      {error && (
        <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          {error}
        </div>
      )}

      {!loading && !error && agents.length === 0 && (
        <p className="text-[11px] text-gray-400 py-2">
          Add agents to assign per-agent models.
        </p>
      )}

      {!loading && !error && agents.length > 0 && (
        <div className="space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="flex items-center gap-2 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5"
            >
              <p className="text-[11px] font-semibold text-gray-800 truncate flex-1 min-w-0">
                {agent.name}
              </p>
              <select
                value={overrides[agent.id] ?? ""}
                onChange={(e) => setAgentModel(agent.id, e.target.value)}
                className="text-[10px] text-gray-700 bg-white border border-gray-200 rounded-md px-1.5 py-1 focus:outline-none focus:border-[#1B2A4A] max-w-[140px]"
              >
                <option value="">Default</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
