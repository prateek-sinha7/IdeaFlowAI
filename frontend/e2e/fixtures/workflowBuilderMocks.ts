/**
 * Mocked AI Workflow Builder backend for the Flowin E2E suite (mocked project).
 *
 * Covers the `/api/workflow-builder` surface the panel uses, with NO backend and NO
 * model:
 *
 *   REST  `page.route("** /api/workflow-builder/**")`: GET /models, POST|GET /sessions,
 *         GET|DELETE /sessions/{id}, POST /sessions/{id}/messages, .../link, .../cancel.
 *         Registered AFTER the `mockApi` fixture's catch-all, so it wins by Playwright's
 *         last-registered-first precedence.
 *   SSE   the Session_Stream (`GET /sessions/{id}/events`) is served by a page-side
 *         `fetch` stub, not by `page.route`. `route.fulfill` can only send a finished
 *         body, which ends the stream; the app's hook then reconnects after 1 s and
 *         opens with a fresh `snapshot`, so every batch of events would cost a second
 *         and "see progress, then the draft" could not be shown step by step. The stub
 *         returns a real `ReadableStream` that stays open and receives frames from
 *         `publish()`. Every new connection opens with a `snapshot` built from the
 *         mock's state, as the server does.
 *
 * A spec drives a turn through a `ScriptedTurn`:
 *
 *   const builder = await installWorkflowBuilderMocks(page);
 *   ...send a message in the UI...
 *   const turn = await builder.nextTurn();   // resolves when the POST arrived
 *   await turn.start();
 *   await turn.setStage("reading", "Reading the builder guide");
 *   await turn.applyDraft({ manifest: DRAFT_MANIFEST, changeSummary: DRAFT_CHANGE_SUMMARY });
 *   await turn.complete({ status: "completed", content: "..." });
 *
 * Stored state (`GET /sessions/{id}`) is updated before the matching event is
 * published, so the reload the panel does after `turn_completed` sees the final
 * message and the draft, as it does against the real server.
 *
 * The wire shapes mirror `frontend/src/types/workflowBuilder.ts`. They are restated
 * here on purpose: a fixture that imported the app's types would follow a wrong type
 * change silently instead of failing the journey.
 */
import { expect } from "@playwright/test";
import type { Page, Route } from "@playwright/test";

// ── Wire shapes ─────────────────────────────────────────────────────────────────

export type JsonObject = Record<string, unknown>;

export type MockTurnStatus = "completed" | "failed" | "cancelled" | "timed_out" | "interrupted";
export type MockStopReason =
  | "time"
  | "tool_calls"
  | "tokens"
  | "recursion"
  | "gate_rejections"
  | "cancelled"
  | "deleted"
  | "shutdown"
  | "restart"
  | "error";
export type MockOutcome = "draft" | "reply" | "unfinished";
export type MockStage =
  | "starting"
  | "thinking"
  | "reading"
  | "looking_up"
  | "writing"
  | "checking"
  | "platform_check"
  | "applying"
  | "responding";
export type MockToolKind = "read" | "write" | "script" | "lookup" | "propose";
export type MockToolFinishStatus = "ok" | "error" | "refused" | "timed_out";

export interface MockToolActivity {
  call_id: string;
  tool: string;
  kind: MockToolKind;
  label: string;
  status: "running" | MockToolFinishStatus;
  duration_ms: number | null;
  command: string | null;
  exit_code: number | null;
  summary: string | null;
}

export interface MockCheck {
  source: "skill_validator" | "platform_dry_run" | "server_gate";
  verdict: "valid" | "invalid" | "unknown";
  errors: number;
  warnings: number;
  attempt: number | null;
  attempts_left: number | null;
}

export interface MockChangeSummary {
  added: string[];
  removed: string[];
  reordered: boolean;
  gates_changed: string[];
  validators_changed: string[];
  models_changed: string[];
  prompts_changed: number;
}

export interface MockDraftRevision {
  revision: number;
  kind: "seed" | "accepted" | "undo" | "unproposed";
  manifest: JsonObject;
  target_trust: "user" | "db" | null;
  change_summary: MockChangeSummary | null;
  launch_needs: Array<{ kind: string; detail: string | null }>;
  source_turn_id: string | null;
  created_at: string;
}

export interface MockMessage {
  id: string;
  seq: number;
  role: "user" | "assistant";
  turn_id: string;
  reply_to_message_id: string | null;
  status: MockTurnStatus | "accepted";
  outcome: MockOutcome | null;
  stop_reason: MockStopReason | null;
  content: string;
  thinking: string | null;
  model_id: string;
  effort: string | null;
  skill_hash: string | null;
  skill_updated: boolean;
  error: { code: string; message: string; retryable: boolean } | null;
  revision: number | null;
  activity: MockToolActivity[];
  activity_summary: { actions: number; checks: number; duration_ms: number } | null;
  created_at: string;
  ended_at: string | null;
}

export interface MockSession {
  id: string;
  title: string;
  mode: "create" | "edit";
  workflow_id: string | null;
  model_id: string;
  effort: string | null;
  running: boolean;
  created_at: string;
  updated_at: string;
  target_trust: "user" | "db";
  skill_hash: string;
  messages: MockMessage[];
  latest_draft: MockDraftRevision | null;
  latest_unproposed: MockDraftRevision | null;
  running_turn: JsonObject | null;
  linked_row_changed: boolean;
}

/** A message the app POSTed, as the server would read it. */
export interface SentMessage {
  sessionId: string;
  content: string;
  model_id: string;
  effort: string | null;
  canvas_state: JsonObject;
  client_message_id: string;
}

export interface RecordedBuilderRequest {
  method: string;
  /** Path below `/api/workflow-builder`, for example `/sessions/sess-e2e-1/messages`. */
  path: string;
  body?: unknown;
}

// ── Constants ───────────────────────────────────────────────────────────────────

/** The two models `GET /models` offers. The first is the default. */
export const E2E_MODELS = [
  {
    id: "e2e.builder.deep",
    label: "Builder Deep",
    description: "Reasons step by step",
    tier: "powerful",
    cost_class: "high",
    provider: "bedrock",
    context_window: 200000,
    user_allowed: true,
    reasoning_mode: "effort",
    reasoning_levels: ["low", "medium", "high"],
  },
  {
    id: "e2e.builder.quick",
    label: "Builder Quick",
    description: "Fast answers",
    tier: "fast",
    cost_class: "low",
    provider: "bedrock",
    context_window: 200000,
    user_allowed: true,
    reasoning_mode: "none",
    reasoning_levels: [],
  },
] as const;

export const E2E_DEFAULT_MODEL_ID: string = E2E_MODELS[0].id;
export const E2E_DEFAULT_EFFORT = "medium";

/** The 503 body the Capacity_Gate returns (same shape `ts-z3.capacity-busy` uses). */
export const CAPACITY_REJECTION = {
  detail: {
    error: "The service is busy right now. Please try again in a few minutes.",
    code: "host_capacity_exhausted",
    recoverable: true,
    retry_after_seconds: 90,
    signals: [{ name: "cpu", value: 91.4, threshold: 75 }],
  },
};

/** A two-step draft in the shape `patterns.md` section 1 produces (custom-agent steps only). */
export const DRAFT_MANIFEST: JsonObject = {
  id: "e2e-ai-research-brief",
  name: "AI research brief",
  description: "Analyse a topic, then write a short brief.",
  planner: "skip",
  clarify: { mode: "skip", defaults: [] },
  deliverable: { strategy: "streamed_text", name: "brief.md" },
  steps: [
    {
      agent: "custom-agent",
      instance_id: "analyze",
      name: "Analyst",
      gates: [],
      prompt:
        "You are the Analyst. From the brief, list audience, goals and constraints as Markdown sections. Do not write the brief.",
    },
    {
      agent: "custom-agent",
      instance_id: "write",
      name: "Writer",
      gates: [],
      depends_on: ["custom-agent:analyze"],
      tools: { read_files: true, write_files: false },
      prompt:
        "You are the Writer. Read the analysis listed under 'Earlier steps produced'. Write the brief in Markdown.",
    },
  ],
};

export const DRAFT_CHANGE_SUMMARY: MockChangeSummary = {
  added: ["Analyst", "Writer"],
  removed: [],
  reordered: false,
  gates_changed: [],
  validators_changed: [],
  models_changed: [],
  prompts_changed: 0,
};

// ── Page-side stream stub ───────────────────────────────────────────────────────

interface StreamConnection {
  sessionId: string;
  closed: boolean;
  controller: ReadableStreamDefaultController<Uint8Array>;
}

interface StreamWindow {
  __wbStream?: { conns: StreamConnection[] };
  __wbSnapshot?: (sessionId: string) => Promise<string>;
}

/**
 * Runs in the browser before the app loads (`addInitScript`). It must be
 * self-contained: Playwright serialises the function body, so it can use nothing
 * from this module.
 */
function installStreamStub(): void {
  const w = window as unknown as StreamWindow & { fetch: typeof fetch };
  if (w.__wbStream) return;
  const encoder = new TextEncoder();
  const state = { conns: [] as StreamConnection[] };
  w.__wbStream = state;

  const realFetch = w.fetch.bind(window);
  const eventsUrl = /\/api\/workflow-builder\/sessions\/([^/?]+)\/events(\?|$)/;

  w.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const match = eventsUrl.exec(url);
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    if (!match || method !== "GET") return realFetch(input, init);

    const sessionId = decodeURIComponent(match[1]);
    const snapshot = w.__wbSnapshot ? await w.__wbSnapshot(sessionId) : "";
    const holder: { conn: StreamConnection | null } = { conn: null };
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        holder.conn = { sessionId, closed: false, controller };
        state.conns.push(holder.conn);
        if (snapshot) controller.enqueue(encoder.encode(snapshot));
      },
      cancel() {
        if (holder.conn) holder.conn.closed = true;
      },
    });
    init?.signal?.addEventListener("abort", () => {
      const conn = holder.conn;
      if (!conn || conn.closed) return;
      conn.closed = true;
      try {
        conn.controller.error(new DOMException("Aborted", "AbortError"));
      } catch {
        /* already closed */
      }
    });
    return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  };
}

/** Runs in the browser: write one frame to every open connection. */
function writeFrame(text: string): void {
  const state = (window as unknown as StreamWindow).__wbStream;
  if (!state) return;
  const bytes = new TextEncoder().encode(text);
  for (const conn of state.conns) {
    if (!conn.closed) conn.controller.enqueue(bytes);
  }
}

/** Runs in the browser: is a Session_Stream connection open right now? */
function hasOpenConnection(): boolean {
  const state = (window as unknown as StreamWindow).__wbStream;
  return !!state && state.conns.some((conn) => !conn.closed);
}

/** One SSE block in the real wire shape: `{type, data}` in a single `data:` line. */
function frame(type: string, data: JsonObject): string {
  return `data: ${JSON.stringify({ type, data })}\n\n`;
}

// ── Scripted turn ───────────────────────────────────────────────────────────────

export interface CompleteOptions {
  status: MockTurnStatus;
  /** Defaults to `draft` when a draft was applied, else `reply`. */
  outcome?: MockOutcome;
  stopReason?: MockStopReason | null;
  /** The stored assistant message text. */
  content: string;
}

/**
 * One turn the app started. It publishes events in order (`seq` starts at 1 and
 * only grows) and keeps the stored session in step with what it publishes.
 */
export class ScriptedTurn {
  private seq = 0;
  private stage: { stage: MockStage; label: string } = { stage: "starting", label: "Starting" };
  private activity: MockToolActivity[] = [];
  private checks: MockCheck[] = [];
  private revision: number | null = null;
  private readonly startedAtMs = Date.now();

  constructor(
    private readonly owner: WorkflowBuilderMock,
    readonly sessionId: string,
    readonly turnId: string,
    /** Id of the assistant message this turn stores. */
    readonly messageId: string,
    /** Id of the user message it answers. */
    readonly userMessageId: string,
  ) {}

  /** The `running_turn` object of a snapshot taken now. */
  snapshot(): JsonObject {
    return {
      turn_id: this.turnId,
      message_id: this.messageId,
      stage: this.stage.stage,
      label: this.stage.label,
      started_at: new Date(this.startedAtMs).toISOString(),
      through_seq: this.seq,
      activity: this.activity,
      checks: this.checks,
    };
  }

  private emit(type: string, data: JsonObject): Promise<void> {
    this.seq += 1;
    return this.owner.publish(type, {
      turn_id: this.turnId,
      seq: this.seq,
      ts: new Date().toISOString(),
      ...data,
    });
  }

  async start(): Promise<void> {
    const session = this.owner.requireSession(this.sessionId);
    await this.emit("turn_started", {
      message_id: this.messageId,
      model_id: session.model_id,
      effort: session.effort,
      skill_hash: session.skill_hash,
    });
  }

  async setStage(stage: MockStage, label: string): Promise<void> {
    this.stage = { stage, label };
    await this.emit("stage", { stage, label });
  }

  async toolStarted(call: {
    callId: string;
    tool: string;
    kind: MockToolKind;
    label: string;
    command?: string | null;
  }): Promise<void> {
    this.activity.push({
      call_id: call.callId,
      tool: call.tool,
      kind: call.kind,
      label: call.label,
      status: "running",
      duration_ms: null,
      command: call.command ?? null,
      exit_code: null,
      summary: null,
    });
    await this.emit("tool_started", {
      call_id: call.callId,
      tool: call.tool,
      kind: call.kind,
      label: call.label,
      command: call.command ?? null,
    });
  }

  async toolFinished(call: {
    callId: string;
    status?: MockToolFinishStatus;
    durationMs?: number;
    summary: string;
  }): Promise<void> {
    const status = call.status ?? "ok";
    const durationMs = call.durationMs ?? 1200;
    this.activity = this.activity.map((line) =>
      line.call_id === call.callId
        ? { ...line, status, duration_ms: durationMs, summary: call.summary }
        : line,
    );
    await this.emit("tool_finished", {
      call_id: call.callId,
      status,
      duration_ms: durationMs,
      summary: call.summary,
    });
  }

  async check(result: Partial<MockCheck> = {}): Promise<void> {
    const check: MockCheck = {
      source: "skill_validator",
      verdict: "valid",
      errors: 0,
      warnings: 0,
      attempt: null,
      attempts_left: null,
      ...result,
    };
    this.checks.push(check);
    await this.emit("check_result", { ...check });
  }

  async text(text: string): Promise<void> {
    await this.emit("text", { text });
  }

  /** Accept a draft: store it as the next revision, then publish `draft_applied`. */
  async applyDraft(draft: {
    manifest: JsonObject;
    changeSummary?: MockChangeSummary;
    targetTrust?: "user" | "db";
  }): Promise<number> {
    const session = this.owner.requireSession(this.sessionId);
    const revision = (session.latest_draft?.revision ?? 0) + 1;
    const trust = draft.targetTrust ?? "user";
    const summary = draft.changeSummary ?? DRAFT_CHANGE_SUMMARY;
    session.latest_draft = {
      revision,
      kind: "accepted",
      manifest: draft.manifest,
      target_trust: trust,
      change_summary: summary,
      launch_needs: [],
      source_turn_id: this.turnId,
      created_at: new Date().toISOString(),
    };
    this.revision = revision;
    await this.emit("draft_applied", {
      revision,
      target_trust: trust,
      change_summary: summary,
      launch_needs: [],
      manifest: draft.manifest,
    });
    return revision;
  }

  /** Store the final assistant message, then publish `turn_completed`. */
  async complete(options: CompleteOptions): Promise<void> {
    const session = this.owner.requireSession(this.sessionId);
    const now = new Date().toISOString();
    const outcome: MockOutcome =
      options.outcome ?? (this.revision !== null ? "draft" : "reply");
    const stopReason = options.stopReason ?? null;
    const last = session.messages[session.messages.length - 1];
    session.messages.push({
      id: this.messageId,
      seq: (last?.seq ?? 0) + 1,
      role: "assistant",
      turn_id: this.turnId,
      reply_to_message_id: this.userMessageId,
      status: options.status,
      outcome,
      stop_reason: stopReason,
      content: options.content,
      thinking: null,
      model_id: session.model_id,
      effort: session.effort,
      skill_hash: session.skill_hash,
      skill_updated: false,
      error: null,
      revision: this.revision,
      activity: this.activity,
      activity_summary: {
        actions: this.activity.length,
        checks: this.checks.length,
        duration_ms: Date.now() - this.startedAtMs,
      },
      created_at: now,
      ended_at: now,
    });
    session.running = false;
    session.updated_at = now;
    this.owner.endTurn(this);
    await this.emit("turn_completed", {
      status: options.status,
      outcome,
      stop_reason: stopReason,
      message_id: this.messageId,
      revision: this.revision,
      usage: { input: 1200, output: 800, cache_read: 0, cache_write: 0, summary: null },
    });
  }
}

// ── The mock ────────────────────────────────────────────────────────────────────

function json(route: Route, status: number, body: unknown): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: status === 204 ? "" : JSON.stringify(body),
  });
}

export class WorkflowBuilderMock {
  /** Every request the app made below `/api/workflow-builder`, in order. */
  readonly requests: RecordedBuilderRequest[] = [];
  /** Every message the app POSTed, in order. */
  readonly messages: SentMessage[] = [];
  /** Every `POST .../link` body. */
  readonly links: Array<{ sessionId: string; workflowId: string }> = [];
  readonly sessions = new Map<string, MockSession>();

  private counter = 0;
  private busyOnNextMessage = false;
  private activeTurn: ScriptedTurn | null = null;
  private readonly queue: ScriptedTurn[] = [];
  private waiters: Array<(turn: ScriptedTurn) => void> = [];

  constructor(private readonly page: Page) {}

  async install(): Promise<void> {
    await this.page.addInitScript(installStreamStub);
    await this.page.exposeFunction("__wbSnapshot", (sessionId: string) =>
      this.snapshotFrame(sessionId),
    );
    await this.page.route("**/api/workflow-builder/**", (route) => this.handle(route));
  }

  // ── Control surface for specs ───────────────────────────────────────────────────

  /** Resolves with the next turn the app starts (a message was POSTed and accepted). */
  nextTurn(timeoutMs = 15_000): Promise<ScriptedTurn> {
    const ready = this.queue.shift();
    if (ready) return Promise.resolve(ready);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`No builder message was sent within ${timeoutMs} ms`)),
        timeoutMs,
      );
      this.waiters.push((turn) => {
        clearTimeout(timer);
        resolve(turn);
      });
    });
  }

  /** The next `POST .../messages` answers 503 `host_capacity_exhausted`, once. */
  rejectNextMessageWithBusy(): void {
    this.busyOnNextMessage = true;
  }

  requireSession(sessionId: string): MockSession {
    const session = this.sessions.get(sessionId);
    if (!session) throw new Error(`Unknown mock builder session ${sessionId}`);
    return session;
  }

  /** Called by a turn when it completes. */
  endTurn(turn: ScriptedTurn): void {
    if (this.activeTurn === turn) this.activeTurn = null;
  }

  /** Publish one event to every open Session_Stream connection. */
  async publish(type: string, data: JsonObject): Promise<void> {
    await expect
      .poll(() => this.page.evaluate(hasOpenConnection), {
        message: "a builder Session_Stream connection should be open",
        timeout: 10_000,
      })
      .toBe(true);
    await this.page.evaluate(writeFrame, frame(type, data));
  }

  // ── Stream snapshot ─────────────────────────────────────────────────────────────

  /** The first frame of every connection (`BuilderEvent` `snapshot`). */
  private snapshotFrame(sessionId: string): string {
    const session = this.sessions.get(sessionId);
    const turn = this.activeTurn?.sessionId === sessionId ? this.activeTurn : null;
    const last = session?.messages[session.messages.length - 1];
    return frame("snapshot", {
      ts: new Date().toISOString(),
      state: turn ? "running" : "idle",
      running_turn: turn ? turn.snapshot() : null,
      latest_message_id: last?.id ?? null,
      latest_revision: session?.latest_draft?.revision ?? null,
      latest_unproposed_revision: null,
    });
  }

  // ── REST ────────────────────────────────────────────────────────────────────────

  private async handle(route: Route): Promise<void> {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname.replace(/^.*\/api\/workflow-builder/, "");
    let body: unknown;
    try {
      body = request.postDataJSON();
    } catch {
      body = undefined;
    }
    this.requests.push({ method, path, body });
    const input = (body ?? {}) as JsonObject;

    if (method === "GET" && path === "/models") {
      return json(route, 200, {
        models: E2E_MODELS,
        default_model_id: E2E_DEFAULT_MODEL_ID,
        default_efforts: { [E2E_MODELS[0].id]: E2E_DEFAULT_EFFORT, [E2E_MODELS[1].id]: null },
      });
    }
    if (path === "/sessions" && method === "POST") return this.createSession(route, input);
    if (path === "/sessions" && method === "GET") {
      const items = [...this.sessions.values()].map((s) => summaryOf(s));
      return json(route, 200, { items, next_cursor: null });
    }

    const match = /^\/sessions\/([^/]+)(?:\/(.*))?$/.exec(path);
    const session = match ? this.sessions.get(decodeURIComponent(match[1])) : undefined;
    if (!match || !session) return json(route, 404, { detail: "Session not found" });
    const rest = match[2] ?? "";

    if (rest === "" && method === "GET") return json(route, 200, this.detailOf(session));
    if (rest === "" && method === "DELETE") {
      this.sessions.delete(session.id);
      return json(route, 204, null);
    }
    if (rest === "messages" && method === "POST") return this.acceptMessage(route, session, input);
    if (rest === "link" && method === "POST") {
      const workflowId = String(input.workflow_id ?? "");
      session.workflow_id = workflowId;
      this.links.push({ sessionId: session.id, workflowId });
      return json(route, 200, summaryOf(session));
    }
    if (/^turns\/[^/]+\/cancel$/.test(rest) && method === "POST") return json(route, 202, {});
    return json(route, 404, { detail: `Not mocked: ${method} ${path}` });
  }

  private detailOf(session: MockSession): MockSession {
    const turn = this.activeTurn?.sessionId === session.id ? this.activeTurn : null;
    return { ...session, running: turn !== null, running_turn: turn ? turn.snapshot() : null };
  }

  private async createSession(route: Route, input: JsonObject): Promise<void> {
    const now = new Date().toISOString();
    const id = `sess-e2e-${this.sessions.size + 1}`;
    const session: MockSession = {
      id,
      title: "Untitled",
      mode: input.mode === "edit" ? "edit" : "create",
      workflow_id: typeof input.workflow_id === "string" ? input.workflow_id : null,
      model_id: String(input.model_id ?? E2E_DEFAULT_MODEL_ID),
      effort: typeof input.effort === "string" ? input.effort : null,
      running: false,
      created_at: now,
      updated_at: now,
      target_trust: "user",
      skill_hash: "e2e-skill-hash",
      messages: [],
      latest_draft: null,
      latest_unproposed: null,
      running_turn: null,
      linked_row_changed: false,
    };
    this.sessions.set(id, session);
    return json(route, 201, session);
  }

  private async acceptMessage(route: Route, session: MockSession, input: JsonObject): Promise<void> {
    if (this.busyOnNextMessage) {
      this.busyOnNextMessage = false;
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        headers: { "Retry-After": "90" },
        body: JSON.stringify(CAPACITY_REJECTION),
      });
    }
    if (this.activeTurn?.sessionId === session.id) {
      return json(route, 409, { detail: "A reply is already being written." });
    }

    this.counter += 1;
    const n = this.counter;
    const content = String(input.content ?? "");
    const now = new Date().toISOString();
    const last = session.messages[session.messages.length - 1];
    const turnId = `turn-e2e-${n}`;
    const userMessageId = `msg-user-${n}`;
    const assistantMessageId = `msg-assistant-${n}`;

    this.messages.push({
      sessionId: session.id,
      content,
      model_id: String(input.model_id ?? ""),
      effort: typeof input.effort === "string" ? input.effort : null,
      canvas_state: (input.canvas_state ?? {}) as JsonObject,
      client_message_id: String(input.client_message_id ?? ""),
    });
    session.messages.push({
      id: userMessageId,
      seq: (last?.seq ?? 0) + 1,
      role: "user",
      turn_id: turnId,
      reply_to_message_id: null,
      status: "accepted",
      outcome: null,
      stop_reason: null,
      content,
      thinking: null,
      model_id: String(input.model_id ?? session.model_id),
      effort: typeof input.effort === "string" ? input.effort : null,
      skill_hash: null,
      skill_updated: false,
      error: null,
      revision: null,
      activity: [],
      activity_summary: null,
      created_at: now,
      ended_at: null,
    });
    if (session.title === "Untitled") session.title = content.split("\n")[0].slice(0, 60);
    session.running = true;
    session.updated_at = now;

    const turn = new ScriptedTurn(this, session.id, turnId, assistantMessageId, userMessageId);
    this.activeTurn = turn;
    const waiter = this.waiters.shift();
    if (waiter) waiter(turn);
    else this.queue.push(turn);

    return json(route, 202, { turn_id: turnId, message_id: assistantMessageId, replayed: false });
  }
}

function summaryOf(session: MockSession): JsonObject {
  return {
    id: session.id,
    title: session.title,
    mode: session.mode,
    workflow_id: session.workflow_id,
    model_id: session.model_id,
    effort: session.effort,
    running: session.running,
    created_at: session.created_at,
    updated_at: session.updated_at,
  };
}

/**
 * Install the builder backend on a page. Call it AFTER the `test` fixtures are up
 * (inside the test body or a `beforeEach`) and before the first navigation, so its
 * routes win over the `mockApi` catch-all and the stream stub is in place when the
 * app mounts.
 */
export async function installWorkflowBuilderMocks(page: Page): Promise<WorkflowBuilderMock> {
  const mock = new WorkflowBuilderMock(page);
  await mock.install();
  return mock;
}
