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
