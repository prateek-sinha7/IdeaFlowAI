/**
 * Mock REST backend for the Flowin E2E suite (mocked mode).
 *
 * Routes every `**​/api/**` request the dashboard makes on load and during a
 * run, so the UI renders deterministically with NO backend:
 *   - GET  /api/auth/me            → the current User (tier drives entitlement)
 *   - POST /api/auth/login         → { token, user }
 *   - POST /api/auth/logout        → 200
 *   - GET  /api/runs(?...)         → RawWorkflowRun[]   (history list)
 *   - GET  /api/runs/:id           → RawWorkflowRun     (reopen detail)
 *   - DELETE /api/runs/:id         → 204
 *   - GET  /api/capabilities       → { capabilities, model_catalog }
 *   - GET  /api/settings/preferences → { preferred_model, available_models }
 *   - GET  /api/chats              → []
 *   - anything else under /api     → 200 {}
 *
 * The controller is mutable mid-test (setUser / setRuns / setRunDetail) so a
 * spec can, e.g., set the history list, reopen a run, then assert the preview.
 */
import type { Page, Route } from "@playwright/test";
import { MODEL_CATALOG, CAPABILITIES } from "./constants";

export type Tier = "basic" | "pro" | "enterprise";

export interface MockUser {
  id: string;
  email: string;
  tier: Tier;
  is_admin?: boolean;
}

/** snake_case run shape the FE's normalizeWorkflowRun() expects (lib/api.ts). */
export interface RawRun {
  id: string;
  title: string;
  type: string;
  status: string; // completed | failed | cancelled | running | degraded | revising
  input: string;
  output: string | null;
  agent_outputs: string | null;
  agent_count: number;
  duration: number | null;
  error: string | null;
  token_usage: string | null;
  model_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export function makeRun(partial: Partial<RawRun> & { id: string }): RawRun {
  return {
    title: "Untitled run",
    type: "user_stories",
    status: "completed",
    input: "test brief",
    output: null,
    agent_outputs: null,
    agent_count: 0,
    duration: 12.3,
    error: null,
    token_usage: null,
    model_id: null,
    created_at: "2026-06-13T12:00:00Z",
    completed_at: "2026-06-13T12:00:30Z",
    ...partial,
  };
}

export interface MockApiOptions {
  user?: Partial<MockUser>;
  runs?: RawRun[];
  capabilities?: { capabilities: unknown[]; model_catalog: unknown[] };
  /** Resolve a single run by id (reopen). Falls back to the runs list. */
  runDetail?: (id: string) => RawRun | undefined;
}

export class MockApi {
  user: MockUser;
  runs: RawRun[];
  capabilities: { capabilities: unknown[]; model_catalog: unknown[] };
  private runDetail?: (id: string) => RawRun | undefined;
  /** Recorded request log for assertions (method + path). */
  readonly requests: { method: string; url: string; body?: unknown }[] = [];

  constructor(opts: MockApiOptions) {
    this.user = {
      id: "u-test",
      email: "qa@flowinqa.com",
      tier: "enterprise",
      is_admin: false,
      ...opts.user,
    };
    this.runs = opts.runs ?? [];
    this.capabilities = opts.capabilities ?? {
      capabilities: CAPABILITIES as unknown as unknown[],
      model_catalog: MODEL_CATALOG as unknown as unknown[],
    };
    this.runDetail = opts.runDetail;
  }

  setUser(patch: Partial<MockUser>) {
    this.user = { ...this.user, ...patch };
  }
  setRuns(runs: RawRun[]) {
    this.runs = runs;
  }
  setRunDetail(fn: (id: string) => RawRun | undefined) {
    this.runDetail = fn;
  }

  private resolveDetail(id: string): RawRun | undefined {
    return this.runDetail?.(id) ?? this.runs.find((r) => r.id === id);
  }

  async handle(route: Route) {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const path = url.pathname;
    let body: unknown;
    try {
      body = req.postDataJSON?.();
    } catch {
      /* non-json */
    }
    this.requests.push({ method, url: path, body });

    const json = (data: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });

    // --- auth ---
    if (path.endsWith("/api/auth/me")) return json(this.user);
    if (path.endsWith("/api/auth/login") && method === "POST") {
      const b = (body as { email?: string }) ?? {};
      return json({ token: "e2e.login.jwt", user: { ...this.user, email: b.email ?? this.user.email } });
    }
    if (path.endsWith("/api/auth/logout")) return json({ ok: true });
    if (path.endsWith("/api/auth/change-password")) return json({ message: "ok" });

    // --- capabilities (model picker) ---
    if (path.endsWith("/api/capabilities")) return json(this.capabilities);

    // --- settings ---
    if (path.endsWith("/api/settings/preferences")) {
      return json({
        preferred_model: null,
        available_models: (this.capabilities.model_catalog as { id: string; label: string; description: string; tier: string }[])
          .map((m) => ({ id: m.id, name: m.label, description: m.description, tier: m.tier })),
      });
    }

    // --- runs (history) ---
    const runDetailMatch = path.match(/\/api\/runs\/([^/]+)(\/chain-context)?$/);
    if (runDetailMatch) {
      const id = runDetailMatch[1];
      if (runDetailMatch[2] === "/chain-context") {
        return json({ workflow_id: id, pipeline_type: "user_stories", title: "", brief: "", structured_summary: "", agent_summaries: [], context_block: "" });
      }
      if (method === "DELETE") return route.fulfill({ status: 204, body: "" });
      const detail = this.resolveDetail(id);
      if (!detail) return json({ detail: "not found" }, 404);
      return json(detail);
    }
    if (path.endsWith("/api/runs")) return json(this.runs);

    // --- chats (secondary) ---
    if (path.match(/\/api\/chats(\/.*)?$/)) {
      if (method === "POST") return json({ id: "chat-1", title: "New chat", last_activity: "2026-06-13T12:00:00Z", created_at: "2026-06-13T12:00:00Z" });
      return json([]);
    }

    // --- anything else under /api → empty 200 ---
    return json({});
  }
}

/** Install the mock REST backend on a page. Call before navigation. */
export async function installMockApi(page: Page, opts: MockApiOptions = {}): Promise<MockApi> {
  const mock = new MockApi(opts);
  await page.route("**/api/**", (route) => mock.handle(route));
  return mock;
}
