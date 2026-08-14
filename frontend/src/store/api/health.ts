import { http } from "./http";

export interface HealthResponse {
  status: string;
  [key: string]: unknown;
}

export const healthApi = {
  check: async (): Promise<HealthResponse> => {
    const { data } = await http.get<HealthResponse>("/health");
    return data;
  },
};
