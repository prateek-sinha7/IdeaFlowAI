/**
 * Flowin handoff endpoints. Auth here is a Flowin API key
 * (`X-Flowin-API-Key` header), NOT the user JWT the shared `http`
 * instance auto-attaches — so `receive` sets its own header explicitly,
 * which the http.ts request interceptor leaves untouched.
 */
import { http } from "./http";

export interface HandoffReceiveRequest {
  task: string;
  transcript: string;
  repo_url: string;
  mode: string;
  source_branch: string;
  source_client: string;
}

export interface HandoffReceiveResponse {
  handoff_token: string;
  [key: string]: unknown;
}

export interface HandoffDetail {
  id: string;
  status: string;
  [key: string]: unknown;
}

export const handoffApi = {
  receive: async (
    body: HandoffReceiveRequest,
    flowinApiKey: string
  ): Promise<HandoffReceiveResponse> => {
    const { data } = await http.post<HandoffReceiveResponse>("/api/handoff/receive", body, {
      headers: { "X-Flowin-API-Key": flowinApiKey },
    });
    return data;
  },

  get: async (handoffToken: string): Promise<HandoffDetail> => {
    const { data } = await http.get<HandoffDetail>(`/api/handoff/${handoffToken}`);
    return data;
  },

  start: async (handoffToken: string): Promise<HandoffDetail> => {
    const { data } = await http.post<HandoffDetail>(`/api/handoff/${handoffToken}/start`);
    return data;
  },
};
