/**
 * Mock-SSE transport driver for the Flowin E2E suite (mocked mode).
 *
 * SSE + REST is the SOLE run transport (44-06 hard cutoff): the app opens NO
 * WebSocket. This driver is the whole mocked harness for the run surface — it
 * replaces the retired WebSocket-route path with:
 *
 *   1. A mocked SSE DOWN-channel (`GET /api/runs/{id}/events/stream`) — served
 *      via Playwright `page.route` as a `text/event-stream` body built from a
 *      durable frame tail (NO backend, NO Bedrock). The full pipeline-emit helper
 *      surface (`start`/`agent_*`/`wave_*`/`questionnaire_ready`/`review_gate_*`/
 *      `pipeline_complete|failed|cancelled` + the chat helpers) enqueues onto this
 *      tail so a spec drives the mounted app deterministically.
 *   2. A REST UP-channel command mock — `page.route` handlers for the launch
 *      (`POST /api/runs`) and the per-run commands
 *      (`POST /api/runs/{id}/{answers,cancel,gate,revisions,messages}`). Each
 *      records the request body into `sent[]` (normalized to a `{ type, … }`
 *      shape mirroring the old WS client frames) so a spec asserts the up-channel
 *      via `waitForCommand(...)` (the heir of the old `waitForClientFrame`).
 *
 * Attach model (the SSE analogue of "the socket is open"): the app only streams a
 * run that the RunConnectionProvider knows is live — from the boot `GET /api/runs`
 * (non-terminal) query, or an imperative `attachRun` after a launch. A spec that
 * emits WITHOUT launching (e.g. `dashboard.goto()` then `mockSse.start(...)`) is
 * served by the LAZY attach: the first emit registers the run into the mock's
 * live-run registry (surfaced on `GET /api/runs`) and fires a page `online` event
 * so the provider re-queries and attaches the stream. The durable tail means a
 * frame emitted before the attach completes is still replayed on attach — no race.
 *
 * Wire model (mirrors the WS envelope projected onto SSE):
 *   - `id: {seq}`      → the SSE id line == the shared monotonic `seq` cursor.
 *   - `event: {type}`  → the frame's event-type discriminator.
 *   - `data: {json}`   → the payload, carrying `event_id` (dedup key) + `seq`
 *                        (resume cursor), exactly as `useRunStream` dispatches.
 *
 * Replay / drop / reattach:
 *   - `handleStream()` honors `Last-Event-ID` — it serves only frames with `seq`
 *     strictly greater than that cursor (full tail when absent). It LONG-POLLS an
 *     empty tail (holding the response open until a frame is emitted / the
 *     transport drops / a short timeout) so a live burst is delivered promptly
 *     without hammering the endpoint on the app's reconnect backoff.
 *   - `drop()` closes the current stream so the app reconnects from its cursor.
 *   - `expireJwt()` makes the next attach return 401 → the app clears the token
 *     and redirects to /login (the WS 4001-close heir).
 */
import type { Page, Route } from "@playwright/test";
import type { MockApi, RawRun } from "./mockApi";
import { makeRun } from "./mockApi";

/** GET /api/runs/{id}/events/stream — the SSE down-channel (any host). */
export const SSE_URL_RE = /\/api\/runs\/[^/]+\/events\/stream(\?|$)/;

/** The per-run command endpoints (POST up-channel). */
const COMMAND_RE = /\/api\/runs\/([^/]+)\/(answers|cancel|gate|revisions|messages)$/;

/** A frame on the durable tail — same shape the WS emit() produced under `data`. */
export interface SseFrame {
  type: string;
  data: Record<string, unknown>; // always carries event_id (string) + seq (number)
}

export interface AgentSeed {
  id: string;
  name: string;
  role: string;
  icon?: string;
  order?: number;
}

export interface TokenStats {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  estimatedCostUsd?: number;
}

/** A recorded up-channel command — the SSE/REST heir of the WS client frame. */
export type RecordedCommand = Record<string, unknown> & { type: string };

/** Minimal shared seq/event_id source — kept for back-compat callers. */
export interface SeqSource {
  nextSeq(): number;
  readonly currentSeq: number;
}

let GLOBAL_EVENT_ID = 0;
/** Monotonic event_id source (dedup key), globally unique across the suite. */
export function nextEventId(): string {
  GLOBAL_EVENT_ID += 1;
  return `evt-${GLOBAL_EVENT_ID}`;
}

// Hold an idle stream open (no frames past the cursor) essentially for the whole
// test rather than serving an empty body every few seconds — each empty serve
// closes the stream and forces the app's 1s-backoff reconnect (a "Reconnecting…"
// flicker + re-render churn that adds parallel-load latency/flakiness). Held far
// above the per-test timeout so an idle stream never self-cycles mid-test; a real
// frame / drop / expiry wakes it immediately (see wakeStreams).
const STREAM_LONGPOLL_MS = 120_000;

/** Frames that flip the run to a terminal (isRunning=false) React commit. The
 *  stream serves them in a SEPARATE response from any preceding frames so the
 *  app commits the live-run state (pipeline_start → isRunning=true, the
 *  pipeline_type/workflowType sync) BEFORE the terminal — mirroring the discrete
 *  frame-by-frame delivery of the retired WebSocket path (a single buffered SSE
 *  body would otherwise batch start+complete into ONE commit and skip the
 *  isRunning-gated sync). */
const TERMINAL_TYPES = new Set(["pipeline_complete", "pipeline_failed", "pipeline_cancelled"]);

export class MockSse implements SeqSource {
  private readonly page: Page;
  private readonly api: MockApi | null;

  private seq = 0;
  private runId = "run-e2e-1";

  /** The durable tail — every frame emitted, in seq order (the replay source). */
  readonly frames: SseFrame[] = [];
  /** Number of times a consumer attached to the stream (reconnect counting). */
  connectionCount = 0;
  /** The `Last-Event-ID` cursor of the most recent attach (null = full tail). */
  lastAttachCursor: number | null = null;

  /** Every recorded up-channel command (launch / answers / cancel / gate / …). */
  readonly sent: RecordedCommand[] = [];

  private dropped = false;
  private authExpired = false;
  private attachActivated = false;
  private chatReplyCount = 0;

  /**
   * When false, `emit()` does NOT lazily register the run + nudge the provider to
   * attach (and `GET /api/runs` never surfaces the live run). Set false by the
   * transport-resilience specs that drive the stream by hand via a synthetic
   * `fetch` consumer and assert `connectionCount`/`lastAttachCursor` — there the
   * mounted app must NOT open a competing stream.
   */
  autoAttach = true;

  /** The mock's live-run registry — surfaced (merged) on GET /api/runs so the
   *  provider boot/reattach query finds the active run and streams it. */
  private liveRuns: RawRun[] = [];

  /** Pending long-poll wakeups (resolved on emit / drop / expire). */
  private streamWaiters: Array<() => void> = [];
  /** Pending command waiters (waitForCommand). */
  private commandWaiters: Array<{ match: (c: RecordedCommand) => boolean; resolve: (c: RecordedCommand) => void }> = [];
  /** Resolvers for `ready()` (first attach). */
  private readyResolvers: Array<() => void> = [];
  private everAttached = false;

  constructor(page: Page, api: MockApi | null = null) {
    this.page = page;
    this.api = api;
  }

  // ── identity / seq ──────────────────────────────────────────────────────────
  get currentRunId() { return this.runId; }
  setRunId(id: string) { this.runId = id; }
  get currentSeq(): number { return this.seq; }
  nextSeq(): number { this.seq += 1; return this.seq; }

  // ── low-level emit (enqueue onto the durable tail) ──────────────────────────
  /** Emit a frame with payload nested under `data` (+ auto event_id/seq). Lazily
   *  ensures the run's SSE stream is attached so the mounted app receives it. */
  emit(type: string, data: Record<string, unknown> = {}): SseFrame {
    const seq = this.nextSeq();
    const frame: SseFrame = { type, data: { ...data, event_id: nextEventId(), seq } };
    this.frames.push(frame);
    this.ensureAttached();
    this.wakeStreams();
    return frame;
  }

  /** Emit a legacy `stream` frame (top-level chunk/section). */
  emitStream(chunk: string, section?: string): SseFrame {
    const seq = this.nextSeq();
    const frame: SseFrame = { type: "stream", data: { event_id: nextEventId(), seq } };
    (frame as unknown as Record<string, unknown>).chunk = chunk;
    if (section) (frame as unknown as Record<string, unknown>).section = section;
    this.frames.push(frame);
    this.ensureAttached();
    this.wakeStreams();
    return frame;
  }

  // ── high-level pipeline event helpers (parity with the retired MockWs) ───────
  /** pipeline_start — seeds the agent cards (each idle). */
  start(agents: AgentSeed[], opts: { pipelineType?: string; runId?: string; createdAt?: string } = {}) {
    if (opts.runId) this.runId = opts.runId;
    this.emit("pipeline_start", {
      pipeline_run_id: this.runId,
      pipeline_type: opts.pipelineType ?? "user_stories",
      created_at: opts.createdAt,
      agents: agents.map((a, i) => ({ id: a.id, name: a.name, role: a.role, icon: a.icon ?? "🤖", order: a.order ?? i })),
    });
  }

  plannerStart() { this.emit("planner_start", { pipeline_run_id: this.runId }); }
  plannerComplete(intent = "Build the requested output", gate: "PROCEED" | "CLARIFY_REQUIRED" = "PROCEED") {
    this.emit("planner_complete", { planning_context: { inferred_intent: intent }, execution_gate: gate });
  }

  agentStart(id: string) { this.emit("agent_start", { agent_id: id }); }
  agentThinking(id: string, thinking: string) { this.emit("agent_thinking", { agent_id: id, thinking }); }
  agentChunk(id: string, chunk: string) { this.emit("agent_chunk", { agent_id: id, chunk }); }
  agentComplete(id: string, t: TokenStats & { duration?: number } = {}) {
    this.emit("agent_complete", {
      agent_id: id,
      input_tokens: t.inputTokens ?? 1200,
      output_tokens: t.outputTokens ?? 800,
      total_tokens: t.totalTokens ?? (t.inputTokens ?? 1200) + (t.outputTokens ?? 800),
      estimated_cost_usd: t.estimatedCostUsd ?? 0.004,
      duration: t.duration,
    });
  }
  agentError(id: string, error = "The model rejected this request.") { this.emit("agent_error", { agent_id: id, error }); }

  // clarify / gates
  questionnaireReady(questions: Array<{ id: string; text: string; options?: string[]; answerType?: string }>) {
    this.emit("questionnaire_ready", {
      pipeline_run_id: this.runId,
      questions: questions.map((q) => ({ question_id: q.id, question_text: q.text, options: q.options, answer_type: q.answerType })),
    });
  }
  questionnaireComplete() { this.emit("questionnaire_complete", {}); }
  reviewGateReady(opts: { gateKey: string; agentId: string; agentName: string; output: string }) {
    this.emit("review_gate_ready", { gate_key: opts.gateKey, agent_id: opts.agentId, agent_name: opts.agentName, output: opts.output, pipeline_run_id: this.runId });
  }
  reviewGateApproved() { this.emit("review_gate_approved", {}); }

  // waves / fan-out
  waveStarted(waveIndex: number, step: string, taskIds: string[] = []) { this.emit("wave_started", { wave_index: waveIndex, step, task_ids: taskIds }); }
  waveCompleted(waveIndex: number, step: string) { this.emit("wave_completed", { wave_index: waveIndex, step }); }
  waveFailed(waveIndex: number, step: string) { this.emit("wave_failed", { wave_index: waveIndex, step }); }
  subagentSpawned(waveIndex: number, step: string, agent: string, worker: number, status = "running") { this.emit("subagent_spawned", { wave_index: waveIndex, step, agent, worker, status }); }
  subagentResult(waveIndex: number, step: string, agent: string, worker: number, status = "completed") { this.emit("subagent_result", { wave_index: waveIndex, step, agent, worker, status }); }

  // terminal
  complete(opts: {
    pipelineType: string;
    finalOutput?: string;
    deliverableMimetype?: string;
    deliverableFilename?: string;
    deliverableVersion?: number;
    status?: "degraded";
    agentsFailed?: string[];
    totalDuration?: number;
  } & TokenStats) {
    this.emit("pipeline_complete", {
      pipeline_type: opts.pipelineType,
      pipeline_run_id: this.runId,
      final_output: opts.finalOutput ?? "",
      total_duration: opts.totalDuration ?? 31.4,
      status: opts.status,
      agents_failed: opts.agentsFailed,
      total_input_tokens: opts.inputTokens ?? 5000,
      total_output_tokens: opts.outputTokens ?? 3000,
      total_tokens: opts.totalTokens ?? 8000,
      estimated_cost_usd: opts.estimatedCostUsd ?? 0.042,
      model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
      deliverable_mimetype: opts.deliverableMimetype,
      deliverable_filename: opts.deliverableFilename,
      deliverable_version: opts.deliverableVersion,
    });
  }
  failed(opts: { agentsFailed?: string[]; error?: string; totalDuration?: number } = {}) {
    this.emit("pipeline_failed", {
      pipeline_type: "user_stories",
      pipeline_run_id: this.runId,
      total_duration: opts.totalDuration ?? 5.0,
      agents_completed: 0,
      agents_failed: opts.agentsFailed ?? [],
      error: opts.error ?? "Pipeline failed",
    });
  }
  cancelled(opts: { duration?: number } = {}) { this.emit("pipeline_cancelled", { pipeline_run_id: this.runId, duration: opts.duration ?? 8.0 }); }

  /** `pipeline_reconnected` — the durable-replay verdict. Retained (the reducer
   *  still handles it) so the reconnect specs can drive live/terminal resolution. */
  reconnected(opts: { live: boolean; status?: string | null }) {
    this.emit("pipeline_reconnected", { pipeline_run_id: this.runId, live: opts.live, status: opts.status ?? null, replayed_through_seq: this.seq });
  }

  // ── chat helpers ─────────────────────────────────────────────────────────────
  chatMessage(opts: { messageId: string; text: string; attachments?: unknown[] }): SseFrame {
    return this.emit("chat_message", {
      message_id: opts.messageId,
      text: opts.text,
      attachments: opts.attachments ?? [],
      run_id: this.runId,
      thread_id: this.runId,
    });
  }

  chatNarration(text: string, messageId?: string): SseFrame {
    return this.emit("chat_reply", {
      message_id: messageId ?? `narr-${(this.chatReplyCount += 1)}`,
      text,
      run_id: this.runId,
      thread_id: this.runId,
    });
  }

  chatReply(opts: {
    cardKind: "clarify" | "gate" | "pipeline" | "deliverable" | "spec_revision";
    text: string;
    deepLink?: { target: string; nonce: string };
    messageId?: string;
  }): SseFrame {
    return this.emit("chat_reply", {
      message_id: opts.messageId ?? `reply-${(this.chatReplyCount += 1)}`,
      card_kind: opts.cardKind,
      text: opts.text,
      deep_link: opts.deepLink,
      run_id: this.runId,
      thread_id: this.runId,
    });
  }

  streamAttached(opts: { live: boolean; replayedThroughSeq?: number }): SseFrame {
    return this.emit("stream_attached", {
      live: opts.live,
      replayed_through_seq: opts.replayedThroughSeq ?? this.seq,
      run_id: this.runId,
      thread_id: this.runId,
    });
  }

  // ── up-channel command capture (heir of MockWs.sent / waitForClientFrame) ────
  /** All recorded commands of a given `type`. */
  framesOfType(type: string): RecordedCommand[] {
    return this.sent.filter((c) => c.type === type);
  }

  /** Wait for the app to send a REST command matching `type` (or a predicate).
   *  The SSE/REST heir of the old `waitForClientFrame`. */
  waitForCommand(typeOrPredicate: string | ((c: RecordedCommand) => boolean), timeoutMs = 10000): Promise<RecordedCommand> {
    const match = typeof typeOrPredicate === "string" ? (c: RecordedCommand) => c.type === typeOrPredicate : typeOrPredicate;
    const already = this.sent.find(match);
    if (already) return Promise.resolve(already);
    return new Promise((resolve, reject) => {
      const t = setTimeout(
        () => reject(new Error(`Timed out waiting for command ${String(typeOrPredicate)}; got: ${this.sent.map((c) => c.type).join(", ")}`)),
        timeoutMs,
      );
      this.commandWaiters.push({ match, resolve: (c) => { clearTimeout(t); resolve(c); } });
    });
  }

  /** Back-compat alias — the specs' historical up-channel accessor name. */
  waitForClientFrame(typeOrPredicate: string | ((c: RecordedCommand) => boolean), timeoutMs = 10000): Promise<RecordedCommand> {
    return this.waitForCommand(typeOrPredicate, timeoutMs);
  }

  /** Wait for a chat command (default: a message-shaped up-channel command). */
  waitForChatCommand(predicate?: (c: RecordedCommand) => boolean, timeoutMs = 10000): Promise<RecordedCommand> {
    const match =
      predicate ??
      ((c: RecordedCommand) =>
        c.type === "user_message" || c.type === "chat_command" || typeof c.message_id === "string");
    return this.waitForCommand(match, timeoutMs);
  }

  private recordCommand(cmd: RecordedCommand) {
    this.sent.push(cmd);
    this.commandWaiters = this.commandWaiters.filter((w) => {
      if (w.match(cmd)) { w.resolve(cmd); return false; }
      return true;
    });
  }

  // ── transport lifecycle ─────────────────────────────────────────────────────
  /** Resolves once the app has attached the run's SSE stream at least once. */
  ready(): Promise<void> {
    if (this.everAttached) return Promise.resolve();
    return new Promise((resolve) => this.readyResolvers.push(resolve));
  }

  /** Simulate a server-side drop → close the open stream so the app reconnects. */
  drop(): void {
    this.dropped = true;
    this.wakeStreams();
  }

  get isDropped(): boolean { return this.dropped; }

  /** Simulate JWT expiry → the next attach 401s (WS 4001-close heir). */
  expireJwt(): void {
    this.authExpired = true;
    this.wakeStreams();
  }

  /** Frames with seq strictly greater than the cursor (replay-from-Last-Event-ID). */
  framesAfter(cursor: number | null): SseFrame[] {
    if (cursor == null) return [...this.frames];
    return this.frames.filter((f) => (f.data.seq as number) > cursor);
  }

  // ── internal: lazy attach + long-poll plumbing ───────────────────────────────
  private wakeStreams() {
    const w = this.streamWaiters;
    this.streamWaiters = [];
    w.forEach((r) => r());
  }

  /** Register the run as live + nudge the provider to attach its SSE stream. */
  private ensureAttached() {
    if (!this.autoAttach || this.attachActivated) return;
    this.attachActivated = true;
    this.liveRuns = [makeRun({ id: this.runId, status: "running", type: "user_stories" }) as unknown as RawRun];
    // Nudge RunConnectionProvider.refreshLiveRuns() so it re-queries GET /api/runs
    // and attaches the now-live run. Fire-and-forget: the durable tail means any
    // frame already emitted is replayed on attach (no race).
    this.page
      .evaluate(() => window.dispatchEvent(new Event("online")))
      .catch(() => {});
  }

  private serialize(frames: SseFrame[]): string {
    return frames
      .map((f) => {
        const extras: Record<string, unknown> = {};
        const top = f as unknown as Record<string, unknown>;
        if (top.chunk !== undefined) extras.chunk = top.chunk;
        if (top.section !== undefined) extras.section = top.section;
        const dataObj = { ...f.data, ...extras };
        return `id: ${f.data.seq}\nevent: ${f.type}\ndata: ${JSON.stringify(dataObj)}\n\n`;
      })
      .join("");
  }

  // ── route dispatch (registered as a single `**​/api/runs**` handler) ──────────
  async route(route: Route): Promise<void> {
    const req = route.request();
    const method = req.method();
    const path = new URL(req.url()).pathname;

    if (method === "GET" && SSE_URL_RE.test(path)) return this.handleStream(route);

    if (method === "POST") {
      if (path.endsWith("/api/runs")) return this.handleLaunch(route);
      const m = path.match(COMMAND_RE);
      if (m) return this.handleCommand(route, m[1], m[2]);
    }

    if (method === "GET" && path.endsWith("/api/runs")) return this.handleRunList(route);

    // Everything else under /api/runs (family / summary / artifacts / detail …)
    // is the REST backend's job.
    return route.fallback();
  }

  /** GET /api/runs — merge the live-run registry on top of the REST backend list
   *  so the provider's boot/reattach query finds the active run and streams it. */
  private async handleRunList(route: Route): Promise<void> {
    const base = this.api ? this.api.runs : [];
    const merged = [...this.liveRuns, ...base];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(merged) });
  }

  /** POST /api/runs — record the launch command + return the created run_id. */
  private async handleLaunch(route: Route): Promise<void> {
    let body: Record<string, unknown> = {};
    try { body = (route.request().postDataJSON?.() as Record<string, unknown>) ?? {}; } catch { /* non-json */ }
    const type = typeof body.type === "string" ? (body.type as string) : "run_pipeline";
    this.recordCommand({ ...body, type });
    // A launched run becomes live (so a reload reattaches it).
    this.attachActivated = true;
    this.liveRuns = [makeRun({ id: this.runId, status: "running", type: "user_stories" }) as unknown as RawRun];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ run_id: this.runId }) });
  }

  /** POST /api/runs/{id}/{answers,cancel,gate,revisions,messages}. */
  private async handleCommand(route: Route, runId: string, kind: string): Promise<void> {
    let body: Record<string, unknown> = {};
    try { body = (route.request().postDataJSON?.() as Record<string, unknown>) ?? {}; } catch { /* non-json */ }

    // The run id lives in the URL path (the REST up-channel), not the body — thread
    // it onto the recorded command as BOTH `run_id` and `pipeline_run_id` so specs
    // asserting either field (the WS frames carried `pipeline_run_id`) still bind.
    const ids = { run_id: runId, pipeline_run_id: runId };
    let cmd: RecordedCommand;
    let resBody: unknown = { ok: true };
    switch (kind) {
      case "messages":
        cmd = { ...body, ...ids, type: "user_message" };
        break;
      case "cancel":
        cmd = { ...body, ...ids, type: "cancel_pipeline" };
        resBody = { ok: true, run_id: runId, cancelled: true };
        break;
      case "gate":
        cmd = { ...body, ...ids, type: "approve_review" };
        resBody = { ok: true, action: body.action ?? "approve", gate_key: body.gate_key ?? "" };
        break;
      case "answers":
        cmd = { ...body, ...ids, type: "submit_questionnaire" };
        resBody = { ok: true, run_id: runId, count: Array.isArray(body.responses) ? body.responses.length : 0 };
        break;
      case "revisions":
        cmd = { ...body, ...ids, type: "run_revision", parent_run_id: runId };
        resBody = { run_id: this.runId };
        break;
      default:
        cmd = { ...body, ...ids, type: kind };
    }
    this.recordCommand(cmd);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(resBody) });
  }

  /**
   * The SSE stream handler. Honors `Last-Event-ID`, LONG-POLLS an empty tail (so a
   * live burst is served promptly), and 401s once `expireJwt()` has fired.
   */
  private async handleStream(route: Route): Promise<void> {
    this.connectionCount += 1;
    if (!this.everAttached) {
      this.everAttached = true;
      const rs = this.readyResolvers;
      this.readyResolvers = [];
      rs.forEach((r) => r());
    }
    this.dropped = false;

    if (this.authExpired) {
      try {
        await route.fulfill({ status: 401, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ detail: "token expired" }) });
      } catch { /* aborted */ }
      return;
    }

    const headers = route.request().headers();
    const lastEventId = headers["last-event-id"];
    const cursor = lastEventId != null && lastEventId !== "" ? Number(lastEventId) : null;
    this.lastAttachCursor = cursor;

    // Long-poll: if nothing new is on the tail, hold the response open until a
    // frame is emitted / the transport drops / a short timeout elapses.
    if (this.framesAfter(cursor).length === 0) {
      await new Promise<void>((resolve) => {
        const t = setTimeout(resolve, STREAM_LONGPOLL_MS);
        this.streamWaiters.push(() => { clearTimeout(t); resolve(); });
      });
    }

    if (this.authExpired) {
      try {
        await route.fulfill({ status: 401, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ detail: "token expired" }) });
      } catch { /* aborted */ }
      return;
    }

    // Deliver in discrete React-commit batches: never ship a terminal frame in
    // the same response as preceding frames (the app must commit isRunning=true
    // + its pipeline_type sync first). If the first pending frame IS terminal,
    // ship it alone; otherwise ship everything up to (not including) it.
    let pending = this.framesAfter(cursor);
    const termIdx = pending.findIndex((f) => TERMINAL_TYPES.has(f.type));
    if (termIdx > 0) pending = pending.slice(0, termIdx);
    else if (termIdx === 0) pending = pending.slice(0, 1);

    const body = this.serialize(pending);
    try {
      await route.fulfill({
        status: 200,
        headers: {
          "content-type": "text/event-stream",
          "cache-control": "no-cache",
          "access-control-allow-origin": "*",
        },
        body,
      });
    } catch { /* the app aborted the fetch (reconnect) — safe to ignore */ }
  }
}

/**
 * Install the mock-SSE + REST-command harness on a page. Register AFTER the
 * mockApi `**​/api/**` route so this more specific `**​/api/runs**` handler wins by
 * Playwright's last-registered-first precedence; anything it does not own falls
 * back to mockApi via `route.fallback()`.
 */
export async function installMockSse(page: Page, api: MockApi | null = null): Promise<MockSse> {
  const mock = new MockSse(page, api);
  await page.route("**/api/runs**", (route) => mock.route(route));
  return mock;
}
