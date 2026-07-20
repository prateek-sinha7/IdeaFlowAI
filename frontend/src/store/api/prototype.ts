import { http } from "./http";
import { getToken } from "@/lib/api";
import { ENV } from "@/lib/env";

export interface PrototypeTemplateSummary {
  id: string;
  name: string;
  [key: string]: unknown;
}

export interface DesignSystemSummary {
  id: string;
  name: string;
  [key: string]: unknown;
}

export interface PrototypeRunRequest {
  template_id: string;
  design_system_id: string;
  brief: string;
  discovery: {
    audience: string;
    cta: string;
    [key: string]: unknown;
  };
}

export const prototypeApi = {
  listTemplates: async (): Promise<PrototypeTemplateSummary[]> => {
    const { data } = await http.get<PrototypeTemplateSummary[]>("/api/prototype/templates");
    return data;
  },
  getTemplate: async (templateId: string): Promise<PrototypeTemplateSummary> => {
    const { data } = await http.get<PrototypeTemplateSummary>(
      `/api/prototype/templates/${encodeURIComponent(templateId)}`
    );
    return data;
  },
  previewUrl: (templateId: string): string =>
    `${http.defaults.baseURL ?? ""}/api/prototype/templates/${encodeURIComponent(templateId)}/preview`,
  thumbnailUrl: (templateId: string): string =>
    `${http.defaults.baseURL ?? ""}/api/prototype/templates/${encodeURIComponent(templateId)}/thumbnail`,
  assetUrl: (templateId: string, assetPath: string): string =>
    `${http.defaults.baseURL ?? ""}/api/prototype/templates/${encodeURIComponent(templateId)}/assets/${assetPath}`,

  listDesignSystems: async (): Promise<DesignSystemSummary[]> => {
    const { data } = await http.get<DesignSystemSummary[]>("/api/prototype/design-systems");
    return data;
  },
  getDesignSystem: async (designSystemId: string): Promise<DesignSystemSummary> => {
    const { data } = await http.get<DesignSystemSummary>(
      `/api/prototype/design-systems/${encodeURIComponent(designSystemId)}`
    );
    return data;
  },
  designSystemPreviewUrl: (designSystemId: string): string =>
    `${http.defaults.baseURL ?? ""}/api/prototype/design-systems/${encodeURIComponent(designSystemId)}/preview`,

  fetchUrl: async (url: string): Promise<unknown> => {
    const { data } = await http.get("/api/prototype/fetch-url", { params: { url } });
    return data;
  },

  /**
   * POST /api/prototype/run streams newline-delimited JSON, which axios's
   * browser (XHR) adapter cannot read incrementally — so this uses fetch
   * directly and yields one parsed JSON object per NDJSON line.
   */
  run: async function* (body: PrototypeRunRequest): AsyncGenerator<unknown, void, unknown> {
    const token = getToken();
    const response = await fetch(`${ENV.API_URL}/api/prototype/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });

    if (!response.ok || !response.body) {
      const text = await response.text().catch(() => response.statusText);
      throw new Error(`prototype run failed (${response.status}): ${text}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        yield JSON.parse(trimmed);
      }
    }

    const trailing = buffer.trim();
    if (trailing) {
      yield JSON.parse(trailing);
    }
  },
};
