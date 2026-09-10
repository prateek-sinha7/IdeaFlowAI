---
spec: 014-host-capacity-monitoring
title: Host Capacity Matrix (admin) + Capacity Admission Gate
type: plan
status: implemented
authored: 2026-09-08
updated: 2026-09-08           # operator answered §10 Q1-Q5 — see §10 Resolutions
waves: 4                      # + optional Wave 5, deferred (§10 Q5)
autonomous: true               # Wave 0 decisions are resolved; no blocking question remains
requirements: [CAP-01, CAP-02, CAP-03, CAP-04, CAP-05, CAP-06]

files_modified:
  # === Wave 1: backend read path
  - backend/app/core/config.py
  - backend/app/services/host_metrics.py                    # NEW — AWS adapter
  - backend/app/services/capacity_state.py                  # NEW — pure decision logic + snapshot cache
  - backend/app/api/admin_capacity.py                       # NEW — admin-only router
  - backend/app/main.py                                     # poller in lifespan + router registration
  - backend/tests/unit/test_capacity_state.py               # NEW
  - backend/tests/unit/test_host_metrics_adapter.py         # NEW
  - backend/tests/unit/test_admin_capacity_api.py           # NEW
  # === Wave 2: the gate
  - backend/app/api/run_commands.py                         # _require_host_capacity beside _require_tier_entitlement
  - backend/app/api/handoff.py                              # gate POST /{token}/start
  - backend/tests/unit/test_capacity_gate_endpoints.py      # NEW
  # === Wave 3: frontend
  - frontend/src/lib/api.ts                                 # adminListCapacity + 503 listener seam
  - frontend/src/components/ui/Modal.tsx                    # NEW — first real dialog primitive
  - frontend/src/providers/ServiceBusyProvider.tsx           # NEW
  - frontend/src/app/layout.tsx                             # mount the provider
  - frontend/src/app/admin/page.tsx                         # Tabs: Users | Machines
  - frontend/src/components/admin/CapacityMatrix.tsx        # NEW
  - frontend/src/hooks/useCapacityMatrix.ts                 # NEW — polling hook
  - frontend/src/providers/RunConnectionProvider.tsx        # FIX: launch branch swallows non-2xx
  - frontend/src/components/admin/CapacityMatrix.test.tsx   # NEW
  - frontend/src/providers/ServiceBusyProvider.test.tsx     # NEW
  - frontend/src/components/ui/__tests__/modal.test.tsx     # NEW
  - frontend/e2e/tests/ts-<n>.capacity-busy.spec.ts         # NEW
  # === Wave 4: infra
  - infra/terraform/modules/iam/main.tf                     # new inline policy + exclusive list
  - infra/terraform/modules/iam/variables.tf
  - infra/terraform/modules/iam/policies/capacity-read.json # NEW
  - infra/terraform/modules/iam/README.md
  # === Wave 4: CI/CD wiring (§10 resolutions — instance id + per-env gate toggle)
  - .github/workflows/deploy.yml                            # push HOST_CAPACITY_* to SSM
  - infra/scripts/bootstrap-ec2.sh                          # velocityai-load-secrets allow-list
  - docs/GITHUB_CICD_SETUP.md                                # §3.2 + §10 reference tables
  - app.env.example                                          # local-dev HOST_CAPACITY_* block

must_haves:
  truths:
    - "An admin sees a per-instance matrix of every running EC2 instance belonging to this environment, each row carrying CPU used %, memory used %, the age of the reading, and the instance's current gate contribution."
    - "A non-admin attempting an expensive operation while the gate is engaged receives HTTP 503 with detail.code == 'host_capacity_exhausted' and a Retry-After header, and the frontend renders a modal explaining the service is busy."
    - "Cancel, gate-resolve, clarify-answers, SSE reconnect, and every GET read remain available while the gate is engaged — the gate is admission control for NEW work only and never strands work already in flight."
    - "When capacity cannot be determined (CloudWatch unreachable, IAM denied, CloudWatch agent degraded, reading older than the staleness bound, running outside AWS) the gate ALLOWS the operation, logs at WARNING, and the admin matrix reports the blind state explicitly."
    - "No request-path code calls AWS: the gate and the matrix both read a process-local snapshot refreshed by one background poller, so a CloudWatch outage cannot add latency to a launch."
    - "The gate is disabled by default (HOST_CAPACITY_GATE_ENABLED=false) and is enabled per environment only after the matrix has been observed in that environment."
    - "HOST_CAPACITY_INSTANCE_IDS (the operator-supplied EC2 instance id override) and every other HOST_CAPACITY_* setting flow through the deploy.yml -> SSM -> velocityai-load-secrets -> app.env pipeline exactly like the existing BEDROCK_*/CORS_ORIGINS variables, so setting a GitHub Environment variable is sufficient — no manual SSH/SSM edit is required per environment."
  artifacts:
    - path: "backend/app/services/capacity_state.py"
      provides: "CapacitySnapshot / InstanceCapacity frozen dataclasses, the pure threshold+hysteresis+staleness decision function, and the process-wide snapshot holder"
      contains: "def evaluate_admission"
    - path: "backend/app/services/host_metrics.py"
      provides: "the boto3 adapter: instance discovery via ec2:DescribeInstances, CPU/memory series via cloudwatch:GetMetricData, behind a patchable _client() seam"
      contains: "def _client"
    - path: "backend/app/api/admin_capacity.py"
      provides: "GET /api/admin/capacity — admin-only matrix, reuses require_admin"
      contains: "Depends(require_admin)"
    - path: "frontend/src/providers/ServiceBusyProvider.tsx"
      provides: "app-level busy-modal owner subscribing to the api.ts capacity-rejection seam"
      contains: "host_capacity_exhausted"
  key_links:
    - from: "backend/app/api/run_commands.py launch / resume / revision / user_message"
      to: "backend/app/services/capacity_state.py evaluate_admission"
      via: "_require_host_capacity(current_user) called from the same seam as _require_tier_entitlement"
      pattern: "_require_host_capacity"
    - from: "frontend/src/lib/api.ts request()"
      to: "frontend/src/providers/ServiceBusyProvider.tsx"
      via: "module-level onCapacityRejected listener registry, fired on 503 + code host_capacity_exhausted"
      pattern: "onCapacityRejected"
    - from: "backend/app/main.py lifespan"
      to: "backend/app/services/host_metrics.py refresh_snapshot"
      via: "asyncio.create_task(_capacity_poll_loop()) with asyncio.to_thread offload, mirroring _sandbox_sweep_loop"
      pattern: "_capacity_poll_loop"
---

# 014 — Host Capacity Matrix + Capacity Admission Gate

## 1. Objective

Two connected capabilities:

1. **Admin capacity matrix** — an admin-only tab listing the EC2 instances this
   environment runs on, with live CPU and memory utilisation per instance.
2. **Capacity admission gate** — when CPU or memory on the host serving a
   request crosses a configured threshold (75% as requested), *new expensive
   work* is refused with a clear "service is busy" modal, while everything
   already in flight keeps working.

Metrics come from CloudWatch using the boto3 **default credential chain** (the
EC2 instance profile in deployed environments, `AWS_PROFILE`/SSO locally) —
matching how Bedrock and Cognito already authenticate. No credentials are
introduced anywhere.

---

## 2. Ground truth verified during planning

Everything below was read, not assumed. It changes the shape of the feature
materially, so it is recorded before the design.

### 2.1 The metrics already exist — no new agent, no new dependency

`infra/scripts/reconcile-host-config.sh` installs and configures the CloudWatch
Agent on the host today. Its config publishes, every **60 seconds**, to
namespace `VelocityAI/${ENV_TITLE}` (e.g. `VelocityAI/Prod`):

| Series | Notes |
|---|---|
| `cpu_usage_idle`, `cpu_usage_user`, `cpu_usage_system`, `cpu_usage_iowait` | `totalcpu: true` |
| `mem_used_percent`, `mem_available` | the memory half this feature needs |
| `used_percent`, `inodes_free` | disk, on `/` and `/var/lib/postgresql` |
| `swap_used_percent`, net/diskio counters | |

Dimensions appended by the agent: **`InstanceId`, `InstanceType`**.

This is the single most important finding: **memory is already available.**
Memory is not an `AWS/EC2` metric — the hypervisor cannot see guest memory — so
without the agent the memory half of this request would have been impossible
without adding `psutil` (which is not a declared backend dependency). It is
already solved.

`boto3==1.43.2` is already pinned (`backend/pyproject.toml:23`), and it ships
the `ec2` and `cloudwatch` clients. **This feature adds zero dependencies.**

### 2.2 CPU: `cpu_usage_user` is the wrong series to threshold on

`infra/terraform/modules/monitoring/main.tf:473` alarms on `cpu_usage_user`.
That is *user-mode* CPU only — it excludes `system` and `iowait`, so a host
pinned at 95% busy by system time and I/O wait reads as quiet. For an admission
gate that would be a silent miss.

**Canonical CPU-used % for this feature is `100 - cpu_usage_idle`.** It is
derived in one `GetMetricData` expression, costs nothing extra, and is the only
definition that captures all busy time. The matrix will also surface the
`user`/`system`/`iowait` split as secondary detail, because when the gate
engages the first question an admin asks is "busy doing what".

### 2.3 The requested 75% is *tighter* than what already pages ops — confirmed anyway

Existing alarm defaults (`modules/monitoring/variables.tf:66,72`):

| Signal | Existing alarm threshold | Periods |
|---|---|---|
| CPU | **80%** | 3 × 300 s (15 min sustained) |
| Memory | **85%** | 2 × 300 s (10 min sustained) |

This means a 75/75 gate refuses new work *below* the level ops currently
considers alarm-worthy — the operator confirmed both thresholds at 75%
explicitly (§10 Resolutions, Q1), accepting refuse-early / page-later as the
intended posture rather than parity with the alarms. CPU and memory remain
**separately** configurable settings regardless, so either can be tuned
independently once the admin matrix has shown real load (see D-10's rollout).

### 2.4 Admin already exists — reuse, do not invent

- `users.is_admin` column (`backend/app/models/user.py:44`), Cognito group
  `flowin-admins` authoritative over it (`app/core/entitlements.py:98`).
- `require_admin` dependency, **including the admin-MFA gate**
  (`backend/app/api/admin.py:57`), mounted router `/api/admin`
  (`app/main.py:373`).
- `/admin` page with a client-side `getMe().is_admin` guard
  (`frontend/src/app/admin/page.tsx:158-169`) and an `isAdmin`-gated nav item
  (`AppHeader.tsx:560-570`).

No new role model, no new auth surface.

### 2.5 The gate has an exact precedent to mirror

`_require_tier_entitlement` (`run_commands.py:2301`) is *the* "refuse to start
work for this caller" helper. It is one function called from one shared seam
covering launch / resume / revision, and it rejects through `_reject(...)`
(`run_commands.py:2285`), which emits the structured triple
`{"detail": {"error", "code", "recoverable"}}`. The new gate is a sibling of
that function, called from the same seam, with a distinct `code`. Nothing new
is invented.

### 2.6 Three real defects/absences this feature depends on

1. **The frontend launch path swallows non-2xx.** In
   `RunConnectionProvider.tsx:385-428` the `!res.ok` guard sits *inside*
   `if (runId)`. The launch branch (`runId === null`) has no status check, so a
   503 on `POST /api/runs` falls through and returns `null` — a dead UI with no
   error. **The busy modal cannot fire on launch until this is fixed.** It is a
   prerequisite task, not a nice-to-have.
2. **`Retry-After` is not readable by the browser.** CORS `expose_headers` lists
   only `X-Total-Count` (`app/main.py:317-322`). A `Retry-After` header is
   invisible to `fetch` until it is added.
3. **There is no dialog primitive.** No `Modal`, no `Dialog`, no focus trap
   anywhere in the frontend; at least nine hand-rolled modal copies exist and two
   of them (`admin/page.tsx:398`, `:463`) are missing
   `role="dialog"`/`aria-modal` entirely. This feature needs an accessible modal,
   so it builds the first real one.

### 2.7 Constraints that shape placement

- **Import boundaries** (`backend/pyproject.toml:303-357`): `agents.capabilities`,
  `agents.workflows`, `agents.runtime` may not import `app`. The adapter needs
  `settings`, so it lives **app-side**. `app/services/` it is.
- **CI offline guards** (`backend/tools/ci/offline_guards.py`) block `boto3` at
  module scope. Import it **function-locally**, exactly as `cognito._client()`
  does.
- **`aws_iam_role_policies_exclusive`** (`modules/iam/main.tf:265-283`) locks the
  inline-policy set. A new `aws_iam_role_policy` that is **not** added to that
  list is silently deleted on the next apply. This has a comment warning about
  it; the plan honours it.
- **INV-3 characterization goldens are safe.** They drive
  `agents.execution_engine` directly and never construct the FastAPI app, and
  there is no route-table or OpenAPI snapshot test. A new router and a new API
  dependency cannot break them. They *would* break if capacity data were
  emitted as an engine event — so it deliberately is not.
- **SC-001 / INV-1**: the gate reads no workflow name and adds no
  `pipeline_type` branch. It is uniform across every workflow.

---

## 3. Extension-point analysis

```
FEATURE TYPE: new API surface (admin read) + new admission gate + new FE surface

EXTENSION POINT
  - Gate:    _require_tier_entitlement's seam in run_commands.py (:2301, called
             from launch/resume/revision) — the established "deny before mint"
             point. New sibling: _require_host_capacity.
  - Admin:   require_admin (admin.py:57) + the /api/admin prefix. Precedent for
             multiple routers on one prefix already exists (/api/runs has four).
  - Poller:  the _sandbox_sweep_loop pattern in main.py's lifespan (:188-226) —
             interval from settings, blocking work via asyncio.to_thread, broad
             non-fatal except, cancel-then-await after yield.
  - Client:  cognito._client() (core/cognito.py:251) — lazy function-local boto3
             import, region from settings, no explicit credentials.
  - FE tab:  ui/Tabs.tsx into the existing /admin page (reuses its is_admin gate).
  - FE modal: new provider in layout.tsx's stack, modelled on
             RunConnectionProvider (context + inert default + subscriber fanout).

CONSTRAINTS ON THE DESIGN
  INV-1  (kernel workflow-agnostic):     not affected — nothing under
                                         agents/execution_engine/ is touched.
  INV-2  (no per-run state on singleton): not affected — the snapshot is
                                         host-scoped, not run-scoped.
  INV-3  (event/behaviour parity):        not affected — no engine event is added
                                         or changed; goldens untouched.
  INV-12 (move-don't-copy):               confirmed clean — reuses require_admin,
                                         _reject, the Tabs primitive, and the
                                         sweep-loop pattern rather than forking.
  INV-13 (deepagents only):               not affected — no agent involved.
  SC-001 (zero engine edits):             confirmed — this feature edits no file
                                         under agents/.
  LOCK-B (no WS run frames):              honoured — capacity is polled over
                                         REST, not pushed over a socket.
```

Deliberately **not** built: a `Protocol` port for the metrics backend. There is
exactly one backend (CloudWatch) and no second one in view. The concrete
`app/services/host_metrics.py` factory-function shape matches `model_factory`;
a port can be extracted when a second backend actually appears (YAGNI).

---

## 4. Architecture

```
                       ┌── background, every HOST_CAPACITY_POLL_SECONDS (30s) ──┐
                       │                                                        │
  main.py lifespan ───►│ _capacity_poll_loop                                    │
                       │   await asyncio.to_thread(                             │
                       │     host_metrics.collect_snapshot)  ──► boto3          │
                       │                                        ec2:DescribeInstances
                       │                                        cloudwatch:GetMetricData
                       │   capacity_state.publish(snapshot)                     │
                       └────────────────────┬───────────────────────────────────┘
                                            │  single atomic assignment of a
                                            │  frozen dataclass (no lock needed
                                            ▼  on the read path)
                              capacity_state._SNAPSHOT
                                            │
              ┌─────────────────────────────┴──────────────────────────────┐
              │                                                            │
   evaluate_admission(snapshot, now)                        GET /api/admin/capacity
   pure function, zero I/O                                  (require_admin)
              │                                                            │
   _require_host_capacity()  ──► 503 + Retry-After          matrix rows + gate state
   in run_commands.py / handoff.py                                         │
              │                                                            ▼
              ▼                                            /admin → Machines tab
   lib/api.ts request() sees 503 + code                    (polls every 15s, pauses
              │                                             when tab hidden)
              ▼
   ServiceBusyProvider → Modal "Service is busy"
```

Two properties this shape buys, and the reasons they matter:

- **The request path never touches AWS.** boto3 is synchronous; a
  `GetMetricData` call inside `launch_run` would add latency to every launch and,
  on a CloudWatch hang, would occupy the event loop and stall in-flight SSE
  streams. The gate is an in-memory struct read — microseconds, cannot fail.
- **A monitoring outage degrades to "allow", not "down".** See D-03.

---

## 5. Decisions

Each of these is a scenario that will occur in production. They are decided
here rather than discovered later.

### D-01 — Gate only *new expensive work*. Never gate release or teardown.

"Don't allow any operation" taken literally would be actively harmful. Three of
the endpoints in scope *reduce* load or *unstick* users:

**GATED** (each starts new agent work, i.e. new token spend and new CPU):

| Endpoint | File |
|---|---|
| `POST /api/runs` (launch) | `run_commands.py:2459` |
| `POST /api/runs/{id}/resume` | `run_commands.py:607` |
| `POST /api/runs/{id}/revisions` | `run_commands.py:3606` |
| `POST /api/runs/user_message` (free chat) | `run_commands.py:3875` |
| `POST /api/runs/{id}/messages` — concierge + revision channels only | `run_commands.py:1563` |
| `POST /api/handoff/{token}/start` | `handoff.py:269` |
| `POST /api/runs/export-pptx` (forks a Node renderer) | `runs.py:369` |

**NEVER GATED**, with the reason:

| Endpoint | Why it must stay open |
|---|---|
| `POST /api/runs/{id}/cancel` | It *frees* capacity. Blocking it is perverse. |
| `POST /api/runs/{id}/gate` | Releases a paused run that is already holding a sandbox and has already been paid for. Blocking strands it at the gate indefinitely. |
| `POST /api/runs/{id}/answers` | Same as above, for clarify. |
| `GET /api/runs/{id}/events/stream` | Blocking a reconnect *blinds a running run*. Costs almost no CPU. |
| `POST /api/runs/{id}/messages` — steering channel | Cheap; steering an existing run does not start new work. |
| every `GET`, all of `/api/auth/*`, `/health`, `/api/admin/*` | Reads and diagnosis must work *especially* under load. |

### D-02 — Admins are exempt

An admin locked out by the condition they are trying to diagnose is a dead end.
The exemption reads `current_user.is_admin` (the advisory DB column), not a live
`cognito:groups` read, for one reason: the launch handlers take
`Depends(get_current_user)` and threading `get_current_principal` through them
would change signatures that ~25 existing tests override. `_require_tier_entitlement`
already accepts exactly this staleness window and documents why (refreshed on
every login; every admin role write stamps `tokens_valid_from` **and** calls
`AdminUserGlobalSignOut`). The exemption is a throttle bypass, not a privilege —
worst case a just-demoted user launches during a busy window. Upgrading to a
live principal read is recorded as follow-up hardening, mirroring the note
already on `require_admin`.

### D-03 — Fail **open** when capacity is unknown

This inverts the repo's usual fail-closed posture, deliberately.

Unknown happens for mundane reasons: CloudWatch throttles, the instance role is
missing the new permission, the CloudWatch agent has degraded (a documented,
handled state — `reconcile-host-config.sh::degrade_agent`), a freshly replaced
instance has no datapoints yet, or the process is running locally with no IMDS.

Fail-closed would turn *any* of those into "nobody can use the product". That
converts a monitoring problem into a total outage, and the monitoring dependency
becomes strictly less reliable than the thing it protects. The gate is a
courtesy throttle, not a security control, so:

- unknown ⇒ **allow**, log once per transition at WARNING (not per request),
- the admin matrix reports `gate: "blind"` with the reason, so the blindness is
  visible rather than silent,
- the blind state is worth an alarm later; it is out of scope here.

### D-04 — Bound staleness; never act on an old datapoint

The agent publishes every 60 s and CloudWatch adds 1–3 min of its own lag for
custom metrics, so a reading is **inherently 1–3 minutes old**. Consequences,
both accepted: a spike is detected late, and recovery is detected late.

What is *not* accepted is acting on a very old reading. A datapoint older than
`HOST_CAPACITY_MAX_STALENESS_SECONDS` (default **300**) is treated as unknown
⇒ fail open (D-03). Without this, a poller that has been failing for an hour
would keep gating the product on an hour-old spike.

The matrix always shows the reading's age. An admin looking at a number with no
age cannot tell live from frozen.

### D-05 — Hysteresis, or the modal will flicker

A bare `>= 75` test against a 60 s series oscillating around the threshold
produces block / allow / block / allow, and the user sees the busy modal appear
and vanish. Three mechanisms, all mirroring conventions already in the alarm
config:

- **Engage** at `>= HOST_CAPACITY_{CPU,MEM}_THRESHOLD_PERCENT` (75 / 75 — both
  confirmed by the operator, §10 Resolutions Q1).
- **Clear** only below `HOST_CAPACITY_CLEAR_MARGIN_PERCENT` below the threshold
  (default 10, i.e. clear at < 65). Classic hysteresis band.
- **Confirm** with `HOST_CAPACITY_BREACH_DATAPOINTS` consecutive breaching
  datapoints (default 2 — the same "sustained, not a burst" logic as the
  existing alarms' `evaluation_periods`), and hold an engaged gate for at least
  `HOST_CAPACITY_MIN_BLOCK_SECONDS` (default 60) so one spike cannot produce a
  three-second modal.

All of this lives in `evaluate_admission`, a pure function of
`(snapshot, previous_state, now)`. That is what makes it testable without
touching AWS, and property-testable with `hypothesis` (already a pinned dev dep).

### D-06 — Which instance decides: `self` (confirmed single-instance today)

`HOST_CAPACITY_GATE_SCOPE`:

- `"self"` (**default**) — the instance serving the request. Its CPU is what
  actually constrains this request. Self-id resolved once at startup from
  IMDSv2 (`PUT /latest/api/token` then `GET /latest/meta-data/instance-id`, 1 s
  timeout), falling back to the configured override (D-07), then to unknown ⇒
  D-03.
- `"fleet_worst"` — worst instance in the fleet. Documented for a future
  load-balanced fleet; not the default, because on a fleet it would let one hot
  node gate every node.

The operator confirmed the fleet is single-instance today (§10 Resolutions,
Q2), matching what `modules/compute/main.tf` already shows (exactly one
`aws_instance.app`) — so `self` == the fleet and the matrix renders one row.
`fleet_worst` and the multi-instance sharding concerns noted in the original
Q2 stay explicitly out of scope for this plan; revisit if a fleet is ever
actually provisioned.

### D-07 — Instance discovery: tag-based by default, operator-supplied ID as an env-var override

The operator will supply the EC2 instance ID **as an environment variable**
(§10 Resolutions, Q3) rather than it being hardcoded in `.tf`/`.py` source,
which is exactly the shape this decision already required — configuration,
not code, because `aws_instance.app` is replaced by Terraform on any AMI or
user-data change and a literal ID in source would go stale silently.

1. `HOST_CAPACITY_INSTANCE_IDS` — optional comma-separated allow-list, sourced
   from the environment (locally: `backend/.env`; deployed: SSM
   `/velocityai/<env>/HOST_CAPACITY_INSTANCE_IDS` → `app.env`, wired in Wave 4
   CI/CD — see §7 Wave 4 and §10 Resolutions). **Highest precedence** — set it
   and discovery is skipped entirely.
2. Otherwise discover via `ec2:DescribeInstances` filtered on
   `tag:Project=velocityai`, `tag:Environment=<settings.ENV>`, and
   `instance-state-name=running`. Those tag keys are set by the provider
   `default_tags` block (`infra/terraform/*/providers.tf`) so they are reliably
   present on every project resource. This stays the *default* path — the
   operator confirmed discovery should remain default with the supplied ID
   as override/cross-check only, not the other way round.
3. Neither resolves ⇒ empty matrix, gate blind (D-03).

Inventory is cached separately from metrics with a much longer TTL
(`HOST_CAPACITY_INVENTORY_TTL_SECONDS`, default 300): the instance list changes
rarely, the metrics change every minute, and `DescribeInstances` is the more
expensive call.

**Cross-check task (Wave 1):** when `HOST_CAPACITY_INSTANCE_IDS` is set, log a
one-time WARNING if tag-based discovery (run once, independent of the override,
purely for comparison) disagrees with the configured ID — this is what makes
the override useful as a *cross-check* rather than a silent divergence.

### D-08 — Admission control only. Running work is never touched.

The gate refuses to *start* work. It never pauses, cancels, or degrades a run
already in flight — that would discard tokens already spent, which is the
opposite of the goal. A run launched at 74% that drives the host to 90% runs to
completion; only the *next* launch is refused.

### D-09 — Response contract

```
HTTP 503 Service Unavailable
Retry-After: <seconds>
{
  "detail": {
    "error": "The service is busy right now. Please try again in a few minutes.",
    "code": "host_capacity_exhausted",
    "recoverable": true,
    "retry_after_seconds": 120,
    "signals": [{"name": "memory", "value": 81.4, "threshold": 75.0}]
  }
}
```

- Reuses `_reject(...)`'s triple verbatim, so the existing frontend `ApiError`
  already surfaces it intact on `err.detail`.
- 503 not 429: this is server capacity, not per-client rate limiting. A 429
  would tell the client *it* is at fault.
- `signals` is a **list**, so disk or connection pressure can be added later
  without a contract change — but only CPU and memory populate it now.
- `signals` values are numbers about the host. They are only sent to the caller
  who was refused, and they are the same class of information as a "server busy"
  page. If even that is unwanted, dropping `signals` from the non-admin response
  is a one-line change; the modal does not require it.

### D-10 — Default **off**

`HOST_CAPACITY_GATE_ENABLED = False`. A feature capable of refusing every launch
must not switch itself on at deploy time. Rollout: ship it off, watch the matrix
in dev/staging for real load, then enable per environment. The matrix itself
ships **on** (read-only, harmless, and it is the evidence needed to choose
thresholds).

### D-11 — One poller per process

Each uvicorn worker runs its own poller and its own hysteresis state. On a
multi-worker deployment that means N× the CloudWatch calls and workers that can
briefly disagree about the gate. This is consistent with the existing
single-process assumptions the codebase already documents and relies on
(`_PIPELINE_QUEUES`, the JWKS cache, `websocket_handoff.py:9-12`), so it is
accepted, not solved. `HOST_CAPACITY_POLL_SECONDS` exists so the call volume can
be tuned if worker count ever rises.

---

## 6. Settings (all new, all on `Settings` in `app/core/config.py`)

`Settings` is configured `extra = "ignore"`, so **every** field must be declared
or reads raise `AttributeError` at runtime — the exact trap documented at
`config.py:140-142`.

| Setting | Default | Purpose |
|---|---|---|
| `HOST_CAPACITY_ENABLED` | `True` | Master switch for collection (matrix + poller). |
| `HOST_CAPACITY_GATE_ENABLED` | `False` | Enforce the gate. Off by default (D-10). |
| `HOST_CAPACITY_CPU_THRESHOLD_PERCENT` | `75.0` | Engage threshold, CPU (`100 - cpu_usage_idle`). |
| `HOST_CAPACITY_MEM_THRESHOLD_PERCENT` | `75.0` | Engage threshold, memory (`mem_used_percent`). |
| `HOST_CAPACITY_CLEAR_MARGIN_PERCENT` | `10.0` | Hysteresis band (D-05). |
| `HOST_CAPACITY_BREACH_DATAPOINTS` | `2` | Consecutive breaching datapoints to engage. |
| `HOST_CAPACITY_MIN_BLOCK_SECONDS` | `60` | Minimum engaged duration. |
| `HOST_CAPACITY_MAX_STALENESS_SECONDS` | `300` | Older than this ⇒ unknown ⇒ allow (D-04). |
| `HOST_CAPACITY_POLL_SECONDS` | `30` | Poller interval. |
| `HOST_CAPACITY_INVENTORY_TTL_SECONDS` | `300` | `DescribeInstances` cache TTL. |
| `HOST_CAPACITY_METRIC_NAMESPACE` | `""` | Empty ⇒ derive `VelocityAI/{ENV.title()}` to match the agent config. |
| `HOST_CAPACITY_INSTANCE_IDS` | `""` | Comma-separated override (D-07). |
| `HOST_CAPACITY_GATE_SCOPE` | `"self"` | `self` \| `fleet_worst` (D-06). |
| `HOST_CAPACITY_RETRY_AFTER_SECONDS` | `120` | `Retry-After` value. |
| `HOST_CAPACITY_AWS_CONNECT_TIMEOUT` | `5` | botocore connect timeout. |
| `HOST_CAPACITY_AWS_READ_TIMEOUT` | `10` | botocore read timeout. |

Note the timeouts: **not** the Bedrock `read_timeout=600` config. A metrics call
must fail fast; a hung one must never wedge the poller.

---

## 7. Waves and tasks

### Wave 0 — decisions (resolved 2026-09-08; kept as a record, no remaining code impact)

All three were blocking before the operator answered them (§10 Resolutions).
None are blocking now — recorded here only so the wave numbering in this plan
matches its own history.

| # | Task | Resolution |
|---|---|---|
| 0.1 | Threshold intent given §2.3 (75% gates below the 80/85 that pages ops); memory specifically. | CPU 75%, memory 75% — confirmed as-is (§10 Q1). |
| 0.2 | Fleet size (§10 Q2). | Single instance today (`self` scope stands, D-06). |
| 0.3 | `signals` numbers on a refused non-admin's 503 body (D-09). | Keep actual numbers (§10 Q4). |

### Wave 1 — backend read path (matrix)

| # | Task | Notes |
|---|---|---|
| 1.1 | Add the 16 settings to `Settings` + the derived-namespace `model_validator`. | `extra="ignore"` trap. |
| 1.2 | `app/services/host_metrics.py`: `_client(service)` seam (lazy boto3 import, region from `settings.AWS_REGION`, tight botocore `Config`, double-checked-lock cache mirroring `otel_tracing._get_tracer`). | Patchable seam is what makes 1.7 possible without `moto`. |
| 1.3 | `resolve_instance_ids()` — override → tag discovery → empty. `resolve_self_instance_id()` — IMDSv2 with 1 s timeout, cached, never raises. | D-06, D-07. |
| 1.4 | `collect_snapshot()` — one `GetMetricData` for all instances × {`100 - cpu_usage_idle`, `mem_used_percent`, cpu split}; handles `NextToken`, empty result sets, partial results, `ClientError`/`EndpointConnectionError`/`NoCredentialsError` → returns a snapshot with `unknown` rows rather than raising. | Never raises to the caller. |
| 1.5 | `app/services/capacity_state.py` — frozen `InstanceCapacity` / `CapacitySnapshot` / `AdmissionDecision`; `publish()` (single atomic assignment); `current()`; `evaluate_admission(snapshot, prev, now)` pure. | Zero boto3 import here — that is the point. |
| 1.6 | `app/api/admin_capacity.py` — `GET /api/admin/capacity`, `Depends(require_admin)`; returns rows + `gate` block (`enabled`, `state: allowing\|blocking\|blind`, thresholds, `reason`). No private IPs. Register in `main.py`. | Reuses the MFA-carrying guard. |
| 1.7 | `_capacity_poll_loop` in the lifespan: `asyncio.to_thread(collect_snapshot)`, broad non-fatal except, cancel-then-await after `yield`; skipped entirely when `HOST_CAPACITY_ENABLED` is false. | Copy `_sandbox_sweep_loop`'s shape. |
| 1.8 | Tests: adapter (`patch.object(_client)` + `MagicMock` + `call_args.kwargs`), decision logic (unit + `hypothesis`), endpoint (bare `FastAPI()` + `dependency_overrides`), non-admin → 403, blind-state rendering. | |

### Wave 2 — the gate

| # | Task | Notes |
|---|---|---|
| 2.1 | `_require_host_capacity(current_user)` in `run_commands.py`, beside `_require_tier_entitlement`: disabled/admin/unknown → return; else `_reject("host_capacity_exhausted", ..., http_status=503, recoverable=True, retry_after_seconds=..., signals=[...])`. | No `pipeline_type` branch (INV-1). |
| 2.2 | Call it from the launch / resume / revision shared seam + `user_message_shim` + the concierge/revision channels of `post_message`. **Do not** touch cancel / gate / answers / steering / SSE. | D-01 is the review checklist. |
| 2.3 | Gate `POST /api/handoff/{token}/start`. Note it uses plain-string details, not the `_reject` triple — emit the triple here so the FE sees one contract. | Easy to miss; it is outside `/api/runs`. |
| 2.4 | Attach `Retry-After` to the 503 and add it to CORS `expose_headers` in `main.py`. | Invisible to `fetch` otherwise. |
| 2.5 | Tests: each gated endpoint 503s with the right code when engaged; each exempt endpoint still 2xx while engaged; admin exempt; unknown ⇒ allow; disabled ⇒ allow. | The exempt-endpoint assertions are the regression guard on D-01. |

### Wave 3 — frontend

| # | Task | Notes |
|---|---|---|
| 3.1 | **Fix** `RunConnectionProvider.sendCommand`: hoist the `!res.ok` check above `if (runId)` so the launch branch throws. | Prerequisite (§2.6.1). |
| 3.2 | `lib/api.ts`: `adminListCapacity(token)` (explicit-token convention, beside the other admin calls) + a module-level `onCapacityRejected` listener registry fired from `request()` on 503 + `code === "host_capacity_exhausted"`. Keeps `api.ts` React-free, as it is today. | Single detection seam. |
| 3.3 | `components/ui/Modal.tsx` — first real dialog: `role="dialog"`, `aria-modal`, `aria-labelledby`, `window` keydown Escape with cleanup, initial focus, focus **cycle**, focus **restore** on close. Tokens only (`--scrim`, `--elevation-modal`, `--radius-card`). | Nine duplicates exist; do not retrofit them here (YAGNI) — just make the primitive available. |
| 3.4 | `providers/ServiceBusyProvider.tsx` — context + inert default + subscriber fanout, modelled on `RunConnectionProvider`; mounted in `layout.tsx`'s stack. Renders the busy modal with the retry hint; coalesces repeated rejections into one modal. | |
| 3.5 | `hooks/useCapacityMatrix.ts` — `setInterval` poll (15 s), `clearInterval` cleanup, paused on `document.visibilityState !== "visible"`, discriminated-union state `loading \| error \| ready \| empty`. | **Polling, not SSE** — BUG-013: long-lived streams saturate the browser's ~6-socket-per-origin pool and starve REST. Upstream data only changes every 60 s anyway. |
| 3.6 | `components/admin/CapacityMatrix.tsx` — semantic `<table>` mirroring `admin/page.tsx:356-395` (incl. its loading / empty / data triad), columns: Instance · Type · State · CPU % · Memory % · Reading age · Gate. Severity colour via `var(--severity-low\|medium\|high\|critical)` arbitrary values (those four vars are **not** in `@theme inline`, so `text-severity-high` does not exist). Show the "as of" age always. | No raw hex — a token-layer test enforces this. |
| 3.7 | Add `<Tabs>` to `/admin/page.tsx` with two panels — *Users* (the existing table, moved into a panel) and *Machines* (the new matrix). Existing `is_admin` guard unchanged. |
| 3.8 | Tests: `CapacityMatrix` (mirror `admin.reskin.test.tsx` — `vi.hoisted` mocks, `next/navigation` stub, the `motion/react` Proxy mock, role-based queries); `ServiceBusyProvider` (503 → modal, Escape closes, focus restored); `Modal` a11y; Playwright `mocked` spec registering `page.route("**/api/runs", 503)` **after** `dashboard.goto()` (handlers match in reverse registration order). | Coverage thresholds are 80% and enforced. |

### Wave 4 — infra (IAM)

| # | Task | Notes |
|---|---|---|
| 4.1 | `modules/iam/policies/capacity-read.json`: `cloudwatch:GetMetricData` + `ec2:DescribeInstances`, `Resource: "*"` (neither action supports resource-level ARNs), with the `aws:RequestedRegion` condition the sibling `cw_agent` policy already uses. | Least privilege within what the API allows. |
| 4.2 | New `aws_iam_role_policy "capacity_read"` **and add its name to `aws_iam_role_policies_exclusive.policy_names`**. | Omitting step two silently deletes the policy on next apply. |
| 4.3 | Update `modules/iam/README.md`; run `terraform fmt -check -recursive`, `validate`, `checkov`, `trivy config`. | Per the terraform gate order. |
| 4.4 | Document the enable procedure in `infra/terraform/RUNBOOK.md`: apply IAM → confirm the matrix populates → set thresholds → enable the gate per environment. | D-10 rollout. |

### Wave 4 — CI/CD wiring (new — resolves §10 Q3's "supply the id as an env var")

The operator will provide the EC2 instance ID as an environment variable
(§10 Resolutions, Q3). This repo's existing pipeline for exactly that shape —
a per-environment plain-config value reaching the running container — is
`deploy.yml`'s "Push config to SSM Parameter Store" step, so `HOST_CAPACITY_*`
rides that same rail rather than inventing a new one. Every hop below already
exists for `BEDROCK_MODEL_ID`/`CORS_ORIGINS`/etc.; this wave is additive rows,
not new mechanism.

```
GitHub Environment variable (per env: dev/stage/prod)
        │  vars.HOST_CAPACITY_INSTANCE_IDS, vars.HOST_CAPACITY_GATE_ENABLED, ...
        ▼
deploy.yml "Push config to SSM Parameter Store" step
        │  put_param "HOST_CAPACITY_INSTANCE_IDS" "$HOST_CAPACITY_INSTANCE_IDS" \
        │            "String" "delete-if-empty"
        ▼
SSM Parameter Store  /velocityai/<env>/HOST_CAPACITY_INSTANCE_IDS  (+ siblings)
        │
        ▼
velocityai-load-secrets (bootstrap-ec2.sh, runs as ExecStartPre on every start)
        │  case "$rel" in ... HOST_CAPACITY_*) emit "$rel" "$value" ;; ...
        ▼
/etc/velocityai/app.env  →  docker compose  →  backend container env
        ▼
Settings (pydantic-settings reads process env; extra="ignore" means each
          HOST_CAPACITY_* field must already be declared on Settings — Wave 1)
```

| # | Task | Notes |
|---|---|---|
| 4.5 | Add every `HOST_CAPACITY_*` setting from §6 as a **String** `put_param` call in `deploy.yml`'s "Push config to SSM Parameter Store" step, sourced from `vars.HOST_CAPACITY_*` GitHub Environment variables, `delete-if-empty` policy (so an unset GitHub var removes the SSM override and the app's own default in `Settings` applies — never `required`, since every field already has a safe default). | Mirrors the existing `BEDROCK_MODEL_ID` block verbatim; **none** of these are secrets, so all `String`, never `SecureString`. |
| 4.6 | Add the matching `case` arm in `infra/scripts/bootstrap-ec2.sh`'s `velocityai-load-secrets` loader (the `SECRET_KEY|ACCESS_TOKEN_EXPIRE_HOURS|...)` pattern list, ~line 833) so each `HOST_CAPACITY_*` SSM key is emitted into `app.env` verbatim. **Do not** namespace these under a sub-prefix like `llm/` — they map 1:1 to their `Settings` field name, so the plain top-level key name already matches, unlike `llm/region → AWS_REGION`. | Omitting this makes every `HOST_CAPACITY_*` SSM parameter silently dropped with a WARN on every app start (the documented, load-bearing "unknown keys" behavior) — this is the step that is easy to forget. |
| 4.7 | Add a new row for each `HOST_CAPACITY_*` variable to `docs/GITHUB_CICD_SETUP.md` §3.2's Variables table and §10's config-key-mapping reference table (`SSM Key → Env var → Pushed by`). | Keeps the two hand-authored docs the operator actually reads in sync with 4.5/4.6 — this doc is what a future operator copies commands from. |
| 4.8 | Add a `# ---- Host capacity gate (optional) ----` block to `app.env.example` documenting every `HOST_CAPACITY_*` var with its default and a one-line purpose, so local dev can flip the gate on without reading the plan. | Matches the existing `app.env.example` style (commented defaults, no real values). |
| 4.9 | Confirm the `.github/environments/{dev,staging,prod}.json` files need **no** change — they gate *who* can deploy (branch policy, reviewers), not *which variables* exist; `HOST_CAPACITY_*` values are set as ordinary Environment variables through the GitHub UI/API per §4.5, the same way `BEDROCK_MODEL_ID` is today. | No `.json` file edit is required — verified by reading `dev.json`/`prod.json`: they contain no variable declarations, only protection rules. |
| 4.10 | End-to-end check per environment after 4.5–4.8 land: set `vars.HOST_CAPACITY_INSTANCE_IDS` on the `dev` GitHub Environment to the operator-supplied ID, run `deploy.yml` against `dev`, then confirm `GET /api/admin/capacity` shows that instance and that the Wave-1 cross-check task (D-07) logs no WARNING (i.e. tag discovery agrees with the supplied ID). | This is the actual "send me the ID" delivery — as a GitHub Environment variable, never pasted into source or Terraform. |

---

## 8. Test plan

Following the repo's actual conventions — **`moto` is not available** and adding
it would need a `pyproject.toml` + `uv.lock` + `requirements-dev.txt` change
that `test_dependency_lock_contracts.py` polices.

**Backend unit — decision logic (no mocking at all).** `evaluate_admission` is
pure, so: below threshold → allow; at threshold with 1 datapoint → allow
(confirmation not met); 2 datapoints → block; drop to 70 → still block
(hysteresis band); drop to 64 → allow; engaged for < `MIN_BLOCK_SECONDS` → still
block; datapoint older than the staleness bound → unknown → allow; `None`
memory with breaching CPU → block on CPU alone; both `None` → allow + blind.

**Backend property (`hypothesis`).** Over arbitrary datapoint sequences and
timestamps: the decision never blocks when every reading is stale; blocking
implies at least one signal at-or-above its threshold within the staleness
window; the function never raises. `@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])`
if combined with a fixture.

**Backend unit — adapter.** `patch.object(host_metrics, "_client", return_value=MagicMock())`,
then assert on `call_args.kwargs`: correct `Namespace`, `MetricDataQueries`
expression for `100 - cpu_usage_idle`, `InstanceId` dimension, UTC window.
Failure shapes via hand-built `botocore.exceptions.ClientError` (the
`test_llm_errors.py` idiom) for `AccessDenied`, `Throttling`,
`EndpointConnectionError`, `NoCredentialsError` — each must return an unknown
snapshot, never raise. Empty `MetricDataResults`. `NextToken` pagination.

**Backend API.** Bare `FastAPI()` + `include_router` + `dependency_overrides`
(the `test_runs_api.py` pattern): admin 200 / non-admin 403 on the matrix; each
gated endpoint 503-with-code while engaged; **each exempt endpoint 2xx while
engaged** (the D-01 regression guard); admin exempt from the gate.

**Time.** No `freezegun` in this repo. Inject `now` into `evaluate_admission`
and pass explicit timestamps — the convention `test_cognito_verifier.py:370-380`
documents (monotonic-clock resolution on Windows makes real-clock TTL tests
flaky).

**Async.** `asyncio_mode` is **strict** (unset in config), so every async test
needs an explicit `@pytest.mark.asyncio`.

**Frontend.** Vitest + RTL, `vi.mock` (no MSW), the `motion/react` Proxy mock
copied verbatim, role-based queries. Playwright `mocked` project, per-spec
`page.route` registered after navigation.

**Gates that must be green before done:**

```
# backend/
uv run ruff check . ; uv run ruff format --check . ; uv run pyright
uv run lint-imports          # must stay 4 kept / 0 broken — run from backend/
uv run vulture app agents    # min_confidence 80 — an unwired helper fails this
uv run bandit -c pyproject.toml -r app agents -ll
uv run pytest                # coverage fail_under = 80
uv run pytest tests/agents/test_characterization_*.py   # SNAPSHOT_UPDATE unset
uv run pytest tests/agents/test_banned_patterns.py tests/agents/test_sse_cutover_banned_patterns.py

# frontend/
npm run lint ; npm run typecheck ; npm run test ; npm run build ; npm run e2e

# infra/terraform/
terraform fmt -check -recursive ; terraform validate ; checkov -d . ; trivy config .
```

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The gate blocks all launches after deploy. | Default off (D-10); admin exempt (D-02); unknown allows (D-03); staged enable per environment. |
| R2 | CloudWatch agent degrades → memory goes blind → gate silently stops protecting. | Blind state is surfaced in the matrix and logged at WARNING; CPU falls back to `AWS/EC2 CPUUtilization`. Memory has no hypervisor-side fallback — this is a real, irreducible limitation of the approach and must be understood by whoever relies on the gate. |
| R3 | 1–3 min metric lag means a fast spike is refused only after it has already hurt. | Accepted and documented (D-04). A same-second signal would need in-process sampling (a new `psutil` dependency) — deliberately out of scope; if the lag proves unacceptable, that is the follow-up. |
| R4 | Poller adds CloudWatch cost / hits API limits. | One call set per 30 s per process; inventory cached at 300 s; both intervals are settings. |
| R5 | `aws_iam_role_policies_exclusive` deletes the new policy. | Task 4.2 explicitly pairs the resource with the list entry. |
| R6 | 75% memory is normal for this host class → permanent gating. | CPU and memory thresholds are separate settings; Wave 0 confirms the number against real matrix data before the gate is enabled. |
| R7 | Multi-worker disagreement on gate state. | Documented (D-11), consistent with existing single-process assumptions. |
| R8 | New `Modal` diverges from the existing hand-rolled ones. | Scoped as "new primitive, no retrofit"; the duplicates keep working untouched. |

---

## 10. Operator resolutions (2026-09-08)

All five questions from the draft are answered. Nothing below is still open;
this section is kept as the record of *why* the plan reads the way it does,
since each answer changed a decision elsewhere in this document.

**Q1 — thresholds → CPU 75%, memory 75%.** Confirmed as-requested, explicitly
accepting that this is tighter than the existing 80/85 alarms (§2.3). Both
settings (`HOST_CAPACITY_CPU_THRESHOLD_PERCENT`, `HOST_CAPACITY_MEM_THRESHOLD_PERCENT`)
default to `75.0` (§6) and stay independently tunable — the operator's own
stated plan is to watch the admin matrix for a few days and adjust from real
data, which requires nothing further from this plan; it's a config edit against
already-shipped settings.

**Q2 — fleet size → one instance today.** Confirmed. `HOST_CAPACITY_GATE_SCOPE`
stays `"self"` (D-06); the matrix renders one row `self == the fleet`.
`fleet_worst` and the sharding hazards a real fleet would expose
(`_PIPELINE_QUEUES`, JWKS cache — noted in the draft's Q2) remain explicitly
out of scope (§11) — they are a separate body of work if a fleet is ever
actually provisioned, not something this plan defers silently.

**Q3 — instance id → env var, discovery stays default.** Confirmed: tag-based
discovery (`tag:Project=velocityai` + `tag:Environment=<env>`) remains the
default resolution path; the operator-supplied ID is delivered as
`HOST_CAPACITY_INSTANCE_IDS`, an **environment variable** — concretely, a
GitHub Environment variable pushed through the same SSM pipeline every other
plain config value already uses (`BEDROCK_MODEL_ID`, `CORS_ORIGINS`, ...).
This added the entire new **Wave 4 — CI/CD wiring** (§7): `deploy.yml` gets a
`put_param` call per `HOST_CAPACITY_*` setting, `bootstrap-ec2.sh`'s
`velocityai-load-secrets` loader gets a matching case arm to actually forward
those SSM keys into `app.env` (skipping this step is the exact silent-drop
failure mode `docs/GITHUB_CICD_SETUP.md` §10 already documents for unknown
keys), and both `docs/GITHUB_CICD_SETUP.md` and `app.env.example` get updated
so the mapping is discoverable. Task 4.10 is the actual delivery mechanism for
the ID: set it as a GitHub Environment variable, never paste it into source or
`.tf` files. The Wave-1 cross-check (D-07) logs a WARNING if discovery
disagrees with the supplied override, which is what makes the override
meaningfully act as a *cross-check* rather than a value nothing verifies.

**Q4 — response detail → actual numbers.** Confirmed. `D-09`'s response
contract keeps the `signals` list with real CPU/memory values and thresholds
on the 503 body, as originally drafted. No change needed to D-09.

**Q5 — pre-emptive UI → follow-on, not this plan.** Confirmed as a deferred
Wave 5, not part of this execution. `GET /api/capacity` (a public,
numbers-free `{accepting_work, retry_after_seconds}` endpoint so the launch
button can disable itself before a user composes a brief) is recorded in §11
as deliberately out of scope for this plan, to be scoped as its own follow-on
once the core gate has run in production.

---

## 11. Deliberately out of scope

Disk and inode pressure (the `signals` list is shaped to accept them later);
queue-depth or `len(_PIPELINE_TASKS)`-based admission control (a genuinely
better signal than host CPU for this workload, and worth its own plan);
per-user quotas; auto-scaling; retiring the nine duplicate modals; an alarm on
the gate's own blind state; in-process sampling for sub-minute reaction;
`fleet_worst` gate scope and the multi-instance sharding hazards a real fleet
would expose (§10 Q2); the pre-emptive `GET /api/capacity` endpoint (§10 Q5) —
each is a legitimate follow-on, deliberately not bundled into this plan.
