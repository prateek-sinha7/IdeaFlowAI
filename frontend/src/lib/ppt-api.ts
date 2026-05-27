/**
 * API client for the OpenDesign-style PPT/deck template catalogue.
 * Mirrors prototype-api.ts exactly.
 */

import { ENV } from "@/lib/env";

export interface PPTTemplate {
  id: string;
  name: string;
  description: string;
  mode: string | null;
  platform: string | null;
  scenario: string | null;
  triggers: string[];
  craft_required: string[];
  example_prompt: string | null;
  has_preview: boolean;
  /** design_system.requires == true means this template needs a DESIGN.md */
  design_system: { requires?: boolean; [key: string]: unknown };
}

export interface PPTTemplateDetail extends PPTTemplate {
  inputs: Record<string, unknown>[] | Record<string, unknown>;
  outputs: Record<string, unknown>;
  body: string;
}

async function apiFetch<T>(token: string, path: string): Promise<T> {
  const res = await fetch(`${ENV.API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function listPPTTemplates(token: string): Promise<PPTTemplate[]> {
  return apiFetch<PPTTemplate[]>(token, "/api/ppt/templates");
}

export async function getPPTTemplate(token: string, id: string): Promise<PPTTemplateDetail> {
  return apiFetch<PPTTemplateDetail>(token, `/api/ppt/templates/${id}`);
}

/** URL for the template's example.html preview iframe. Unauthenticated. */
export function getPPTTemplatePreviewUrl(id: string): string {
  return `${ENV.API_URL}/api/ppt/templates/${id}/preview`;
}
