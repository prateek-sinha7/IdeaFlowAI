import { http } from "./http";

export interface PptTemplateSummary {
  id: string;
  name: string;
  [key: string]: unknown;
}

export interface PptTemplateDetail extends PptTemplateSummary {
  [key: string]: unknown;
}

export const pptApi = {
  listTemplates: async (): Promise<PptTemplateSummary[]> => {
    const { data } = await http.get<PptTemplateSummary[]>("/api/ppt/templates");
    return data;
  },
  getTemplate: async (templateId: string): Promise<PptTemplateDetail> => {
    const { data } = await http.get<PptTemplateDetail>(
      `/api/ppt/templates/${encodeURIComponent(templateId)}`
    );
    return data;
  },
  /** Returns a preview asset URL (image/HTML) — public, no auth required. */
  previewUrl: (templateId: string): string => {
    return `${http.defaults.baseURL ?? ""}/api/ppt/templates/${encodeURIComponent(templateId)}/preview`;
  },
  thumbnailUrl: (templateId: string): string => {
    return `${http.defaults.baseURL ?? ""}/api/ppt/templates/${encodeURIComponent(templateId)}/thumbnail`;
  },
};
