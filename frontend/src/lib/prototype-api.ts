/**
 * Client for the OpenDesign-style prototype catalogue endpoints.
 *
 * Backend routes mounted under /api/prototype/ in backend/app/api/prototype_templates.py.
 * Catalogue endpoints require auth; /preview is unauthenticated so it can be
 * embedded directly via <iframe src> without JWT plumbing.
 */

import { ENV } from "@/lib/env";

const BASE_URL = ENV.API_URL;

export interface PrototypeTemplate {
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
  has_thumbnail: boolean;
}

export interface PrototypeTemplateDetail extends PrototypeTemplate {
  design_system: Record<string, unknown>;
  inputs: unknown;
  outputs: Record<string, unknown>;
  body: string;
}

export interface DesignSystemListItem {
  id: string;
  name: string;
  category: string;
  description: string;
  has_preview: boolean;
}

export interface DesignSystemDetail extends DesignSystemListItem {
  body: string;
}

async function authFetch<T>(token: string, path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function listPrototypeTemplates(token: string): Promise<PrototypeTemplate[]> {
  return authFetch<PrototypeTemplate[]>(token, "/api/prototype/templates");
}

export function getPrototypeTemplate(
  token: string,
  id: string,
): Promise<PrototypeTemplateDetail> {
  return authFetch<PrototypeTemplateDetail>(
    token,
    `/api/prototype/templates/${encodeURIComponent(id)}`,
  );
}

export function listDesignSystems(token: string): Promise<DesignSystemListItem[]> {
  return authFetch<DesignSystemListItem[]>(token, "/api/prototype/design-systems");
}

export function getDesignSystem(
  token: string,
  id: string,
): Promise<DesignSystemDetail> {
  return authFetch<DesignSystemDetail>(
    token,
    `/api/prototype/design-systems/${encodeURIComponent(id)}`,
  );
}

/**
 * Public URL for the template's example.html. Safe to drop directly into
 * <iframe src> — the endpoint is unauthenticated and the file is static.
 */
export function getTemplatePreviewUrl(id: string): string {
  return `${BASE_URL}/api/prototype/templates/${encodeURIComponent(id)}/preview`;
}

/**
 * Public URL for the template's pre-rendered thumbnail image (a screenshot of
 * example.html). Safe to drop directly into <img src> — unauthenticated and
 * static. Only present when `has_thumbnail` is true; the gallery falls back to
 * the sandboxed preview iframe otherwise.
 */
export function getTemplateThumbnailUrl(id: string): string {
  return `${BASE_URL}/api/prototype/templates/${encodeURIComponent(id)}/thumbnail`;
}

/**
 * Public URL for the design system's components.html preview.
 * Unauthenticated — safe to use directly as <iframe src>.
 * Only available for the 17 design systems that ship components.html.
 */
export function getDesignSystemPreviewUrl(id: string): string {
  return `${BASE_URL}/api/prototype/design-systems/${encodeURIComponent(id)}/preview`;
}
