import { http } from "./http";
import {
  isAuthorizeResponse,
  isConnectorListResponse,
  isConnectorToolsResponse,
  isDisconnectResponse,
  type AuthorizeResponse,
  type ConnectorListResponse,
  type ConnectorToolsResponse,
  type DisconnectResponse,
} from "@/types/connectors";

/** Thrown when the server answers 2xx with a body that does not match the contract. */
export class ConnectorsContractError extends Error {
  constructor(endpoint: string) {
    super(`Unexpected response from ${endpoint}`);
    this.name = "ConnectorsContractError";
  }
}

function checked<T>(endpoint: string, data: unknown, guard: (value: unknown) => value is T): T {
  if (!guard(data)) throw new ConnectorsContractError(endpoint);
  return data;
}

function connectorPath(key: string, suffix = ""): string {
  return `/api/connectors/${encodeURIComponent(key)}${suffix}`;
}

/**
 * Connectors REST client (backend/app/api/connectors.py). The shared axios
 * client attaches the JWT. Errors arrive as ApiError with the backend envelope
 * `{error, code, recoverable}` in `detail`. The OAuth callback is not called
 * from here: the provider redirects the popup to it.
 */
export const connectorsApi = {
  list: async (): Promise<ConnectorListResponse> => {
    const { data } = await http.get<unknown>("/api/connectors");
    return checked("GET /api/connectors", data, isConnectorListResponse);
  },

  authorize: async (key: string): Promise<AuthorizeResponse> => {
    const { data } = await http.post<unknown>(connectorPath(key, "/authorize"));
    return checked("POST /api/connectors/{key}/authorize", data, isAuthorizeResponse);
  },

  disconnect: async (key: string): Promise<DisconnectResponse> => {
    const { data } = await http.delete<unknown>(connectorPath(key));
    return checked("DELETE /api/connectors/{key}", data, isDisconnectResponse);
  },

  tools: async (key: string): Promise<ConnectorToolsResponse> => {
    const { data } = await http.get<unknown>(connectorPath(key, "/tools"));
    return checked("GET /api/connectors/{key}/tools", data, isConnectorToolsResponse);
  },
};
