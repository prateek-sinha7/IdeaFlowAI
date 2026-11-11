# Requirements Document

> **Amended 2026-11-10 (entry flow and panel layout).** The Builder_Popup is removed. Both entry controls now open the Builder_Panel, whose empty state took over the popup's content (example prompts, recent conversations) and whose message box starts the Session. The panel docks under the Composer header at 360 px from a 1280 px viewport. Changed: the In scope list, the Glossary, Requirement 1 (criteria 3 to 12), Requirement 3 (criteria 1 and 3), Requirement 4 (criterion 11), Requirement 6 (criteria 1 to 6 and 8), Requirement 12 (criteria 1 and 3), Requirement 14 (criteria 1 and 6 to 8) and Requirement 48 (criterion 4). ADR-0061 in `.knowledge/` records the change.

## Introduction

Users build and edit workflows on `/workflows/new` and `/workflows/{id}/edit` by chatting with a dedicated deep agent, the Builder_Agent. The Builder_Agent follows the `velocity-workflow-creator` skill, reads the skill's guides, runs the skill's lookup and validation scripts through a tool, and writes a workflow manifest. The chat panel shows live progress over SSE. The Canvas renders each validated draft automatically, and the user saves it through the existing save flow. The same panel edits the workflow afterwards. The user picks the LLM and its thinking level in the panel.

This document converts the v0.4 draft of spec 023 into EARS requirements. The draft is the authoritative input and stays in the workspace at `specs/023-ai-workflow-builder/requirements.md`. Its sections that describe the current code (§2.1, §2.2 facts S-01 to S-18), the backend overview and turn sequence diagram (§6), and the risk register (§10, R-01 to R-27) are not repeated here; criteria cite them by ID.

### Reading conventions

- Every criterion cites its source in the draft in parentheses, for example `(FR-33.4, Q-58)`. FR = functional requirement, NFR = non-functional requirement, Q = decision, S = skill fact, R = risk, § = draft section.
- `[placeholder: Q-NN]` marks a limit value that the draft states as a placeholder until the Spike.
- `[proposed]` marks a value the draft proposes but that is not yet decided.
- `Draft strength: SHOULD` marks a criterion the draft states as SHOULD. It is written with SHALL to fit EARS; the design may treat it as best effort.
- `[see G-NN]` points to a gap found while detailing the requirements (see Gaps Found During Detailing). `Draft strength: MAY` marks a criterion the draft states as MAY.

### Environment notes

- Backend commands run from `backend/` with `uv run` in PowerShell. Frontend commands run from `frontend/` with `npm`.
- Docker is not installed locally. The integration suite's PostgreSQL fixtures use testcontainers, so integration tests run on the Docker-capable CI runner. The Backend_Image build also runs in CI.
- PostgreSQL is the only database. No suite uses SQLite as a stand-in.

### In scope (phase 1)

- Entry points: "Build with AI" on `/workflows`, and an AI button in the Composer header on both composer routes. Both open the Builder_Panel; there is no popup (Q-01, Q-48; amended 2026-11-10).
- Access for users with the Custom_Entitlement, through the Capacity_Gate (Q-33, Q-25).
- A left-side Builder_Panel on `/workflows/new` and `/workflows/{id}/edit`, under the Composer header, 360 px wide and collapsible (Q-02, Q-03; amended 2026-11-10).
- Live progress over SSE in every open tab: Stages, tool activity, check results (FR-16, FR-35, Q-57).
- Creating, refining and editing workflows, including any user-saved workflow. Rows whose base is not `custom` are saved as new (Q-09, Q-39).
- Every Pattern that passes the Server_Gate: `patterns.md` §1–18 and §21 (Q-34, Q-53).
- Applying each validated Draft straight to the Canvas, with undo of the last AI change (Q-04, Q-10).
- Manual Canvas edits between Turns (Q-05).
- Saving through the existing flow. Later saves update the same row, and "Save as new" stays (Q-07, Q-08).
- Sessions, history, resume and delete (Q-11, Q-12).
- Three new tables. Nothing expires; only the user deletes (Q-14, Q-41).
- Stateless Turns with a stored Transcript_Summary (Q-55).
- A 900 s cap on every Turn, with "continue" after a time-out or a restart (Q-54).
- A model and thinking-level picker over the Builder_Model_Catalog (Q-15, Q-16, Q-36, Q-50, Q-56).
- The Builder_Agent with the Skill, and Harness configuration (Q-19, Q-47).
- The Skill_Folder, and a Script_Runner for the Skill's scripts (Q-42, Q-52, Q-58).
- English only (Q-31).

### Out of scope (phase 1)

The design must not pick up any of these:

- Any change to the Skill made by the Builder. How the Skill's generated catalog is refreshed is Q-61.
- Built-in workflows and spec-016 overrides (Q-09).
- Patterns §19 (code that is compiled and tested, needs `exec`) and §20 (revision workflows, need `previous_run`) (Q-53).
- Attachments and voice input in the chat (Q-23).
- Restoring arbitrary earlier revisions (Q-10).
- Showing builder spend on the Analytics page (Q-26). Usage is still stored from day one.
- Replaying a Turn's streamed text after a reconnect (Q-28). Activity so far is shown.
- Resuming a Turn part-way after a restart. The Turn is marked interrupted and the user continues it (FR-22.10).
- Drafts sent as patches (Q-06).
- Running a workflow from the chat. The Composer's Run once stays.
- Tools that change data outside the Session (Q-18).
- Automatic deletion or expiry of anything the user created (Q-41).
- More than one backend process per environment. The run transport has the same limit (§2.1, Deployment).
- Multi-user collaboration on one Session.
- Languages other than English (Q-31).

### User journeys covered

| Journey (draft §4) | Requirements |
|---|---|
| J1 Create | 1, 3, 6, 7, 10, 16 |
| J2 Refine before saving | 7, 8 |
| J3 Edit after saving, same Session | 10 |
| J4 Edit an existing saved workflow | 1, 10, 20 |
| J5 New conversation | 11 |
| J6 Resume | 12 |
| J7 Undo | 8 |
| J8 Watch progress | 17, 38, 39, 40 |
| J9 Continue after a time-out or restart | 13, 22, 23, 37 |

## Glossary

- **Builder**: The AI workflow builder feature as a whole: the Builder_Panel, the Composer integration and the backend parts.
- **Saved_Workflows_Page**: The `/workflows` "My Workflows" page (`components/savedworkflows/SavedWorkflowsPage.tsx`).
- **Composer**: `ComposerPage` on `/workflows/new` and `/workflows/{id}/edit`, with its header, Save, Run once, config rail (`CanvasConfigRail`), summary rail (`SummaryRail`), agent library (`AgentLibrary`), Simple view and Canvas view.
- **Canvas**: The Composer in Canvas view (`CanvasView`, `CanvasNode`, `CanvasConfigRail`).
- **Builder_Panel**: The left-side chat panel on the composer routes, under the Composer header and left of the Canvas. Its code lives outside `components/workflow`; the Composer only places the element the host renders. With no Session it shows its Empty_State.
- **Empty_State**: What the Builder_Panel shows before a Session exists: a short introduction, example prompts and recent conversations, above the panel's message box and the Model and Thinking picker. It replaced the earlier popup (Q-01; amended 2026-11-10).
- **Session_Stream_Hook**: The frontend hook that reads the Session_Stream. It lives outside `components/workflow` and is separate from `RunConnectionProvider`.
- **Unsaved_Work_Guard**: The Composer's existing ISS-275 guard that compares name and roster against a baseline.
- **Busy_Modal**: The frontend's existing modal for a `host_capacity_exhausted` response.
- **Builder_API**: The new FastAPI router under `backend/app/api/`, under one prefix such as `/api/workflow-builder`.
- **Turn_Runner**: The server component that runs one Turn as a background task, tracks its status, Stage and limits, and stores its results.
- **Builder_Agent**: The new deep agent that builds and edits workflows. It is separate from workflow step agents and from the concierge.
- **Concierge**: The existing run chat agent in `backend/app/agents/chat/concierge.py`, whose tools only propose actions.
- **Workflow step agent**: An agent that runs one step of a workflow inside the ExecutionEngine.
- **DeepAgentRunner**: The existing wrapper around `create_deep_agent` in `backend/app/agents/deep_agent_runner.py`.
- **ExecutionEngine**: The workflow-agnostic runtime kernel in `backend/agents/execution_engine/` that runs workflow manifests.
- **Harness**: The Builder_Agent's DeepAgentRunner configuration: middleware, summarisation, limits and the Adherence_Record (Q-19).
- **System_Prompt**: The Builder_Agent's versioned system prompt file.
- **Turn_Context**: The facts the server gives the Builder_Agent at the start of every Turn (FR-34).
- **Skill**: `velocity-workflow-creator`, the Builder_Agent's method, used unmodified.
- **Skill_Folder**: `backend/app/agents/workflow_builder/skills/velocity-workflow-creator/`, the only copy of the Skill and its source of truth. The backend runs it directly.
- **Skill_View**: The read-only `/skills/` route through which the Builder_Agent reads the deployed Skill.
- **Skill_Hash**: A hash of the files in the Skill_Folder, in path order, computed from disk.
- **Catalog_Snapshot**: The Skill's `references/catalog.json`: platform names as of one commit (S-14).
- **Skill_Validator**: The Skill's `validate_manifest.py`, used by the Builder_Agent as its lint. Advisory only.
- **Script_Runner**: The `run_skill_script` tool, which runs allow-listed Skill scripts in a subprocess.
- **Server_Gate**: The server's check on a Draft before the Canvas sees the Draft: the save check at the Target_Trust plus the Builder_Rules.
- **Builder_Rules**: The checks the Server_Gate adds to the save check: the agent-id allow-list, model entitlement, step models from the Step_List, and the Q-53 list of features the product cannot run or supply.
- **Dry_Run**: A Server_Gate check requested through `validate_manifest.py --compiler`. A Dry_Run emits no Draft and does not count as a rejection.
- **Target_Trust**: The trust level (`user` or `db`) a Draft is designed and checked for (Q-46).
- **Capacity_Gate**: The existing host capacity check used by launches (`HOST_CAPACITY_GATE_ENABLED`, `backend/app/api/run_commands.py`).
- **Model_Catalog**: The platform model catalog in `backend/agents/capabilities/model_catalog.py`, the single model list (INV-12).
- **Builder_Model_Catalog**: The Chat_List and the Step_List, kept as flags on Model_Catalog entries.
- **Chat_List**: The models the Builder_Panel offers for the Builder_Agent.
- **Step_List**: The models the Builder_Agent may assign to workflow steps.
- **Session**: One builder conversation, with one Sandbox. A new conversation is always a new Session.
- **Sandbox**: A Session's working folder on disk, holding `/canvas/`, `/workflows/`, exported payloads and each script call's temp folder.
- **Canvas_File**: `/canvas/current.workflow.json`, the Canvas state the server writes into the Sandbox at the start of each Turn.
- **Session_Store**: The three new tables (`workflow_builder_sessions`, `workflow_builder_messages`, `workflow_builder_drafts`) and their data access.
- **Builder_Migration**: The one additive Alembic migration that creates the Session_Store tables.
- **Session_Stream**: The per-Session SSE stream that carries a Session's Turn events to every open tab.
- **Turn**: One user message and the Builder_Agent's full response to that message. Turns are stateless (Q-55).
- **Interrupted_Turn**: A Turn ended by a server shutdown or restart.
- **Stage**: What the Builder_Agent is doing right now, derived by the server from the Builder_Agent's actions.
- **Transcript_Replay**: The stored user and assistant messages, plus the Transcript_Summary of older Turns, given to the Builder_Agent at the start of each Turn.
- **Transcript_Summary**: The stored summary of Turns older than the replay budget.
- **Draft**: The full manifest the Builder_Agent proposes (S-07).
- **Draft_Revision**: A numbered snapshot of the Draft: an edit Session's seed, an accepted Draft, an undo, or an Unproposed_Revision.
- **Unproposed_Revision**: The Builder_Agent's working manifest, stored when a Turn ends without an accepted Draft. Never shown on the Canvas; used by "continue".
- **Change_Summary**: The server-computed list of what a Draft changed compared with the previous revision.
- **Launch_Needs**: The inputs a Draft needs at launch (uploads, a template or design system, configured connectors, or a source run), derived by the server from the manifest.
- **Adherence_Record**: The per-Turn record of which mandatory Skill files were read in full, whether `overview` and `example` ran, and whether the Skill_Validator ran and what it returned (Q-45 a).
- **Pattern**: One of the workflow shapes in the Skill's `docs/patterns.md`.
- **Spike**: The operator-run measurement of the built Builder on 3 reference requests (NFR-12).
- **Custom_Entitlement**: Permission to run the `custom` pipeline: `canRunPipeline(tier, "custom")` in `frontend/src/lib/entitlements.ts`, mirrored by `TIER_PIPELINES` in `backend/app/core/entitlements.py`.
- **CI_Pipeline**: The repository's CI checks.
- **Backend_Image**: The backend container image built from `backend/Dockerfile`, including its build step.
- **Test_Suite**: The backend tests under `backend/tests/` and the frontend Vitest and Playwright tests under `frontend/`.

## Requirements

### Requirement 1: Entry points and the empty panel

**User Story:** As a user who may create custom workflows, I want to start building a workflow with AI from the workflows page or the composer, so that I can describe a workflow instead of assembling it by hand.

Amended 2026-11-10: criteria 3 to 11 replace the earlier popup flow, and criterion 12 is new. The numbers keep their earlier meaning where one exists.

#### Acceptance Criteria

1. WHILE the user holds the Custom_Entitlement, THE Saved_Workflows_Page SHALL show a "Build with AI" control next to the existing create control. (FR-01.1, FR-01.6, Q-48)
2. WHILE the user holds the Custom_Entitlement, THE Composer SHALL show an AI button in its header on `/workflows/new` and on `/workflows/{id}/edit`. (FR-01.2, FR-01.6, Q-48)
3. WHILE the Builder_Panel is collapsed, WHEN the user clicks the Composer AI button, THE Composer SHALL open the Builder_Panel beside the Canvas it already shows: on the URL's Session when the URL carries `?ai=<sessionId>`, and otherwise with the Empty_State. THE Composer SHALL NOT replace an open workflow's Canvas with an empty one. (FR-01.2, FR-02.6, FR-02.7, Q-49)
4. WHEN the user clicks "Build with AI" on the Saved_Workflows_Page, THE Builder SHALL open a new Canvas on `/workflows/new` with the Builder_Panel open on its Empty_State, and SHALL NOT create a Session. (FR-01.3)
5. WHILE the Builder_Panel is open, WHEN the user clicks the Composer AI button, THE Composer SHALL collapse the Builder_Panel. (FR-01.3, FR-02.2)
6. THE Empty_State SHALL show a short introduction, 3 to 4 example prompts and the user's recent builder conversations (Requirement 12), with the panel's message box and the Model and Thinking-level picker (Requirement 6) below it. WHEN the user selects an example prompt, THE Builder_Panel SHALL put its text in the message box and SHALL NOT send it. (FR-01.3, Q-01 option c, G-25)
7. WHEN the user sends the first message from the Empty_State, THE Builder_Panel SHALL show the message in the transcript at once, SHALL accept no further send until that message's send has settled, and SHALL put the text back in the message box if the Session cannot be created. (FR-01.4, FR-03.3)
8. WHEN the user sends the first message from the Empty_State on `/workflows/new`, THE Builder SHALL create a Session in create mode with the Canvas as it is, and change the URL to `/workflows/new?ai=<sessionId>`. (FR-02.6, Q-48, Q-49)
9. WHEN the user sends the first message from the Empty_State on `/workflows/{id}/edit`, THE Builder SHALL create a Session seeded with that workflow, keep that workflow on the Canvas, and change the URL to `/workflows/{id}/edit?ai=<sessionId>`. (FR-01.4, Q-12, Q-49)
10. WHEN the Session_Stream_Hook has opened the Session_Stream for a Session created from the Empty_State, THE Builder_Panel SHALL send the first message exactly once, with the model and effort selected when the user sent it. (FR-01.4, FR-05.5, FR-16.8, FR-22.6)
11. WHEN the user selects a recent conversation in the Empty_State, THE Builder SHALL open that Session as described in Requirement 12. (FR-01.5, FR-11.3)
12. IF the Session_Stream closes for good before the first message is sent, THEN THE Builder_Panel SHALL put the first message back in the message box. (FR-12.2)

### Requirement 2: Access control and authorisation

**User Story:** As a platform owner, I want the Builder limited to users who may create custom workflows, with no feature flag or environment variable to switch it on, so that no user reaches another user's data.

#### Acceptance Criteria

1. THE Builder SHALL show the "Build with AI" control on the Saved_Workflows_Page and the AI button in the Composer header to users who hold the Custom_Entitlement, and SHALL hide both controls from all other users. (FR-01.6, FR-01.1, FR-01.2, Q-33, Q-25)
2. (Removed: the Builder has no feature flag, so it is always on for users who hold the Custom_Entitlement.)
3. THE Builder SHALL determine the Custom_Entitlement only through `canRunPipeline(tier, "custom")` on the frontend and `TIER_PIPELINES` on the backend, with no tier list of its own, so that a change to that table changes access without a change to Builder code. (FR-01.6)
4. THE Builder_API SHALL authenticate every endpoint with `Depends(get_current_user)` and require the Custom_Entitlement. (FR-28.1, Q-33)
5. IF a caller without the Custom_Entitlement calls a Builder_API endpoint, THEN THE Builder_API SHALL refuse the request without creating, changing or deleting any Session_Store data, starting or cancelling a Turn, or opening a Session_Stream. (FR-28.1)
6. THE Builder_API SHALL look up every Session by `id` and `user_id` together, with `user_id` as the authorisation key. (FR-28.2, FR-25.4)
7. IF a request names a Session that does not exist or belongs to another user, THEN THE Builder_API SHALL return 404, never 403, on every endpoint that takes a Session id, including the Session_Stream, and SHALL leave that Session and any running Turn unchanged. (FR-28.2)
8. WHEN a user lists Sessions, THE Builder_API SHALL return only Sessions whose `user_id` is the caller's. (FR-31.1, FR-28.2)
9. WHEN a user links a Session to a saved workflow, THE Builder_API SHALL check that the user owns that workflow. (FR-22.9)
10. IF the user does not own that workflow, THEN THE Builder_API SHALL refuse the link and leave the Session's linked workflow unchanged. (FR-22.9)

### Requirement 3: Builder layout and URL

**User Story:** As a user, I want the chat panel docked beside the canvas with the session in the URL, so that I can see the workflow while I chat and come back to the same conversation.

#### Acceptance Criteria

1. WHILE the Builder_Panel is open, not collapsed, and the viewport is at least 1280 px wide, THE Composer SHALL dock the Builder_Panel on the left, under the Composer header, at 360 px wide with the Canvas to its right, and SHALL keep the header at full width. (FR-02.1, Q-03; amended 2026-11-10: 1024 px and 380 px before)
2. WHEN the user collapses the Builder_Panel, THE Builder SHALL keep `?ai=<sessionId>` in the URL, let any running Turn continue, and keep the Session_Stream connected. (FR-02.2)
3. WHILE the Builder_Panel is open, not collapsed, and the viewport is narrower than 1280 px, THE Builder_Panel SHALL overlay the Canvas without reducing the Canvas width. (FR-02.3, FR-13.5, Q-03; amended 2026-11-10: 1024 px before)
4. WHEN the Builder_Panel opens, THE Composer SHALL show Canvas view, whichever view the Composer showed before. (FR-02.4, Q-03)
5. WHILE the Builder_Panel is open, WHEN the user selects Simple view, THE Composer SHALL show the same steps in the same order as Canvas view, including manual edits. (FR-02.4, Q-03)
6. WHILE the Builder_Panel is open, THE Composer SHALL show the header, Save, Run once, the config rail, the summary rail and the agent library, disabled only where Requirement 7 (Run once at `db` trust) and Requirement 9 (running Turn) require. (FR-02.5)
7. WHILE the Composer on `/workflows/new` or `/workflows/{id}/edit` has a Session, THE Builder SHALL carry the Session id in the URL as `?ai=<sessionId>`. (FR-02.6, Q-49)
8. WHEN a Session's first save succeeds on `/workflows/new`, THE Builder SHALL change the URL to `/workflows/{id}/edit?ai=<sessionId>`, using the saved row's id. (FR-02.6, Q-49; new work per §2.1 "After the first save")
9. WHEN the user opens or reloads a URL that carries `?ai=<sessionId>`, THE Builder SHALL restore the transcript and the Canvas of that Session. (FR-02.6, Q-49)
10. WHILE `/workflows/{id}/edit` is open without `ai`, THE Composer SHALL treat the Canvas as having no Session, even when earlier Sessions link to that workflow. (FR-02.7, Q-12, Q-49)

### Requirement 4: Transcript and message input

**User Story:** As a user, I want a readable transcript and a message box that behaves predictably, so that I can hold a conversation with the builder.

#### Acceptance Criteria

1. THE Builder_Panel SHALL show the Session's user and assistant messages in the order they were created. (FR-03.1)
2. THE Builder_Panel SHALL accept multi-line input. (FR-03.2)
3. WHEN the user presses Enter in the input, THE Builder_Panel SHALL send the message. (FR-03.2)
4. WHEN the user presses Shift+Enter in the input, THE Builder_Panel SHALL insert a newline. (FR-03.2)
5. WHILE the input is empty or whitespace-only, or a Turn of the open Session is running, including a Turn started in another tab, THE Builder_Panel SHALL disable Send and SHALL NOT send the message on Enter. (FR-03.3, FR-16.7)
6. IF the input holds more than 12,000 characters, THEN THE Builder_Panel SHALL NOT send the message. [placeholder: Q-24] (FR-03.4)
7. IF a message longer than 12,000 characters reaches the Builder_API, THEN THE Builder_API SHALL return an error indicating the length limit and SHALL NOT start a Turn. [placeholder: Q-24] (FR-03.4)
8. THE Builder_Panel SHALL NOT create HTML elements from raw HTML contained in assistant Markdown. (FR-03.5)
9. IF the Builder_Panel passes content to `dangerouslySetInnerHTML`, THEN THE Builder_Panel SHALL sanitise that content first. (FR-03.5)
10. THE Builder SHALL present every label, control text, notice and error message it renders in English. (FR-03.6, Q-31)
11. WHILE the transcript is scrolled to its end, WHEN new content arrives (a message, streamed text, activity), THE Builder_Panel SHALL keep the newest content in view; WHILE the user has scrolled up, THE Builder_Panel SHALL NOT move the transcript. WHEN the user sends a message, THE Builder_Panel SHALL scroll to the end. (FR-03.1; added 2026-11-10)

### Requirement 5: Streaming text, thinking and stop

**User Story:** As a user, I want to see the reply and the model's reasoning as they are written, and stop a turn, so that I am not waiting blind.

#### Acceptance Criteria

1. WHEN a `text` event arrives, THE Builder_Panel SHALL append the text to the in-progress assistant message. (FR-04.1)
2. WHEN a `thinking` event arrives, THE Builder_Panel SHALL append the event's text to a "Thinking" block in the in-progress assistant message, and the block SHALL stay collapsed until the user expands it. (FR-04.3, FR-35.1, Q-16)
3. WHEN a Turn starts and the model selected for its message supports summarised reasoning display, THE Harness SHALL request summarised display on every model call of that Turn. (FR-04.3, Q-16)
4. WHEN a Turn ends with any status, THE Session_Store SHALL store the text of that Turn's `thinking` events with the Turn's assistant message. (FR-04.3, FR-22.5, FR-25.2, Q-13)
5. WHILE a Turn is running, THE Builder_Panel SHALL show a Stop control in every tab that has the Session open. (FR-04.4, FR-30.1)
6. WHEN the user activates the Stop control, THE Builder_Panel SHALL request cancellation of the running Turn as described in Requirement 30. (FR-04.4, FR-30)

### Requirement 6: Model and thinking-level picker

**User Story:** As a user, I want to choose the LLM and its thinking level for the builder, so that I can trade speed and cost against quality.

#### Acceptance Criteria

1. THE Builder_Panel SHALL show a labelled Model select and, except as stated in criterion 4, a labelled Thinking-level select, in its message box's toolbar. The Model select's label MAY be visually hidden, because the selected model's name says what the control is; the Thinking-level label SHALL stay visible. (FR-05.1, FR-13.3; amended 2026-11-10)
2. THE Builder_Panel SHALL offer as model options only the Chat_List entries that the user is entitled to under `TIER_MODEL_COST_CLASSES`, as returned by the Builder_API, with no model list hardcoded in the frontend. (FR-05.2, FR-36.8, INV-12, Q-29, Q-56)
3. THE Builder_Panel SHALL offer as thinking levels the selected model's `reasoning_levels`, labelled with `effortLabel`. (FR-05.3)
4. WHILE the selected model has `reasoning_mode: none`, THE Builder_Panel SHALL hide the Thinking-level select. (FR-05.3)
5. WHILE Opus 4.6 is selected, THE Builder_Panel SHALL offer exactly two thinking levels, Off and On. (FR-05.3, §2.1 Model limits)
6. WHEN the user changes the model, THE Builder_Panel SHALL set the effort with the existing `modelChangePatch` rules. (FR-05.4)
7. WHEN the user sends a message, THE Builder_Panel SHALL send the current model and effort with the message. (FR-05.5, Q-15)
8. WHEN the Builder_Panel opens with no Session, or for a Session with no stored model, THE Builder_Panel SHALL preselect the user's Settings model preference if it is among the offered model options, and otherwise Sonnet 5.5. (FR-05.6, Q-50, Q-56)
9. WHEN the Builder_Panel opens for a Session with a stored model and effort, THE Builder_Panel SHALL preselect that model and effort. (FR-05.5, FR-21.1, FR-27.3, Q-15)
10. THE Builder SHALL use the selected model and effort only for the Builder_Agent's own model calls, and SHALL NOT apply them to any workflow step of a Draft. (FR-05.7, Q-17, Q-35)

### Requirement 7: Apply the draft to the canvas

**User Story:** As a user, I want each validated workflow to appear on the canvas automatically, so that I can see and adjust what the builder made.

#### Acceptance Criteria

1. THE Turn_Runner SHALL emit at most one `draft_applied` event per Turn, and only for a full manifest that passed the Server_Gate. (FR-06.1, Q-06)
2. WHEN the Session_Stream_Hook of the sending tab receives a `draft_applied` event, THE Composer SHALL render the Draft, received as props, on the Canvas without a page reload and within 300 ms of the event's arrival. [other tabs: see G-03] (FR-06.2, Q-04, Q-30, §8.9)
3. THE Composer SHALL render a Draft with the same mapping the Composer uses to reopen a saved workflow (`manifestStepsToAgents`, `manifestStepsToGateSelections`). (FR-06.3)
4. WHEN the Composer applies a Draft, THE Composer SHALL make the Draft the passthrough source for Save (`buildWorkflowManifest(..., sourceManifest)`), so that keys the Canvas does not model survive save. (FR-06.3, §2.1 Canvas round trip)
5. WHEN a Draft arrives while the Composer is mounted, including Drafts after the first, THE Composer SHALL replace the steps, gate selections, capabilities and passthrough source with the Draft's, and SHALL NOT reset the Unsaved_Work_Guard baseline to the Draft. (R-02, §2.1 Seeding runs once)
6. THE Composer SHALL show only Drafts that the Server_Gate accepted, and SHALL keep every Unproposed_Revision off the Canvas. (FR-06.4, FR-24.8)
7. WHEN a Draft is applied, THE Builder_Panel SHALL show the Change_Summary computed by the server from the previous revision: steps added, removed or reordered, and gates, validators or models changed. (FR-06.5, FR-24.7)
8. WHEN a Draft is applied, THE Unsaved_Work_Guard SHALL report unsaved changes until the next successful Save, including when the Draft changes neither the name nor the roster. (FR-06.6)
9. THE Composer config rail SHALL show the model and the effort that the Draft set on each step. (FR-06.7, R-12)
10. WHEN a Turn ends without an accepted Draft, whatever its status, THE Composer SHALL keep the Canvas identical to its state at the start of the Turn. (FR-06.8, FR-24.4, FR-30.3)
11. THE Server_Gate SHALL attach to each accepted Draft the Target_Trust the Draft was checked at. (FR-06.9, Q-46)
12. WHILE the most recently applied Draft's Target_Trust is `db` and the Canvas has unsaved changes, THE Composer SHALL disable Run once and show a note that an unsaved canvas runs at `user` trust. (FR-06.9, Q-46, §2.1 Saved-row trust)
13. WHEN an applied Draft has Launch_Needs, THE Builder_Panel SHALL list the Launch_Needs with the Change_Summary. (FR-06.10, FR-24.7)

### Requirement 8: Edit through chat and undo

**User Story:** As a user, I want to ask for changes in plain language and undo the last AI change, so that I can iterate without fear of losing work.

#### Acceptance Criteria

1. WHEN the user sends a message that asks to change the workflow without asking for a rebuild, THE Builder_Agent SHALL base its Draft on the Canvas state sent with that message and SHALL NOT rebuild the workflow from scratch. (FR-07.1)
2. WHEN the user explicitly asks for a rebuild, THE Builder_Agent SHALL rebuild the workflow from scratch. (FR-07.1)
3. THE Builder_Panel SHALL offer "Undo this change" only on the latest assistant message whose Turn produced an accepted Draft. (FR-07.2, Q-04, Q-10)
4. WHEN the user clicks "Undo this change" with no manual Canvas edits since that Draft was applied, or confirms the manual-edit prompt, THE Builder_Panel SHALL restore the Canvas to the Canvas state carried by the user message that started that Turn. (FR-07.3, Q-10)
5. WHEN an Undo restores the Canvas, THE Builder_API SHALL store the restored state as a new numbered Draft_Revision. (FR-07.3, FR-24.5, Q-10)
6. IF the user clicks "Undo this change" after editing the Canvas by hand since that Draft was applied, THEN THE Builder_Panel SHALL ask for confirmation before discarding those edits. (FR-07.4)
7. IF the user declines that confirmation, THEN THE Builder SHALL leave the Canvas and its manual edits unchanged and store no Draft_Revision. (FR-07.4)

### Requirement 9: Manual canvas edits

**User Story:** As a user, I want to edit the canvas by hand between turns, so that small changes do not need a chat message.

#### Acceptance Criteria

1. WHILE no Turn is running in the Session, THE Composer SHALL let the user change the Canvas with the Composer's existing editing controls. (FR-08.1, Q-05)
2. WHEN the user sends a message, THE Builder_Panel SHALL send in `canvas_state` the full manifest that the Composer's Save would build at that moment, including manual edits made since the last applied Draft and the keys passed through from the latest Draft. (FR-08.1, FR-22.7, FR-06.3, Q-05)
3. WHILE a Turn is running in the Session, from the `turn_started` event or a `snapshot` that reports a running Turn until `turn_completed` with any status, THE Composer SHALL make the Canvas read-only in every tab that has the Session open. (FR-08.2, FR-16.7, FR-35.1, Q-05)
4. WHILE a Turn is running in the Session, THE Composer SHALL disable Save and Run once in every tab that has the Session open. (FR-08.2, FR-16.7, Q-05)

### Requirement 10: Save

**User Story:** As a user, I want to save the AI's workflow through the normal save flow, so that it becomes a regular saved workflow I can run and edit.

#### Acceptance Criteria

1. THE Composer SHALL save through the existing `POST /api/user-workflows` and `PATCH /api/user-workflows/{id}` endpoints, with their validation unchanged. (FR-09.1)
2. WHEN the user clicks Save while the Session is not linked to a saved workflow, THE Composer SHALL open the name modal pre-filled with the Draft's `name` (or `id` when `name` is absent) and `description`. (FR-09.2, Q-07)
3. WHEN the user confirms the name modal, THE Composer SHALL save with the confirmed name and description. (FR-09.2, Q-07)
4. THE Builder_Agent SHALL NOT create or update a saved workflow row; only a Save or "Save as new" that the user confirms in the Composer SHALL do so. (FR-09.3, FR-20.5)
5. WHILE the Session is linked to a saved workflow whose base is `custom`, WHEN the user clicks Save, THE Composer SHALL update that row with `PATCH /api/user-workflows/{id}`. (FR-09.4, Q-08)
6. WHILE the Session is linked to a saved workflow whose base is `custom`, THE Composer SHALL show "Save as new" next to Save. (FR-09.4, Q-08)
7. WHEN a save succeeds, THE Builder SHALL link the Session to the saved workflow id and update the URL as in Requirement 3. (FR-09.5, Q-12)
8. IF a save fails with 422 (compile failure) or 409 (duplicate name), THEN THE Composer SHALL show the error in the existing save UI, leave the Canvas and the Session's link unchanged, and keep the Builder_Panel's message input available. (FR-09.6)
9. WHEN the user saves the Draft from the latest `draft_applied` event and has made no Canvas edit since it was applied, THE Composer SHALL send the same `agent_ids` as `export_manifest.py --save-payload` on that manifest, a manifest equal to its output after canonical JSON serialisation, and, on POST, base `custom`. (FR-09.7, S-07)
10. WHILE the linked row's base is not `custom`, THE Composer SHALL replace Save with "Save as new" and leave the original row unchanged. (FR-09.8, Q-39, R-21)
11. WHEN "Save as new" succeeds for a row whose base is not `custom`, THE Builder SHALL link the Session to the new row and move the URL to the new row's edit route. (FR-09.8, Q-39)

### Requirement 11: New conversation

**User Story:** As a user, I want to start a fresh conversation, so that I can build a different workflow without old context.

#### Acceptance Criteria

1. WHEN the user clicks "New conversation" in the Builder_Panel header and either the Unsaved_Work_Guard reports no unsaved work or the user confirms the prompt in criterion 3, THE Builder SHALL start a new Session in create mode, with no linked workflow and an empty Canvas. (FR-10.1, FR-21.1, Q-12)
2. WHEN a new conversation starts under criterion 1 on `/workflows/{id}/edit`, THE Builder SHALL navigate to `/workflows/new`. (FR-10.1)
3. IF the Unsaved_Work_Guard reports unsaved work, including an applied Draft not yet saved, when the user clicks "New conversation", THEN THE Builder SHALL ask the user to confirm discarding that work before starting a new Session. (FR-10.2, FR-06.6, Q-12)
4. IF the user declines the prompt in criterion 3, THEN THE Builder SHALL keep the current Session, Canvas and URL unchanged. (FR-10.2, Q-12)
5. WHEN a new conversation starts, THE Builder_API SHALL create a Session whose id differs from every existing Session id, and SHALL leave the previous Session and its stored messages and Draft_Revisions unchanged. (FR-21.7, Q-12, Q-41)

### Requirement 12: Conversation history and resume

**User Story:** As a user, I want to see, reopen and delete my builder conversations, so that I can pick up earlier work.

#### Acceptance Criteria

1. WHEN the Empty_State opens or the Builder_Panel header dropdown opens, THE Builder SHALL list the signed-in user's Sessions newest first, each labelled with its title. (FR-11.1, FR-11.2, Q-11)
2. WHEN the Builder_API stores a Session's first user message, THE Builder_API SHALL generate the Session's title from that message. (FR-11.2, Q-11)
3. WHEN the user selects a Session in the Empty_State or the Builder_Panel dropdown, THE Builder SHALL load the Session's transcript and render the Session's latest Draft on the Canvas. (FR-11.3, FR-01.5, J6)
4. IF the selected Session is linked to a saved workflow, THEN THE Builder SHALL render the saved row on the Canvas instead of the latest Draft. (FR-11.3, Q-49)
5. IF the linked saved row has changed since the Session's latest Draft, THEN THE Builder_Panel SHALL show a note in the chat saying so. (FR-11.3, Q-49)
6. WHEN a client requests a Session, THE Builder_API SHALL return the Session's title, mode, linked workflow id, model, effort, Target_Trust and Skill_Hash; its transcript; its latest Draft; its latest Unproposed_Revision when that revision's number is higher than the latest Draft's; and a snapshot of any running Turn (Stage, activity so far, start time). (FR-26.1, FR-21.1, FR-24.5)
7. WHEN the user selects delete on a Session, THE Builder SHALL show a confirmation prompt and SHALL NOT delete the Session before the user confirms. (FR-11.4, Q-11)
8. IF the user dismisses the confirmation prompt, THEN THE Builder SHALL leave the Session unchanged. (FR-11.4, Q-41)
9. WHEN the user confirms deletion of a conversation, THE Builder SHALL delete the Session as described in Requirement 31. (FR-11.4, Q-11, Q-41)

### Requirement 13: Errors and recovery in the panel

**User Story:** As a user, I want clear recovery paths when something fails, so that I never lose my message or my work.

#### Acceptance Criteria

1. IF a Turn ends with status `failed` because an LLM call failed, THEN THE Builder_Panel SHALL show an error in the transcript with a Retry that resends the last user message, such that the transcript shows that user message once, also after a reload. [see G-01] (FR-12.1, FR-22.5)
2. IF the Session_Stream drops, THEN THE Turn_Runner SHALL keep the Turn running on the server. (FR-12.2, Q-28)
3. WHILE a Turn is running, WHEN the Builder_Panel reconnects to the Session_Stream or reloads, THE Builder_Panel SHALL show the Turn's stored activity so far, then the final message and any Draft when the Turn ends. (FR-12.2, FR-16.6, Q-28)
4. IF a Turn ended while the Builder_Panel was disconnected, THEN THE Builder_Panel SHALL show that Turn's stored final message and the latest Draft on reconnect or reload. (FR-12.2, FR-26.1)
5. IF a Builder_API call returns 401, THEN THE Builder_Panel SHALL pass the response to the existing `authedFetch` session-expiry handling. (FR-12.3)
6. IF a Session request returns 404, THEN THE Builder_Panel SHALL show a not-found state. (FR-12.4)
7. IF sending a message returns 409 because a Turn is already running in the Session, THEN THE Builder_Panel SHALL show that a reply is being written. (FR-12.5, FR-22.4, Q-27)
8. WHEN a Turn ends with status `timed_out`, THE Builder_Panel SHALL say that the Turn stopped at the time limit and the work so far is kept, and SHALL offer a Continue action that sends "continue" as the next message. (FR-12.6, Q-54, J9)
9. WHEN a Turn ends with status `interrupted`, THE Builder_Panel SHALL say that a server restart stopped the Turn and the work so far is kept, and SHALL offer the same Continue action as for `timed_out`. (FR-12.7, FR-22.10, J9)
10. IF the Capacity_Gate refuses a message with 503 `host_capacity_exhausted`, THEN THE Builder_Panel SHALL show the existing Busy_Modal and keep the text in the input so the user can send the text again. (FR-12.8, FR-29.6)

### Requirement 14: Accessibility

**User Story:** As a keyboard or screen-reader user, I want the builder to be fully operable and announced, so that I can use it without a mouse or sight.

#### Acceptance Criteria

1. THE Builder SHALL make every control it adds (the entry controls on the Saved_Workflows_Page and in the Composer header, and the Builder_Panel) reachable by keyboard, with a visible focus state. (FR-13.1, NFR-10)
2. WHEN the Stage changes, THE Builder_Panel SHALL announce the new Stage label in a polite live region. (FR-13.2, FR-35.3)
3. WHEN a Draft is applied to the Canvas, THE Builder_Panel SHALL announce in the polite live region that the Draft was applied. (FR-13.2)
4. WHEN a Turn ends, THE Builder_Panel SHALL announce in the polite live region that the Turn ended. (FR-13.2)
5. THE Builder_Panel SHALL keep individual chunks of streamed text out of the live region. (FR-13.2)
6. THE Builder_Panel SHALL use only colours defined as design tokens in `frontend/src/styles/globals.css`. (FR-13.4)
7. THE Composer AI button SHALL expose whether the Builder_Panel is open through `aria-expanded`, and SHALL name the open panel in `aria-controls`. (FR-13.1; added 2026-11-10)
8. WHEN the Builder_Panel opens, THE Builder_Panel SHALL move focus to its message box. (FR-13.1; added 2026-11-10)

### Requirement 15: Showing the skill's report

**User Story:** As a user, I want the skill's long report shown compactly with canvas-oriented instructions, so that I can read the result without irrelevant export steps.

#### Acceptance Criteria

1. WHEN the Builder_Panel renders an assistant reply that carries the Skill's report, THE Builder_Panel SHALL show a short summary first, followed by the full report in a section that is collapsed by default and that the user can expand. (FR-14.1, Q-44, S-13)
2. IF a table in an assistant message is wider than the message, THEN THE Builder_Panel SHALL scroll that table horizontally inside the message. (FR-14.2)
3. WHEN the user opens the reading view of an assistant message, THE Builder_Panel SHALL show that message in a view wider than the Builder_Panel. (FR-14.2, Q-03)
4. THE System_Prompt SHALL instruct the Builder_Agent to replace the Skill's "Run it" section with canvas instructions (Save, Run once) and to keep the report's list of what a launch needs (uploads, a template, connectors, a source run). (FR-14.3, FR-20.3.5, Q-44, S-13)
5. THE Builder_Panel SHALL NOT show instructions to export files or to call the API with a bearer token in assistant replies. (FR-14.4, S-13)

### Requirement 16: Clarifying questions

**User Story:** As a user, I want the builder to ask a few functional questions and then proceed, so that the workflow fits my needs without an endless interview.

#### Acceptance Criteria

1. WHEN the Builder_Agent replies with clarifying questions, THE Builder_Panel SHALL show the reply as a normal assistant message in the transcript, keeping the numbering, options and recommended default as the Skill writes them. (FR-15.1, S-11)
2. THE Builder_Panel SHALL accept answers to the questions as free text, sent through the normal message input as ordinary user messages. (FR-15.2, Q-22)
3. THE Turn_Runner SHALL count, per Session, the Turns that ended with status `completed` without an accepted Draft, until the Session's first accepted Draft. [see G-09, G-10] (FR-15.3, FR-34.6)
4. WHEN a Turn starts in a Session that has no accepted Draft and a count of 2 or more under criterion 3, THE Builder_Agent SHALL propose a Draft in that Turn, using the recommended default for each unanswered question, without asking further questions. (FR-15.3, Q-22, S-11)
5. WHEN the Builder_Agent proposes a Draft under criterion 4, THE Builder_Agent SHALL list each question the user left unanswered as a risk in that Turn's reply. (FR-15.3, S-11)

### Requirement 17: Live progress in the panel

**User Story:** As a user, I want to see what the builder is doing while it works, in every tab I have open, so that I know progress is being made and can stop it if needed.

#### Acceptance Criteria

1. WHILE a Turn is running, THE Builder_Panel SHALL show on the in-progress assistant message the label of the current Stage and the time elapsed since the Turn started, for example "Checking the workflow · 1 min 12 s". (FR-16.1, FR-35.3)
2. WHILE a Turn is running, THE Builder_Panel SHALL show a collapsible activity list with one line per tool call, each with a readable label, a status (running, done, failed, refused) and a duration. (FR-16.2)
3. WHEN the user expands an activity line, THE Builder_Panel SHALL show that call's `tool_finished` summary and, for script calls only, the command the Builder_Agent ran. Draft strength: MAY. (FR-16.2, FR-35.1)
4. THE Builder_Panel SHALL keep file contents, environment values and raw tool arguments, other than a script call's command line, out of the activity list. (FR-16.2, FR-35.5)
5. WHEN a `check_result` event arrives, THE Builder_Panel SHALL show its source, verdict, error count and warning count, plus the attempt and attempts left when present, for example "Skill validator: VALID, 1 warning" or "Platform check: 2 problems, fixing (attempt 1 of 2)". (FR-16.3, FR-35.1)
6. WHEN a `limit_warning` event arrives, THE Builder_Panel SHALL show a quiet notice naming the limit kind and how much is left, for example "About 3 minutes left in this turn". (FR-16.4, FR-35.1)
7. WHEN a Turn ends, THE Builder_Panel SHALL collapse the activity list to a one-line summary of the Turn's tool-call count, check-result count and duration, for example "14 actions, 2 checks, 1 min 40 s", that the user can expand again. (FR-16.5)
8. WHEN a tab opens or reloads a Session, THE Builder_Panel SHALL show each ended Turn's stored activity list, collapsed to its one-line summary. (FR-16.5, FR-25.2)
9. WHEN a tab opens or reloads the Session while a Turn is running, THE Builder_Panel SHALL show the stored activity so far and "Still working", then, when the Turn ends, the final assistant message and any accepted Draft, without replaying text written before the reload. (FR-16.6, FR-12.2, Q-28)
10. WHILE a Turn is running, THE Builder_Panel in every open tab other than the sending tab SHALL show that Turn's Stage, elapsed time, activity list and check results from the Session_Stream. (FR-16.7, Q-27, Q-57)
11. WHEN a Turn ends, THE Builder_Panel in every other open tab of the Session SHALL load the new transcript and any accepted Draft, asking first when the Unsaved_Work_Guard reports unsaved changes. (FR-16.7, R-27)
12. WHEN the Builder_Panel opens, THE Session_Stream_Hook SHALL open the Session_Stream. (FR-16.8)
13. WHILE the Builder_Panel is mounted, including while collapsed, THE Session_Stream_Hook SHALL keep the Session_Stream open, so that the sending tab receives every event of the sending tab's Turn. (FR-16.8)

### Requirement 18: The builder deep agent

**User Story:** As a platform engineer, I want a dedicated deep agent for building workflows, so that workflow creation has its own method and limits without touching the runtime kernel.

#### Acceptance Criteria

1. THE Builder SHALL provide a Builder_Agent separate from workflow step agents and from the concierge, built with the real `deepagents` library through DeepAgentRunner. (FR-20.1, INV-13)
2. THE Builder_Agent SHALL use the Skill as the Builder_Agent's method. (FR-20.2, Q-47)
3. THE Builder SHALL change no file of the Skill_Folder. (FR-20.2, FR-32, §3.2, §8.11)
4. THE Builder_Agent SHALL read the Builder_Agent's skill list from data, so that another builder skill can be added without a code change. (FR-20.2, Q-47)
5. THE Builder_Agent SHALL run outside the ExecutionEngine. (FR-20.4, SC-001, INV-1)
6. THE Builder SHALL leave the ExecutionEngine kernel unedited. (FR-20.4, SC-001, INV-1)
7. THE Builder_Agent SHALL NOT save, launch or delete anything, so that saving, launching and deleting stay user actions. (FR-20.5, FR-09.3)
8. THE Builder_Agent SHALL write files only inside the Session's Sandbox, at the paths that Requirement 27 allows for writes, and SHALL change stored data only through the Session_Store. (FR-20.5, FR-23 SR-08)

### Requirement 19: System prompt

**User Story:** As a platform engineer, I want the system prompt to carry only what the skill cannot know, so that the skill stays the single method and the agent still fits this product.

#### Acceptance Criteria

1. THE Builder SHALL keep the System_Prompt in a versioned file. (FR-20.3)
2. THE System_Prompt SHALL contain only the content that criteria 3 to 9 require. (FR-20.3, §8.11)
3. THE System_Prompt SHALL state the product context: the user works in a chat panel next to a canvas, saves and runs from the canvas, and receives no file. (FR-20.3.1)
4. THE System_Prompt SHALL tell the Builder_Agent to pass each script command line to `run_skill_script`, that `<skill>` is `/skills/velocity-workflow-creator`, and that the platform compiler check is available through `validate_manifest.py --compiler`. (FR-20.3.2, FR-33.5)
5. THE System_Prompt SHALL restate the re-activation rule that description truncation cuts: follow the Skill from step 1 on every message that creates or changes a workflow. (FR-20.3.3, S-06, R-10)
6. THE System_Prompt SHALL tell the Builder_Agent to read each Skill file in full with one `read_file` call, and SHALL state a line limit at least as large as the line count of the longest Markdown file in the deployed Skill. (FR-20.3.4, Q-45 a, S-05, R-09)
   Fact check 2026-11-05: the longest file is `docs/catalog.md` at 757 lines; `patterns.md` (481 lines), which the draft's FR-20.3.4 names as the longest, is second. See G-38.
7. THE System_Prompt SHALL tell the Builder_Agent to write the manifest to a file under `/workflows/` and then call `propose_draft` with that file's path. (FR-20.3.5, FR-24.1)
8. THE System_Prompt SHALL tell the Builder_Agent to replace the Skill's "Run it" section with canvas instructions (Save, Run once) and to keep the list of Launch_Needs. (FR-20.3.5, FR-14.3, Q-44, S-13)
9. THE System_Prompt SHALL state that step models come from the Step_List, that a Draft must not use the features in Requirement 23's feature-list criterion, and that the Target_Trust is chosen by the rule in Requirement 37's Target_Trust criterion. (FR-20.3.6, Q-46, Q-53)

### Requirement 20: Sessions, sandbox and skill access

**User Story:** As a platform engineer, I want each session to have its own working files and read-only access to the deployed skill, so that turns are isolated and the skill cannot be changed.

#### Acceptance Criteria

1. WHEN a Session is created, THE Builder_API SHALL record the owner, the mode (create or edit), the linked workflow id (nullable), the model, the effort, the Target_Trust and the Skill_Hash of the deployed Skill. (FR-21.1, Q-20, Q-40)
2. THE Turn_Runner SHALL build a new Builder_Agent graph for every Turn, with no checkpointer and no agent state carried over from earlier Turns. (FR-21.2, §6 item 2, Q-55)
3. THE Builder SHALL use the Session id as the trace id for logs and traces. (FR-21.2)
4. THE Builder SHALL give each Session a Sandbox on disk that holds `/canvas/` (written by the server), `/workflows/` (the Builder_Agent's manifests), exported payloads and each script call's temp folder. (FR-21.3)
5. THE Builder SHALL create each Sandbox as a plain folder without a git repository. (FR-21.3, R-04)
6. THE Skill_View SHALL serve the deployed Skill read-only under `/skills/`. (FR-21.4)
7. IF the Builder_Agent attempts to write, edit or create a file under `/skills/`, THEN THE Skill_View SHALL refuse the operation, return the refusal as the tool result, and leave the deployed Skill's files unchanged. (FR-21.4)
8. THE Builder SHALL copy no Skill file into any Session's Sandbox. (FR-21.4)
9. WHEN a Turn starts, THE Turn_Runner SHALL use the Skill version deployed at that time and record that Skill_Hash on the Turn's messages. (FR-21.5, Q-40)
10. WHEN the Builder_Panel shows a message whose Skill_Hash differs from the Session's previous message's Skill_Hash, THE Builder_Panel SHALL show one line at that point in the transcript saying the builder was updated. (FR-21.5, Q-40)
11. THE Builder SHALL keep each Sandbox until the user deletes the Session or the account, except each script call's temp folder, which is removed when the call ends. (FR-21.6, FR-31.3, FR-31.4, §7.1, Q-41)
12. IF a Session's Sandbox does not exist on disk when a Turn starts, THEN THE Turn_Runner SHALL recreate the Sandbox before the Builder_Agent runs and write into it the latest accepted Draft and the latest Unproposed_Revision from the Session_Store. (FR-21.6, FR-24.8)
13. WHEN an edit Session is created, THE Builder_API SHALL store the row's effective manifest as Draft_Revision 0. (FR-21.8, Q-12)
14. IF an edit Session is requested for a workflow the user does not own, THEN THE Builder_API SHALL create no Session and no Draft_Revision. (FR-22.9, FR-21.1)
15. WHEN an edit Session is created for a row whose base is not `custom`, THE Builder_API SHALL fill in the base pipeline's own top-level settings (deliverable, planner, clarify) in Draft_Revision 0, so that the Builder_Agent sees what the workflow does today; the design decides how. (FR-21.8, Q-39)
16. WHEN the linked workflow is deleted, THE Builder SHALL set the Session's linked workflow id to null and keep the Session's messages, Draft_Revisions and Sandbox. (FR-21.9, Q-12)

### Requirement 21: Session and turn endpoints

**User Story:** As a frontend developer, I want REST endpoints for sessions and messages that return quickly and run turns in the background, so that the UI stays responsive and turns survive disconnects.

#### Acceptance Criteria

1. THE Builder_API SHALL offer, under one prefix such as `/api/workflow-builder`, endpoints to create, list, get and delete a Session; send a message; open the Session_Stream; cancel a Turn; undo the last AI change; link a Session to a saved workflow; and list the chat models. The design settles the names. (FR-22.1)
2. THE Builder_API SHALL accept a message as `{content, model_id, effort, canvas_state, client_message_id}`. (FR-22.2)
3. WHEN a message passes the Capacity_Gate check (Requirement 29) and the other checks in this requirement, THE Builder_API SHALL store the user message and return 202 with the Turn id and the message id. (FR-22.2, Q-57)
4. THE Builder_API SHALL deliver a Turn's events through the Session_Stream and keep the send-message response free of Turn events. (FR-22.2, Q-57)
5. WHEN the Builder_API accepts a message, THE Turn_Runner SHALL run the Turn as a background task outside the request. (FR-22.3, Q-28)
6. IF every client disconnects from the Session_Stream while a Turn runs, THEN THE Turn_Runner SHALL continue the Turn and store the Turn's result. (FR-22.3, FR-12.2, Q-28)
7. IF a message arrives for a Session that has a running Turn, THEN THE Builder_API SHALL return 409 and start no Turn for that message. (FR-22.4, Q-27)
8. THE Builder_API SHALL decide whether a Session has a running Turn from the stored Session state, so that a restart cannot leave two Turns running. (FR-22.4, NFR-04)
9. WHEN a Turn ends, THE Turn_Runner SHALL store the assistant message, with the text generated before the end, and exactly one status: `completed`, `failed`, `cancelled`, `timed_out` or `interrupted`. (FR-22.5)
10. IF a message arrives with a `client_message_id` that the Session already holds, THEN THE Builder_API SHALL start no second Turn and store no second user message. (FR-22.6, FR-12.1, NFR-04)
11. IF `canvas_state` is not the Composer's full manifest, THEN THE Builder_API SHALL reject the message without starting a Turn. (FR-22.7, NFR-01)
12. IF `canvas_state` is larger than 512 KB, THEN THE Builder_API SHALL reject the message without starting a Turn. [placeholder: Q-51] (FR-22.7, §7.1)

### Requirement 22: Shutdown, restart and interrupted turns

**User Story:** As a user, I want a deploy or restart to leave my session usable with the work so far kept, so that I can continue instead of starting over.

#### Acceptance Criteria

1. WHEN the server shuts down, THE Turn_Runner SHALL stop every running Turn and store each stopped Turn's assistant message, including any partial text, with status `interrupted`. (FR-22.10, FR-22.5, R-23)
2. WHEN the server starts, THE Turn_Runner SHALL mark every Turn whose stored status is still running as `interrupted`. (FR-22.10)
3. WHEN a Turn is marked `interrupted`, THE Turn_Runner SHALL keep the Session's Sandbox files, except the script-call temp folders removed under FR-31.3, and SHALL apply Requirement 23's Unproposed_Revision criterion to that Turn. (FR-22.10, FR-24.8, FR-31.3, Q-54)
4. WHEN a Turn is marked `interrupted`, THE Builder_API SHALL stop treating the Session as having a running Turn, so that the Session's next message gets no 409 under Requirement 21. (FR-22.10, FR-22.4)
5. WHEN the server starts, THE Turn_Runner SHALL start no Turn and make no Builder_Agent call for any Interrupted_Turn. (FR-22.10, Q-55)

### Requirement 23: Draft contract and server gate

**User Story:** As a platform owner, I want every AI draft checked by the same validation as save, plus explicit builder rules, before the canvas sees it, so that the canvas never shows a workflow the product cannot save or run.

#### Acceptance Criteria

1. THE Draft SHALL be the Skill's full manifest: `id`, `planner`, `clarify`, `deliverable`, `steps` and presentation keys. (FR-24.1, S-07)
2. WHEN the Builder_Agent calls `propose_draft` with a file path, THE Server_Gate SHALL read the Draft from that Sandbox file, so that the model does not resend the JSON. (FR-24.1)
3. WHEN `propose_draft` is called, THE Server_Gate SHALL check the Draft with the same code save uses (`_validated_manifest` calling `_compile_check_manifest`) at the Target_Trust, before any `draft_applied` event. (FR-24.2, Q-46, §8.5, §8.6)
4. THE Server_Gate SHALL apply the Builder_Rules: the agent-id allow-list, model entitlement, step models from the Step_List, and the feature list in criterion 5. (FR-24.2)
5. IF a Draft uses an `exec`, `network` or `secrets` grant, the `filesystem` or `postgres` MCP server, or the `previous_run` context provider, THEN THE Server_Gate SHALL reject the Draft with an error that names the feature and says why the feature cannot be used. (FR-24.2, Q-53, R-17)
6. THE Server_Gate and the Turn_Context SHALL read the criterion 5 feature list from one definition. (FR-24.2, FR-34.5, Q-53)
7. THE Server_Gate's feature list SHALL contain only the criterion 5 features and additions the user has approved. (FR-24.2)
8. THE Server_Gate SHALL reject a Draft only for a save-check error or a Builder_Rules violation. (FR-24.2, §8.5)
9. WHEN the Builder_Agent runs the Skill_Validator, THE Builder_Panel SHALL show the Skill_Validator's findings as tool activity. (FR-24.3, §8.13)
10. IF the Server_Gate rejects a Draft, THEN THE Server_Gate SHALL return the errors to the Builder_Agent as the `propose_draft` tool result, without storing a Draft_Revision or sending `draft_applied`. (FR-24.4, FR-06.4)
11. THE Turn_Runner SHALL count each Server_Gate rejection of `propose_draft` toward a limit of 2 per Turn, excluding Dry_Runs. [placeholder: Q-24] (FR-24.4, Q-37)
12. IF the Server_Gate rejects a Draft for the second time in a Turn, THEN THE Turn_Runner SHALL end the Turn with status `completed` and outcome `unfinished`, with an assistant message saying the Draft failed the Server_Gate and which checks failed, leaving the Canvas unchanged. [decided: G-12] (FR-24.4, Q-37)
13. WHEN the Server_Gate accepts a Draft, THE Session_Store SHALL store the Draft as a numbered Draft_Revision. (FR-24.5, Q-10)
14. WHEN the Server_Gate accepts a Draft, THE Session_Stream SHALL send `draft_applied` to every open tab of the Session. (FR-24.5, §6 step 6)
15. WHEN the user undoes an AI change, THE Session_Store SHALL store the undo as a numbered Draft_Revision. (FR-24.5, Q-10)
16. THE Server_Gate SHALL treat every Draft as a full replacement of the previous revision. (FR-24.6, Q-06)
17. WHEN the Server_Gate accepts a Draft, THE Server_Gate SHALL derive the Change_Summary and the Launch_Needs from the accepted manifest and include both in `draft_applied`. (FR-24.7)
18. IF a Turn ends with status `timed_out`, `interrupted`, `cancelled` or `failed`, or with status `completed` and outcome `unfinished` (criterion 12), without an accepted Draft, and the Builder_Agent changed a file under `/workflows/` during the Turn, THEN THE Turn_Runner SHALL store the most recently changed file as an Unproposed_Revision. (FR-24.8, Q-54)

### Requirement 24: Conversation persistence

**User Story:** As a user, I want my conversations, drafts and progress stored, so that I can resume them later on any device.

#### Acceptance Criteria

1. THE Session_Store SHALL store Sessions, messages and Draft_Revisions in three new tables: `workflow_builder_sessions`, `workflow_builder_messages` and `workflow_builder_drafts`, separate from the existing `chat_sessions` and `messages` tables. (FR-25.1, Q-14)
2. THE Session_Store SHALL store each Draft_Revision in `workflow_builder_drafts` with its revision number and its kind: edit-Session seed, accepted Draft, undo, or Unproposed_Revision. (FR-25.1, FR-24.5, FR-21.8)
3. THE Session_Store SHALL store each user and assistant message with its status, model id, effort, Skill_Hash, token usage and any reasoning the Builder_Panel shows. An assistant message's status SHALL be one of `completed`, `failed`, `cancelled`, `timed_out` or `interrupted`. (FR-25.2, FR-22.5, FR-27.3, FR-21.5, Q-13, Q-16)
4. THE Session_Store SHALL store each Session's Transcript_Summary and the tokens used to write it, counted toward the Session's usage. (FR-25.2, FR-26.4, NFR-03)
5. WHEN a tool call ends with status `ok`, `error`, `refused` or `timed_out`, THE Session_Store SHALL store that call's tool activity before the Turn ends: tool, label, status, duration and truncated result, plus the command and exit code for script calls. (FR-25.2, FR-33.11, FR-35.1, FR-16.6, Q-13)
6. THE Session_Store SHALL give every new table `owner_id` and `workspace_id` columns. (FR-25.3, §8.7)
7. THE Session_Store SHALL use `user_id` as the authorisation key. (FR-25.4)
8. THE Builder_Migration SHALL create the Session_Store tables without dropping or altering any existing table or column, and SHALL leave exactly one Alembic head, as printed by `uv run alembic heads` from `backend/`. (FR-25.3, §8.7)
9. THE Builder SHALL keep Sessions, messages, tool activity, Draft_Revisions, Transcript_Summaries and Sandboxes until the user deletes the Session or the account, and SHALL NOT expire or clean them up automatically. The one exception is each script call's temp folder, which is removed when the call ends. (FR-25.5, FR-31.3, Q-41)

### Requirement 25: Stateless turn input: transcript replay and summary

**User Story:** As a platform engineer, I want each turn built from the stored transcript rather than carried agent state, so that turns survive restarts, model changes and long sessions.

#### Acceptance Criteria

1. WHEN a Turn starts, THE Turn_Runner SHALL build the Builder_Agent's input from the System_Prompt, the Transcript_Replay and the Turn_Context. (FR-26.2, Q-55)
2. THE Turn_Runner SHALL build the Transcript_Replay from user and assistant messages and the Transcript_Summary only, leaving out earlier Turns' tool calls, tool results and thinking. (FR-26.2, S-18, Q-55)
3. THE Turn_Runner SHALL fill the Transcript_Replay with user and assistant messages, verbatim, selected from the newest to the oldest, until adding the next message would exceed a budget of 25 % of the context window of the model chosen for the message: 250,000 tokens on Sonnet 5.5 and Haiku 5.5, 50,000 tokens on Opus 4.6. [proposed, set after the Spike] (FR-26.3, §7.1, R-24)
4. WHEN a Turn starts, THE Turn_Runner SHALL recompute the replay budget for the model chosen for that message. (FR-26.3, Q-15)
5. THE Turn_Runner SHALL represent the messages left out of the Transcript_Replay by the stored Transcript_Summary. (FR-26.3)
6. THE Turn_Runner SHALL replay the latest 4 Turns verbatim, even when they exceed the replay budget. [proposed] (FR-26.5, R-25)
7. WHEN the Turn_Runner writes or updates the Transcript_Summary, THE Turn_Runner SHALL include every answer the user gave to the Builder_Agent's questions, every requirement or constraint the user stated, and the Workflow Brief and Decisions from the latest report. (FR-26.4, R-25)
8. WHEN a Turn starts, no Transcript_Summary exists and the stored messages exceed the replay budget for that Turn's model, THE Turn_Runner SHALL write and store the Transcript_Summary before building the Transcript_Replay. (FR-26.4)
9. WHEN a Turn starts and the stored Transcript_Summary does not cover every message left out of the Transcript_Replay, THE Turn_Runner SHALL update and store the Transcript_Summary to cover those messages before building the Transcript_Replay. (FR-26.4)
10. WHEN the Turn_Runner writes or updates the Transcript_Summary, THE Session_Store SHALL store that token usage with the Turn's message and count it toward the Session. (FR-26.4, NFR-03)

### Requirement 26: Model and effort validation per message

**User Story:** As a platform owner, I want every message's model and effort checked on the server, so that users only use models they are entitled to.

#### Acceptance Criteria

1. WHEN the Builder_API receives a message, THE Builder_API SHALL check its `model_id` against the Chat_List filtered by the user's entitlement (`_model_entitlement_error`, `TIER_MODEL_COST_CLASSES`) and against the GPT exclusion. (FR-27.1, FR-36.8, Q-29, Q-50, Q-56)
2. IF `model_id` fails the check in criterion 1, THEN THE Builder_API SHALL reject the message without starting a Turn. (FR-27.1)
3. IF `effort` is not one of the `reasoning_levels` of the model named by `model_id` in the same message, THEN THE Builder_API SHALL reject the message with 422 without starting a Turn. (FR-27.2, FR-05.3)
4. WHEN the Builder_API accepts a message, THE Session_Store SHALL record the message's `model_id` and `effort` on that user message and on the assistant message of the Turn it starts. (FR-27.3, FR-25.2)
5. WHEN the Builder_API accepts a message, THE Session_Store SHALL set the Session's default model and effort to that message's `model_id` and `effort`. (FR-27.3, FR-05.5, Q-15)

### Requirement 27: Agent tool set

**User Story:** As a platform engineer, I want the agent to have exactly the tools the skill's procedure needs, so that it can build workflows without broader access.

#### Acceptance Criteria

1. THE Harness SHALL give the Builder_Agent the deepagents `read_file`, `ls`, `glob` and `grep` tools over the Skill_View. (FR-23 SR-01)
2. THE Harness SHALL give the Builder_Agent the deepagents `write_file` and `edit_file` tools, scoped to `/workflows/`. (FR-23 SR-02)
3. IF the Builder_Agent calls `write_file` or `edit_file` on a path outside `/workflows/`, THEN THE Harness SHALL refuse the call and leave the target path unchanged. (FR-23 SR-02, SR-08, FR-21.4)
4. THE Harness SHALL give the Builder_Agent the Script_Runner for `catalog_lookup.py` and the check scripts (`validate_manifest.py`, `selftest.py`, the `--check` modes). (FR-23 SR-03, SR-04)
5. THE Harness SHALL return the platform compiler's verdict to the Builder_Agent as the result of each Dry_Run (`validate_manifest.py --compiler`) and each `propose_draft` call. (FR-23 SR-05)
6. THE Harness SHALL give the Builder_Agent `propose_draft` as its only way to hand a manifest to the Canvas. (FR-23 SR-06, SR-08)
7. THE Harness SHALL give the Builder_Agent read tools for facts the Catalog_Snapshot lacks: the user's own agents, the user's skills, existing workflow names (to pick a unique name), configured connectors, and the workflows the user may hand off to. (FR-23 SR-07, Q-43)
8. THE Harness SHALL give the Builder_Agent a read tool that returns the Builder_Model_Catalog filtered by the user's entitlement. (FR-23 SR-09, FR-36.7, FR-36.8)
9. THE Harness SHALL give the Builder_Agent no shell, no `execute`, no `task`, no network access, and no write access outside `/workflows/` and each script call's temp folder. (FR-23 SR-08, FR-29.2, §8.12)
10. THE Builder_Agent's tools SHALL write only to the Session's Sandbox and the Session_Store, and SHALL NOT save, launch or delete anything. (FR-20.5, §3.2, Q-18)
11. THE Harness SHALL give the Builder_Agent exactly the tools in the user-supplied tool list, and that list SHALL provide every capability in criteria 1 to 10. (FR-23, Q-18)

### Requirement 28: Agent harness and turn limits

**User Story:** As a platform owner, I want each turn bounded in time, tool calls and tokens, and its adherence to the skill recorded, so that turns cannot run away and quality can be measured.

#### Acceptance Criteria

1. THE Harness SHALL reuse the DeepAgentRunner middleware stack. (FR-29.1, Q-19)
2. THE Harness SHALL keep `task` and `execute` off, so that scripts run only through the Script_Runner. (FR-29.2)
3. THE Harness SHALL keep deepagents summarisation on inside a Turn as a backstop, keeping the user's message and the Turn_Context verbatim and allowing old tool results to be dropped. (FR-29.3)
4. THE Harness SHALL apply the tool-call, token-budget and `propose_draft` rejection limits in Requirement 47, and the DeepAgentRunner's existing recursion limit. (FR-29.4)
5. WHEN a Turn reaches 900 s, counted from Turn start after the Capacity_Gate check, THE Turn_Runner SHALL stop the Turn with status `timed_out`. (FR-29.4, Q-54)
6. WHEN a Turn reaches 80 % of the turn cap (720 s while the cap is 900 s), THE Session_Stream SHALL send `limit_warning` with kind `time`. (FR-29.4, FR-35.1, Q-54)
7. WHEN a Turn reaches 80 % of the tool-call limit, THE Session_Stream SHALL send `limit_warning` with kind `tool_calls`. (FR-35.1)
8. WHEN a Turn reaches 80 % of a token budget, THE Session_Stream SHALL send `limit_warning` with kind `tokens`. [Q-51; values pending the Spike] (FR-35.1)
9. WHEN a Turn reaches 80 % of the time limit or of the tool-call limit, THE Harness SHALL tell the Builder_Agent how much remains, so that the Builder_Agent can finish checking and call `propose_draft` before the cap. Draft strength: SHOULD. (FR-29.7)
10. WHEN a Turn ends with any status, THE Harness SHALL store the Turn's Adherence_Record. (FR-29.5, Q-45 a)
11. WHERE the Spike has set a turn cap, THE Turn_Runner SHALL apply that cap in place of 900 s. (FR-29.4, Q-38, Q-54)

### Requirement 29: Capacity gate

**User Story:** As a platform owner, I want builder messages to go through the same capacity check as launches, so that the host is not overloaded and users see a familiar busy message.

#### Acceptance Criteria

1. WHEN the Builder_API receives a send-message request, THE Builder_API SHALL run the same Capacity_Gate check as launches before it stores the user message or starts a Turn. (FR-29.6, FR-22.2, Q-25)
2. IF the Capacity_Gate refuses a message, THEN THE Builder_API SHALL return the same response as for a refused launch (503, code `host_capacity_exhausted`, `recoverable: true`, a `Retry-After` header) and SHALL store no message. (FR-29.6)
3. IF the Capacity_Gate refuses a message, THEN THE Builder_API SHALL NOT queue the message, start a Turn for it, or send any Session_Stream event for it, then or after capacity frees. (FR-29.6, §2.1 Capacity gate, FR-16.4, FR-35.3)
4. IF the caller is an admin whom the Capacity_Gate exempts for launches, THEN THE Builder_API SHALL skip the Capacity_Gate check for the message. (FR-29.6)
5. WHILE the Capacity_Gate has no metrics, THE Builder_API SHALL let messages through, as the Capacity_Gate does for launches. (§2.1 Capacity gate)

### Requirement 30: Cancel a turn

**User Story:** As a user, I want to stop a running turn from any tab, so that I can change direction without waiting.

#### Acceptance Criteria

1. WHILE a Turn is running, THE Builder_Panel SHALL show the Stop control (Requirement 5) in every tab that has the Session open, including tabs that did not send the message. (FR-30.1, FR-04.4)
2. WHEN the Builder_API receives a cancel request for a running Turn, THE Turn_Runner SHALL stop the Builder_Agent and end any Script_Runner subprocess running for that Turn. (FR-30.2)
3. WHEN a Turn is cancelled, THE Turn_Runner SHALL store the assistant message, including any partial text, with status `cancelled`. (FR-30.2, FR-22.5)
4. WHEN a Turn is cancelled, THE Session_Stream SHALL send no `draft_applied` event for that Turn after the cancel request. (FR-30.3)
5. WHEN a Turn is cancelled, THE Turn_Runner SHALL keep the Sandbox files and SHALL store an Unproposed_Revision under the conditions in Requirement 23's Unproposed_Revision criterion. (FR-30.4, FR-24.8)

### Requirement 31: List and delete sessions

**User Story:** As a user, I want to list and delete my conversations, and know nothing is deleted behind my back, so that I control my data.

#### Acceptance Criteria

1. WHEN the user lists Sessions, THE Builder_API SHALL return the user's Sessions paginated, newest first. (FR-31.1, Q-11)
2. WHEN the user deletes a Session, THE Builder_API SHALL remove the Session and its messages, tool activity, Draft_Revisions, Transcript_Summary and Sandbox. (FR-31.2, Q-11)
3. WHILE a Turn of the Session is running, WHEN the user deletes the Session, THE Builder_API SHALL cancel that Turn, with no Draft emitted, before removing any of the Session's data. (FR-31.2, FR-30.3)
4. WHEN a Session is deleted, THE Session_Stream SHALL send `session_deleted` on every open stream of that Session and then close those streams. (FR-31.2)
5. THE Builder SHALL NOT delete, expire or clean up any Session, message, tool activity, Draft_Revision, Transcript_Summary or Sandbox, except when the user deletes that Session or the user's account, and except for the temp-folder removal in criterion 6. (FR-31.3, FR-25.5, Q-41, §8.14)
6. WHEN a script call ends, including by a non-zero exit, a timeout or a cancel, THE Script_Runner SHALL remove that call's temp folder. (FR-31.3, FR-33.6)
7. WHEN the user deletes the user's account, THE Builder SHALL delete all of that user's Sessions, messages, tool activity, Draft_Revisions, Transcript_Summaries and Sandboxes along with the rest of the user's data. (FR-31.4, NFR-07)

### Requirement 32: Skill in backend code

**User Story:** As a platform engineer, I want the skill to live in the backend, in the Builder's own folder, so that it ships with the app and there is exactly one copy to edit.

#### Acceptance Criteria

1. THE Builder SHALL treat the Skill_Folder as the only copy of the Skill and its source of truth. There is no copy under `.kiro` and no sync step. (FR-32.1, Q-52)
2. THE Skill_Folder SHALL live at `backend/app/agents/workflow_builder/skills/velocity-workflow-creator/`. Other locations fail: `backend/skills/` is left out of the image and hidden by the `/app/skills` volume, and its skills appear in the Skills library; `backend/tools/` is left out of the image. (FR-32.2, S-16, R-15)
3. (Removed 2026-11-10: the Skill_Sync_Command. A developer edits the Skill_Folder in place and commits the change. Formerly FR-32.3, S-15.)
4. (Removed 2026-11-10: the comparison of a Source_Skill with a Backend_Copy. There is one copy.)
5. THE Backend_Image SHALL include the Skill_Folder, because it sits under `app/`, which `backend/Dockerfile` copies. A re-include in `backend/.dockerignore` keeps the Skill_Folder's `.md` files, which the `*.md` rule would otherwise drop. (FR-32.4, §6 item 1, R-19)
6. IF a mandatory file of the Skill_Folder is absent in the Backend_Image, THEN THE Backend_Image build SHALL fail. The build checks `SKILL.md`, three guide files and `validate_manifest.py`. At run time, a missing mandatory file (the guides and the scripts the script policy allows) SHALL make the Builder unavailable (503 `builder_unavailable`) while the rest of the app keeps serving. (FR-32.4, R-19, G-21)
7. THE CI_Pipeline and the static analysis tools SHALL exclude the Skill_Folder from ruff, pyright, vulture, bandit, compileall and coverage. Its scripts are standalone tools run only as subprocesses, checked by their own `selftest.py`, and the app never imports them. (FR-32.5, R-19)
8. THE Builder SHALL read the Skill from the fixed path `app/agents/workflow_builder/skills/`, worked out from the location of `skill_package.py`. No setting names the folder. The `BUILDER_SKILLS_ROOT` and `BUILDER_SKILL_IDS` settings were removed on 2026-11-10. (FR-32.6, G-21)
9. THE Builder SHALL compute the Skill_Hash and the line counts from the files of the Skill_Folder on disk, in path order, each time they are needed, so that identical files give the same Skill_Hash and a changed, added, removed or renamed file gives a different one. No lock file is stored. [see G-20] (FR-32.7, S-15, Q-40)
10. THE Builder SHALL keep the Skill_Folder outside the global skills root, so that the Skills library does not offer the Skill as a step skill. (S-16, R-15)
11. WHILE the Builder runs Sessions, Turns and Script_Runner calls, THE Builder SHALL NOT create, change or delete any file in the Skill_Folder, including `__pycache__` files. (§8.11, Q-52, Q-58, R-20)
12. (Removed 2026-11-10: the warning on jsonschema and PyYAML pins, FR-32.9 and S-02. Pin drift is no longer checked in CI.)

### Requirement 33: Skill checks in CI

**User Story:** As a platform engineer, I want CI to check that the skill still runs and that the Builder's model list matches the skill's snapshot, so that a broken skill or a missing model is caught before users see it.

#### Acceptance Criteria

1. THE CI_Pipeline SHALL run `selftest.py` on the Skill_Folder, both plain and with `--compiler` against the backend, and SHALL fail if either run fails or leaves a new file in the Skill_Folder. (FR-32.8, §8.11, Q-52)
2. (Removed 2026-11-10: rebuilding the catalog from source and comparing it with the committed `catalog.json`. FR-32.8, Q-43, S-14. Q-61 no longer applies. `selftest.py` still checks that `catalog.md` and the schema match `catalog.json`.)
3. (Removed 2026-11-10: sending the rebuild's outputs to a temp folder. FR-32.8, S-04.)
4. (Removed 2026-11-10: checking the Skill_Folder is unchanged after the other checks. Criterion 1 now covers this for `selftest.py`.)
5. (Removed 2026-11-10: running `refresh_catalog.py --check` in CI. FR-32.8.)
6. (Removed 2026-11-10: naming each differing catalog entry in the job output. FR-32.8, S-14, R-13.)
7. (Removed 2026-11-10: warning or blocking on catalog differences. FR-32.8, Q-61.)
8. THE CI_Pipeline SHALL check that the id of every model flagged for the Step_List in the Model_Catalog, before entitlement filtering, appears among the Catalog_Snapshot's models. (FR-36.5, FR-36.8, R-18)

### Requirement 34: Script runner: command parsing and paths

**User Story:** As a platform engineer, I want the agent to run skill commands exactly as the skill writes them, safely parsed and confined to the session, so that the skill works unchanged without a shell.

#### Acceptance Criteria

1. THE Script_Runner SHALL be the `run_skill_script(command)` tool and accept the command line as the Skill writes the command. (FR-33.1)
2. THE Script_Runner SHALL split the command into arguments without a shell and run one script per call. (FR-33.1)
3. IF a command contains chaining (`&&`, `;`, `|`), a redirect, or inline code (`python -c`), THEN THE Script_Runner SHALL refuse the command without starting a subprocess. (FR-33.1)
4. WHEN a command starts with `python`, `py -3`, `python3` or `uv run python`, THE Script_Runner SHALL accept the command and discard the launcher. (FR-33.2)
5. THE Script_Runner SHALL run every accepted script with the backend's own interpreter with bytecode writing off, so that no `__pycache__` is written into the Skill_Folder. (FR-33.2, S-03, R-20, NFR-09)
6. THE Script_Runner SHALL map a path that begins with `/skills/velocity-workflow-creator/`, `<skill>/`, or the repository path `app/agents/workflow_builder/skills/velocity-workflow-creator/` (also with a leading `./`, `backend/` or `./backend/`), written with forward slashes or backslashes, to the Skill_Folder. The `.kiro/skills/...` spellings were dropped on 2026-11-10, because that folder is no longer the skill the Builder runs. (FR-33.3, FR-32.6)
7. THE Script_Runner SHALL resolve every other path, absolute (such as `/workflows/<id>.workflow.json`) or relative, against the root of the calling Session's Sandbox. (FR-33.3, FR-33.6, §6 item 5)
8. IF a path, after its `.` and `..` segments are resolved, lies outside the calling Session's Sandbox and outside the Skill_Folder, THEN THE Script_Runner SHALL refuse the command without starting a subprocess. (FR-33.3, R-05)

### Requirement 35: Script runner: allow-list policy

**User Story:** As a platform owner, I want only read-only and check modes of the skill's scripts to run, so that the skill never changes at run time and no script reaches the network.

#### Acceptance Criteria

1. THE Script_Runner SHALL allow every `catalog_lookup.py` subcommand: overview, models, icons, kind, agents, agent, skills, workflows, mcp, trust, field, search and example. (FR-33.4, Q-58)
2. IF a `catalog_lookup.py` or `validate_manifest.py` call passes `--catalog` or `--schema`, THEN THE Script_Runner SHALL refuse the call, so that the script always reads the Skill's own files. (FR-33.4, S-04)
3. THE Script_Runner SHALL allow `validate_manifest.py` on a manifest inside the Sandbox, with the options `--trust`, `--summary`, `--json`, `--strict`, `--quiet-info` and `--compiler`; Requirement 36 answers `--compiler` with a Dry_Run. (FR-33.4, FR-33.5)
4. IF the manifest path of a `validate_manifest.py` call, or the input or output path of an `export_manifest.py` call, resolves outside the Sandbox, including into the deployed Skill folder, THEN THE Script_Runner SHALL refuse the call. (FR-33.4, Q-52)
5. THE Script_Runner SHALL allow `selftest.py`, with the script's temp copies placed in the call's temp folder. (FR-33.4, S-04)
6. IF a `selftest.py` call passes `--compiler` or `--catalog`, THEN THE Script_Runner SHALL refuse the call; `--compiler` is refused because CI runs the compiler self-test. (FR-33.4, FR-32.8)
7. THE Script_Runner SHALL allow `refresh_catalog.py --check` and `schema_sync.py --check`. (FR-33.4)
8. IF a `refresh_catalog.py` or `schema_sync.py` call is not a `-h` or `--help` call and either omits `--check` or uses `--source`, `--api` or `--render`, THEN THE Script_Runner SHALL refuse the call, because the Skill never changes at run time. (FR-33.4, Q-52, Q-58, S-04)
9. THE Script_Runner SHALL allow `export_manifest.py` with its input path inside the Sandbox and its output path under the Sandbox's `/exports/` folder. [decided: G-02; narrows FR-33.4] (FR-33.4, FR-09)
10. THE Script_Runner SHALL allow `-h` and `--help` on each allowed script. (FR-33.4)
11. IF a call names a script other than `catalog_lookup.py`, `validate_manifest.py`, `selftest.py`, `refresh_catalog.py`, `schema_sync.py` or `export_manifest.py`, THEN THE Script_Runner SHALL refuse the call. (FR-33.4)
12. WHEN the Script_Runner refuses a call, THE Script_Runner SHALL start no subprocess and SHALL return the reason and the allowed alternative as the tool result, for example "The catalog is refreshed in CI. Use catalog_lookup.py to read it." (FR-33.8)

### Requirement 36: Script runner: execution

**User Story:** As a platform engineer, I want scripts run in an isolated, bounded subprocess with their results reported like a terminal, so that the API process stays safe and the agent can follow the skill's loop.

#### Acceptance Criteria

1. WHEN the Builder_Agent calls `validate_manifest.py --compiler <path>`, THE Script_Runner SHALL run the validator without `--compiler` in the subprocess, run a Dry_Run on the same file inside the server, append the Dry_Run result to the output, and return exit code 0 only when both the validator and the Dry_Run pass. (FR-33.5)
2. WHEN a Dry_Run returns, THE Server_Gate SHALL send no `draft_applied` event and SHALL NOT count the Dry_Run as a `propose_draft` rejection. (FR-33.5, Q-37)
3. THE Script_Runner SHALL run each script in a subprocess with the Sandbox as working directory and a minimal environment that sets `PYTHONDONTWRITEBYTECODE=1`, `PYTHONIOENCODING=utf-8`, and `TMP`, `TEMP` and `TMPDIR` to the call's temp folder. (FR-33.6, S-03, R-20)
4. THE Script_Runner SHALL start each subprocess without the database URL, AWS credentials, tokens or signing keys in the subprocess environment. (FR-33.6, R-16)
5. THE Script_Runner SHALL stop each call 30 s after its subprocess starts, and SHALL cap each call's combined output at 80,000 characters. [placeholder: Q-51] (FR-33.7, S-17)
6. THE Script_Runner SHALL cap concurrent script processes at 8 per host. [proposed] (FR-33.7)
7. IF a call's output exceeds the output cap, THEN THE Script_Runner SHALL cut the output and add a note saying so. (FR-33.7)
8. IF a call runs past the timeout, THEN THE Script_Runner SHALL stop the subprocess and end the call with `tool_finished` status `timed_out`. (FR-33.7, FR-35.1)
9. WHEN a call ends, THE Script_Runner SHALL return the exit code and the combined standard output and standard error as the tool result. (FR-33.8)
10. WHEN a call starts, THE Script_Runner SHALL emit `tool_started`, and WHEN the call ends, `tool_finished`, with the fields listed in Requirement 38. (FR-33.9, FR-35.1)
11. WHEN a `validate_manifest.py` call finishes, THE Script_Runner SHALL take the verdict from the last output line, or from the `valid` field when `--json` was passed, and emit `check_result` with source `skill_validator`, the verdict, the error count and the warning count. (FR-33.9, FR-35.1)
12. THE Script_Runner SHALL run every script outside the API process and start the subprocess without blocking the event loop. (FR-33.10, S-03, R-11, §8.15)
13. WHEN a call ends, THE Session_Store SHALL store the call as tool activity with the command, exit code, duration and truncated output. (FR-33.11, FR-25.2)

### Requirement 37: Turn context

**User Story:** As a platform engineer, I want the agent to receive the product facts the skill would otherwise ask about, so that it designs for this product without asking the user.

#### Acceptance Criteria

1. WHEN a Turn starts, THE Turn_Runner SHALL write the message's `canvas_state` to the Canvas_File before the Builder_Agent receives its input, and SHALL NOT overwrite files under `/workflows/`. (FR-34.1, FR-22.2, Q-54, §6)
2. THE Turn_Context SHALL state the mode (create or edit), name the Canvas_File, and say whether the Canvas changed since the last applied Draft. (FR-34.1)
3. IF the latest Unproposed_Revision has a higher revision number than the last applied Draft, THEN THE Turn_Context SHALL say so and name that revision's Sandbox file. (FR-34.2, FR-24.5, Q-54)
4. THE Turn_Context SHALL state `user` as the default Target_Trust, that `db` applies only when a requirement needs a `db` feature, and that the user is entitled to `db`. [see G-13] (FR-34.3, Q-46, Q-33, S-08)
5. THE Turn_Context SHALL state that the workflow is saved from the Composer and run with Run once, and whether the user's tier permits the `premium` cost class. (FR-34.3, FR-36.8, S-08)
6. THE Turn_Context SHALL list the id and cost class of each Step_List model the user is entitled to. (FR-34.4, FR-36.8)
7. THE Turn_Context SHALL list the features of Requirement 23's feature-list criterion, read from the list the Server_Gate uses. (FR-34.5, FR-24.2, Q-53)
8. THE Turn_Context SHALL state how many completed Turns ended without an accepted Draft before the Session's first accepted Draft. (FR-34.6, FR-15.3, Q-22)
9. THE Turn_Context SHALL state the Turn's time limit (900 s, Q-54) and tool-call limit (60 [placeholder: Q-51]). (FR-34.7, §7.1)
10. THE Turn_Context SHALL state the Skill path `/skills/velocity-workflow-creator`, that Skill script commands go to the Script_Runner, and that replies are in English. (FR-34.8, FR-20.3.2, Q-31)

### Requirement 38: Session event stream: event types

**User Story:** As a frontend developer, I want a defined set of SSE events per session, so that every tab can show the same progress and results.

#### Acceptance Criteria

1. THE Builder_API SHALL offer one Session_Stream per Session at `GET …/sessions/{id}/events` (SSE) that carries the Session's Turn events to every open tab. (FR-35.1, Q-57)
2. THE Session_Stream SHALL put a timestamp on every event, and SHALL put on every Turn-scoped event (`turn_started`, `stage`, `thinking`, `tool_started`, `tool_finished`, `check_result`, `draft_applied`, `text`, `limit_warning`, `turn_completed`), and on an `error` raised inside a Turn, the Turn id and a sequence number greater than that of the previous event of the same Turn. `snapshot`, `session_deleted`, `session_revoked`, `draft_restored` and a Session-level `error` carry no Turn id. [decided 2026-11-06] (FR-35.2)
3. WHEN a client connects, THE Session_Stream SHALL send `snapshot` with either idle or the running Turn's Stage, activity so far and start time, plus the latest message and revision ids. (FR-35.1)
4. WHEN a Turn starts, THE Session_Stream SHALL send `turn_started` with `turn_id`, `message_id`, `model_id`, `effort` and `skill_hash`. (FR-35.1)
5. WHEN the Stage changes, THE Session_Stream SHALL send `stage` with `stage` and `label`. (FR-35.1)
6. WHEN the Builder_Agent emits reasoning text during a Turn, THE Session_Stream SHALL send `thinking` with `text`. (FR-35.1, Q-16)
7. WHEN a tool call starts, THE Session_Stream SHALL send `tool_started` with `call_id`, `tool`, `kind` (read, write, script, lookup, propose), `label`, and `command` for script calls only. (FR-35.1)
8. WHEN a tool call ends, THE Session_Stream SHALL send `tool_finished` with `call_id`, `status` (ok, error, refused, timed_out), `duration_ms` and `summary`. (FR-35.1)
9. THE Session_Stream SHALL send exactly one `tool_finished` for every `tool_started`, with the same `call_id`. (FR-33.9, FR-35.1)
10. WHEN a Skill_Validator run, a Dry_Run or a `propose_draft` Server_Gate check returns, THE Session_Stream SHALL send one `check_result` for it, with `source` `skill_validator`, `platform_dry_run` or `server_gate` respectively, plus the verdict, error count, warning count, attempt and attempts left. (FR-35.1, FR-33.5, FR-33.9)
11. WHEN the Server_Gate accepts a Draft, THE Session_Stream SHALL send `draft_applied` with the revision, the Target_Trust, the Change_Summary, the Launch_Needs and the manifest. (FR-35.1, FR-24.7)
12. WHEN the Builder_Agent emits assistant text during a Turn, THE Session_Stream SHALL send `text` with `text`. (FR-35.1)
13. WHEN a Turn reaches 80 % of a limit, THE Session_Stream SHALL send `limit_warning` with `kind` (time, tool_calls, tokens), `used` and `limit`. (FR-35.1)
14. WHEN a Turn ends, THE Session_Stream SHALL send `turn_completed` with `status` (completed, failed, cancelled, timed_out, interrupted), `outcome` (draft, reply or unfinished), `message_id`, revision and token usage. (FR-35.1)
15. IF a failure occurs that the user should see, THEN THE Session_Stream SHALL send `error` with a code, a generic message and `retryable`. (FR-35.1)
16. THE Session_Stream SHALL describe tool calls and check results with labels and summaries only, and SHALL carry the manifest only in `draft_applied`. (FR-35.5)
17. THE Session_Stream SHALL keep file contents, raw tool arguments other than a script's command line, environment values and stack traces out of every event. (FR-35.5, NFR-01)

### Requirement 39: Session event stream: stages

**User Story:** As a user, I want a plain label for what the agent is doing, so that I can follow its progress without reading tool output.

#### Acceptance Criteria

1. THE Turn_Runner SHALL derive the Stage from the Builder_Agent's actions without asking the model to report the Stage. (FR-35.3)
2. WHEN a Turn is accepted, THE Turn_Runner SHALL set the Stage `starting` with label "Starting" before the first model output of that Turn. (FR-35.3)
3. WHILE no tool call is running, WHEN reasoning text arrives, THE Turn_Runner SHALL set the Stage `thinking` with label "Thinking". (FR-35.3)
4. WHEN the Builder_Agent calls `read_file` under `/skills/`, THE Turn_Runner SHALL set the Stage `reading` with label "Reading the workflow guide". (FR-35.3)
5. WHEN the Builder_Agent runs `catalog_lookup.py` through the Script_Runner or calls a read tool from Requirement 27 (user facts or Builder_Model_Catalog), THE Turn_Runner SHALL set the Stage `looking_up` with label "Looking up agents, models and examples". (FR-35.3, FR-23 SR-07, SR-09)
6. WHEN the Builder_Agent calls `write_file` or `edit_file` on a `*.workflow.json` file, THE Turn_Runner SHALL set the Stage `writing` with label "Writing the workflow". (FR-35.3)
7. WHEN the Script_Runner starts `validate_manifest.py` (including the validator subprocess of a `--compiler` call), `selftest.py`, `refresh_catalog.py --check` or `schema_sync.py --check`, THE Turn_Runner SHALL set the Stage `checking` with label "Checking the workflow". (FR-35.3, FR-33.4, FR-33.5)
8. WHEN the Builder_Agent calls `propose_draft`, or the Dry_Run of a `--compiler` call runs, THE Turn_Runner SHALL set the Stage `platform_check` with label "Checking with the platform". (FR-35.3)
9. WHEN the Server_Gate accepts a Draft submitted through `propose_draft`, THE Turn_Runner SHALL set the Stage `applying` with label "Updating the canvas". (FR-35.3, FR-33.5)
10. WHEN assistant text arrives after the last tool call, THE Turn_Runner SHALL set the Stage `responding` with label "Writing the reply". (FR-35.3)

### Requirement 40: Session event stream: connection and authentication

**User Story:** As a user, I want the progress stream to stay connected through long turns and to stop when my login is revoked, so that progress is reliable and secure.

#### Acceptance Criteria

1. WHILE the Session_Stream is open, during Turns and between Turns, THE Session_Stream SHALL send the existing keep-alive ping every `SSE_KEEPALIVE_PING_SECONDS` (15 s). (FR-35.4, R-22, §2.1 SSE settings)
2. THE Session_Stream SHALL send the `X-Accel-Buffering: no` response header. (§2.1 SSE settings)
3. WHILE no Turn is running in the Session, THE Session_Stream SHALL keep each connection open, so that every connected client receives `turn_started` on that connection when the next Turn starts. (FR-35.7)
4. WHEN a client connects, THE Session_Stream SHALL send `snapshot` first and then live events. (FR-35.7)
5. WHEN the Turn_Runner emits a live event for a Session, THE Session_Stream SHALL deliver that event to every client connected to that Session's stream, through an in-process fan-out as for runs. (FR-35.7, §8.16)
6. WHEN a client connects while a Turn is running, THE Session_Stream SHALL build `snapshot` from the running Turn's in-process state and the stored tool activity, including every tool call that finished before the connect. (FR-35.7, FR-25.2)
7. WHILE the Session_Stream is open, during Turns and between Turns, THE Session_Stream SHALL re-check the caller's token revocation on the same cadence as run streams: after every `SSE_REVOCATION_CHECK_EVERY_N_EVENTS` (5) events and at least every `SSE_REVOCATION_CHECK_INTERVAL_SECONDS` (30 s). (FR-35.8)
8. IF the revocation check fails, THEN THE Session_Stream SHALL send the existing `session_revoked` event and then close the connection. (FR-35.8)
9. THE Session_Stream_Hook SHALL read the Session_Stream with `fetch` and a `ReadableStream` reader and send the `Authorization: Bearer` header, because `EventSource` cannot send that header. (FR-35.9)
10. THE Session_Stream_Hook SHALL pass each Draft received in `draft_applied`, and whether a Turn is running in the Session, to the Composer as props, and THE Composer SHALL open no stream connection. (§8.9, §8.10, §2.1 Composer and SSE)

### Requirement 41: Builder model catalog

**User Story:** As a platform owner, I want one builder model catalog derived from the platform catalog, so that the chat models and the step models stay consistent and GPT stays excluded.

#### Acceptance Criteria

1. THE Builder_Model_Catalog SHALL have a Chat_List and a Step_List. (FR-36.1, Q-36)
2. THE Chat_List SHALL contain only Sonnet 5.5 (`eu.anthropic.claude-sonnet-5-5`), marked as the default chat model, and Opus 4.6 (`eu.anthropic.claude-opus-4-6-v1`), plus Haiku 5.5 only as criterion 3 allows. (FR-36.1.1, Q-56)
3. WHILE Haiku 5.5 (`eu.anthropic.claude-haiku-5-5`) has not passed the Spike's 3 reference requests, THE Chat_List SHALL exclude Haiku 5.5. (FR-36.1.1, Q-56)
4. THE Step_List SHALL contain exactly Haiku 5.5, Sonnet 5.5 and Opus 4.6, the 3 EU models that the Skill's `quick-reference.md` §6 recommends. (FR-36.1.2, Q-56)
5. THE Model_Catalog SHALL hold both lists as opt-in fields on `ModelEntry`, off by default, plus one marker for the default chat model. (FR-36.2, Q-56)
6. THE Builder_Model_Catalog SHALL take labels, levels, cost class, context window and limits from the existing `ModelEntry`. (FR-36.2, INV-12)
7. THE Model_Catalog SHALL keep the builder flags out of the fields that `refresh_catalog.py` copies and out of the responses of the model-listing endpoints in `capabilities.py` and `settings.py`. (FR-36.2, §2.1 `ModelEntry` readers)
8. IF the Model_Catalog has other than exactly one default chat model, or the default is not on the Chat_List, THEN THE Builder SHALL fail at startup. (FR-36.3)
9. WHILE spec 020's compliance sign-off is outstanding, THE Model_Catalog SHALL give no GPT model the Chat_List flag, the Step_List flag or the default chat model marker. (FR-36.4, Q-29)
10. THE Builder_Model_Catalog SHALL hold no effort data of its own. (FR-36.6)
11. IF a Draft sets a step's effort to a value outside that step model's levels in the Model_Catalog, THEN THE Server_Gate SHALL reject the Draft. (FR-36.6)
12. IF a Draft assigns a step model outside the Step_List, THEN THE Server_Gate SHALL reject the Draft with an error that names the allowed ids. (FR-36.7, R-18)
13. THE Builder SHALL give the user the Chat_List, and the Builder_Agent the Step_List, filtered to the models whose cost class the user's tier allows in `TIER_MODEL_COST_CLASSES`. (FR-36.8)
14. THE Builder_API SHALL return the Chat_List in the same shape as the existing capability model entries, so that `effortLevelsFor`, `effortLabel` and `modelChangePatch` work unchanged. (FR-36.9)

### Requirement 42: Security

**User Story:** As a security owner, I want model output and every input treated as untrusted and every privileged action confined, so that prompt injection cannot change data, leak secrets or alter the skill.

#### Acceptance Criteria

1. THE Builder SHALL send no `draft_applied` event for a Draft that the Server_Gate has not accepted. (NFR-01, FR-06.4, FR-24.2)
2. THE Builder SHALL build the System_Prompt from its versioned file only, and SHALL NOT insert user messages, tool results, library descriptions or `canvas_state` into the System_Prompt. (NFR-01, FR-20.3, R-05)
3. IF a Draft breaks the Builder_Rules, THEN THE Server_Gate SHALL reject the Draft whatever instructions the Turn's user messages, tool results, library descriptions or `canvas_state` contain. (R-05, FR-24.2, NFR-09)
4. THE Builder SHALL NOT write the text of the System_Prompt, Turn_Context, Transcript_Replay, user messages or assistant messages to logs, and SHALL refer to them in logs by Session id, Turn id or message id. (NFR-01, NFR-05)
5. IF a Builder_API request or a Turn fails, THEN THE Builder SHALL return an error code and a message that contains no stack trace, SQL error text or server file-system path, in the HTTP response or the Session_Stream `error` event. (FR-35.1 `error`, FR-35.5, backend coding guardrails §5)

### Requirement 43: Performance

**User Story:** As a user, I want the builder to respond quickly and the canvas to update immediately, so that the conversation feels live.

#### Acceptance Criteria

1. THE Builder SHALL deliver a Turn's first `thinking`, `tool_started` or `text` event to the Session_Stream_Hook of the sending tab within 3 s at p50, measured from Turn start after the Capacity_Gate check; `turn_started` and `stage` events do not count. (NFR-02, Q-30)
2. WHEN the Session_Stream_Hook of the sending tab receives a `draft_applied` event, THE Composer SHALL show the Draft within 300 ms of receipt. (NFR-02, FR-06.2, Q-30)
3. WHEN the Turn_Runner emits a `stage`, `tool_started`, `tool_finished`, `check_result` or `limit_warning` event, THE Session_Stream SHALL deliver the event to every connected Session_Stream_Hook of that Session within 1 s of the event's "Sent when" moment in FR-35.1. [proposed] (NFR-02, FR-16.7)
4. WHEN the Spike runs the Simple reference request, THE Spike SHALL report each Turn's duration against the 180 s target. (Q-38, §7.1, NFR-12)
5. WHILE the Spike has not replaced the 900 s Turn cap, THE Turn_Runner SHALL NOT stop a Turn or send `limit_warning` because the Turn passed 180 s. (Q-38, Q-54)

### Requirement 44: Cost, observability and success metrics

**User Story:** As a platform owner, I want usage, behaviour and outcomes recorded from day one, so that cost and quality can be tracked and the phase-2 analytics view has data.

#### Acceptance Criteria

1. WHEN a Turn ends, with any status, THE Session_Store SHALL store that Turn's token usage on its assistant message, including the usage of any Transcript_Summary written or updated for that Turn, and SHALL count that usage toward the Session. (NFR-03, FR-25.2, FR-26.4, Q-26)
2. WHILE a Turn runs, THE Builder SHALL write every log entry for that Turn as a structured entry that carries the Session id and the Turn id. (NFR-05, FR-21.2)
3. WHEN a Turn ends, THE Builder SHALL emit metrics for that Turn: latency, time in each Stage, tokens, the Adherence_Record, the status (completed, failed, cancelled, timed_out or interrupted) and the Skill_Hash of its message. (NFR-05, FR-22.5, FR-29.5)
4. WHEN a Script_Runner call ends, THE Builder SHALL emit a metric with the call's duration, its exit code and whether it was refused. (NFR-05, FR-33.11)
5. WHEN the Server_Gate rejects a Draft proposed through `propose_draft`, THE Builder SHALL emit a rejection metric; Dry_Runs are not rejections. (NFR-05, FR-24.4)
6. THE Builder SHALL record three success metrics: the share of Sessions from which at least one save was made; the share of Turns, among those that call `propose_draft` at least once, whose first call passes the Server_Gate; and the median number of Turns run before the first save, over Sessions with at least one save. Until a column records the Turn count at the first save, the report SHALL label the third metric an upper bound (the Session's Turn count when reported). [decided 2026-11-06] (NFR-06, Q-32, FR-09.5)
7. THE Builder SHALL report the storage that each user's Sandboxes and Session_Store data use. (R-04, Q-41)

### Requirement 45: Privacy, residency, language and rollout

**User Story:** As a compliance owner, I want residency limits, the language and the rollout conditions stated, so that the feature launches only within its approved bounds.

#### Acceptance Criteria

1. WHILE spec 020's compliance sign-off is not recorded, THE Builder_Model_Catalog SHALL exclude every GPT model from the Chat_List and from the Step_List. (NFR-07, Q-29, Q-36, R-06)
2. THE Builder SHALL present every UI text in English, and THE Turn_Context SHALL tell the Builder_Agent to reply in English. (NFR-11, Q-31, FR-03.6, FR-34.8)
3. THE Builder SHALL require the Custom_Entitlement as Requirement 2 specifies, and SHALL pass every message through the Capacity_Gate as Requirement 29 specifies. (NFR-08, Q-33, Q-25)
4. WHILE the Spike has not passed with Sonnet 5.5, the default Chat_List model, THE Builder SHALL NOT be launched. (NFR-08, NFR-12, Q-56)

### Requirement 46: Spike

**User Story:** As a platform owner, I want the built builder measured on reference requests before launch, so that limits, models and pre-loading are set from evidence.

#### Acceptance Criteria

1. THE Spike SHALL be run by an operator, because the Spike costs money. (NFR-12)
2. THE Spike SHALL run 3 reference requests (Simple, Standard, Complex) end to end through the built Builder: deepagents, the Script_Runner and the Server_Gate. (NFR-12, Q-38)
3. THE Spike SHALL record, for each reference request and each model run, the Turn duration, tokens, cost, tool calls, Server_Gate rejections and the Adherence_Record. The report script prints tokens per kind; the operator computes cost from them and the provider's prices, because the repository holds no price table. [decided 2026-11-06] (NFR-12)
4. WHEN the Spike completes, THE Spike SHALL record a decision for each of: the turn cap that replaces 900 s; whether Haiku 5.5 joins the Chat_List; the token budgets per Turn, per Session and per user per day; the Transcript_Replay budget; and whether to pre-load the mandatory Skill files. (NFR-12, Q-38, Q-54, Q-56, Q-45 b, §7.1)
5. THE Spike SHALL run each reference request on Sonnet 5.5, the default model, and on Haiku 5.5, plus any model Q-59 adds, using the requests and pass criteria settled by Q-60. (NFR-12, Q-38, Q-56)
6. IF the Spike results show that the mandatory Skill reads cost too much time, THEN THE Harness SHALL pre-load the mandatory Skill files. (Q-45 b, NFR-12)
7. THE Builder SHALL NOT apply Q-45 option (c) unless the Adherence_Record shows skipped mandatory reads. (Q-45)

### Requirement 47: Limits

**User Story:** As a platform owner, I want every limit stated with its status, so that the design implements them and the Spike can replace placeholders.

#### Acceptance Criteria

1. IF a message longer than 12,000 characters reaches the Builder_API, THEN THE Builder_API SHALL reject the message without starting a Turn. [placeholder: Q-24] (§7.1, FR-03.4)
2. IF a Session already has 100 Turns, THEN THE Builder_API SHALL refuse a new message for that Session. [placeholder: Q-24] (§7.1)
3. THE Turn_Runner SHALL allow 2 `propose_draft` rejections per Turn, not counting Dry_Runs. [placeholder: Q-24; meaning decided in Q-37] (§7.1, FR-24.4)
4. WHEN a Turn reaches 900 s, counted from Turn start after the Capacity_Gate check, THE Turn_Runner SHALL stop the Turn with status `timed_out`. 180 s stays an unenforced target for Simple Turns. [decided until the Spike: Q-54, Q-38] (§7.1, FR-29.4)
5. WHEN a Turn reaches 80 % of the turn cap (720 s while the cap is 900 s), THE Session_Stream SHALL send `limit_warning` with kind `time`. [decided until the Spike: Q-54] (§7.1, FR-35.1)
6. IF a user sends more than 5 messages within one minute, THEN THE Builder_API SHALL refuse the extra messages. [placeholder: Q-24] (§7.1)
7. THE Turn_Runner SHALL use 2 as the number of completed Turns without a Draft after which the next Turn produces a Draft from defaults (Requirement 16). [decided: Q-22] (§7.1, FR-15.3)
8. THE Harness SHALL run at most 60 tool calls per Turn. [placeholder: Q-51] (§7.1)
9. THE Harness SHALL enforce token budgets per Turn, per Session and per user per day, with values set after the Spike. [Q-51; values pending the Spike] (§7.1)
10. IF a user already has 2 running Turns, THEN THE Builder_API SHALL refuse a message that would start another Turn for that user. [placeholder: Q-51] (§7.1)
11. IF `canvas_state` is larger than 512 KB, THEN THE Builder_API SHALL reject the message without starting a Turn. [placeholder: Q-51] (§7.1, FR-22.7)
12. WHEN a Turn starts, THE Turn_Runner SHALL set the Transcript_Replay budget to 25 % of the context window of the model chosen for that message: 250,000 tokens on Sonnet 5.5 and Haiku 5.5, 50,000 on Opus 4.6. [proposed, set after the Spike] (§7.1, FR-26.3)
13. THE Turn_Runner SHALL replay the latest 4 Turns verbatim, whatever their size, even beyond the criterion 12 budget. [proposed] (§7.1, FR-26.5)
14. THE Script_Runner SHALL apply a 30 s timeout and an 80,000-character output cap per call. [placeholder: Q-51; measured calls took 0.46–1.1 s and printed at most 14,935 characters, S-17] (§7.1)
15. THE Script_Runner SHALL cap concurrent script processes at 8 per host. [proposed] (§7.1, FR-33.7)
16. THE Builder SHALL delete or expire no Session, message, tool activity, Draft_Revision, Transcript_Summary or Sandbox until the user deletes the Session or the account. The only exception is each script call's temp folder, removed when the call ends. [decided: Q-41] (§7.1, FR-25.5, FR-31.3)

### Requirement 48: Architecture constraints

**User Story:** As a platform architect, I want the builder to respect the platform's locked invariants, so that it adds a feature without eroding the runtime's design.

#### Acceptance Criteria

1. THE Builder SHALL run the Builder_Agent outside the ExecutionEngine, make no edit to the ExecutionEngine kernel, and add no `if pipeline_type == ...` branch. (§8.1, FR-20.4, SC-001, INV-1)
2. THE Builder_Agent SHALL use the real `deepagents` library, with no hand-rolled runtime. (§8.2, INV-13)
3. THE Builder SHALL use SSE for events down and REST for commands up, and add no WebSocket. (§8.3, FR-22.8, LOCK-B)
4. THE Builder SHALL derive the Builder_Model_Catalog and the model options of the Builder_Panel from the Model_Catalog, with no separate model list in backend or frontend code. (§8.4, FR-05.2, INV-12)
5. THE Server_Gate SHALL reuse the checks in `backend/app/api/user_workflows.py`, plus the Builder_Rules, and nothing else. (§8.5)
6. THE Server_Gate SHALL call `_compile_check_manifest` instead of adding a second place where `app.*` imports the engine. (§8.6, R-07)
7. THE Builder_Migration SHALL be additive, give every new table `owner_id` and `workspace_id`, and leave exactly one Alembic head. (§8.7)
8. IF the Builder changes DeepAgentRunner, for example to accept a composite backend or to build a graph with no checkpointer, THEN THE DeepAgentRunner SHALL keep existing agents' behaviour identical and the characterization goldens byte- and event-identical. (§8.8, INV-3)
9. THE Composer SHALL receive Drafts as props and subscribe to no stream. (§8.9)
10. THE Builder SHALL read the Session_Stream only through the Session_Stream_Hook and SHALL leave run streams to `RunConnectionProvider`. (§8.10)
11. THE Builder SHALL change no file of the Skill_Folder, and SHALL place every adaptation in the System_Prompt, the Turn_Context or the Builder_Agent's tools. (§8.11)
12. THE Builder_Agent SHALL have no `execute` tool and no general exec, and SHALL run Skill scripts only through the Script_Runner's allow-list. Note: any broader exec is an "Ask first" change under the project's architecture rules. (§8.12, FR-29.2)
13. THE Server_Gate SHALL decide whether a Draft reaches the Canvas, without reading the Catalog_Snapshot and regardless of the Skill_Validator's verdict. (§8.13, FR-24.3)
14. THE Builder SHALL delete or expire Builder data only when the user deletes a Session or the account, except each Script_Runner call's temp folder, which is removed when that call ends. (§8.14, Q-41, FR-31.3)
15. THE Script_Runner SHALL run scripts only outside the API process. (§8.15, S-03)
16. WHILE each environment runs one backend process, THE Turn_Runner SHALL store Turn status, tool activity, Draft_Revisions and Unproposed_Revisions in the Session_Store, so that each is readable after a restart. (§8.16, §2.1 Deployment)

### Requirement 49: Testing and verification

**User Story:** As a developer, I want the tests and checks the feature needs stated up front and placed by the workspace's test layout, so that the feature is verified the same way as the rest of the platform.

#### Acceptance Criteria

1. THE Test_Suite SHALL place backend tests in the `backend/tests/` layout (`unit/` mirroring the package path, `integration/`, `contract/`, `security/`, `property/`, `e2e/`), with exactly one suite marker applied by the folder hook and test function names of the form `test_<function>_<outcome>_when_<condition>`. (NFR-09, workspace test layout)
2. THE Test_Suite SHALL cover in unit tests, with zero real I/O: the Draft mapping; the Server_Gate rules, including the Q-53 list; the Builder_Model_Catalog flags and the startup check; the Script_Runner's command parsing, allow-list, path mapping and refusals; Stage derivation; the Change_Summary and Launch_Needs; the Transcript_Replay budget and summary rules; and a GPT-has-no-builder-flag test. (NFR-09, FR-36.4)
3. FOR ALL generated commands and paths, THE Script_Runner SHALL resolve no path outside the Sandbox or the deployed Skill folder and reach no refused script mode, verified by a hypothesis property test in `tests/property/`. (NFR-09)
4. THE Test_Suite SHALL cover in integration tests on real PostgreSQL, with the LLM faked and never SQLite: the Session endpoints, including the 202 and Session_Stream flow, 409 on a second Turn, cancel, a time-out with an Unproposed_Revision, and the startup sweep of Interrupted_Turns. These tests run on the Docker-capable CI runner, because the integration fixtures use testcontainers and Docker is not installed locally. (NFR-09)
5. THE Test_Suite SHALL cover in integration tests the Script_Runner running the real scripts against `tmp_path`: environment scrubbed, no `__pycache__` written into the Skill folder, the timeout and the output cap. (NFR-09, R-16, R-20)
6. THE Test_Suite SHALL cover in contract tests the OpenAPI snapshot and the Session_Stream event schema. (NFR-09, FR-35.6)
7. THE Test_Suite SHALL cover in security tests: IDOR returning 404, on the Session_Stream too; refused scripts, modes and path escapes returning a refusal with a reason; no FR-33.6 environment value reaching a script; writes under `/skills/` refused; `canvas_state` content reaching the Builder_Agent only as the Canvas_File; revocation closing the Session_Stream with `session_revoked`. (NFR-09, FR-21.4, FR-33.8, FR-34.1, FR-35.8)
8. FOR ALL allowed Patterns (`patterns.md` §1–18 and §21), rendering an unedited Draft and saving SHALL produce a Save payload equivalent to `export_manifest.py --save-payload` on that Draft (base `custom`, same `agent_ids`, manifest equal after canonical JSON serialisation), with one test per Pattern. (NFR-09, Q-34, FR-09.7, §2.1 Canvas round trip)
9. THE Test_Suite SHALL include a frontend Vitest test that applies a Draft setting a step's effort, checks that the config rail shows it, then changes that step's model and checks that the effort follows `modelChangePatch`. (R-12, FR-06.7, FR-05.4)
10. THE CI_Pipeline SHALL fail when `selftest.py` fails plain or with `--compiler`, when the per-pattern fixtures differ from a rebuild, or when a Step_List model is missing from the Catalog_Snapshot. The copy comparison and the catalog drift check were removed on 2026-11-10. (NFR-09, FR-32.8, FR-36.5, Req 33)
11. THE Test_Suite SHALL cover in the Playwright `mocked` project: create, see progress, render and save; and continue after a time-out. (NFR-09)
12. THE Test_Suite SHALL cover in frontend Vitest tests, using React Testing Library queries by role, label or text: the Builder_Panel, the progress view, other-tab behaviour and the apply-draft path. (NFR-09)
13. THE CI_Pipeline SHALL keep the characterization goldens unchanged, with `SNAPSHOT_UPDATE` unset and `git status --porcelain tests/agents/characterization/golden/` empty. (§8.8, INV-3)
14. WHEN a pull request is opened or updated, THE CI_Pipeline SHALL require `uv run pytest`, `uv run ruff check`, `uv run pyright` and `uv run lint-imports` (backend, from `backend/`) and `npm run test`, `npm run lint`, `npm run build` and `npm run e2e` (frontend, from `frontend/`) to pass, each single-pass with no watch mode and no dev server started by automation. (Workspace rules)

## Gaps Found During Detailing

These came up while making each criterion testable. Where the draft itself conflicts, the conflict is named. Every gap was decided on 2026-11-06; the answers are in "Decisions Recorded" below. A `[see G-NN]` tag in a criterion points to that answer.

| ID | Gap | Affects |
|---|---|---|
| G-01 | Retry versus idempotency: FR-12.1 says Retry resends the last user message without duplicating it, but FR-22.6 says a repeated `client_message_id` starts no Turn. Decide how Retry starts a new Turn without storing a second copy of the message. | Req 13, 21 |
| G-02 | `export_manifest.py` output paths: FR-33.4 allows outputs anywhere in the Sandbox, but SR-08 allows writes only under `/workflows/` and the call's temp folder. One of the two must change. | Req 27, 35 |
| G-03 | When other tabs apply a Draft: FR-06.2 applies a Draft on `draft_applied`, while FR-16.7 has other tabs load it at Turn end after an unsaved-work prompt. The requirements now scope the 300 ms render to the sending tab; please confirm. | Req 7, 17, 43 |
| G-04 | Hitting the tool-call cap, a token budget or the recursion limit: no Turn status is defined for these cases, and it is unclear whether the Unproposed_Revision rule applies. | Req 23, 28, 47 |
| G-05 | The order of the send-message checks (entitlement and flag, capacity, 409, model and effort 422, length, `canvas_state` size, duplicate id, rate limit) is not defined. Also undefined: which refusals store nothing and which count toward the rate limit. | Req 21, 26, 29, 47 |
| G-06 | Response for a rejected `model_id`: reuse the existing `_model_entitlement_error` split (422 for an unknown model, 403 for an unentitled one), or use one code. | Req 26 |
| G-07 | Response codes for a refused workflow link and for an edit Session requested on a workflow the user does not own, and whether the 404-not-403 rule applies to them. Also which response wins when the caller lacks the entitlement and the Session is unknown. | Req 2, 20 |
| G-08 | Change_Summary baseline: the previous accepted revision, the Canvas_File with manual edits, or nothing for a first Draft. | Req 7, 23 |
| G-09 | Whether an edit Session's seed (revision 0) or an undo counts as a "Draft" or an "applied Draft" for the clarifying-turn count and the Turn_Context. | Req 16, 37 |
| G-10 | Which Turn statuses count as "completed Turns without a Draft": only `completed`, or also `timed_out` and `interrupted`. | Req 16, 37 |
| G-11 | `propose_draft` called again after an accepted Draft in the same Turn, or naming a missing, non-JSON or out-of-Sandbox file: the response is undefined, and so is whether the call counts as a rejection. | Req 7, 23 |
| G-12 | The Turn status after the second Server_Gate rejection is undefined. It decides whether the Unproposed_Revision rule applies. | Req 23 |
| G-13 | Who sets Target_Trust `db` for a Draft, and how the Server_Gate learns it (for example, an argument to `propose_draft`). | Req 7, 20, 37 |
| G-14 | Snapshot versus live events: run streams send `replayed_through_seq`, but the builder `snapshot` has no sequence number, so a late client cannot drop duplicates. Also undefined: whether the hook reconnects automatically, and how often. | Req 38, 40 |
| G-15 | After `session_revoked`: whether the revoked caller's running Turn continues, and whether the hook routes the event to the `authedFetch` session-expiry handling. Also what a tab shows after `session_deleted`. | Req 13, 40 |
| G-16 | Undo while a Turn runs, the Undo control after an undo, and how other tabs learn of an undo, since no event exists for it. | Req 8, 38 |
| G-17 | Shutdown: whether script subprocesses are killed, whether a stopping Turn may still emit a Draft, and whether the startup sweep must finish before the API accepts messages or streams send snapshots. | Req 22 |
| G-18 | Script runner details. Undefined: commands with no launcher or an unlisted one; which arguments count as paths; operators inside quoted arguments; the options allowed for `selftest.py` and `export_manifest.py`; whether a 9th concurrent process waits or is refused; whether truncation keeps the start or the end, and whether the verdict is parsed before the cut; whether the environment is an allow-list or a blocklist; the `tool_finished` status when the validator exits 1; `check_result` when no verdict parses; and the `tool_finished` status for calls stopped by cancel, the turn cap or a restart. | Req 34, 35, 36, 38 |
| G-19 | The length of the truncated tool result that is stored is undefined. | Req 24, 36 |
| G-20 | Resolved 2026-11-10: the Skill_Hash is computed from the Skill_Folder's files on disk, with git-style blob hashes of LF content and no lock file (design decision 19). | Req 32 |
| G-21 | Resolved 2026-11-10: the skill path is fixed in code with no setting. A missing mandatory file disables only the builder, and a bad model catalog stops the process (design decision 20). | Req 32, 41 |
| G-22 | Transcript replay: how tokens are counted; whether the summary counts inside the 25 % budget; whether the current message counts among the latest 4 Turns; the presentation order; and whether summarised messages are replayed verbatim again after a switch to a model with a larger window. | Req 25, 47 |
| G-23 | Input limits: how characters are counted for the 12,000 limit (UTF-16 units or code points, the same on client and server); whether whitespace-only input is empty; whether 512 KB means 512,000 or 524,288 bytes; whether the rate limit uses a rolling or a calendar minute; and which Turn statuses count toward the 100-Turn limit. | Req 4, 21, 47 |
| G-24 | Session list: the sort key (created or last activity), the page size, and how many recent Sessions the popup shows. Also how "row changed since the latest Draft" is detected, and the title method and length. | Req 12, 31 |
| G-25 | Popup: whether clicking an example prompt fills the prompt box or sends it, whether the panel's input rules apply to the popup box, and the behaviour when Session creation fails. | Req 1 |
| G-26 | New conversation: whether the Session is created on the click or on the first message, what happens while a Turn runs, and whether the model choice carries over. | Req 11 |
| G-27 | Model picker: which effort is preselected (the model's `default_effort`?), the behaviour when the stored model is no longer offered or the model list fails to load, and what effort is sent while the Thinking select is hidden. | Req 6 |
| G-28 | Thinking: which Chat_List models support summarised display and where that is recorded, whether stored thinking is shown on reopen, and whether a tab that joins mid-Turn appends later `text` and `thinking` events. | Req 5, 17 |
| G-29 | Accessibility: throttling of Stage announcements (a Turn can make up to 60 tool calls), focus handling for the popup and the overlay, and what the Turn-end announcement says. | Req 14 |
| G-30 | Report display: how the panel recognises the Skill's report, who writes the short summary, and whether reply filtering backs up the System_Prompt rule against export and bearer-token instructions. | Req 15 |
| G-33 | Logging: whether thinking text, tool results, script output or `canvas_state` may be logged by value. | Req 42 |
| G-34 | Save: the pre-filled name for "Save as new" on a row whose base is not `custom` will probably collide (409). Also undefined: the URL and link after "Save as new" on a `custom` row, the definition of canonical JSON, and whether `agent_ids` order counts. | Req 3, 10 |
| G-35 | Cancel: the time bound for stopping, the response when no Turn is running, what happens to a `propose_draft` whose gate check is running at cancel, and which `outcome` `turn_completed` carries when a Draft was accepted before the cancel. | Req 30 |
| G-36 | SSE frame round-trip property test: it was proposed earlier but is not in the draft, so it was removed. Decide whether to add it back. | Req 49 |
| G-37 | Undecided Session data: how `owner_id` relates to `user_id`, what `workspace_id` holds for builder rows, and which statuses a user message may have. | Req 24 |
| G-38 | Fact correction for FR-20.3.4: the longest Skill doc is `docs/catalog.md` (757 lines), not `patterns.md` (481). The criterion now asks for a limit at least as large as the longest file's line count. | Req 19 |

## Decisions Recorded

Recorded on 2026-11-06. Each answer is what the code does today, as the design proposed it. Change a row here first if you want different behaviour, then change the code.

### Answers to the gaps

| ID | Decision | Criteria amended |
|---|---|---|
| G-01 | Retry is its own route, `POST /sessions/{id}/turns/{turn_id}/retry`. It accepts only the Session's latest Turn when that Turn ended `failed`, reuses the stored user message, and starts a new assistant message that replies to it. A repeated `client_message_id` never starts a Turn. The transcript shows the user message once and the earlier failed reply as "failed, retried". | none |
| G-02 | `export_manifest.py` writes only under `/exports/` in the Sandbox. Agent writes stay limited to `/workflows/`. | Req 35.9 |
| G-03 | The sending tab applies a Draft on `draft_applied`. Other tabs hold it until `turn_completed`, then apply it, asking first when they have unsaved edits. The 300 ms target is measured in the sending tab. | none |
| G-04 | The tool-call cap, a token budget and the recursion limit end the Turn `timed_out` with `stop_reason` `tool_calls`, `tokens` or `recursion`. The Unproposed_Revision rule applies. | none |
| G-05 | Send-message check order: authentication 401, Custom_Entitlement 403, readiness 503, body 422, Session lookup 404, duplicate `client_message_id` 202 replay, running Turn 409, model 422 or 403, effort 422, `canvas_state` 422 or 413, Turn limit 409, rate limit 429, running Turns per user 429, Capacity_Gate 503. Then the store and the Turn start. A refused request stores and publishes nothing, and does not count toward any limit. | none |
| G-06 | An unknown or GPT `model_id` gives 422 `model_not_allowed`. An unentitled one gives 403 `model_not_entitled`. | none |
| G-07 | A link or edit Session for a workflow the user does not own, or that does not exist, gives 404 `workflow_not_found`. The entitlement check (403) runs before any lookup, so it wins over an unknown Session or workflow. | none |
| G-08 | The Change_Summary baseline is the `canvas_state` sent with the Turn's message. For a first Draft it is an empty canvas. | none |
| G-09 | Only an accepted Draft ends the clarifying-turn count. An edit Session's seed and an undo do not. | none |
| G-10 | Only Turns that ended `completed` with outcome `reply` count. | none |
| G-11 | These calls return their reason and do not count as rejections: a second `propose_draft` after an accepted Draft in the same Turn, a path outside `/workflows/*.workflow.json`, a missing file, invalid JSON, a non-object, or a file over 1,000,000 bytes. | none |
| G-12 | After the second rejection, the Turn ends `completed` with outcome `unfinished`. The reply names the failed checks, and the last manifest is stored as an Unproposed_Revision. | Req 23.12, 23.18 |
| G-13 | The Builder_Agent asks for `db` by calling `propose_draft(path, target_trust="db", trust_reason=...)`. The Server_Gate accepts at `user` whenever the Draft compiles at `user`. It accepts at `db` only when all four hold: the Draft fails at `user`, compiles at `db`, `db` was requested, and the tier's saved-row trust is `db`. When `user` was requested and `db` would compile, the rejection says so. `trust_reason` is not stored; logs record only whether it was given. | none |
| G-14 | The snapshot is built in the same step as the subscription and carries `through_seq`. The client drops Turn events whose `seq` is at or below the last one it applied. No `Last-Event-ID` is used. Reconnects back off from 1 s, doubling up to 30 s, with no give-up while the panel is mounted. The hook stops on 404, `session_deleted` and `session_revoked`. | none |
| G-15 | On `session_revoked`, the hook calls `expireSession()`, and the revoked caller's running Turn continues and is stored. On `session_deleted`, the panel shows "This conversation was deleted in another tab" with "New conversation", and the canvas stays as unsaved work. | none |
| G-16 | Undo is refused with 409 `turn_running` while a Turn runs, and with 409 `undo_stale` unless the latest revision is the accepted Draft named by `expected_revision`. An undo is stored as a revision of kind `undo`, and `draft_restored` tells other tabs. Once the top revision is not `accepted`, no Undo is offered. | none |
| G-17 | Shutdown runs these steps in order: mark the builder not ready, stop every builder Turn, wait up to 2 s for the `interrupted` rows, then close the Session_Streams. Cancelling a Turn kills its script subprocesses, and a stopping Turn cannot emit a Draft. The startup sweep runs in the app lifespan before any request is served. If the sweep fails, the builder is unavailable for that process. | none |
| G-18 | Script_Runner rules:<br>- A command with no launcher is accepted. Any other unlisted first token is refused.<br>- Path arguments are decided by the policy's slots, not by guessing.<br>- Operators inside quotes are literal text.<br>- `selftest.py` takes no options. `export_manifest.py` takes exactly one output option.<br>- A 9th concurrent call waits for a slot.<br>- Output keeps the first 60,000 and the last 15,000 characters. The verdict is parsed from the uncut tail.<br>- The environment is an allow-list.<br>- A validator exit of 0 or 1 is `ok`.<br>- No parsed verdict gives `unknown`. An `unknown` dry run makes the call exit 1.<br>- A call stopped by a turn cap is `timed_out`. A call stopped by cancel or shutdown is `error`. | none |
| G-19 | A stored tool result keeps the first 3,000 and the last 1,000 characters (4,000 at most). A `tool_finished` summary keeps 280. | none |
| G-20 | Skill_Hash = `sha256:` of the sorted `path\0blob\n` lines. Each blob is the git blob SHA-1 of the file's content with CRLF turned into LF. Resolved 2026-11-10: the values are computed from the Skill_Folder's files on disk, and no lock file is kept. | none |
| G-21 | Resolved 2026-11-10: the path is fixed in code, with no setting. A missing or mismatched skill package makes only the builder unavailable (503 `builder_unavailable`); the rest of the app keeps serving. A bad builder model catalog stops the process. With the Feature_Flag off, neither startup check runs. | none |
| G-22 | Tokens are counted with `count_tokens_approximately`. The summary counts inside the budget. The current message is not one of the 4 kept Turns. Messages are in chronological order. Selection reruns every Turn, so a model with a larger window can bring summarised messages back verbatim. | none |
| G-23 | Characters are counted as code points on client and server. Whitespace-only means empty, using Python's whitespace set. 512 KB means 524,288 bytes of compact UTF-8 JSON. The rate limit is a rolling 60 s window over stored user messages. The 100-Turn limit counts the Session's Turns; a retry of a failed Turn does not add one. | Req 4.5 |
| G-24 | Sessions sort by last activity, 20 per page (50 at most). The popup shows 5 (amended 2026-11-10: the panel's Empty_State shows 5). The title is the first non-blank line, with whitespace collapsed and cut at 60 characters plus an ellipsis, made without a model call. "Row changed" compares the canonical hash of the saved row with the hash stored at the latest Draft or save. | none |
| G-25 | Clicking an example prompt fills the box without sending. The popup box follows the panel's input rules. If Session creation fails, the popup stays open with an inline error and keeps the text. Amended 2026-11-10: the popup is gone; the same rules apply to the Empty_State's examples and the panel's box, and a failed creation puts the text back in the box with an inline error (Req 1.6, 1.7). | none |
| G-26 | The Session is created on the first message, not on the click. "New conversation" is disabled while a Turn runs. The model and effort carry over. | none |
| G-27 | `GET /models` returns `default_efforts`. Preselection goes: the stored choice, then the Settings preference, then the default model, then the first offered model. The default effort is used when the server's default is one of the model's levels, otherwise the first level. A model with no levels sends `effort: null`. If the stored model is gone, the panel uses the default and shows one note. If the list fails to load, the panel shows Retry and disables Send. | none |
| G-28 | Summarised thinking display comes from `Reasoning.display` (Sonnet 5.5 and Haiku 5.5). Stored thinking shows collapsed on reopen. A tab that joins mid-Turn shows progress only, without `text` or `thinking` deltas, and loads the stored final message at the end. | none |
| G-29 | Stage announcements: at most one every 3 s, and the latest stage wins. The draft line and the Turn-end lines ("Reply finished", "Turn stopped", "Turn failed") are not throttled. The overlay panel traps focus and returns it to the AI button on close. | none |
| G-30 | A reply is the Skill's report when its first line starts with "Context loaded this turn". The summary is the text up to the first `## ` heading. Replies are not filtered; the System_Prompt carries the rule against export and bearer-token instructions. | none |
| G-33 | The text of the System_Prompt, Turn_Context, replay, user messages, assistant messages and thinking is never logged; the builder's runner logs no model output. Tool arguments, tool results, `canvas_state` and exception text may appear in logs and tracebacks. | none |
| G-34 | "Save as new" pre-fills "<name> (AI)" and adds " 2", " 3" and so on after a 409. After any "Save as new", the Session links to the new row and the URL moves to its edit route. Canonical JSON: drop nulls, drop the Composer defaults (`tools.exec: false`, `tools.read_files: true`, `tools.write_files: true`, `gates: []`, sequential `depends_on`, `name` equal to `instance_id`, `strategy: "single_shot"` on a leaf step, `tools.spawn_subagents: false` on a parent step), then sort keys, use compact separators and UTF-8. The hash is plain 64-character SHA-256 hex. The form is defined for JSON without non-integral floats or lone surrogates. `agent_ids` order counts, and builder saves send `custom-agent:<instance_id>` ids. | none |
| G-35 | A cancel takes effect at the next await point. A cancel with no running Turn returns 200 `not_running`. A gate check that is still running when the cancel arrives is discarded. A Draft accepted before the cancel stays: `turn_completed` carries `cancelled` with outcome `draft`. | none |
| G-36 | Not needed: the event round-trip property test (8.4) covers the wire format. | none |
| G-37 | `owner_id` and `workspace_id` are stamped with the user id. Queries filter on `user_id`. User messages have status `accepted`. | none |
| G-38 | The System_Prompt uses `limit=1000`. A unit test fails if any Markdown file in the Skill grows past that. | none |

### Other recorded choices

- The Builder_Rules also check the workflow-level `model` and each `subagents.agent`, so a Draft cannot get past the Step_List or the agent allow-list that way.
- In Script_Runner paths, `..` is collapsed as text before the path is resolved, and the result must still be inside the Sandbox. `//workflows/x` is read as `/workflows/x`.
- Script output of 75,001 to about 79,900 characters is cut although it would fit the 80,000 cap. The result stays valid.
- `validate_manifest.py --compiler` runs the dry run also after an `INVALID` validator, so the agent gets both reports in one call.
- Token budgets count input plus output tokens only. The Transcript_Summary call's tokens are stored but not counted against the per-Turn budget.
- The Composer header (name, description, view toggle, Back) stays editable during a Turn. Req 9.3 covers the canvas, the rails and the library.
- When the builder is unavailable, the Composer host renders two boxless `display: contents` wrappers around the Composer. Nothing visible changes.
- Turn and script metrics are structured `builder_metric` log lines. An OpenTelemetry exporter is a separate decision for the whole backend.
- The success metrics and the storage report are logged at startup. No admin view in phase 1.
- Known limitation: deleting an account stops the user's Turns but does not wait for them. A Turn that is mid-write can leave a stray tool row or file.
