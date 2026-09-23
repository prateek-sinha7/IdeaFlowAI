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
  /** spec 020 — reasoning capability; `reasoning_levels` drives the Effort dropdown. */
  reasoning_mode?: "effort" | "adaptive" | "budget" | "none";
  reasoning_levels?: string[];
}

export interface CapabilitiesPalette {
  capabilities: CapabilityEntry[];
  model_catalog: CapabilityModelEntry[];
}

/**
 * ISS-834 — single-flight guard, the axios twin of `inFlightWorkflows`
 * (`lib/api.ts`). This is a second implementation of `GET /api/capabilities`
 * sitting on `store/api/http.ts`, which has no cache or dedupe of its own, so
 * it cannot reach FIX-617's `cachedGet()` in `lib/api.ts`. It has no callers
 * today; the moment one lands, two components mounting together would each
 * open their own 27 KB request — exactly the duplication FIX-617 closed on the
 * other implementation. Dropped as soon as the request settles: this
 * de-duplicates, it does not cache.
 */
let inFlightPalette: Promise<CapabilitiesPalette> | null = null;

export const capabilitiesApi = {
  get: (): Promise<CapabilitiesPalette> => {
    inFlightPalette ??= http
      .get<CapabilitiesPalette>("/api/capabilities")
      .then(({ data }) => data)
      .finally(() => {
        inFlightPalette = null;
      });
    return inFlightPalette;
  },
};
