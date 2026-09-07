import { http } from "./http";

export interface CapabilityEntry {
  kind: string;
  name: string;
  user_allowed: boolean;
  description: string;
  security_gated: boolean;
  config_schema: Record<string, unknown>;
}

export interface CapabilityModelEntry {
  id: string;
  label: string;
  description: string;
  tier: string;
  cost_class: string;
  provider: string;
  context_window: number;
  user_allowed: boolean;
  /** RFN-002b — pricing rates in USD per 1 M tokens. */
  input_rate_per_1m?: number;
  output_rate_per_1m?: number;
  cache_read_rate_per_1m?: number;
  cache_write_5m_rate_per_1m?: number;
  thinking_supported?: boolean;
}

export interface CapabilitiesPalette {
  capabilities: CapabilityEntry[];
  model_catalog: CapabilityModelEntry[];
}

export const capabilitiesApi = {
  get: async (): Promise<CapabilitiesPalette> => {
    const { data } = await http.get<CapabilitiesPalette>("/api/capabilities");
    return data;
  },
};
