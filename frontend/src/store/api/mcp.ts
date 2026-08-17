/**
 * MCP JSON-RPC endpoint. Auth is a Flowin API key sent as a Bearer token
 * (not the user JWT), so calls set their own Authorization header, which
 * the http.ts request interceptor leaves untouched.
 */
import { http } from "./http";

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: "2.0";
  id: number;
  result?: T;
  error?: { code: number; message: string; data?: unknown };
}

export const mcpApi = {
  call: async <T = unknown>(
    request: JsonRpcRequest,
    flowinApiKey: string
  ): Promise<JsonRpcResponse<T>> => {
    const { data } = await http.post<JsonRpcResponse<T>>("/mcp/handoff", request, {
      headers: { Authorization: `Bearer ${flowinApiKey}` },
    });
    return data;
  },
};
