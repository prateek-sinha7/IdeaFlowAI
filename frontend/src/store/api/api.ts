/**
 * Consolidated axios-based API client. Each backend resource lives in its
 * own module (see tools/api/endpoints/*.http for the endpoint reference this mirrors);
 * this file re-exports them under one `api` namespace plus named exports for
 * direct imports. The shared axios instance (auto-attaches the JWT, maps
 * errors to the existing ApiError) lives in ./http.
 */

import { authApi } from "./auth";
import { chatsApi } from "./chats";
import { capabilitiesApi } from "./capabilities";
import { settingsApi } from "./settings";
import { agentsApi } from "./agents";
import { handoffApi } from "./handoff";
import { mcpApi } from "./mcp";
import { installApi } from "./install";
import { filesApi } from "./files";
import { pptApi } from "./ppt";
import { prototypeApi } from "./prototype";
import { workflowsApi } from "./workflows";
import { userWorkflowsApi } from "./userWorkflows";
import { runsApi } from "./runs";
import { adminApi } from "./admin";
import { healthApi } from "./health";

export const api = {
  auth: authApi,
  chats: chatsApi,
  capabilities: capabilitiesApi,
  settings: settingsApi,
  agents: agentsApi,
  handoff: handoffApi,
  mcp: mcpApi,
  install: installApi,
  files: filesApi,
  ppt: pptApi,
  prototype: prototypeApi,
  workflows: workflowsApi,
  userWorkflows: userWorkflowsApi,
  runs: runsApi,
  admin: adminApi,
  health: healthApi,
};

export {
  authApi,
  chatsApi,
  capabilitiesApi,
  settingsApi,
  agentsApi,
  handoffApi,
  mcpApi,
  installApi,
  filesApi,
  pptApi,
  prototypeApi,
  workflowsApi,
  userWorkflowsApi,
  runsApi,
  adminApi,
  healthApi,
};

export { http } from "./http";

export default api;
