# Backlog workflow audit — 2026-09-25

Scope: `backend/agents/workflows/backlog/workflow.yaml` (15 steps, as of the UI/UX step
landing), its three code steps, the engine's Clarify path, and two past runs
(`5ab1be23` completed draft, `05832e65` failed at assembly). Three questions:

1. Which agent does what, and do we need it?
2. Can every agent get a Clarify stage that analyses its input and asks the user for gaps?
3. Does the workflow produce a correct backlog for every application type?

Every fact below was found by a reader and re-checked by a second, adversarial reader
against the file and line cited.

---

## 1. Agents: what each does, and whether we need it

Steps run **one at a time** in manifest order (engine.py:6069, a single cursor). Only the
two wave steps fan out workers (max 6 at once).

| # | Step | Runs on | Does | Verdict |
|---|------|---------|------|---------|
| 1 | UI Extract | code | Measures the prototype (tokens, components, navigation) into `build/ui/` | Keep |
| 2 | Reading Planner | Sonnet | Calls `extract_text` per upload and turns shard manifests into `build/tasks.json` by fixed rules | **Replace with code.** Every rule is deterministic (slug, shard, rollup). 200 s and 89 k input tokens in 5ab1be23 for bookkeeping. prototype_v2 has the same step, so one code step serves both. |
| 3 | Readers (fan-out) | Sonnet | Read each shard or text file into notes, gaps and synthesis | Keep — core |
| 4 | Synthesizer | Sonnet | Merges every document, closes gaps across documents, writes `validate.json` | Keep — core |
| 5 | Clarify | session model | Asks every open gap once | Keep — becomes the template for all Clarify points (§2) |
| 6 | Answer Integrator | session model | Copies answers into `validate.json` and adds `[user]` lines to `synthesis.md` | **Replace with code.** It is exact-string copying. With one Clarify point per stage (§2), keeping an LLM for this would add one agent per stage. |
| 7 | Solution Analyst | Sonnet | Builds the nine-list model of the whole application | Keep — core; this is where the application type must enter (§3) |
| 8 | UI/UX Writer | Sonnet | `ui.md` from measurements, `ux.md` journeys | Keep, **split**: `ui.md` is a table rendering of `build/ui/*.json` and can be code; only `ux.md` journeys need a model |
| 9 | API Designer | Sonnet | Designs the application's own `/v1/` REST API | Keep, **but only when the application has its own backend** (§3) |
| 10 | Architect | Sonnet | Writes `architecture.md` | Keep, **but wire it in**: only the export reads it (backlog_export.py:48-62). No story is ever written for an architectural decision (CI/CD, environments, infrastructure, release). |
| 11 | Backlog Planner | Sonnet | Personas, epics, hierarchy, writing slices | Keep. Its `depends_on: us-architect` is a **false edge**: it never reads `architecture.md` (workflow.yaml:929 vs :956). |
| 12 | Story Writers (fan-out) | Sonnet | One file of stories per epic slice | Keep — core |
| 13 | Assemble | code | Builds backlog.md/csv/json and the coverage report | Keep |
| 14 | Reviewer | Sonnet | Fixes exactly what the coverage report lists | Keep |
| 15 | Final Assemble | code | Rebuilds after review; enforces coverage; exports | Keep |

Net: 12 model steps become 10 (planner and answer integrator become code), and `ui.md`
moves to code.

Other findings:

- `backlog-plan.md` is written but read by nothing and not exported.
- UI/UX Writer and API Designer are siblings in the graph but still run one after the other.
  The engine has no step-level parallelism, so this costs wall-clock time only; it is not a bug.
- In run 05832e65, 5 story writers also wrote to `build/stories/`, which assembly never reads
  (backlog_assemble.py:63). Four of them also wrote the right path; `EPIC-26b` exists only in
  the wrong place, so its stories would have been lost. This is the same path drift the
  prompt already warns against (workflow.yaml:1065).
- Run 5ab1be23 took 69 min. The Clarify step asked 24 questions and all 24 were answered. The
  run produced 196 stories. In the architecture's technology stack, **10 of 16 rows are
  inferred**, and 05832e65 inferred a different stack shape (15 rows, 11 inferred). The model
  improvises the stack on every run because nobody asks.

---

## 2. A Clarify stage for every agent

### How asking works today (verified)

- `ask_user` only **emits a request**. The engine parks the run, the user answers, and the
  engine writes `clarify/answers.json` (engine.py:8480-8700).
- **The asking agent never sees its own answers.** langchain_core 1.4.6 runs the agent's
  graph in a background task that feeds an unbounded queue
  (`tracers/event_stream.py:1067`, `memory_stream.py`). The agent finishes its turn while the
  engine is still waiting on the user. That is why Clarify and Answer Integrator are two steps.
- **Parallel workers must not ask.** The questionnaire slot and the resume event are one per
  run with no lock, so two workers asking at once overwrite each other's round.
- **Question ids share one file**, merged newest-wins (`_merge_clarify_rounds`). Two stages
  that both use `gap-1` overwrite each other.
- A backend restart while a run is parked cancels it (known). Every extra pause is more
  exposure.
- `wall_clock_seconds` is checked only at fan-out boundaries (budget.py, fanout.py), so a
  long wait at a Clarify does not time the run out mid-wait.

### What "every agent" should mean

Taken literally, "every agent" would mean one questionnaire per Reader and per Story Writer,
which is 50+ questionnaires and a race. The rule should be:

| Kind of step | Asks? | How its gaps reach the user |
|---|---|---|
| Decision agents: Synthesizer, Solution Analyst, API Designer, Architect, Backlog Planner | **Yes**, one Clarify point each | Its own questions |
| Fan-out workers: Readers, Story Writers | No | Write gaps to a file; the next decision agent asks them (Readers already do this) |
| Copy-only agents: UI/UX Writer, Reviewer | No | Nothing to decide |
| Code steps | Never | — |

What each Clarify point asks (asked only when the answer changes the output; zero questions
means no pause):

| Stage | Asks about |
|---|---|
| Synthesizer → Clarify (exists) | Document gaps, **plus the application profile first** (§3): clients, backend, integrations, offline |
| Solution Analyst | Anything that changes **what exists**: an admin portal, a payment flow, a role's permissions, an entity's lifecycle. A pure default (audit log, backups) is still inferred and marked |
| API Designer | Only with its own backend: public or partner API, auth scheme, anything the corpus contradicts |
| Architect | Mandated stack or cloud, hosting, data residency, SSO provider, scale and availability targets (today 10 of 16 stack rows are guesses) |
| Backlog Planner | MVP cut (which features ship first), priorities, Jira project key and conventions |

Rules for every Clarify point:

- Question ids carry the stage: `gap-N`, `sol-N`, `api-N`, `arch-N`, `plan-N`.
- Every question has a recommended answer, so "Accept all recommended" is one click.
- Anything not asked is recorded as `inferred` with a reason, as today.

### Two ways to build it

| | A. Ask step before each stage (no engine change) | B. Blocking `ask_user` (engine change) — **recommended** |
|---|---|---|
| Shape | A cheap `<Stage> Clarify` step reads the stage's inputs and asks; the stage reads `clarify/answers.json` | Each agent gets a Phase 0 "Intake": read inputs, list what is missing, ask, then **continue with the answers in hand** |
| Steps added | +4 model steps | None |
| Quality | The asker re-reads the stage's inputs without doing the work, so it guesses what the worker will miss. The Solution Analyst's corpus read is the most expensive read in the run. | The agent that analyses its input is the one that asks |
| Engine work | None | `ask_user` pauses the graph with a LangGraph `interrupt()` and resumes it with the answers as the tool result. The runner already has interrupt detection and `Command(resume)` (deep_agent_runner.py:740-1083); it is not armed for workflow agents today (engine.py:9660). A per-run lock on the questionnaire slot is also needed. |
| Bonus | — | A checkpointed interrupt is the natural path to surviving a restart while parked |

**Decision (2026-09-26): A, with no engine change.** Built as the Clarify step for the
Solution Analyst (`us-gaps`, existing), plus API Clarify, Architecture Clarify and Backlog
Clarify. Each stage reads `clarify/answers.json` and takes only its own id prefix. Asking on
the NEXT agent's behalf was rejected: it ties each agent to whichever step follows it, so
inserting a step breaks it. The Solution Analyst's own scope questions (`sol-N`) wait for the
application profile work (§3).

---

## 3. Every application type

### What is hard-wired to web today (verified, workflow.yaml)

- No mobile or desktop concept appears in any prompt or in the spec. A search for mobile,
  iOS, Android, desktop, offline, push, deep link, app store, installer, auto-update,
  biometric, camera, GPS and crash reporting finds zero real hits. `spec.md:39` says
  "Everything a full application needs" but never names the application types in scope.
- Readers: NFR heading "browser and device support" (:196); controls are web form controls
  only (:214).
- Solution Analyst:
  - screen kind is only `page` or `dialog` (:600).
  - Inferred NFRs are WCAG 2.1 AA, browser support and page response (:610).
  - The platform list (:612) has no push notifications, device permissions, offline sync,
    deep links, force-update, crash reporting, secure local storage, installer, code
    signing or auto-update.
- API Designer: **always** designs its own `/v1/` REST API (:778-820). That is wrong for:
  - a front end or mobile app that consumes an existing or third-party API;
  - a backend-as-a-service app;
  - an offline desktop app.
- Architect: "one deployable backend, one relational database" (:869). There is no client
  architecture section: no native vs cross-platform choice, local storage, sync or release
  channels.
- Backlog Planner: the only epic types are `functional`, `data`, `integration` and
  `platform` (:964-969). There is no client epic (app shell, device capabilities, store
  release) and no technical epic (environments, CI/CD).
- Clarify: the workflow's `clarify: mode: skip` and no launch field mean **nobody ever asks
  what kind of application this is**.
- The prototype is always HTML, even for a mobile app, so the readers record it as web
  screens. Nothing tells the model that an HTML mock may stand for an iOS app.

### What already degrades well (verified, do not rebuild)

- Assembly and export do not depend on item counts. Zero screens or zero endpoints produce
  empty sections, not failures (backlog_assemble.py:543, 1158-1252). Coverage passes when
  nothing is evidenced (:1324).
- No prototype writes `build/ui/source.json` with `source: null`, and the UI/UX Writer
  writes a one-paragraph note (prototype_ui_extract.py:313; workflow.yaml:686).
- An API-only product still gets endpoints from entity operations, inbound webhooks and
  platform capabilities, and still gets data, integration and platform epics. Only the
  `functional` epic definition ("a flow through screens") needs "or API calls".

### The fix: an application profile, decided once, read by every stage

The Synthesizer drafts `build/profile.json` from the corpus with references. The first
Clarify asks whatever the corpus leaves open, first in the list and high impact. Every
later stage reads the profile and branches on it with rules (no code in prompts).

```json
{"clients": [{"kind": "web | ios | android | cross-platform-mobile | desktop-windows | desktop-macos | desktop-linux",
              "audience": "customers", "offline": false}],
 "backend": "own-new | own-existing | third-party | baas | none",
 "external_apis": ["..."],
 "distribution": ["web hosting", "app store", "play store", "installer", "MDM"],
 "sources": ["..."]}
```

| Stage | Change |
|---|---|
| Readers | Controls and NFR headings become platform-neutral (gestures, device permissions, notifications, OS versions) |
| Solution Analyst | Every screen names its client. Screen kinds grow per client: mobile adds tab, sheet and notification; desktop adds window, menu and tray. The platform list and inferred NFRs are the base list plus a per-client list (web: browsers, WCAG; mobile: OS versions, device matrix, VoiceOver/TalkBack, store rules, offline; desktop: OS versions, installer, auto-update, code signing) |
| API Designer | Three modes by `backend`. `own-new`: as today. `own-existing` or `third-party`: no new API, and the consumed calls go into the integrations' `calls`. `none`: none. `endpoints.json` says which mode and why |
| Architect | Adds a "Client architecture" section per client (native or cross-platform, local storage, sync, release channel). The "simplest architecture" default follows the profile: no backend means no server components |
| Backlog Planner | Adds two epic types. `client`: app shell, device capabilities, release and distribution, per client. `technical`: from `architecture.md` (environments, CI/CD, infrastructure). This also makes the Architect → Planner edge real |
| Story Writers | `ui` rows name their client. Gherkin and EARS are already platform-neutral |
| Assemble | Writes `api.md` and `openapi.json` only when there is an own API; otherwise one line saying why |

Multi-client products (web + mobile + admin portal on one backend) fall out naturally,
because `clients` is a list.

### Application types this must cover

| Type | Profile |
|---|---|
| Web front end on third-party APIs | clients web · backend third-party |
| Web app + own backend | web · own-new |
| Mobile app, standalone / offline | ios/android · none · offline |
| Mobile app + integrations | ios/android · third-party |
| Mobile app + own backend API | ios/android · own-new |
| Desktop app (standalone or syncing) | desktop-* · none or own-new |
| Multi-client product | web + ios + android · own-new |
| API / backend-only product | no clients · own-new |

Verification: offline tests of the assembly for each profile (no live runs). Then one live
run per profile class, each only with an explicit go-ahead.

---

## Suggested order

1. Application profile + Clarify asks it first + per-stage prompt rules (§3). This is the
   biggest correctness gap, needs no engine change, and fixes the improvised stack.
2. Reading Planner and Answer Integrator → code (§1).
3. Blocking `ask_user` spike (§2 option B), then per-stage Intake phases.
4. Architect → `technical` epics, and `client` epics.
5. `ui.md` → code.
