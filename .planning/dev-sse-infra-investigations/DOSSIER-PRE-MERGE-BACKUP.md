# Dev-environment SSE + Infrastructure Issue Dossier — 2026-07-29

> **Scope.** 27 issues found while root-causing three reported AWS-only symptoms: bolder fonts, a
> recurring "Reconnecting…" banner, and run screens that show no live updates until you navigate
> away and back. Covers clusters **A** (SSE run transport), **B** (observability), **C** (delivery),
> **D** (separable defects), **E** (monitoring config). Clusters F (org/security decisions) and G
> (fonts) are deliberately excluded per instruction.
>
> **Branch under investigation:** `dev` @ `3429d2d9` (the commit deployed to dev — CodeBuild
> `velocityai-gitlab-runner-dev` succeeded 2026-07-29T16:27Z with that source version).
> **Environment:** account `577954642302`, `eu-central-1`, instance `velocityai-dev-app` /
> `i-092d5961f5aca87a6` / `63.181.129.187` / `https://63-181-129-187.nip.io`.
>
> **Evidence standard.** Every claim is tagged:
> - **[V]** — verified by direct observation: a file read, a command run, an AWS API response, or a
>   test executed. Where a number is quoted, it was measured.
> - **[I]** — inferred from evidence but not directly observed. Treated as a hypothesis, not a fact.
>
> **Line numbers** are as of `3429d2d9`. Re-confirm anchors before editing — the tree moves.
>
> **Nothing in this dossier has been fixed.** No repo file and no AWS resource was mutated during
> the investigation; the only on-box commands were read-only (`sha256sum`, `nginx -T | grep`,
> `systemctl status`, `journalctl`, `tail`, `id`, `getfacl`, `df`, `test -r`).

---

## Contents

- [Why this happened at all — the one structural cause](#why-this-happened-at-all)
- [Cluster A — SSE run transport (A1–A5)](#cluster-a--sse-run-transport)
- [Cluster B — Observability (B1–B6)](#cluster-b--observability)
- [Cluster C — Delivery (C1)](#cluster-c--delivery)
- [Cluster D — Separable defects (D1–D11)](#cluster-d--separable-defects)
- [Cluster E — Monitoring configuration (E1–E4)](#cluster-e--monitoring-configuration)
- [Appendix 1 — Measured baselines](#appendix-1--measured-baselines)
- [Appendix 2 — Environment facts](#appendix-2--environment-facts)

---

## Why this happened at all

Three independent facts combine to explain nearly every issue below, and none of them is a coding
mistake:

1. **The WebSocket→SSE cutover (Phase 44) moved the run event firehose to a different URL**, and the
   reverse proxy was never told. [V] `/ws/chat` was deleted from the backend on 2026-07-15; the SSE
   endpoint landed 2026-07-08; the dev instance was provisioned 2026-07-01. The nginx config running
   today was written **a week before the endpoint it is supposed to serve existed**.
2. **`infra/scripts/bootstrap-ec2.sh` runs once per instance, forever.** [V] So a host-config fix in
   the repo cannot reach a running box — which is why item 1 was never correctable by a normal
   deploy, and why the CloudWatch failure below has survived a month of deploys.
3. **The instance has had no working log or metric shipping since it was built.** [V] So every
   symptom had to be found by black-box probing from outside, and the internal evidence that would
   have named the cause on day one was never recorded anywhere.

The multi-client SSE defect (A2) is different in kind: it **predates** the cutover. The deleted
WebSocket drainer had the identical consume-once pattern on the same registry. It was dormant while
the frontend only ever opened one connection per run, and the cutover plus the per-run multi-attach
architecture made it reachable. [V]

---

## Cluster A — SSE run transport

**These five must ship as one change set.** A1 alone converts A2 from an intermittent corruption
into a consistent one, and A5 is the ceiling that A1 removes the brake from. Shipping them
separately produces a worse system at each intermediate step.

---

### A1 — The run event stream is rate-limited and rejected with HTTP 429

**Severity:** the reported symptom. Both the "Reconnecting…" banner and the dead run screen.
**Confidence:** [V] — reproduced live, reproduced in a real nginx, and the live config confirmed
byte-identical to the repo.

#### Symptom

A run screen shows a yellow "Reconnecting…" banner and stops advancing. Navigating to Home and back
into the run from Recents makes it work again. Intermittent, and worse when several people are using
the app at once. Never reproduces on a developer's machine.

#### Root cause

The SSE run stream is `GET /api/runs/{workflow_id}/events/stream` — `backend/app/api/run_stream.py`
declares `router = APIRouter(prefix="/api/runs")` at `:64` and the route at `:208`. [V] That URL
matches nginx's generic `location /api/` block, which is built for short REST calls:

```nginx
# infra/scripts/bootstrap-ec2.sh:822-830
location /api/ {
    limit_req zone=velocityai_api burst=20 nodelay;
    limit_req_status 429;
    proxy_pass         http://velocityai_backend;
    include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    proxy_buffering    off;
    proxy_request_buffering off;
    proxy_read_timeout 300s;
}
```

The zone is `limit_req_zone $binary_remote_addr zone=velocityai_api:10m rate=120r/m;`
(`bootstrap-ec2.sh:710`) — **two requests per second per client IP**, burst 20. [V]

Before the cutover the stream lived at `location /ws/chat` (`bootstrap-ec2.sh:843-856`), which has
**no rate limit at all** and `proxy_read_timeout 5400s`. [V] That block still exists and is now dead
config: the backend's only remaining WebSocket route is `/ws/handoff/{token}`
(`backend/app/api/websocket_handoff.py:80`). [V]

The frontend converts the 429 into the visible symptom. `frontend/src/hooks/useRunStream.ts:359-360`
treats **any** non-OK response as fatal:

```ts
if (!res.ok || !res.body) {
    throw new Error(`SSE stream failed with status ${res.status}`);
}
```

The `catch` at `:405-408` calls `scheduleReconnect()` (`:296-309`), which sets the phase to
`reconnecting` — surfaced as the banner via `frontend/src/app/dashboard/page.tsx:44` — and backs off
`1s → 2 → 4 → 8 → 16 → 30s`, capped by `MAX_RETRY_DELAY_MS = 30000` with the comment "never give
up" (`:98`). [V] Navigating away and back remounts the hook, resetting `retryCountRef` to zero, so a
fresh attach usually lands. That is exactly the workaround the team discovered.

#### Why it occurred

The rate limit is not a mistake — it is correct and valuable protection for REST endpoints, several
of which trigger a Bedrock call. The mistake is **an unstated assumption that every URL under
`/api/` is a short request**. That assumption was true when the block was written (2026-05-11) and
became false on 2026-07-08 when a URL representing a connection held open for the entire duration of
a run was added under the same prefix. Nothing in the system could detect the assumption breaking,
because the 429s were logged only to `/var/log/nginx/access.log`, which is not shipped anywhere
(see B1).

#### Measured proof

Against live dev, 30 concurrent unauthenticated `GET /api/auth/me`:

```
21 x 403      9 x 429
```

The 21/9 split is `burst=20` exactly. And the stream endpoint itself, with a valid JWT, under
concurrent `/api/` load — 3 trials:

```
trial 1 -> 200      trial 2 -> 429      trial 3 -> 429
```

Independently, a faithful local reproduction (nginx 1.24-alpine, every location from
`bootstrap-ec2.sh:761-914` verbatim, real zone values, `$loc` logged per location), 40 concurrent
requests to the stream path:

```
BEFORE:  21 x 200, 19 x 429     (all logged LOC=api-prefix)
AFTER:   40 x 200               (all logged LOC=sse-regex)
```

#### The fix

Add to `/etc/nginx/conf.d/velocityai-limits.conf` (written by `bootstrap-ec2.sh:706-716`):

```nginx
limit_conn_zone $binary_remote_addr zone=velocityai_stream:10m;
```

Add to the 443 server block, immediately before `location /api/ {`:

```nginx
location ~ ^/api/runs/[^/]+/events/stream/?$ {
    # No limit_req: a long-lived SSE stream is a concurrency phenomenon, not a
    # request-rate one. The shared velocityai_api zone (2r/s, burst 20) rejected
    # stream attaches whenever normal page traffic drained the bucket.
    # limit_conn is the correct shape. Under HTTP/2 each concurrent request counts
    # separately, which is the accounting we want. 64 is sized so a NAT'd office
    # sharing one egress IP cannot trip it.
    limit_conn         velocityai_stream 64;
    proxy_pass         http://velocityai_backend;
    include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    proxy_buffering    off;
    proxy_request_buffering off;
    proxy_cache        off;
    # sse-starlette pings every 15s (SSE_KEEPALIVE_PING_SECONDS), so 300s already
    # sufficed. 5400s is defence-in-depth if pings are ever disabled.
    proxy_read_timeout 5400s;
    proxy_send_timeout 5400s;   # no-op for a GET; kept for symmetry with /ws/chat.
}
```

Five details that are load-bearing, each with its reason:

1. **`limit_conn`, not nothing.** Removing all metering would leave an authenticated
   attach-churn amplifier: every attach runs two unbounded `read_events` queries (see A5). A
   `limit_conn 4` test against a real 20-second upstream produced exactly `4 x 200, 4 x 429` with
   the four admitted streams running to completion undisturbed. [V] **64** is chosen because
   per-IP is blunt behind corporate NAT — the whole team shares one key, and a user legitimately
   holds one stream per live run per tab. Do not pick a small number.
2. **`/?$` is not cosmetic.** A trailing slash misses the bare regex and falls back to the
   rate-limited block — measured. [V]
3. **The `include` is mandatory.** Omitting it drops `Host`, `X-Real-IP`, `X-Forwarded-*` and
   `proxy_http_version 1.1` (`bootstrap-ec2.sh:718-726`); without HTTP/1.1 upstream, chunked
   streaming breaks. [V]
4. **Do not set `limit_conn_status 429`.** Leave the default 503, so verification stays
   unambiguous: 429 means rate-limited (the bug), 503 means connection cap reached (working).
5. **Position is free but fragile.** This is currently the only regex location in the server
   block, and no prefix location uses `^~`, so it wins regardless of placement — proven by placing
   it *last*, after `/_next/static/`, where it still won. [V] Add a comment: if anyone later adds
   a regex location above it that also matches, that one wins.

**Explicitly do NOT extend this exemption to the other three streaming endpoints.** There are four
streaming responses in the backend [V]:

| Endpoint | File | Exempt? |
|---|---|---|
| `GET /api/runs/{id}/events/stream` | `run_stream.py:285` | **Yes** — this fix |
| `POST /api/runs/{id}/messages` (Concierge, conditionally streaming) | `run_commands.py:1414` | **No** |
| `POST /api/runs/user_message` (legacy free-chat) | `run_commands.py:2601` | **No** |
| `POST /api/prototype/run` (NDJSON, appears dead — no frontend caller) | `prototype_templates.py:287` | **No** |

The Concierge endpoint triggers a Bedrock LLM call per request; exempting it from `limit_req` hands
an authenticated attacker unbounded model spend, which is worse than the failure it prevents. And
none of them needs it: `sse-starlette` runs `_ping` as an **independent concurrent task**
(`sse_starlette/sse.py:255-271`, a `while self.active: await anyio.sleep(interval); send(...)` loop
at `:221-246`), so all three emit a comment frame every 15 seconds regardless of what the body
generator is doing — comfortably inside the existing 300s. `sse-starlette` also force-sets
`X-Accel-Buffering: no` on every response (`sse.py:140`). [V]

**Correction to an earlier belief:** the 300s timeout was never a contributing factor. Because the
ping task is independent, a write happens every 15 seconds even while the generator blocks on
`live_queue.get()` during a human review gate. `proxy_send_timeout` is likewise a no-op — it
governs nginx *writing a request* to the upstream, which never applies to a bodyless GET. [V]

#### Verification

- **Pre-flight:** confirm no config drift. `sha256sum /etc/nginx/sites-available/velocityai` on the
  box must equal the locally rendered template. **Measured 2026-07-29: identical**
  (`5f090af17801bcf6d11c7964f3fe80cc58bbe4ed5bb4a031d365875bc474083d`). [V] Render with:
  ```bash
  DOMAIN='63-181-129-187.nip.io' bash -c \
    '{ echo "cat <<EOF"; sed -n "732,915p" infra/scripts/bootstrap-ec2.sh; } | bash' > expected
  ```
- **Apply** with `nginx -t` gating before `systemctl reload`. If `nginx -t` fails, nothing happened:
  it parses the on-disk config in a throwaway process and the live master keeps its in-memory config
  until a *successful* reload. Downtime on a failed validation is zero.
- **Probe A — the stream must no longer 429.** 40 parallel requests; expect **401 only** (the route
  has `Depends(get_current_user)` at `:214`, so 401 proves nginx passed it through):
  ```bash
  seq 1 40 | xargs -P 40 -I{} curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 \
    "https://63-181-129-187.nip.io/api/runs/probe-{}/events/stream" | sort | uniq -c
  ```
- **Probe B — general `/api/` limiting must survive.** Wait ~30s for the bucket to refill, then 60
  parallel requests to `/api/_ratelimit_probe_{}`; expect a substantial count of 429.
- **The pair is the proof.** A alone could mean nginx is broken; B alone proves nothing about the
  stream. Run both from the same machine, since the zone keys on `$binary_remote_addr`.

---

### A2 — Two browsers watching one run split its event stream between them

**Severity:** silent data loss on the primary user-facing path. Pre-existing; A1 makes it
consistently reproducible instead of intermittent.
**Confidence:** [V] — reproduced three separate ways, including a test run through the production
endpoint that I executed myself.

#### Symptom

Open a running pipeline in two browser tabs. Each tab receives roughly **half** the events, and the
halves are disjoint. Concretely:

- Streamed agent text is permanently garbled or truncated in both tabs. `agent_chunk` frames are the
  overwhelming majority of traffic and have **no reconciliation path** — `agent_complete` carries
  `output_length`, not the output text (`engine.py:4087-4098`), so the chunks are the only source. [V]
- A missing `agent_start` means that agent's card never renders; a missing `agent_complete` means it
  spins forever.
- **`review_gate_ready` and `questionnaire_ready` go to exactly one tab.** The other shows a running
  pipeline with no questions and no Approve button.
- `task_progress` jumps ("Task 1 of 7" → "Task 3 of 7").

The damage is **symmetric**: opening the second tab corrupts the first tab too.

With three or more clients it is worse — one hangs forever at phase `live`, spinner running,
receiving nothing, until the user switches to it or reloads.

#### Root cause

`_PIPELINE_QUEUES` holds **one** `asyncio.Queue` per run id:

```python
# backend/app/api/run_engine.py:39
_PIPELINE_QUEUES: dict[str, asyncio.Queue] = {}
# :64-67
def _get_or_create_queue(pipeline_run_id: str) -> asyncio.Queue:
    if pipeline_run_id not in _PIPELINE_QUEUES:
        _PIPELINE_QUEUES[pipeline_run_id] = asyncio.Queue(maxsize=0)  # unbounded
    return _PIPELINE_QUEUES[pipeline_run_id]
```

The SSE endpoint attaches to that shared object (`run_stream.py:281`) and drains it with
`event = await live_queue.get()` (`:197`). **`asyncio.Queue.get()` is consume-once** — each item is
delivered to exactly one awaiting consumer. N concurrent clients therefore round-robin the events.

`run_stream.py:197` is the **only** consumer of `_PIPELINE_QUEUES` in production code. [V] Every
other reference is a producer obtaining the queue to put events into it (`run_commands.py:991`,
`:1204`, `:1775`, `:2383`, `:2084`, `:2433`; `engine.py:7781`, `:7802`; `kernel_services.py:386`) or
a membership test. So the entire defect, and the entire fix, live on the consumer side.

Termination is the second half of the problem: there is exactly **one** terminal event and **one**
`None` sentinel per run (`run_commands.py:2185`, engine twin at `engine.py:7823`). With N consumers
there are only two "closers", so N−2 generators park in `await live_queue.get()` on a queue nobody
will ever feed again. The disconnect check at `:195` runs *before* the `get()`, so a parked consumer
never re-checks it.

The module docstring encodes the false assumption verbatim, at `run_stream.py:13-14`:

> "the same queue the WS drainer attaches to, so an SSE client and a WS client observe the identical
> live stream."

They would observe **disjoint halves**.

**Durable replay cannot heal it.** This is the part that makes it data loss rather than a display
glitch. `Last-Event-ID` is a monotonic high-water mark and the replay query is strictly greater-than:

```python
# backend/agents/authz.py:324
RunEvent.seq > after_seq
```

and the client cursor only ever advances (`useRunStream.ts:255-263`; `dashboard/page.tsx:447`). Every
stolen event therefore sits **below** the cursor and is never replayed by anything. The two durable
re-fetches both pass a high-water cursor (`page.tsx:1381`, `useRunChat.ts:515`) so they return
nothing. The only full re-read is `page.tsx:1689`, gated on opening a *different* run — never the
one you are watching.

The terminal event does self-heal about a second late, because `pipeline_complete` carries the
highest seq and is therefore above the cursor. The body of the run does not.

#### Why it occurred

The queue was designed as a **point-to-point channel for one connection**, which is exactly what a
single WebSocket is. The registry name (`_PIPELINE_QUEUES`) and the LOCK-B constraint that
`websocket.py` must not be modified both pushed the SSE implementation toward reusing the existing
object read-only rather than reconsidering its cardinality. The assumption "one run has one viewer"
was never written down and never enforced, so nothing flagged it when the frontend gained a per-run
multi-attach architecture.

Two things then hid it for a month:

1. **A false-green test.** `frontend/e2e/tests/ts-sse-resilience.spec.ts:216`, titled *"multi-tab
   consumers ride ONE monotonic seq/event_id space"*, routes **one** mock driver to both tabs
   (`tab2.route(SSE_URL_RE, (route) => sse.route(route))`) and asserts both received `[1,2,3]`. The
   mock serves from a persistent frame log via `framesAfter(cursor)`
   (`frontend/e2e/fixtures/mockSse.ts:534-592`) — it models a durable replay, not a consume-once
   queue. It asserts the exact property that is false in production. [V] See D1.
2. **The rate limit.** A2 needs two *simultaneously alive* consumers. A1 was 429-ing the second
   attach, delaying it by up to thirty seconds. Not a reliable mask — the frontend retries and
   eventually lands — but enough to make the corruption sporadic.

A partial accidental mitigation also exists and is worth understanding, because it is **not** the
fix: `frontend/src/providers/RunConnectionProvider.tsx:270-295` (labelled "KAN-125 MULTI-TAB FIX",
logged as FIX-137) gates *auto*-attach on a per-tab `sessionStorage` key. That stops a cold second
tab attaching by itself. But the explicit path is wide open — `dashboard/page.tsx:1632` calls
`attachRun(fullRun.id)` when a non-terminal run is opened from History, and `attachRun`'s sticky
focus is unioned in regardless of tab ownership. **Opening a running run from History in a second
tab is the reproduction.**

**Age:** `git blame` attributes `run_stream.py` to `7020bf82` (2026-07-08, Phase 29-02), but the
deleted WebSocket drainer had the identical `await running_queue.get()` on the same registry
(`websocket.py:767` at `0c8ee539e~1`). The defect **predates SSE**; the cutover made it reachable. [V]

#### Measured proof

Three independent reproductions:

1. Driving the real `_iter_sse_frames` with two consumers on one queue:
   `TAB-A [4,6,8,10]` / `TAB-B [5,7,9,11]`, **overlap `[]`**. Three consumers:
   `stranded-forever consumers: ['TAB-A']`.
2. A second, independent agent: client A received events 0-4, client B received 5-9.
3. **A pytest driving the production `stream_run_events` endpoint, which I ran myself against
   `dev`:**
   ```
   FAILED test_two_concurrent_clients_observe_the_same_ordered_seq_set
          AssertionError: client A saw [1, 2, 4, 6, 8, 10]
   FAILED test_three_concurrent_clients_none_strands
          AssertionError: 1 of 3 client stream(s) never terminated
   2 failed
   ```
   With the design applied: `2 passed`.

#### The fix

A per-run subscriber registry plus **one pump task per run** that is the sole consumer of the shared
queue and re-publishes to every subscriber. The codebase already contains this pattern at
`backend/app/api/websocket_handoff.py:37-68` (`_SUBSCRIBERS: dict[str, list[asyncio.Queue]]` plus
`dispatch_event` looping `await q.put(event)`). That asymmetry — the handoff path has fan-out, the
run path does not — is the cleanest single proof of the defect. [V]

**In `backend/app/api/run_engine.py`,** beside the existing registries:

```python
_SUBSCRIBERS: dict[str, set[asyncio.Queue]] = {}
_PUMPS: dict[str, asyncio.Task] = {}
```

`_PUMPS` must hold a **strong** reference — asyncio keeps only weak references to tasks, so a pump
whose only reference was local would be garbage-collected mid-run.

New functions:

| Function | Contract |
|---|---|
| `_ensure_pump(run_id) -> None` | Idempotent. No-op if a live pump exists, if there is no source queue, or if `asyncio.get_running_loop()` raises (a synchronous test caller). |
| `_pump(run_id, source)` | `while True: e = await source.get(); if e is None: return; _publish(run_id, e)`. Re-raises `CancelledError`; logs anything else at `exception`. `finally: _close_run(run_id)`. |
| `_publish(run_id, event) -> None` | **Synchronous.** `put_nowait` to each subscriber over a `list(...)` snapshot; on `QueueFull`, evict. Hands the **same dict object** to every subscriber — never copy, never mutate. Safe: `_iter_sse_frames` only reads it (`run_stream.py:200-205`). |
| `_evict_subscriber(run_id, q)` | Remove from the set, drain with `get_nowait()` to make room, `put_nowait(None)`, log a warning naming the run. The drain is required because the queue is full by definition and the sentinel must not be what gets dropped. |
| `_close_run(run_id) -> None` | **Synchronous, idempotent.** `_PIPELINE_QUEUES.pop`, `_PUMPS.pop`, **then** sentinel every subscriber and clear the set. |
| `subscribe(run_id) -> asyncio.Queue \| None` | `None` when the run is not live; else a bounded queue added to the set, plus `_ensure_pump`. |
| `unsubscribe(run_id, q) -> None` | Discard; drop the empty set entry. |

Modify `_get_or_create_queue` to call `_ensure_pump` before returning — so all seven queue-creation
sites get a pump for free with no edits. Leave the source queue `maxsize=0` (see below).

**In `backend/app/api/run_stream.py`:** replace the `_PIPELINE_QUEUES` / `_get_or_create_queue`
import at `:62` with `subscribe` / `unsubscribe`, delete the attach at `:281`, and add a thin wrapper
generator whose **first statement** is `subscribe(run_id)`, which delegates to an unchanged
`_iter_sse_frames`, and which `unsubscribe`s in a `finally`. Pass the wrapper to
`EventSourceResponse`.

The subscribe must live *inside* the generator, not in the endpoint body: if the request aborts
before the response body starts, `aclose()` on a never-started async generator does not execute the
body, so an endpoint-body subscribe would leak with no matching `finally`.

Leaving `_iter_sse_frames` itself unchanged preserves every existing test that drives it with a
hand-built queue.

**In `backend/app/core/config.py`,** beside `SSE_KEEPALIVE_PING_SECONDS` (`:132`):

```python
SSE_SUBSCRIBER_QUEUE_MAXSIZE: int = 1000
```

##### Three non-obvious details, each proven with a negative control

**1. Subscribe strictly BEFORE the durable replay read.** The emission order stays as today (replay
→ `stream_attached` → gate re-arm → live drain); only *registration* moves earlier. The durable read
is a snapshot; any event committed after the snapshot but before the subscribe is in neither the
replay nor the queue, and is unrecoverable because replay is `seq > after_seq` and the cursor is a
maximum.

Negative control: replay-then-subscribe with a 50 ms replay round-trip → the client applied
`[1, 3, 4, 5]`; seq 2 was produced inside the window and lost. Subscribe-first → `[1, 2, 3, 4, 5]`. [V]

The resulting overlap is safe because **persistence precedes publication**: `engine.py:1032-1033`
does `await sink.persist(...)` *before* `yield event`, so any event appearing in both the replay and
the queue is a genuine duplicate of the same row with the same `event_id`. It arrives after its
replay copy and is dropped at the single dedup site (`dashboard/page.tsx:436-442` →
`wsReplayState.ts:32-40`) before any routing or cursor advance. Measured: raw frames
`[1, 2, 2, 3, 4, 5]`, applied `[1, 2, 3, 4, 5]`. [V]

**2. `_close_run` pops the liveness key BEFORE broadcasting the sentinel, and every registry
operation is synchronous.** That is what makes subscribe-versus-close race-free **without a lock**.
Since asyncio never preempts between two non-awaiting statements, only two interleavings exist:
either `subscribe()` sees the key present (so its queue is in the set when `_close_run` runs, so it
gets a sentinel), or it sees the key absent (so it returns `None` and `_iter_sse_frames` takes its
existing `live_queue is None` early return at `:192-193`). There is no third case.

The `asyncio.Lock` that `websocket_handoff.py:38` uses was **deliberately dropped**. It buys nothing
on a single-threaded event loop and it *costs* correctness here, because taking a lock introduces an
`await` and destroys the atomicity the argument depends on.

Verified: a witness subscriber plus 59 attach/detach churns at every await point — the witness
received all 60 events contiguously, zero of the 59 stranded, all three registries empty
afterwards. [V] Also verified with 2, 3 and 5 consumers (all saw the identical ordered set, none
stranded) and with a mid-stream disconnect (the two survivors completed; the departed subscriber was
deregistered). [V]

**3. Bound subscriber queues at 1000 and EVICT on overflow — do not drop events.** The source queue
stays unbounded, deliberately: bounding it would apply backpressure to the engine, changing pipeline
timing, and `kernel_services.emit_hook_event` uses `put_nowait` (`:386`) which would start raising
`QueueFull`. With an always-running pump the source never accumulates anyway.

Eviction beats dropping because it is **self-healing**: the sentinel closes the SSE stream; the
client saw `stream_attached {live:true}` so `sawNonLiveAttachRef` is false and it schedules a
reconnect (`useRunStream.ts:398-404`) carrying `Last-Event-ID` (`:334-336`); the server replays
exactly the missing range from `run_events`. The client loses nothing but a reconnect. **This works
only because persistence precedes publication.** Dropping would silently corrupt a stream with no
recovery path, because the frontend has no gap detection — a dropped `agent_chunk` is missing text
forever.

Verified with `maxsize` shrunk to 8: the stuck subscriber stayed at the cap, was evicted exactly
once, ended with a sentinel as its last item, and a healthy subscriber on the same run received all
40 events in order. [V]

**1000 is [I]**, sized from event shapes rather than measured payloads — the individually large
frames (`agent_complete` with a full output, `pipeline_complete` with a deliverable) occur once per
agent and once per run, while the bulk under any burst is `agent_chunk` deltas of roughly 50–500
bytes. Making it a setting means it can be tuned without a code change. Clear the assumption by
logging subscriber queue depth at eviction and at run end for a week.

##### One behaviour change requiring sign-off

**Zero-subscriber policy: discard.** Today, with no client attached, events accumulate in
`_PIPELINE_QUEUES[run_id]` without limit for the run's entire duration. A running pump would discard
them instead. Investigated and nothing depends on retention: `_register_resume_queue`
(`run_engine.py:91`) exists purely so a reconnect observes `live: true` and never reads contents; the
resume overlap mutex (`run_commands.py:390`) tests membership, not depth; every test touching
`_PIPELINE_QUEUES` asserts membership only. Correctness on reattach comes from the durable log.

What is actually lost is the four event classes that are **never persisted** — for a run with zero
attached clients at the moment they are produced:

| Class | Site | Durable substitute? |
|---|---|---|
| `hook_run` | `kernel_services.py:386` | **Yes** — the `hook_runs` table via `GET /api/runs/{id}/hook-runs` (`runs.py:1213`). Only the live tick is lost. |
| Launch driver `except` frames | `run_commands.py:2156`, `:2169` | **Yes** — each is paired with a `WorkflowRun.status` write in the same block. |
| Revision driver `except` frames | `run_commands.py:2467`, `:2474`, `:2481` | **Yes** — same. |
| `state_restoration_failed` | `engine.py:5942` | **No** — genuinely lost. Narrow (a lineage-persist warning on a revision). |

Risk is low and it is a strict improvement on the existing unbounded growth. If the loss is judged
unacceptable, the principled fix is to **persist those four classes**, not to retain them in
memory — a separate, larger change that should not be folded in.

Rejected alternatives: a *lazy* pump (start on first subscribe, stop on last unsubscribe) preserves
the unbounded growth, adds start/stop races, and makes the next attacher absorb a large duplicate
burst. An eager pump with a bounded retention ring re-introduces memory growth to do a job
`run_events` already does correctly.

##### Not changed, deliberately

- `websocket_handoff.py` keeps its own registry. Different key space (handoff token), different
  producer contract (`dispatch_event` is called directly — there is no shared queue to own), no pump
  needed. Merging them would be a false unification.
- The KAN-125 frontend suppression stays for this change. It only suppresses *auto*-attach, so it
  does not mask the fix's own verification, and removing it is a separately revertable decision.
- Fan-out / wave runs need **no** change. `run_fanout` (`fanout.py:251-635`) is an async generator
  whose worker events are yielded through `_execute_impl` into the same stamping wrapper; workers are
  joined with `asyncio.gather` (`:559`, `:576`) and none writes to the queue directly. [V] Fan-out is
  simply the case that benefits most, being the highest-volume emitter.

##### Architecture check

The import-linter contract (`backend/pyproject.toml:133-140`) forbids `agents.*` → `app.api.*`. The
bus lives entirely in `app.api.run_engine`; the engine reaches it only through already-existing
injected callbacks (`_resume_register_queue`, `_resume_cleanup`, wired at `app/main.py:141-143`). No
new boundary crossing. [V]

#### Verification

- **Failing-first unit test** in `backend/tests/unit/test_sse_stream.py`, new class
  `TestConcurrentClients`, reusing that file's existing `db_session` / `_seed_run` / `_seed_events` /
  `_parse` / `_collect` helpers and its `SessionLocal` redirection (`:96-101`). Crucially it drives
  `stream_run_events` and iterates `EventSourceResponse.body_iterator`, so it references **no symbol
  the fix introduces** and produces a diagnostic red on `dev` rather than an `ImportError`. Six
  tests: two clients see the same ordered set; three clients none strands; slow client evicted
  without starving a fast one; cleanup-without-sentinel releases attached clients; late attach after
  terminal reports `live:false`; stale registration self-heals (pairs with A4).
  ```bash
  cd backend && python3.11 -m pytest tests/unit/test_sse_stream.py::TestConcurrentClients -v
  ```
- **Fail-before / pass-after: already demonstrated, not predicted.** See Measured proof above.
- **Live on dev**, once A1 has landed (this test cannot run before it — the whole point is holding
  two concurrent connections open on one URL). Prefer a scripted dual-curl to browser devtools,
  because it yields byte-exact comparable logs:
  ```bash
  for T in A B C; do
    curl -Nsk "https://63-181-129-187.nip.io/api/runs/$RUN/events/stream" \
      -H "Authorization: Bearer $TOKEN" -H 'Accept: text/event-stream' > /tmp/sse-$T.log &
  done; wait
  for T in A B C; do grep '^id:' /tmp/sse-$T.log | sed 's/id: *//' | sort -n | uniq > /tmp/seq-$T; done
  diff /tmp/seq-A /tmp/seq-B && echo IDENTICAL
  ```
  **Before the fix the diff is non-empty** (one file holds the evens of the live tail, the other the
  odds). **After, it must be empty.** That single diff is the proof. Each log must also contain a
  `pipeline_complete` frame and every process must exit — use three clients, since with two the bug
  happens to let both terminate. Launch `user_stories` (six text-only agents, no `template_id` /
  `design_system_id` needed) rather than `od_prototype`.
- **Browser demo** (acceptance, not proof): launch in tab 1, then in tab 2 open the *same* run
  **explicitly from History** — a plain second dashboard load will not attach, because of KAN-125.

---

### A3 — `_cleanup_pipeline` sends no sentinel on eight of its ten call sites

**Severity:** attached clients hang indefinitely on a resume early-return.
**Confidence:** [V] — all ten call sites traced; released-on-cleanup behaviour verified in prototype.

#### Symptom

A client attached at the moment a run takes a resume early-return path blocks forever in
`await live_queue.get()`, holding an open HTTP connection and a generator frame, until the socket
drops.

#### Root cause

`_cleanup_pipeline` (`run_engine.py:70-73`) pops the registry entries and nothing else:

```python
def _cleanup_pipeline(pipeline_run_id: str) -> None:
    _PIPELINE_QUEUES.pop(pipeline_run_id, None)
    ...
```

Two of its ten callers (`run_commands.py:2186`, `:2489`) are immediately preceded by
`await event_queue.put(None)`. **The other eight are not** — they are the resume early-return paths
in `engine._fire_resume_cleanup` (`engine.py:7489`), called from `:5551`, `:7541`, `:7586`, `:7591`,
`:7830`, `:7890`, `:7914`, `:7920`, `:7937`, `:7955`. Those pop the queue with no sentinel ever sent.

#### Why it occurred

The sentinel and the cleanup were written as **two separate steps at the call site** rather than as
one atomic operation inside `_cleanup_pipeline`. That works as long as every author remembers both.
The resume tier was added later, by different plans, and its early-return paths only ever needed to
"stop tracking this run" — the author had no reason to think about a subscriber that might be
blocked on the queue, because on the launch path the sentinel was already someone else's job.

#### The fix

Make `_cleanup_pipeline` send the sentinel itself, through the queue object it just popped:

```python
def _cleanup_pipeline(pipeline_run_id: str) -> None:
    q = _PIPELINE_QUEUES.pop(pipeline_run_id, None)
    ...
    if q is not None:
        try:
            q.put_nowait(None)
        except Exception:
            pass
```

**This is the single most important line in the A-cluster.** Two properties make it safe:

- Because the sentinel goes onto the **source** queue, it queues *behind* anything still pending, so
  nothing is truncated on the normal path where a sentinel was already sent. A second sentinel is
  harmless — the pump breaks on the first, and the queue object is then unreferenced.
- Because the pump holds a direct reference to the queue, popping the dict entry first cannot starve
  it.

**Do NOT sentinel the subscribers directly** — the tempting alternative. Negative control: it
truncates the tail to nothing, because `asyncio.Queue.put` on an unbounded queue does not yield, so
`put(None); _cleanup_pipeline(...)` at `run_commands.py:2185-2186` executes as one atomic step before
the pump has run even once. [V]

#### Verification

`test_cleanup_without_sentinel_releases_attached_clients` — attach a client to a registered queue,
call `_cleanup_pipeline` with no prior sentinel (the resume early-return shape), assert the client's
stream terminates. Verified in prototype. [V]

---

### A4 — A stale queue entry poisons a run permanently

**Severity:** the run becomes un-viewable and un-resumable for the process lifetime.
**Confidence:** [V] for the mechanism and both root causes (control flow read); [I] that this is the
sole source of stale entries.

#### Symptom

A finished or crashed run reports `live: true` forever. Every subsequent SSE attach blocks
indefinitely on a sentinel that will never arrive — one open connection and generator frame per
attempt. `POST /api/runs/{id}/resume` returns 409 for that run until the backend restarts.

#### Root cause

`run_stream.py:281` uses **dict membership as the liveness signal**:

```python
live_queue = _get_or_create_queue(workflow_id) if workflow_id in _PIPELINE_QUEUES else None
```

and `run_commands.py:390` uses the same for the resume overlap mutex. So a surviving entry with no
live driver is indistinguishable from a live run.

Two paths leave such an entry permanently:

1. **`engine.resume_run` (`engine.py:7511-7704`) has no outer `try/finally`.**
   `restore_non_terminal_runs` registers the queue at `:5440` and the task at `:5457`, then spawns
   `resume_run`. If anything between `:7594` and `:7704` raises — `_compute_resume_offset`, the
   durable-tail read, `get_pipeline_agents` — the exception escapes into a bare `create_task` and
   **nothing cleans up**. `_drive_resumed_stream` has its own `finally` (`:7816-7830`), but only once
   entered.
2. **`_drive_user_resume` (`run_commands.py:427-463`) has an `except` but no `finally`.** It
   registers three entries at `:399` / `:400` / `:421`. `resume_run`'s opening DB read
   (`engine.py:7535-7574`) is `try/finally` with no `except`, so a DB error there propagates to
   `_drive_user_resume`'s bare `except Exception`, which cleans up nothing. `CancelledError` escapes
   the handler entirely.

#### Why it occurred

The cleanup contract lives in the **driver's** `finally`, and the resume tier added two new drivers
that do not have one. The launch driver's `finally` was the implicit model, but nothing enforces that
a new driver must have one — no base class, no context manager, no test. This is the same
missing-invariant shape as A3: a two-part protocol (register / unregister) with no mechanism binding
the halves.

#### The fix

One predicate, used in two places:

```python
def _is_run_live(run_id: str) -> bool:
    """True iff run_id has a LIVE in-process driver task.

    Side effect: self-heals a stale registration by calling _cleanup_pipeline.
    """
```

Treat a run as live iff `_PIPELINE_TASKS[run_id]` exists and is not `done()`. Otherwise, if either
registry still holds the id, call `_cleanup_pipeline(run_id)` — which, after A3, also sentinels any
pump and so releases anyone already attached — log a warning, and return `False`.

**Why the predicate is sound:** the driver's `finally` (containing `_cleanup_pipeline`) runs *before*
the task transitions to `done()`, so a `done()` task with a surviving queue entry is unambiguously
stale. And a live queue can never be observed without its task, because every one of the seven
registration sites registers both with **no `await` in between** — verified individually. [V]

**Implementation detail:** use `getattr(task, "done", None)` plus a `callable()` check rather than
calling `.done()` directly. `backend/tests/unit/test_rest_resume.py:260` deliberately installs a bare
`object()` as a task and expects a 409; this shape preserves that. [V]

Wire it into `subscribe()` (fixing the stream attach) and into the resume mutex at
`run_commands.py:390` (fixing the permanent 409).

**Ship as its own commit.** A self-healing side effect inside a function named like a predicate is
surprising, and it should be revertable independently of the fan-out.

Note this does **not** fix the underlying missing `finally` blocks. Adding them to `resume_run` and
`_drive_user_resume` is the deeper fix and belongs in its own change; `_is_run_live` makes the
system tolerant of them, which is worth having regardless.

#### Verification

`test_stale_registration_is_self_healed` — register a queue plus a `done()` task, attach, assert
`stream_attached {live:false}`, the stream terminates, and the id is gone from `_PIPELINE_QUEUES`.
Not yet written; the predicate was verified only to compile into the design without disturbing the
fan-out proofs. [V]

---

### A5 — The entire event log is materialized on every attach, twice on a fresh one

**Severity:** the ceiling that scales with concurrent stream count — i.e. the one A1 removes the
brake from. Also an authenticated attach-churn amplification vector.
**Confidence:** [V] — measured, with equivalence proven over 1,004 differential cases.

#### Symptom

Attaching to a long run is slow and memory-expensive, and the cost is retained for the stream's
entire lifetime rather than released after attach. An authenticated attacker looping
attach-then-abort turns one endpoint into a database and CPU amplifier.

#### Root cause

`run_stream.py` reads the durable log **twice**:

```python
# :151 — the replay tail
rows = await store.read_events(run_id, after_seq=after_seq)
# :184 — the ENTIRE log, unconditionally, on EVERY attach
full_log = await store.read_events(run_id, after_seq=0)
dangling = _dangling_review_gate(full_log)
if dangling is not None and dangling.seq <= after_seq:
    yield _sse_frame(dangling.seq, "review_gate_ready", dangling.payload_json)
```

`read_events` has no `LIMIT` (`agents/authz.py:315-330`). Line 184 exists solely to find the last
still-open `review_gate_ready` — the D-14g gate re-arm — and it scans everything to do it. On a
fresh attach (`after_seq=0`) line 151 reads the whole log as well.

**Both lists are retained.** I expected only `full_log` to be; suspending a real `_iter_sse_frames`
inside its live-drain `await live_queue.get()` and reading the generator frame locals showed:

```
{'rows': 200, 'r': 'RunEvent', 'full_log': 200, 'dangling': 'NoneType'}
```

`rows` is never rebound after the replay loop at `:153-155`, so the true retained cost today is
**≈2× the log per live stream**. [V]

Scale, measured on dev: `run_events` holds **741,914 rows**; the largest single run (`4dfae778`,
app_builder, 39 min) has **97,694 events**, 97,549 of them `agent_chunk`; individual `agent_input`
events average **214 KB**. A 50,000-row synthetic log:

| | rows materialized | wall time | peak alloc |
|---|---|---|---|
| `read_events(after_seq=0)` | **50,000** | 924 ms | **103.7 MB** |
| bounded query | **1** | 2.17 ms | 0.065 MB |

#### Why it occurred

The gate re-arm was specified behaviourally — *"the last `review_gate_ready` not followed by a
resolution"* — and implemented as the most direct expression of that sentence: fetch everything, scan
it in Python (`_dangling_review_gate`, `:115-129`). At the time it was written the runs were short.
Nothing in the design forced the question "what does this cost on a run with a hundred thousand
events", and there was no metric or log that would have shown the answer.

#### The fix

**First, confirm no existing bounded API already does this.** Three candidates were checked and all
three are unusable [V]:

| Candidate | Why not |
|---|---|
| `ArtifactStore.review_event_pending(gate_key)` (`store.py:156-166`) | Reads `self._resume_events` — an **in-memory, per-process** registry (`:42`), not the durable log. Needs a `gate_key` you can only get by reading the log; returns `bool` but the caller needs `seq` **and** `payload_json`; and after a restart the registry is empty — precisely the D-14g case the re-arm exists to serve (`test_attach_replay_matrix.py:424-446` asserts re-arm *with* an empty registry). |
| `gate_pendency.derive_open_gate(events)` (`gate_pendency.py:94`) | A pure function over a caller-supplied full list — `sorted(events, ...)`. It is the shared *vocabulary*, not a bounded reader. All eight production callers pass `read_events(..., after_seq=0)`. |
| `ScopedStore.read_gate_events(run_id)` (`authz.py:904-917`) | Different table (`gate_events`, an audit table), ordered by `created_at`, **no `seq` column** — so it cannot feed the `dangling.seq <= after_seq` comparison — and no `payload_json`. Itself unbounded (`.all()`). |

**So add a new bounded primitive.** In `agents/authz.py`, immediately after `read_events` (`:330`):

```python
async def last_event_of_types(self, run_id: str, types) -> Any | None
```

Mirroring `read_events` exactly: lazy `from app.models.run_event import RunEvent`;
`session, owned = self._acquire()`; filter on `run_id` and `RunEvent.type.in_(tuple(sorted(types)))`;
apply **the same** `self._scope_owner_ws(query, RunEvent)`; `order_by(RunEvent.seq.desc()).limit(1).first()`;
`finally: if owned: session.close()`.

Two details are load-bearing, not stylistic:

- **`tuple(sorted(types))`, not the raw frozenset.** `frozenset` iteration order over `str` varies
  with `PYTHONHASHSEED` across processes; sorting makes the emitted SQL deterministic, which matters
  for Postgres plan reuse and `EXPLAIN` reproducibility.
- **The `_acquire`/`owned` idiom is mandatory.** `run_stream.py:251-265` documents BUG-004: the
  streaming generator is deliberately fed a *session-less* `ScopedStore` so each read opens and
  closes its own session. A new method that skipped the `finally` would reintroduce one leaked
  connection per SSE stream. `tests/unit/test_run_stream_pool_leak.py` is the existing guard and
  exercises the new method automatically.

Then in `run_stream.py`: import `REVIEW_GATE_READY` alongside the existing
`REVIEW_RESOLUTIONS as _GATE_RESOLUTION_TYPES` (`:71-73`), and **derive** the vocabulary rather than
restating it — mirroring how `_STREAM_TERMINAL_TYPES` is already derived at `:83`, so
`gate_pendency.py` stays the single source and needs no edit:

```python
_GATE_REARM_TYPES = frozenset({REVIEW_GATE_READY}) | _GATE_RESOLUTION_TYPES
```

Replace the list-scanning `_dangling_review_gate` (`:115-129`) — **delete it, do not leave it beside
the new path** — with a two-liner over the store:

```python
row = await store.last_event_of_types(run_id, _GATE_REARM_TYPES)
return row if row is not None and row.type == REVIEW_GATE_READY else None
```

and `:184-187` becomes (with `full_log` gone entirely):

```python
if after_seq > 0:
    dangling = await _dangling_review_gate(store, run_id)
    if dangling is not None and dangling.seq <= after_seq:
        yield _sse_frame(dangling.seq, "review_gate_ready", dangling.payload_json)
```

##### The equivalence argument

Let `V = {review_gate_ready} ∪ REVIEW_RESOLUTIONS`. The old loop computes *the last
`review_gate_ready` with no resolution after it*. Then:

- If the max-seq row in `V` is a `review_gate_ready`, nothing in `V` follows it, so no resolution
  does, and it is the last such ready — exactly the loop's answer.
- If the max-seq row in `V` is a resolution, that resolution follows **every** ready, so the loop's
  `last_ready` is `None` at exit.
- If `V` is empty, both return `None`.

`review_gate_ready ∉ REVIEW_RESOLUTIONS` (`gate_pendency.py:53-62`), so the branches are mutually
exclusive on type. [V]

The only residual indeterminacy is a `seq` tie, where stable `sorted()` and `ORDER BY … LIMIT 1`
could differ. **Unreachable by construction:** `uq_run_events_scope_seq` is UNIQUE on
`(run_id, owner_id, workspace_id, seq)` — the exact scope `_scope_owner_ws` filters — declared in
`RunEvent.__table_args__` (`run_event.py:58-61`) so it is present in offline SQLite DDL too, and
enforced in production by migration `0029:129-133`. Probed: seeding two rows at `seq=7` under one
scope raises `IntegrityError`. [V]

**Differential proof, run not asserted.** A harness seeds a real `RunEvent` table, runs the verbatim
pre-fix `_dangling_review_gate` over `read_events(after_seq=0)` and the candidate query over the same
data, comparing `(seq, type, payload_json)`:

- exhaustive — every sequence of length 0–3 over `{review_gate_ready} ∪ REVIEW_RESOLUTIONS ∪ {agent_chunk}` (585 cases)
- 19 named cases — including one per distinct `REVIEW_RESOLUTIONS` member, earlier-open-later-resolved,
  resolution-before-any-ready, `questionnaire_complete` **not** closing a review gate,
  `review_gate_rejected` **not** being a resolution, and approve → re-gate → approve → re-gate
- 400 randomized logs of length 0–40 over a 17-type alphabet

```
DIFFERENTIAL: 1004/1004 identical
```

Note `review_gate_approved` **is** in `REVIEW_RESOLUTIONS` (so it closes a gate for re-arm purposes)
while being *excluded* from `_STREAM_TERMINAL_TYPES` at `:83`. Do not conflate the two sets — this
fix touches only the former.

##### The `after_seq > 0` guard — separable, and proven

Re-arm can only fire when `dangling.seq <= after_seq`, and `after_seq >= 0` (`:271-276`). So at
`after_seq == 0` it could only fire for a row with `seq <= 0`. Every `run_events` writer produces
`seq >= 1` — all four enumerated [V]: `engine.py:995` (fresh, `next_seq = 1`), `engine.py:7629`
(resume, `max(...)+1`), `engine.py:5626-5628` (resume marker), `authz.py:373-375`
(`append_event_next_seq`). So **on a fresh attach — the common case and the churn vector — the
gate-vocabulary read is skipped entirely.**

Ship this as its own commit: it rests on an application invariant rather than a schema `CHECK`, so a
reviewer can drop it without touching the correctness fix. Gate it on
`SELECT min(seq) FROM run_events;` returning ≥ 1 on dev, which covers legacy rows the four current
allocators did not write.

##### The `:151` replay read — fix the retention, do not stream it

**Now, in this change:** rebind `rows = ()` after the replay loop. One token, zero semantic change,
and it converts the replay allocation from *retained for the stream's lifetime* into *transient
during attach* — so the ceiling stops scaling with concurrent **streams** and starts scaling with
concurrent **attaches in flight**. Verified that this actually frees the memory: with the production
session-less store, dropping the reference and collecting releases the ORM rows, because
`read_events`' `finally: session.close()` has already de-associated them. [V]

**Do not** convert it to a server-side cursor, `yield_per`, or chunked pagination:

- A cursor reintroduces BUG-004. Streaming requires holding the session open across yields to
  `sse_starlette`, which awaits the client socket — so a slow client pins a pooled connection for
  the whole replay. The pool is `pool_size=20, max_overflow=40, pool_timeout=30`
  (`database.py:19-28`), 60 connections app-wide. Trading a memory ceiling for **pool exhaustion**
  is a worse failure mode, and is exactly what `run_stream.py:251-261` was written to prevent. [V]
- Chunked keyset pagination widens a correctness race. Today the replay is one `SELECT` — one
  consistent snapshot, with the live queue attached before the generator runs. Chunking turns one
  snapshot into ~98 for a 97,694-row run, widening the window in which a newly-appended row is both
  replayed *and* drained → a duplicate `seq` on the wire, violating the contract asserted by
  `_assert_contiguous_deduped_ordered` (`test_attach_replay_matrix.py:224-248`). [V]

**Separately, later:** the real answer to a 97,694-event replay is a **replay cap** — replay at most
the last *K* events and signal "history truncated, fetch older via REST". That is a product decision
with a frontend contract change and must not be smuggled in here.

##### Index analysis — no migration required

Indexes on `run_events` today [V]: `run_events_pkey (id)`; `ix_run_events_run_seq (run_id, seq)`;
`uq_run_events_scope_event` UNIQUE `(run_id, owner_id, workspace_id, event_id)`;
`uq_run_events_scope_seq` UNIQUE `(run_id, owner_id, workspace_id, seq)`.

The last is an **exact structural match**: equality on the leading three columns, then `seq`. Postgres
can serve it as `Index Scan Backward using uq_run_events_scope_seq` with `Limit 1` — no sort, no
materialization. **[I]** — the structural match is verified from DDL; the chosen plan is not, because
the prototypes ran on SQLite.

Honest caveat: `type` is not in that index, so the backward scan heap-fetches in descending `seq`
until the first gate-vocabulary hit. For the two cases that matter that is 1–10 rows (a run paused at
a gate has `review_gate_ready` at or near the tail; a finished run has its terminal there). The
unbounded case is a run with **neither** a gate event nor a terminal — a process killed mid-run —
where it walks that run's index entries. Even there it is strictly cheaper than today's code, which
performs the same scan *and* ships every row *and* builds 97,694 ORM objects.

**Do not pre-emptively add an index.** If measurement shows that case is common, the additive
follow-up is a **partial** index (own migration, `create_index` only, reversible) whose predicate
matches the query, giving a pure 1-row backward scan. Two costs to weigh first: `run_events` is
append-heavy at 741,914 rows and growing, so any new index taxes the hottest write path; and the
predicate would hard-code `REVIEW_RESOLUTIONS`, so changing that frozenset would then need a
migration. Decide with `EXPLAIN (ANALYZE, BUFFERS)` on the 97,694-event run.

##### Rejected alternatives — two are actively dangerous

1. **Push the CR-01 guard into the query** (`… AND seq <= :after_seq ORDER BY seq DESC LIMIT 1`).
   **Wrong, and tempting.** Counter-example: ready@5, approved@12, `after_seq=8`. The correct answer
   is *no re-arm* (the last gate-vocabulary row is the approval). The filtered query returns ready@5,
   and `5 <= 8` passes → **an already-approved gate is re-opened**, emitted after the replay already
   delivered the approval.
2. **Bound the scan to the last K events.** Breaks semantics: an open gate can legitimately sit far
   from the tail behind chat-lane rows, and "far" has no provable bound.
3. **Two aggregate queries** (max ready seq, max resolution seq). Twice the round trips, and without
   a `type` index each scans the whole run.
4. **Reuse `derive_open_gate`.** Right vocabulary home, but a pure function over a caller-supplied
   list — using it keeps the unbounded read that *is* the bug.

##### Owner-scoping does not regress

The new method calls the **same** `_scope_owner_ws` method object `read_events` uses (`authz.py:326`,
applying `owner_id = :owner AND workspace_id = :ws` per `:120-128`) — default-deny is reused, not
re-implemented. The endpoint's two-layer owner check (`run_stream.py:226-249`) is untouched; IDOR
still resolves to 404, never 403. Confirmed empirically: the bounded query under
`owner_id="attacker"` returns `None`. [V]

#### Verification

- `test_gate_rearm_materializes_at_most_one_row` — seed 5,000 events with a `review_gate_ready` at
  seq 4,990; drive with `after_seq=5000`; assert exactly one `review_gate_ready` frame with `id: 4990`
  and the right `gate_key` (non-vacuity), then assert total rows materialized `<= 1`.
  **Fail-before: `5001`. Pass-after: `1`.**
- `test_fresh_attach_does_not_re_read_the_log` — same fixture, `after_seq=0`; assert total materialized
  `<= 5000`. **Fail-before: `10000`. Pass-after: `5000`**, and with the guard,
  `[k for k,_ in reads] == ["read_events"]`.
- The differential equivalence test, carrying a **frozen pre-fix oracle** copied verbatim from
  `:115-129` and labelled as such (the deleted production loop must survive somewhere as the oracle).
  19 named cases plus the 585-case product.
- Live: reload during a paused human review gate. The new stream request must carry
  `Last-Event-ID: <n>` and its body must contain a `review_gate_ready` frame **after**
  `stream_attached`, with `id:` equal to the gate's original seq. Note the cursor is persisted in
  **`sessionStorage`** (`RunConnectionProvider.tsx:141`, `:197`; written `:151`), so this requires
  **F5 in the same tab** — a new tab starts at `after_seq=0` and takes the replay path instead.
  Negative controls: new tab must show **exactly one** `review_gate_ready` (from replay, none after
  the handshake); and after approving, F5 must show **none**.

---

## Cluster B — Observability

---

### B1 — The CloudWatch agent crash-loops and has never run

**Severity:** the reason every other issue here had to be found by external probing.
**Confidence:** [V] — root cause read directly from the instance's journal.

#### Symptom

Every application log group is empty — not empty streams, **zero streams**:
`/velocityai/dev/nginx-access`, `nginx-error`, `app`, `system`, and the `stage` and `prod`
equivalents. `AWS/Logs IncomingLogEvents` shows **0 datapoint-days over 90 days**, while the control
`/velocityai/dev/cloudtrail-audit` shows 29. CloudTrail records **zero** `CreateLogStream` calls by
the instance role, ever. The agent's *metrics* never flowed either — no `cpu_usage_*` or
`mem_used_percent` series exist in `VelocityAI/Dev`. [V]

#### Root cause

```
Error: failed to create logger: open sink "/var/log/amazon-cloudwatch-agent.log":
       open /var/log/amazon-cloudwatch-agent.log: permission denied
systemd: amazon-cloudwatch-agent.service: Main process exited, code=exited, status=1/FAILURE
systemd: Scheduled restart job, restart counter is at 977
```

The agent's config sets `"run_as_user": "cwagent"` (`bootstrap-ec2.sh:967`). Its telemetry sink is
`/var/log/amazon-cloudwatch-agent.log`, which **does not exist** and which `cwagent` (uid 997) cannot
create because `/var/log` is root-owned. It fails to construct its logger and **exits 1 before doing
any work at all**.

`restart counter is at 977` against 16 hours of uptime is one restart per minute since boot. Given
the log groups have never held a single stream, it has never worked on any boot.

Everything downstream is fine, which is exactly why this was invisible from outside [V]:

- `agent-ctl -a status` → `{"status": "stopped", "configstatus": "configured", ...}`
- The config validates: `Reading json config file path: .../amazon-cloudwatch-agent.d/file_amazon-cloudwatch-agent.json` → `I! Valid Json input schema.`
- Region detection succeeds; `ec2tagger` and delta processors resolve.
- The 7 log-group names Terraform creates (`modules/monitoring/main.tf:15-23`) are **literally
  identical** to the agent's `collect_list` destinations (`bootstrap-ec2.sh:988-995`). No drift.
- `velocityai-dev-cloudwatch-write` grants `logs:CreateLogStream` / `PutLogEvents` on
  `/velocityai/dev/*`; `velocityai-dev-cwagent-describe` grants `cloudwatch:PutMetricData`.
- `logs`, `ssm`, `ssmmessages`, `ec2messages` interface endpoints exist with private DNS, and the app
  SG has explicit 443 egress to the endpoint SG.
- Disk and inodes are healthy: `/` 32% used, 4% inodes.
- The CMK policy grants `logs.eu-central-1.amazonaws.com` (`modules/kms/main.tf:51-54`).

Section 14 of bootstrap provably executed, too: under `set -euo pipefail` (`:26`), sections 16 and 17
cannot run unless 14 exited 0 — and they do run (hourly `pg_dump` objects land in S3, latest
2026-07-29T18:01). [V]

#### Why it occurred

Two compounding reasons.

**The install is correct and the runtime is not, and nothing bridges them.** Section 14 ends at
`amazon-cloudwatch-agent-ctl -a fetch-config -s` (`:1005-1007`) whose **exit status is never
checked**. That wrapper ends in `systemctl restart`, which returns 0 as soon as the process forks.
So bootstrap saw success on a service that died a moment later. This is the classic
fire-and-forget-a-daemon mistake: the script verified that it *asked* for the agent to run, not that
the agent *was* running.

**The one signal that would have named it was the one thing not collected.**
`/var/log/amazon-cloudwatch-agent.log` — the agent's own error log, the file it is dying trying to
create — is **not in the `collect_list`**. Even a working agent would not have shipped its own
diagnostics. This is why a month passed.

#### The fix

Three changes, in `bootstrap-ec2.sh` §14 *and* applied to the running box:

1. **Pre-create the sink with the right ownership** — this alone gets the agent running:
   ```bash
   install -o cwagent -g cwagent -m 0644 /dev/null /var/log/amazon-cloudwatch-agent.log
   ```
   **Not** `run_as_user: root`. Running the whole agent as root would also work and is the shortcut;
   it widens the blast radius of a log-shipping daemon for no reason.
2. **Add the agent's own log to the `collect_list`**, destination `/velocityai/<env>/system`.
   Non-negotiable: it is the only way this class of failure ever becomes visible from outside.
3. **Check `fetch-config`'s exit status** and additionally assert `-a status` reports `running`,
   failing loudly if not. See B5.

Then restart the service and confirm a log stream appears.

#### Verification

```bash
systemctl is-active amazon-cloudwatch-agent          # must be "active", not "activating"
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status
                                                     # "status" must be "running"
journalctl -u amazon-cloudwatch-agent -n 20 --no-pager   # no "failed to create logger"
```
From outside, within minutes:
```bash
aws logs describe-log-streams --log-group-name /velocityai/dev/nginx-access \
  --order-by LastEventTime --descending --max-items 1
```
must return a stream. Then the standing guard in E-cluster (B6/E1) makes a regression alarm.

---

### B2 — `cwagent` cannot read any of the eight configured log files

**Severity:** independently blocking. Fixing B1 alone yields a running agent that ships nothing.
**Confidence:** [V] — permissions and the ACL mask read directly from the instance.

#### Symptom

Even with the agent running, every configured log path would be denied.

#### Root cause

```
$ id cwagent
uid=997(cwagent) gid=986(cwagent) groups=986(cwagent)     <- no supplementary groups

-rw-r----- 1 www-data adm  /var/log/nginx/access.log
-rw-r----- 1 syslog   adm  /var/log/auth.log
-rw-r----- 1 root     adm  /var/log/audit/audit.log

$ sudo -u cwagent test -r /var/log/nginx/access.log ; echo
nginx/access.log: DENIED
```

`cwagent` is in **no supplementary groups**, and every one of those files is group-readable by `adm`
only. `bootstrap-ec2.sh` never runs `usermod -a -G adm cwagent`. [V]

The Docker container logs are the interesting case, and they resolve a puzzle. Bootstrap *does* grant
an ACL for them (`:951-952`, `setfacl -R -m u:cwagent:rX,o::r /var/lib/docker/containers`), which
made a pure-permissions hypothesis look falsified — if the ACL worked, `/velocityai/dev/app` should
have had data. It does not, and here is why:

```
$ getfacl -p /var/lib/docker/containers
user:cwagent:r-x	#effective:--x
group::--x
mask::--x
```

**The mask is `--x`, so the granted read bit is masked off** — effective permission is traverse-only.
Confirmed behaviourally: `sudo -u cwagent ls /var/lib/docker/containers/*/*-json.log` →
`Permission denied`. [V]

#### Why it occurred

The author clearly knew about the permissions problem — the `setfacl` for the Docker path exists
precisely because of it. But it was solved **once, for one path, by the mechanism most likely to be
silently defeated**. `setfacl -m` recalculates the mask from the union of named entries unless `-n`
is passed or the mask is set explicitly; combining `u:cwagent:rX` with `o::r` in a single `-R`
invocation over a tree whose directories have differing base permissions produced a mask that drops
the read bit. Nothing verified the *effective* permission afterwards — only that the command
succeeded.

And the other five paths were never addressed at all, because the failure was invisible: with the
agent crash-looping (B1), no read was ever attempted, so no denial was ever logged.

#### The fix

```bash
usermod -a -G adm cwagent            # covers nginx, auth.log, postgres, audit.log
setfacl -R -m m::rx,u:cwagent:rX /var/lib/docker/containers
setfacl -R -d -m m::rx,u:cwagent:rX /var/lib/docker/containers
systemctl restart amazon-cloudwatch-agent      # required — group membership is read at start
```

Add all of it to `bootstrap-ec2.sh` beside the existing `:951-952`. Note the mask must be set
**explicitly** (`m::rx`) or it will be recalculated and the read bit lost again.

`/var/log/letsencrypt/` is directory-mode `0700 root:root`, so it needs its own ACL if that log is
to be collected; alternatively drop it from the `collect_list`.

#### Verification

For each configured path:
```bash
sudo -u cwagent test -r <path> && echo READABLE || echo DENIED
sudo -u cwagent bash -c 'ls /var/lib/docker/containers/*/*-json.log | head -1'
getfacl -p /var/lib/docker/containers | grep -E 'cwagent|mask'   # effective must include r
```
All eight must be READABLE and the `#effective:` annotation must show `r-x`.

---

### B3 — Two log files collide on one log group and stream

**Severity:** low — sequence-token contention and interleaved output.
**Confidence:** [V] — read from the rendered config.

#### Symptom

Two tailers write to the same CloudWatch stream, contending for its sequence token. Output from the
two files interleaves unpredictably and throughput suffers.

#### Root cause

In the rendered agent config, `audit.log` (`bootstrap-ec2.sh:991`) and `unattended-upgrades.log`
(`:993`) both target `log_group_name = /velocityai/<env>/system` with `log_stream_name` set to the
same `{instance_id}`. CloudWatch identifies a stream by (group, stream), so these are one stream. [V]

#### Why it occurred

`{instance_id}` is the natural stream name for a host-scoped log, and it is correct for *one* file
per group. The config groups several files under `system` for retention/organisation reasons and
reuses the same stream template for each, which is fine for the single-file groups and wrong for the
one with two files. Nothing validates uniqueness of (group, stream) across the `collect_list`.

#### The fix

Give each entry a distinct stream name, e.g. `{instance_id}/audit` and
`{instance_id}/unattended-upgrades`. Audit the whole `collect_list` for any other duplicate pair
while in the file.

#### Verification

After B1/B2 land, `aws logs describe-log-streams --log-group-name /velocityai/dev/system` must show
one stream per configured file, each with a plausible `lastEventTimestamp`.

---

### B4 — The agent's own log is not collected

**Severity:** low as a defect, high as a cause of the month-long blindness.
**Confidence:** [V]

#### Symptom / root cause / why

Covered as part of B1: `/var/log/amazon-cloudwatch-agent.log` is absent from the `collect_list`
(`bootstrap-ec2.sh:988-995`). The observability system does not observe itself, so its own total
failure produced no external signal.

#### The fix

Add it to the `collect_list` with destination `/velocityai/<env>/system` and a distinct stream name
per B3. Note the ordering dependency: this file is also the thing B1 must pre-create, so B1's fix is
a prerequisite for this one to have anything to read.

---

### B5 — `fetch-config` exit status is never checked

**Severity:** the reason B1 was silent at provisioning time.
**Confidence:** [V]

#### Symptom / root cause

`bootstrap-ec2.sh:1003-1007` installs and starts the agent, ending with
`amazon-cloudwatch-agent-ctl -a fetch-config -s`. Its exit status is not checked, and the wrapper
ends in `systemctl restart` which returns 0 on fork. Bootstrap therefore reports success on a service
that dies immediately.

#### Why it occurred

`set -euo pipefail` is in force (`:26`), so the author reasonably expected a failing command to abort
the script. It did not, because the command genuinely *succeeded* — it successfully asked systemd to
start something. The gap is between "the request succeeded" and "the service is running", and
`systemctl restart` does not distinguish them for a service that fails after forking.

#### The fix

After `fetch-config -s`, assert the agent is actually running and fail loudly if not:

```bash
amazon-cloudwatch-agent-ctl -m ec2 -a status | grep -q '"status": *"running"' || {
  echo "FATAL: CloudWatch agent is not running after fetch-config" >&2
  journalctl -u amazon-cloudwatch-agent -n 40 --no-pager >&2
  exit 1
}
```

Also `systemctl enable amazon-cloudwatch-agent` explicitly rather than relying on the package
postinst — `:1003-1004` asserts this without evidence. (Measured: it *is* currently `enabled`, so
this is belt-and-braces, not a live defect. [V])

Apply the same pattern to any future reconcile step (see C1): a deploy that touches the agent must
fail the build when the agent is not running afterwards.

---

### B6 — 41 alarms are firing and no one is subscribed

**Severity:** the monitoring worked. Nobody was listening.
**Confidence:** [V] — counts and subscriber state read from the account.

#### Symptom

```
$ aws cloudwatch describe-alarms --state-value ALARM --query 'length(MetricAlarms)'
41

velocityai-alerts        (prod)   confirmed: 0   pending: 0
velocityai-stage-alerts           confirmed: 0   pending: 0
velocityai-dev-alerts             confirmed: 0   pending: 1   <- never confirmed
flowin-prod-alerts       (legacy) confirmed: 1
flowin-staging-alerts    (legacy) confirmed: 1
```

Every alert topic for the **current** stack has zero confirmed subscribers. The only confirmed
endpoints are on the two legacy `flowin-*` topics, which are firing 16 permanently-stuck alarms — so
even that signal is dead through alarm fatigue. One of the firing alarms is
`velocityai-dev-unexpected-kms-decrypt`, a **security** alarm, going unnoticed. [V]

The dev subscription exists but was never confirmed: endpoint
`velocityai-dev-alerts@hexaware.com`, `SubscriptionArn` literally `"PendingConfirmation"`, created by
Terraform (`modules/monitoring/main.tf:91-97`). [V]

#### Why it occurred

`alert_email` is injected as `TF_VAR_alert_email` from `infra/terraform/bootstrap/cicd.tf:370`,
sourced from the git-ignored `bootstrap.tfvars`. Terraform can *create* an email subscription but
cannot *confirm* one — confirmation requires a human clicking a link in the mailbox. So the resource
is "successfully applied" and permanently inert. Nothing in the pipeline distinguishes
`PendingConfirmation` from confirmed.

Most of the 41 are firing **because** of B1: `cpu-high`, `mem-high`, `disk-root-high`,
`disk-data-high`, `inode-low` all depend on CWAgent metrics that never arrive, and all are configured
`treat_missing_data = breaching`. So the monitoring correctly detected the outage on day one and had
nowhere to send it.

#### The fix

**Order matters. Fix B1 and B2 first, then subscribe.** Confirming now buries the subscriber in
false alarms that will resolve themselves the moment metrics start flowing.

Then, **dev only** per the stated constraint — leave `velocityai-stage-alerts` and
`velocityai-alerts` untouched. Two options, and this needs a human decision:

1. **Confirm the existing pending subscription.** Requires access to the
   `velocityai-dev-alerts@hexaware.com` mailbox. No Terraform drift. Someone must own that address.
2. **Repoint it** via `TF_VAR_alert_email` plus a dev app apply. Note `alert_email` also feeds
   `VELOCITYAI_ACME_EMAIL` into `user_data` (`app/main.tf:68`), which is under `ignore_changes` so no
   instance replacement — but it destroys and recreates the subscription. A plain manual
   `aws sns subscribe` of a personal address works but is untracked: Terraform will not remove it,
   and will not reproduce it on a rebuild.

Two dead signals to fix while here: `PgDumpHeartbeat` and the hardcoded prod namespace — see E2 and E3.

#### Verification

`aws sns get-topic-attributes` on `velocityai-dev-alerts` must show `SubscriptionsConfirmed: 1`. Then
deliberately breach one alarm and confirm an email arrives.

---

## Cluster C — Delivery

---

### C1 — No host-configuration change can reach a running instance

**Severity:** the structural blocker. Without this, A1, B1, B2, B3, B4 and B5 are all unshippable.
**Confidence:** [V] — the gating condition, the Terraform lifecycle, and the live userData all read
directly.

#### Symptom

Editing `infra/scripts/bootstrap-ec2.sh` and pushing to `dev` changes nothing on the dev box. The
build succeeds, the deploy succeeds, and the host configuration is byte-identical afterwards.

#### Root cause

Three independent mechanisms, all deliberate, combining to a dead end:

1. `velocityai-firstboot.service` is gated by
   `ConditionPathExists=!/var/lib/velocityai/.bootstrap-done` (`user_data.sh.tpl:104`). [V]
2. `user_data_replace_on_change = false` and `user_data` is in `ignore_changes`
   (`modules/compute/main.tf:81`, `:134-151`). [V]
3. The CI deploy's on-host script only does `docker compose pull && up -d`
   (`infra/buildspec.yml:225-311`). It says so itself at `:286-287`: *"steady-state CI/CD deploys do
   NOT re-run bootstrap."* [V]

There is **no `aws_ssm_association`, no `aws_ssm_document`, and no agent-config SSM parameter
anywhere in the repo.** [V]

**A dev-specific finding makes this worse.** The live dev userData is **68 lines with no
`velocityai-firstboot.service` and no sentinel logic at all**, ending at *"awaiting SSM RunCommand
for full install"*. Dev launched 2026-07-01T03:59Z, before commit `bdc9e537` added self-bootstrap;
stage (07:10Z) and prod (10:55Z) have it. Confirmed on-box: `/var/lib/velocityai/.bootstrap-done`
**does not exist**. [V] So on dev, **nothing will ever regenerate the nginx or agent config** unless
a human deliberately re-runs the script.

#### Why it occurred

Every one of the three mechanisms is individually correct. Gating on a sentinel makes first-boot
idempotent. `ignore_changes` on `user_data` prevents Terraform from replacing a stateful instance —
which matters enormously here, because Postgres runs on the box and the root volume has
`delete_on_termination = true` with **zero snapshots**. And keeping the steady-state deploy to a
container pull is fast and safe.

What is missing is the fourth thing: a **reconcile** step. The design implicitly assumed host
configuration is immutable after provisioning, which was true until the application's transport
changed underneath it. The buildspec even demonstrates the author understood the general problem —
`chown 10001:10001` on the data directories is re-asserted on *every* deploy, with a comment
explaining that bootstrap does not re-run. The precedent existed; it just was not extended to nginx
or the agent.

#### The fix

**Two halves, both required. They are complements, not alternatives.**

**Now — apply to the running box, scoped to one instance id.**

```bash
DEV=i-092d5961f5aca87a6
NAME=$(aws ec2 describe-instances --instance-ids "$DEV" \
  --query 'Reservations[0].Instances[0].Tags[?Key==`Name`].Value|[0]' --output text)
[ "$NAME" = "velocityai-dev-app" ] || { echo "REFUSING: $DEV is '$NAME'"; exit 1; }

aws ssm send-command --instance-ids "$DEV" --document-name AWS-RunShellScript ...
```

**Never use `--targets`.** Six tag values — `Project`, `Owner`, `CostCenter`, `Repo`, `ManagedBy`,
`Component` — are **byte-identical across dev, stage and prod**. Only `Environment` and `Name`
discriminate, and an instance id is safer than either. [V]

The patch script must be idempotent (`grep -q` before appending), must back up to
`/root/nginx-backup-<ts>/` first, must gate on `nginx -t` before `systemctl reload`, and must restore
the backup and exit non-zero if validation fails. There is **no filesystem-level rollback available**
— `velocityai-dev-root` has zero snapshots — so the file-level backup is the only restore point. [V]

**Durable — the same day, commit to the repo.** Edit `bootstrap-ec2.sh` §13 (nginx) and §14
(CloudWatch agent) with the identical changes. This needs **no new pipeline step**:
`infra/terraform/app/main.tf:79-94` declares `aws_s3_object.bootstrap_script` with
`source_hash = filemd5(...)` into the **per-env** bucket, and every dev push already runs
`$TF/app apply` for `ENVIRONMENT=dev`. So committing to `dev` re-uploads the script to
`s3://velocityai-dev-pg-dumps-577954642302/config/bootstrap-ec2.sh` **and nowhere else**. [V]

**Later — a real reconcile step.** Extract §13/§14 *out* of `bootstrap-ec2.sh` into
`infra/scripts/reconcile-host-config.sh` and have bootstrap call it — one implementation, no shadow
copy. Then the pipeline change is **one line** (`bash infra/scripts/reconcile-host-config.sh` inside
the existing SSM payload), which is cheap to port later.

**Put that line in `.github/workflows/deploy.yml`, not `infra/buildspec.yml`.** The unmerged
`origin/fix/infra-uki` branch **deletes `buildspec.yml` entirely** (−324 lines) along with
`bootstrap/cicd.tf`, migrating to GitHub Actions. Work written into the buildspec is thrown away.
That branch keeps `bootstrap-ec2.sh` and modifies it only at lines 544-573, 1239-1244 and 1261-1274 —
**zero overlap** with §13 (703-938) and §14 (941-1007), so those edits are provably conflict-free. [V]

#### Verification

- The nginx probe pair from A1, run from outside.
- `aws s3api head-object --bucket velocityai-dev-pg-dumps-577954642302 --key config/bootstrap-ec2.sh`
  must show a fresh `LastModified` and the new `ContentLength`.
- **Survival matrix** [V]:

| Event | nginx change survives? | Why |
|---|---|---|
| `docker compose pull && up -d` | **Yes** | nginx is host-installed; compose has only `backend` + `frontend` |
| Reboot | **Yes** | files on root EBS, `nginx.service` enabled, and the IP is a real Elastic IP (`eipalloc-0098c8fa703931a5e`) so the FQDN and TLS cert survive a stop/start |
| `certbot.timer` renewal | **Yes** | no renewal hook rewrites the site file |
| Instance replacement | **No** | root volume `delete_on_termination=true`, zero snapshots — hence the durable half |
| Someone re-runs `bootstrap-ec2.sh` | **No** — overwritten wholesale | hence the durable half |
| Auto-regeneration | **Cannot happen** on dev | its userData has no firstboot service |

---

## Cluster D — Separable defects

Real defects found during the investigation, each with its own root cause and fix. **Deliberately not
folded into the A/B/C change sets** — each one dilutes the proof of the others. Log them as their own
tasks.

---

### D1 — A false-green test asserts a guarantee the backend does not provide

**Confidence:** [V] — read the spec and the mock.

**Symptom.** `frontend/e2e/tests/ts-sse-resilience.spec.ts:216`, titled *"TS-SSE-RESILIENCE-04
sse-resilience: multi-tab consumers ride ONE monotonic seq/event_id space"*, passes — while the
property it claims to test is false in production (A2).

**Root cause.** The test creates a second Playwright page and routes its SSE requests to the **same**
mock driver: `tab2.route(SSE_URL_RE, (route) => sse.route(route))`. It then asserts
`a.map(e => e.seq)` and `b.map(e => e.seq)` both equal `[1,2,3]`. `MockSse.handleStream` serves from
a persistent frame log via `framesAfter(cursor)` (`frontend/e2e/fixtures/mockSse.ts:534-592`) — it
models a **durable replay**, not a consume-once queue. Both tabs receive everything because the mock
re-reads a log, not because anything broadcasts.

**Why it occurred.** The mock *is* the server in this suite, and it was built to model the durable
replay semantics that `run_events` genuinely provides. The test author then wrote a *multi-tab* test
against it and the mock cheerfully answered — because a log-backed mock cannot express
consume-once. The title then encoded the wrong conclusion. This is the same class of trap that made
BUG-014-B false-green for a week.

**The fix — three parts, all honest:**

1. **Retitle and rescope** to *"each tab maintains an INDEPENDENT cursor over one monotonic
   seq/event_id space"*, keeping only what the harness genuinely supports: two independent attaches
   (`connectionCount === 2`), globally unique `event_id`s, identical `event_id` for identical `seq`
   across tabs. **Delete the implication that the backend fans one live tail out to both tabs** —
   replace the comment block at `:214-218` with an explicit note that server-side fan-out is a
   backend property covered by `backend/tests/unit/test_sse_stream.py::TestConcurrentClients`, naming
   it, so nobody re-derives the same false confidence.
2. **Add `TS-SSE-RESILIENCE-05`** for the property the A2 fix actually creates at the frontend layer:
   subscribe-before-replay means a client can legitimately receive the same `event_id` twice, once
   from replay and once live. Extend `MockSse` to emit a frame that is both in the replay log and
   delivered live, and assert the consumer applies it exactly once.
3. **Do not** make the mock consume-once. That would produce a permanently red test no backend fix
   could turn green — a worse lie than the current one.

**Verification.** `cd frontend && npx playwright test --project=mocked e2e/tests/ts-sse-resilience.spec.ts`

---

### D2 — A chat message is silently lost when the up-channel returns 429

**Confidence:** [V] — read the code path.

**Symptom.** The user types a message, presses send, and it vanishes. No error, no retry, no
indication anything failed.

**Root cause.** `frontend/src/providers/RunConnectionProvider.tsx:412-448`: `sendCommand`
content-negotiates on `text/event-stream` to decide whether to drain a streaming response. If
`res.ok` is false the streaming branch is skipped and the function **falls through to
`return null`** with no error path at all. A 429 from the `/api/` rate limiter — or any transient
5xx — therefore discards the message silently.

**Why it occurred.** The function's contract was written around two success shapes (a streaming
Concierge reply, or a JSON launch response) and the failure shape was never given one. The
`return null` is the fall-through for "not a stream", which happens to also catch "not OK".

**The fix.** Distinguish the three cases explicitly: OK-and-streaming, OK-and-JSON, and not-OK. On
not-OK, throw or return a typed error so the caller can surface it; push a failed-send marker into
the transcript so the user sees their message did not land, and keep the text recoverable. This
becomes considerably less likely once A1 lands, but a transient 5xx will still hit it.

**Verification.** A unit test with a mocked 429 response asserting the caller observes a failure and
the transcript shows the message as unsent.

---

### D3 — `/_next/static/` returns none of the five security headers

**Confidence:** [V] — measured live against dev.

**Symptom.**
```
/login                                 -> 5 of 5 security headers
/_next/static/chunks/...css            -> 0 of 5
```
HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy` are all absent on every
static asset.

**Root cause.** nginx inherits `add_header` directives from an outer level **if and only if** no
`add_header` is defined at the current level. `location /_next/static/`
(`bootstrap-ec2.sh:908-913`) defines its own `add_header Cache-Control ...`, which discards all five
server-level headers declared at `:791-799`.

**Why it occurred.** This is one of nginx's genuinely counter-intuitive rules — `add_header` is
replace-not-merge across levels. The location was added to set a long immutable cache lifetime for
hashed assets, a correct and unrelated goal, and the side effect is invisible unless you specifically
curl that path and compare.

**The fix.** Either re-declare the five headers inside the static location, or better, add `always`
and move the shared set into a snippet included by both — a single source, so a future location
cannot silently drop them again. Note `proxy_cache_valid 200 1y` in that block is also a no-op
without a `proxy_cache` zone; worth removing or wiring while in the file.

**Verification.** The measurement above, expecting 5 and 5.

---

### D4 — `ArtifactStore` retains three dicts for the process lifetime

**Confidence:** [V] — no removal site exists outside tests.

**Symptom.** Memory grows monotonically with the number of runs and review gates, never released.

**Root cause.** `agents/artifact_store/store.py:42`, `:43`, `:48` declare
`_questionnaire_responses`, `_resume_events` and `_questionnaire_force_proceed` on an instance held
by a process-lifetime singleton (`:173-184`). Writes at `:59`, `:78-79`, `:115`, `:137`. **There is
no `.pop`, `del` or `.clear` on any of the three anywhere in the repo outside tests.**
`set_review_response` stores the **full user-edited artifact body**, and `review_gate_ready` payloads
average ~34 KB on the dev data. Grows per run *and* per gate, and survives every exit path including
cancel and unhandled exception.

**Why it occurred.** These are coordination structures for an in-flight run — a response slot and an
`asyncio.Event` per gate. Their natural lifetime is the run, but they live on a **singleton**, and no
run-completion hook was ever given the job of clearing them. The store's own API has no concept of
"this run is over".

**The fix.** Add an explicit `forget_run(run_id)` to `ArtifactStore` that clears all three keyed
structures, and call it from the one place that already knows a run has ended — the driver `finally`
that calls `_cleanup_pipeline`. Do **not** add a TTL sweeper: the lifecycle is known exactly, so
tying it to the existing terminal hook is both simpler and correct.

**Verification.** A test that drives a run to terminal and asserts all three structures no longer
contain its id.

---

### D5 — `StateMachine._states` is only ever cleared by the user-resume endpoint

**Confidence:** [V]

**Symptom.** Slow, monotonic memory growth — roughly 172 bytes per entry, so ~17 MB per 100k runs.

**Root cause.** `state_machine.py:60` declares `_states` on a singleton (`:133-141`). It is written on
every transition **including terminal ones**. The only removal in the codebase is
`run_commands.py:412`, which fires solely on the user-resume endpoint. It is also load-bearing — the
guard at `:86-90` requires the entry to persist during the run — so it cannot simply be dropped at
transition time.

**Why it occurred.** Same shape as D4: per-run state on a process-lifetime object, with the one
cleanup call added opportunistically where a specific bug demanded it rather than as part of a
lifecycle contract.

**The fix.** Clear the entry from the same terminal hook as D4, after the final transition has been
recorded and read. Not urgent on its own — the growth rate is small — but it is the same fix, so do
both together.

**Verification.** As D4.

---

### D6 — `sweep_expired()` has zero callers: run sandboxes are never deleted

**Confidence:** [V] — verified myself; the only occurrence in `backend/` is its own definition.

**Symptom.** Unbounded disk growth under the EBS data volume. Every run leaves its sandbox directory
behind forever, on a 30 GB volume.

**Root cause.** `backend/app/agents/sandbox.py:163` defines
`sweep_expired(*, ttl_hours=None, runs_root=None) -> int`. Nothing calls it.

**Why it occurred.** The function was written as part of the sandbox's design — the TTL parameter
shows retention was thought about — but wiring it required choosing a trigger (startup? a timer? a
cron?) and that decision was never made. A function that exists and is never called reads, to a later
reader, as "handled".

**The fix.** Call it on application startup in the lifespan, before `restore_non_terminal_runs()`,
and additionally on a periodic timer. Startup alone is insufficient for a long-lived process.
Configure `ttl_hours` from settings so it is tunable without a code change. Log the count returned so
the sweep is observable — which requires B1 to be fixed to be useful.

**Verification.** Seed an expired sandbox, start the app, assert it is gone and the count was logged.
Then on dev, confirm `du -sh /opt/velocityai/data/runs` stops growing monotonically.

---

### D7 — `close_checkpointer()` has zero callers: the Postgres pool is never closed

**Confidence:** [V] — verified myself.

**Symptom.** The LangGraph checkpointer's `AsyncConnectionPool` is never closed. On shutdown,
connections are dropped rather than returned.

**Root cause.** `backend/app/agents/checkpointer.py:104` defines `close_checkpointer()`. Its own
module docstring at `:12` says *"Wire `get_checkpointer` on startup and `close_checkpointer` on
shutdown"*. Only half of that instruction was followed. The sole other references are two comments in
`engine.py` (`:1421`, `:1425`) discussing it.

**Why it occurred.** The docstring records the intended contract, so the author knew. The startup
half had an obvious home; the shutdown half needed a lifespan shutdown block, and there effectively
isn't one (D8). The two defects are the same omission seen from two directions.

**The fix.** Call it in the lifespan shutdown, as part of D8's fix.

**Verification.** Assert on shutdown that the pool reports closed; confirm no `connection was closed
unexpectedly` entries in the Postgres log after a graceful stop.

---

### D8 — The lifespan shutdown does nothing

**Confidence:** [V] — verified myself.

**Symptom.** On deploy or restart, in-flight runs are abandoned mid-write. Queues are not drained,
tasks are not cancelled, the checkpointer pool is not closed — despite a 30-second
`stop_grace_period` being configured and available.

**Root cause.** `backend/app/main.py` ends with:

```python
    yield
    logger.info("🔴 Shutting down...")
```

That is the entire shutdown path.

**Why it occurred.** The startup half of the lifespan grew substantially — restoring non-terminal
runs, arming resume hooks, wiring injected callbacks — while the shutdown half was left as the
placeholder log line it started as. Nothing forces symmetry, and an abandoned run on shutdown looks,
from the outside, exactly like a run that failed for some other reason. With no logs shipped (B1),
there was no way to see the pattern.

**The fix.** Give the shutdown a real body, inside the grace window:

1. Signal the cancel events for in-flight runs so they can persist a terminal state.
2. Cancel `_PIPELINE_TASKS` and await them with a timeout.
3. Drain and sentinel the per-run queues (after A2, the pumps handle this — `_close_run` per run).
4. `await close_checkpointer()` (D7).
5. Log the count of runs that were still in flight, so the thundering herd (D9) is measurable.

Order matters: cancelling before signalling loses the chance to write a terminal status.

**Verification.** Start a run, issue a graceful stop, assert the run's `WorkflowRun.status` is
terminal rather than left `running`, and that the process exits within the grace period.

---

### D9 — Boot re-launches every non-terminal run at once

**Confidence:** [V] — verified myself that the call is uncapped.

**Symptom.** A restart during active use re-launches all in-flight runs simultaneously. A deploy
during twenty active runs re-launches twenty runs at once into a single event loop and a bounded
thread pool. Plausibly the real cause of unexplained post-deploy incidents.

**Root cause.** `backend/app/main.py:164` calls `await engine_instance.restore_non_terminal_runs()`
with no concurrency limit, and `engine.py:5244` iterates every resumable run creating a task each.
Combined with D8 — which abandons those runs mid-write rather than letting them finish or checkpoint
cleanly — every restart is a worst case.

**Why it occurred.** Resume was designed and verified for *correctness of a single run* (the v3.0
milestone: does a resumed run skip completed work and produce the right deliverable). It was never
load-tested for *N runs at once*, because the offline harness resumes one fixture at a time and there
was no production metric to reveal the aggregate.

**The fix.** Cap concurrent restores with a semaphore and queue the remainder, processing them as
slots free. Size it to the same figure as any global run-admission limit — around 24 is a reasonable
starting point for a 4-vCPU box, and it should be a setting. Log how many were deferred. Note this
becomes much less dangerous once D8 lets runs shut down cleanly, so **do D8 first**.

**Verification.** Seed N non-terminal runs, restart, and assert at most the cap are `running`
simultaneously while all eventually complete.

---

### D10 — `SSE_STREAM_IDLE_TIMEOUT_SECONDS` is defined and never read

**Confidence:** [V] — grepped; only the definition exists.

**Symptom.** None functionally. The harm is to comprehension: `backend/app/core/config.py:133`
declares a knob, and the surrounding comment block (`:119-133`) explains the idle-timeout reasoning
in detail — which makes the timeout story read as *handled* when nothing implements it. It cost real
time during this investigation, and it was independently logged by the team as Phase 44 IN-01.

**Root cause / why.** The setting was added alongside `SSE_KEEPALIVE_PING_SECONDS` when the SSE
transport was designed. The ping was wired (`run_stream.py:293`); the idle timeout was not, because
the keepalive made it unnecessary. The constant and its documentation were left behind.

**The fix.** Delete the constant and fold its useful content — that the ping must be shorter than the
ingress idle timeout, and that the ingress must run `proxy_buffering off` — into the comment above
`SSE_KEEPALIVE_PING_SECONDS`. Deleting superseded configuration is part of the change, not optional
tidying.

**Verification.** Grep returns zero occurrences; the SSE suites stay green.

---

### D11 — `run_stream.py` has no logging at all

**Confidence:** [V]

**Symptom.** There is no server-side record that an SSE stream was ever opened, how long it lived,
how many events it delivered, or why it closed. During this investigation that absence was the single
biggest obstacle: the 429s, the event stealing and the stale-entry hangs are all invisible from
inside the application.

**Root cause.** 300 lines, zero logging calls, no logger, no import. And `uvicorn.access` is pinned to
`WARNING` (`backend/app/main.py:54`), so not even a request line is recorded.

**Why it occurred.** The module was written to a strict parity contract — its frames had to be
byte-identical to the retired WebSocket drainer's — and logging was reasonably seen as out of scope
for a transport shim. But the shim became the sole run transport, and nothing revisited its
observability.

**The fix.** Add an `app.api.run_stream` logger emitting exactly two lines per stream:

- **on open** — run id, user id, resolved `after_seq`, whether a live queue was attached;
- **on close** — a reason from a closed vocabulary (`client_disconnect` | `terminal_event` |
  `sentinel` | `no_live_queue` | `evicted`), duration in seconds, events delivered.

Place the close emit at the four exits (`:193`, `:196`, `:199`, `:205`) — or, after A2, in the
wrapper generator's `finally`, which is a single site.

**Emit as JSON.** The current format is plain pipe-delimited text (`main.py:39`), which no CloudWatch
metric filter can parse structurally. Pair this with E1 so the two are consistent.

**Verification.** Open and close a stream; assert exactly one open and one close line with the
expected reason for each of client-disconnect, terminal-event and no-live-queue.

---

## Cluster E — Monitoring configuration

---

### E1 — The nginx log format captures no upstream variables

**Confidence:** [V]

**Symptom.** A 429 emitted by nginx's own rate limiter is **indistinguishable** in the access log
from a 429 returned by FastAPI. During this investigation that ambiguity had to be resolved by
inspecting the response body for an `nginx` `Server` header. With logs shipping (B1), the same
ambiguity would have made a metric filter unable to tell "we are throttling our own users" from
"the application is rejecting requests".

**Root cause.** `bootstrap-ec2.sh:712-715`:

```nginx
log_format velocityai '$remote_addr - $remote_user [$time_local] '
                  '"$request_method $uri $server_protocol" '
                  '$status $body_bytes_sent "$http_referer" '
                  '"$http_user_agent" rt=$request_time';
```

It captures `$status` and `$request_time` but **no `$upstream_*` variables at all**, and it is
space-delimited rather than structured.

**Why it occurred.** It is a reasonable evolution of the standard combined format, written before the
application had a streaming transport whose diagnosis depends on upstream timing. And since nothing
was ever shipped, no one ever tried to write a query against it and discovered the gap.

**The fix.** Replace with a JSON format. Changing a log format costs nothing at runtime (a reload)
and roughly doubles line size (~200 → ~400 bytes, about $1.30/env/month):

```nginx
log_format velocityai escape=json
  '{"time":"$time_iso8601","remote_addr":"$remote_addr","xff":"$http_x_forwarded_for",'
  '"method":"$request_method","uri":"$uri","proto":"$server_protocol",'
  '"status":$status,"upstream_status":"$upstream_status","upstream_addr":"$upstream_addr",'
  '"bytes_sent":$body_bytes_sent,"request_time":$request_time,'
  '"upstream_connect_time":"$upstream_connect_time","upstream_header_time":"$upstream_header_time",'
  '"upstream_response_time":"$upstream_response_time",'
  '"connection":$connection,"connection_requests":$connection_requests,'
  '"ssl_protocol":"$ssl_protocol","request_id":"$request_id",'
  '"referer":"$http_referer","user_agent":"$http_user_agent"}';
```

`escape=json` and `$request_id` need nginx ≥ 1.11.8; the box runs 1.24.0. [V]

**Blast radius — must be done together.** This breaks the existing space-delimited metric filter
`[ip, id, user, ts, request, status_code=5*, ...]` (`modules/monitoring/main.tf:469`). Replace all
filters with JSON patterns in the same change:

| Metric | Pattern | Alarm |
|---|---|---|
| `Nginx5xx` | `{ $.status >= 500 }` | Sum > 10, period 60, eval 5 (unchanged) |
| `Nginx429` | `{ $.status = 429 }` | Sum > 10 over 300s, eval 2, `datapoints_to_alarm 2`, notBreaching |
| `NginxLimit429` | `{ $.status = 429 && $.upstream_addr = "-" }` | Sum > 0, period 300, eval 3, notBreaching |
| `SseStreamSlow` | `{ $.uri = "*/events/stream" && $.request_time > 1 }` | informational |

`NginxLimit429` is the one that would have caught A1 on day one: `upstream_addr = "-"` means nginx
rejected the request without proxying it, which for an internal tool is essentially always
misconfiguration. Thresholds are defensible from the config — `/api/` allows `120r/m` + `burst=20`
per IP, so an occasional burst overrun yields a handful of 429s, while **10 in five minutes across
two consecutive windows** is a sustained rejection pattern.

Add also the meta-alarm this whole incident argues for: `AWS/Logs` `IncomingLogEvents`, dimension
`LogGroupName=/velocityai/dev/nginx-access`, Sum, period 3600, `LessThanThreshold 1`,
`evaluation_periods 1`, `treat_missing_data = breaching`. Repeat for `/app`. **That single alarm would
have caught B1 on day one.**

**Verification.** `nginx -t`, reload, then confirm the access log emits valid JSON and each metric
filter's test pattern matches a real line (`aws logs test-metric-filter`).

---

### E2 — The `PgDumpHeartbeat` alarm has no publisher

**Confidence:** [V]

**Symptom.** `velocityai-dev-pg-dump-heartbeat-stale` is permanently in ALARM, contributing to the
41 firing alarms in B6 and to alarm fatigue on the legacy topics.

**Root cause.** The alarm watches namespace `VelocityAI/Backups`
(`modules/monitoring/main.tf:733`). **That namespace does not exist** — nothing anywhere publishes to
it. Combined with `treat_missing_data = breaching`, it fires forever.

**Why it occurred.** The alarm was written against an intended heartbeat metric that the backup
script was supposed to emit. The script does the backup correctly (hourly `pg_dump` objects are
landing in S3, latest 2026-07-29T18:01 [V]) but never got the `put-metric-data` call. Alarm and
publisher were built by different changes, and `treat_missing_data = breaching` — correct for a real
heartbeat — turned the gap into a permanent false positive.

**The fix.** Either add a `aws cloudwatch put-metric-data --namespace VelocityAI/Backups` call to the
`velocityai-pg-dump` script on success, or delete the alarm. The former is right: a backup you are not
alerted about is not a backup. Note this alarm currently fires on **dev, stage and prod**, so a fix in
`bootstrap-ec2.sh` benefits all three whenever they are next rebuilt — but per the dev-only
constraint, only apply it to the dev box directly.

**Verification.** After one hour, the metric exists and the alarm transitions to OK.

---

### E3 — The stuck-workflows check hardcodes the prod namespace

**Confidence:** [V]

**Symptom.** `StuckRunningWorkflows` alarms on dev and stage sit permanently in
`INSUFFICIENT_DATA`, while **dev's data lands in prod's namespace**, corrupting prod's metric.

**Root cause.** `bootstrap-ec2.sh:1105-1106` passes `--namespace VelocityAI/Prod` as a literal,
inside a **quoted** heredoc — so the `${ENVIRONMENT}` interpolation that the rest of the script relies
on does not apply, and every environment publishes to `VelocityAI/Prod`.

**Why it occurred.** The quoted-heredoc boundary is the trap. Elsewhere in the same file, unquoted
heredocs are used deliberately so `$DOMAIN` and `${ENVIRONMENT}` expand at install time (see
`:728-731`, which comments on exactly this). This block is quoted — correctly, because it contains
runtime shell variables that must survive — and the namespace literal was written inside it without
noticing that it therefore could not be templated.

**The fix.** Pass the environment into the script's execution context rather than trying to
interpolate inside the quoted heredoc — e.g. write `ENVIRONMENT=<value>` as a line *before* the
quoted heredoc body (the same technique `infra/buildspec.yml` already uses at `:228-232` for
`BUCKET`/`REGISTRY`/`REGION`), and reference `$ENVIRONMENT` inside. Then derive the namespace as
`VelocityAI/${ENV_TITLE}`.

**Verification.** Confirm `VelocityAI/Dev` gains a `StuckRunningWorkflows` metric and the dev alarm
leaves `INSUFFICIENT_DATA`; confirm prod's metric no longer receives dev's data points.

---

### E4 — `logs:DescribeLogGroups` is scoped to a resource ARN, making the grant a no-op

**Confidence:** [V] for the policy text; [I] for whether the agent needs the action.

**Symptom.** None observed — B1 prevents the agent from ever reaching the point of calling it. It is
a latent defect that would surface once B1 is fixed.

**Root cause.** The `velocityai-dev-cloudwatch-write` policy scopes `logs:DescribeLogGroups` to
`arn:aws:logs:...:log-group:/velocityai/dev/*`. That action **does not support resource-level
permissions** and requires `Resource: "*"`, so the statement grants nothing.

**Why it occurred.** Correct instinct — least privilege, scope every action to the resource — applied
to one of the API actions that does not support it. IAM does not error on this; the policy validates
and simply never matches.

**The fix.** Move `logs:DescribeLogGroups` into its own statement with `Resource: "*"`, keeping
`CreateLogStream`, `PutLogEvents` and `DescribeLogStreams` scoped to the log-group prefix as they are.
Add a comment recording why, so it is not "fixed" back later.

**Verification.** After B1, confirm no `AccessDenied` on `DescribeLogGroups` in the agent log, and
that log streams are created.

---

## Appendix 1 — Measured baselines

**These matter because three of them are RED on `dev` before any change.** The bar for the fixes in
this dossier is therefore *delta from a known red baseline*, not absolute green. All measured
2026-07-29 on `dev` @ `3429d2d9`, from `backend/`, with `python3.11` (no venv).

| Command | Result |
|---|---|
| `pytest tests/agents/test_characterization_{prototype,prototype_revision,app_builder,od_prototype,od_ppt}.py tests/agents/test_wire_parity.py -q` | **10 failed, 6 passed** (53.8s) |
| `pytest tests/unit/test_sse_stream.py tests/agents/test_attach_replay_matrix.py tests/unit/test_run_stream_pool_leak.py -q` | **1 failed, 31 passed** (4.3s) |
| `/opt/homebrew/bin/lint-imports` | **1 broken contract** |

**The golden failures.** Every `test_*_event_snapshot` and every `test_wire_parity_matches_golden[*]`
fails. The **byte** goldens still pass — only the event streams diverged, first at index 0
(`pipeline_start`, whose roster carries 5 prototype agents including `prototype-analyze`). The
`.planning/IMPLEMENTATION-REGISTER.md` claim of "goldens 10/10" was measured on `feat/ui-2`; `dev`
has since taken merges — including one deriving `PIPELINE_AGENTS` from a folder scan — without the
goldens being regenerated. **Not yet determined** whether this is benign staleness needing
`SNAPSHOT_UPDATE=1` plus a diff review, or a genuine behavioural regression. Resolve this before
gating any backend change on the goldens.

**The broken import contract.**
`agents.capabilities.strategies.task_loop -> agents.execution_engine.od_context (l.562)` →
`app.services.od_loader (l.26)`. The kernel imports the app layer, violating the hexagonal boundary
the project treats as an invariant. Note it is `app.services`, not `app.api`, so the A2 fix does not
interact with it — but the bar is *exactly* this one violation, and no second.

**The SSE test failure** is
`test_attach_replay_matrix.py::TestMidStreamResume::test_last_event_id_header_resumes_over_http`
(`AssertionError: assert ('3' in ['2'])`). Diagnosed as a **harness gap, not a production bug**: the
`matrix` fixture (`:85-137`) patches `run_engine._get_db` but **not**
`app.models.database.SessionLocal`, which `test_sse_stream.py`'s `api` fixture *does* patch
(`:96-101`). So the endpoint's session-less streaming store (`run_stream.py:262-265`) reads the real
dev database, finds no rows for `run-1`, and replays nothing. Unaffected by anything in this dossier.
Also independently listed as an outstanding red in the v3.0 register follow-ups. **Do not fix it as
part of this work, and do not mistake it for a regression.**

The offline harness additionally logs `no such column: workflow_runs.od_context_json` and
`FOREIGN KEY constraint failed` on `run_events` persist. Both are documented best-effort degradations
and do not stop the event stream.

Frontend baselines (`npm run test`, `npm run e2e`) were **not measured on `dev`**. The last recorded
figure — 132 mocked e2e passing — is from `feat/ui-2`, a different branch. Capture a fresh baseline at
the pre-change commit before touching `ts-sse-resilience.spec.ts`.

---

## Appendix 2 — Environment facts

Verified read-only, 2026-07-29.

**Topology.** Browser → HTTPS → nginx 1.24.0 (Ubuntu) on a single EC2 instance → `127.0.0.1:8000`
(FastAPI/uvicorn) and `127.0.0.1:3000` (Next.js standalone). **No ALB, no API Gateway, no CloudFront,
no ASG, no launch template, no custom AMI, no Route53 zone.** Postgres runs **on the instance**
(apt `postgresql-16`), reached from the backend container via `host.docker.internal`. DNS is
`<dashed-eip>.nip.io`.

**nginx runtime.** `worker_processes auto`, `worker_connections 768` (Ubuntu stock — bootstrap never
sets it). A proxied stream consumes two connections, so ~384 concurrent streams per worker. No
`limit_conn` anywhere; no `events/stream` location.

**In-process state that prevents horizontal scaling.** `_PIPELINE_QUEUES` (`run_engine.py:39`),
`_CANCEL_EVENTS` (`:47`), `_LIVE_ECTX` (`run_commands.py:640`), `_CONCIERGE_STREAM_TASKS` (`:763`) are
module-level dicts. An SSE client must reach the exact process owning its run's queue, so a second
app instance behind a load balancer would serve dead streams roughly half the time. Any load-balancer
proposal is gated on externalising these, the runs filesystem, and Postgres.

**Per-environment isolation (strong).** Separate VPCs (dev `10.40/16`, stage `10.30/16`, prod
`10.20/16`), security groups, instance roles, KMS CMKs, SSM parameter prefixes, S3 buckets,
CloudWatch log groups, SNS topics, alarm namespaces, and Terraform state keys
(`velocityai/<env>/{app,foundation}.tfstate`). No VPC peering or transit gateway.

**Shared across environments (the leak vectors).** ECR repositories `velocityai/backend` and
`velocityai/frontend` — mutable, but partitioned by `dev-`/`stage-`/`prod-` tag prefix with
prefix-partitioned lifecycle rules, and each environment's `deploy.env` pins its own `<env>-<sha>`, so
no environment pulls a floating tag. The tfstate bucket, lock table and its CMK. And
`velocityai/shared.tfstate`, which contains **only** the two ECR repos plus a lifecycle policy and an
account guard — but `infra/buildspec.yml:143-150` runs `$TF/shared apply` on **every** build, so it is
a no-op only while `infra/terraform/shared/` is unchanged. **Do not modify that directory.**

**The tag footgun.** `Project`, `Owner`, `CostCenter`, `Repo`, `ManagedBy` and `Component` are
**byte-identical** on dev, stage and prod. Only `Environment` and `Name` discriminate. Never target
SSM by tag; always `--instance-ids`.

**Elastic IPs.** All four instances have real EIPs — dev is `eipalloc-0098c8fa703931a5e` /
`63.181.129.187`. A stop/start preserves the IP, the `nip.io` FQDN and the TLS certificate. Correcting
an intermediate claim during the investigation that they were ephemeral.

**No root volume in any environment has ever been snapshotted**, and all carry
`delete_on_termination = true`. There is no filesystem-level rollback for any host change.

**Deployed code.** CodeBuild `velocityai-gitlab-runner-dev` succeeded 2026-07-29T16:27Z with source
version `3429d2d9`, image tag `dev-3429d2d942c8`. So the running dev backend is exactly the tree this
dossier analyses.
