/**
 * Mock-SSE transport driver for the Flowin E2E suite (mocked mode).
 *
 * Models the Phase-29 SSE down-channel ADDITIVELY (LOCK-B): it intercepts
 * `GET /api/runs/{id}/events/stream` with Playwright `page.route` and serves an
 * `text/event-stream` body built from a durable frame tail — NO backend. It is a
 * pure ADDITION beside `mockWs.ts` (the WS route path is untouched): the SSE
 * frames it emits ride the SAME monotonic seq/event_id space as every MockWs
 * frame, so the two interleave deterministically on ONE sequence
 * (MOCKWS-CHAT-DRIVER-CONTRACT §1/§5).
 *
 * Wire model (mirrors the WS envelope, projected onto SSE):
 *   - `id: {seq}`         → the SSE stream id line == the shared `seq` cursor.
 *                           A consumer echoes it back as `Last-Event-ID` on
 *                           reconnect → replay-from-cursor.
 *   - `event: {type}`     → the frame's event-type discriminator.
 *   - `data: {json}`      → the payload, carrying `event_id` (dedup key) + `seq`
 *                           (resume cursor) exactly as the WS `data` envelope.
 *
 * Replay / drop / reattach:
 *   - `handle()` honors the request's `Last-Event-ID` header — it serves only the
 *     frames with `seq` strictly greater than that cursor (full tail when absent).
 *   - `drop()` marks the transport dropped; the next attach (a fresh fetch /
 *     EventSource reconnect carrying `Last-Event-ID`) resumes from the cursor.
 *
 * The driver shares the caller's `SeqSource` (a MockWs instance) so it never
 * introduces a second seq counter or a second event_id space (LOCK-B).
 */
import type { Page, Route } from "@playwright/test";
import { nextEventId, type SeqSource } from "./mockWs";

/** GET /api/runs/{id}/events/stream — the Phase-29 SSE down-channel (any host). */
export const SSE_URL_RE = /\/api\/runs\/[^/]+\/events\/stream(\?|$)/;

/** A frame on the durable tail — same shape the WS emit() produces under `data`. */
export interface SseFrame {
  type: string;
  data: Record<string, unknown>; // always carries event_id (string) + seq (number)
}

export class MockSse {
  private readonly seqSource: SeqSource;
  /** The durable tail — every frame emitted, in seq order (the replay source). */
  readonly frames: SseFrame[] = [];
  /** Number of times a consumer attached to the stream (reconnect counting). */
  connectionCount = 0;
  /** The `Last-Event-ID` cursor of the most recent attach (null = full tail). */
  lastAttachCursor: number | null = null;
  private dropped = false;

  constructor(seqSource: SeqSource) {
    this.seqSource = seqSource;
  }

  // ── low-level emit (enqueue onto the durable tail) ──────────────────────────
  /**
   * Enqueue a frame onto the tail on the SHARED seq/event_id space — the seq
   * comes from the caller's `SeqSource.nextSeq()` (the MockWs counter) and the
   * event_id from the shared `nextEventId()`. No second envelope, no second seq.
   */
  emit(type: string, payload: Record<string, unknown> = {}): SseFrame {
    const seq = this.seqSource.nextSeq();
    const frame: SseFrame = { type, data: { ...payload, event_id: nextEventId(), seq } };
    this.frames.push(frame);
    return frame;
  }

  // ── chat convenience (mirror the MockWs chat helpers onto the SSE tail) ──────
  chatMessage(opts: { messageId: string; text: string; attachments?: unknown[] }): SseFrame {
    return this.emit("chat_message", {
      message_id: opts.messageId,
      text: opts.text,
      attachments: opts.attachments ?? [],
    });
  }

  chatReply(opts: {
    cardKind: "clarify" | "gate" | "pipeline" | "deliverable" | "spec_revision";
    text: string;
    deepLink?: { target: string; nonce: string };
    messageId?: string;
  }): SseFrame {
    return this.emit("chat_reply", {
      message_id: opts.messageId,
      card_kind: opts.cardKind,
      text: opts.text,
      deep_link: opts.deepLink,
    });
  }

  /**
   * `stream_attached` handshake — `replayedThroughSeq` defaults to the current
   * shared seq (mirrors MockWs.streamAttached / reconnected()).
   */
  streamAttached(opts: { live: boolean; replayedThroughSeq?: number }): SseFrame {
    return this.emit("stream_attached", {
      live: opts.live,
      replayed_through_seq: opts.replayedThroughSeq ?? this.seqSource.currentSeq,
    });
  }

  // ── transport lifecycle ─────────────────────────────────────────────────────
  /** Simulate a server-side drop → the next attach must resume from the cursor. */
  drop(): void {
    this.dropped = true;
  }

  /** True while the transport is dropped (until the next attach re-establishes it). */
  get isDropped(): boolean {
    return this.dropped;
  }

  /** Frames with seq strictly greater than the cursor (replay-from-Last-Event-ID). */
  framesAfter(cursor: number | null): SseFrame[] {
    if (cursor == null) return [...this.frames];
    return this.frames.filter((f) => (f.data.seq as number) > cursor);
  }

  /** Serialize frames into an SSE `text/event-stream` body (id line == seq). */
  private serialize(frames: SseFrame[]): string {
    return frames
      .map((f) => `id: ${f.data.seq}\nevent: ${f.type}\ndata: ${JSON.stringify(f.data)}\n\n`)
      .join("");
  }

  /**
   * Playwright route handler for the SSE endpoint. Counts the attach, resets the
   * dropped flag, honors `Last-Event-ID` for replay-from-cursor, and fulfills the
   * event-stream body. ACAO is set so a cross-origin consumer fetch is not blocked.
   */
  async handle(route: Route): Promise<void> {
    this.connectionCount += 1;
    this.dropped = false;
    const headers = route.request().headers();
    const lastEventId = headers["last-event-id"];
    const cursor = lastEventId != null && lastEventId !== "" ? Number(lastEventId) : null;
    this.lastAttachCursor = cursor;
    const body = this.serialize(this.framesAfter(cursor));
    await route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
        "access-control-allow-origin": "*",
      },
      body,
    });
  }
}

/**
 * Install the mock-SSE transport on a page, sharing the caller's SeqSource (the
 * MockWs instance) so SSE + WS frames ride ONE monotonic seq/event_id space.
 * Register AFTER the mockApi `**​/api/**` route (in the spec body) so this more
 * specific stream route wins by Playwright's last-registered-first precedence.
 */
export async function installMockSse(page: Page, seqSource: SeqSource): Promise<MockSse> {
  const mock = new MockSse(seqSource);
  await page.route(SSE_URL_RE, (route) => mock.handle(route));
  return mock;
}
