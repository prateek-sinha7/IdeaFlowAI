import { http, multipartConfig } from "./http";

export interface ExtractTextResponse {
  filename: string;
  text: string;
  truncated: boolean;
}

export const filesApi = {
  extractText: async (file: File): Promise<ExtractTextResponse> => {
    const form = new FormData();
    form.append("file", file);
    const { data } = await http.post<ExtractTextResponse>(
      "/api/files/extract-text",
      form,
      multipartConfig()
    );
    return data;
  },
};
