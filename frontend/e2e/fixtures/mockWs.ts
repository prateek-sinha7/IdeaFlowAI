/**
 * Mock WebSocket server for the Flowin E2E suite (mocked mode).
 *
 * Uses Playwright's page.routeWebSocket to intercept the app's
 * `ws://localhost:8000/ws/chat` connection in the browser — NO backend, NO
 * Bedrock. The controller lets a spec drive the inbound event stream
 * deterministically and assert the outbound frames the app sends.
 *
 * INBOUND FRAME CONTRACT (verified against dashboard/page.tsx + useWorkflow.ts):
 *   - Pipeline events (pipeline_start, agent_*, pipeline_complete/failed/
 *     cancelled, planner_*, gate_status, agent_input, tool_*, workflow_validated,
 *     task_progress, task_loop_progress, pipeline_reconnected) are dispatched as
 *     `handlePipelineMessage({ type, ...msg.data })` — so their fields live under
 *     `data`.
 *   - Wave events (wave_*, subagent_*) are read from `msg.data.{wave_index, step,
 *     task_ids, agent|agent_id, worker, status}`.
 *   - questionnaire_ready / review_gate_ready read `msg.data.*`.
 *   - `stream` reads TOP-LEVEL `msg.chunk` / `msg.section`.
 *   - Dedup + the resume cursor read `msg.data.event_id` (string) + `msg.data.seq`
 *     (number) at the TOP of the handler — so EVERY frame carries them under data.
 *
 * Therefore every emit wraps payload as { type, data: { ...payload, event_id, seq } }.
 */
import type { Page } from "@playwright/test";
import { WS_URL_RE } from "./constants";

// Playwright's WebSocketRoute (typed loosely to avoid version-coupling).
interface WSRoute {
  send(message: string): void;
  onMessage(handler: (message: string | Buffer) => void): void;
  onClose(handler: (code: number | undefined, reason: string | undefined) => void): void;
  close(options?: { code?: number; reason?: string }): void;
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

let GLOBAL_EVENT_ID = 0;

export class MockWs {
  private current: WSRoute | null = null;
  private seq = 0;
  private runId = "run-e2e-1";
  /** Every parsed frame the app sent (run_pipeline, ping, cancel_pipeline, …). */
  readonly sent: Array<Record<string, unknown>> = [];
  /** Number of times the app opened a socket (reconnect counting). */
  connectionCount = 0;
  private waiters: Array<{ match: (f: Record<string, unknown>) => boolean; resolve: (f: Record<string, unknown>) => void }> = [];
  private readyResolvers: Array<() => void> = [];
  private connected = false;

  /** Internal — bound by installMockWs when a connection opens. */
  _attach(ws: WSRoute) {
    this.current = ws;
    this.connectionCount += 1;
    this.connected = true;
    ws.onMessage((raw) => {
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(typeof raw === "string" ? raw : raw.toString());
      } catch {
        return;
      }
      this.sent.push(frame);
      this.waiters = this.waiters.filter((w) => {
        if (w.match(frame)) {
          w.resolve(frame);
          return false;
        }
        return true;
      });
    });
    ws.onClose(() => {
      if (this.current === ws) {
        this.current = null;
        this.connected = false;
      }
    });
    const rs = this.readyResolvers;
    this.readyResolvers = [];
    rs.forEach((r) => r());
  }

  /** Resolves once the app has opened the socket at least once. */
  ready(): Promise<void> {
    if (this.connected) return Promise.resolve();
    return new Promise((resolve) => this.readyResolvers.push(resolve));
  }

  /** Wait for the app to send a frame matching `type` (or a predicate). */
  waitForClientFrame(typeOrPredicate: string | ((f: Record<string, unknown>) => boolean), timeoutMs = 10000): Promise<Record<string, unknown>> {
    const match = typeof typeOrPredicate === "string" ? (f: Record<string, unknown>) => f.type === typeOrPredicate : typeOrPredicate;
    const already = this.sent.find(match);
    if (already) return Promise.resolve(already);
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error(`Timed out waiting for client frame ${String(typeOrPredicate)}; got: ${this.sent.map((f) => f.type).join(", ")}`)), timeoutMs);
      this.waiters.push({ match, resolve: (f) => { clearTimeout(t); resolve(f); } });
    });
  }

  /** All frames of a given type the app has sent so far. */
  framesOfType(type: string): Array<Record<string, unknown>> {
    return this.sent.filter((f) => f.type === type);
  }

  // ── low-level emit (server → page) ──────────────────────────────────────────
  private nextEventId() {
    GLOBAL_EVENT_ID += 1;
    return `evt-${GLOBAL_EVENT_ID}`;
  }

  /** Emit a frame with payload nested under `data` (+ auto event_id/seq). */
  emit(type: string, data: Record<string, unknown> = {}) {
    if (!this.current) throw new Error(`MockWs.emit(${type}) but no socket is open — await mockWs.ready() / waitForClientFrame('run_pipeline') first`);
    this.seq += 1;
    const frame = { type, data: { ...data, event_id: this.nextEventId(), seq: this.seq } };
    this.current.send(JSON.stringify(frame));
  }

  /** Emit a legacy `stream` frame (top-level chunk/section). */
  emitStream(chunk: string, section?: string) {
    if (!this.current) throw new Error("MockWs.emitStream but no socket is open");
    this.seq += 1;
    const frame: Record<string, unknown> = { type: "stream", chunk, data: { event_id: this.nextEventId(), seq: this.seq } };
    if (section) frame.section = section;
    this.current.send(JSON.stringify(frame));
  }

  /** Simulate a server-side drop → triggers the app's reconnect/backoff. */
  drop(code = 1006, reason = "dropped") {
    this.current?.close({ code, reason });
    this.connected = false;
    this.current = null;
  }

  /** Simulate JWT-expiry close (code 4001 → app clears token + redirects /login). */
  expireJwt() {
    this.current?.close({ code: 4001, reason: "expired" });
    this.connected = false;
    this.current = null;
  }

  // ── high-level pipeline event helpers ───────────────────────────────────────
  setRunId(id: string) { this.runId = id; }
  get currentRunId() { return this.runId; }

  /** pipeline_start — seeds the agent cards (each idle). Resets the seq cursor. */
  start(agents: AgentSeed[], opts: { pipelineType?: string; runId?: string } = {}) {
    if (opts.runId) this.runId = opts.runId;
    this.seq = 0;
    this.emit("pipeline_start", {
      pipeline_run_id: this.runId,
      pipeline_type: opts.pipelineType ?? "user_stories",
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
  agentComplete(id: string, t: TokenStats = {}) {
    this.emit("agent_complete", {
      agent_id: id,
      input_tokens: t.inputTokens ?? 1200,
      output_tokens: t.outputTokens ?? 800,
      total_tokens: t.totalTokens ?? (t.inputTokens ?? 1200) + (t.outputTokens ?? 800),
      estimated_cost_usd: t.estimatedCostUsd ?? 0.004,
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
  reconnected(opts: { live: boolean; status?: string | null }) {
    this.emit("pipeline_reconnected", { pipeline_run_id: this.runId, live: opts.live, status: opts.status ?? null, replayed_through_seq: this.seq });
  }
}

/** Install the mock WS server on a page. Call before navigation. */
export async function installMockWs(page: Page): Promise<MockWs> {
  const mock = new MockWs();
  await page.routeWebSocket(WS_URL_RE, (ws) => mock._attach(ws as unknown as WSRoute));
  return mock;
}
