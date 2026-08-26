# Feature: The API contract

**Screenshots:** none — this is the layer beneath the UI.
**Snapshot:** `capture/API-CONTRACT.json` — all 108 endpoints with method, path, auth
requirement, status code and response model, extracted from source.

```
python3 tests/integration/capture/_api.py            # inventory + coverage
python3 tests/integration/capture/_api.py --json     # regenerate the snapshot
python3 tests/integration/capture/_api.py --missing  # endpoints no spec names
```

---

## Why this exists

Every other file here asserts what a *user sees*. That catches a broken screen, but
not a contract change underneath it — a route renamed, an auth requirement dropped, a
201 becoming a 200. The UI can keep working while the contract shifts under it, and
the reverse: a UI test fails and nobody can tell whether the screen or the endpoint
moved.

**`API-CONTRACT.json` is the regression detector.** Regenerate it and diff. A changed
line is a changed contract — intended or not, it is now visible in review rather than
discovered in production.

## The surface

**108 endpoints.** By auth requirement:

| | Count |
|---|---:|
| Requires a signed-in user | **84** |
| Requires an admin | **6** |
| Public | **18** |

By area:

| Area | Endpoints | Auth |
|---|---:|---|
| `runs` | 23 | all user |
| `auth` | 14 | 6 public, 8 user |
| `settings` | 11 | all user |
| `prototype` | 10 | 4 public, 6 user |
| `agents` | 9 | all user |
| `admin` | 6 | all admin |
| `user-workflows` | 6 | all user |
| `chats`, `user-agents` | 5 each | all user |
| `ppt` | 4 | 2 public, 2 user |
| `handoff`, `install` | 3 each | mixed / all public |
| `mcp`, `workflows` | 2 each | public / user |
| `analytics`, `capabilities`, `files`, `hooks`, `skills` | 1 each | all user |

Declared status codes: 7 × `201_CREATED`, 8 × `204_NO_CONTENT`, 7 × `200_OK`,
1 × `202_ACCEPTED`, 1 × `403_FORBIDDEN` (`/api/auth/register`, permanently).

## The 18 public endpoints, and why each is public

This is the list that matters most — anything wrongly on it is an authorization hole.

| Endpoint | Why public |
|---|---|
| `POST /api/auth/login` | you have no token yet |
| `POST /api/auth/login/challenge` | mid-authentication |
| `POST /api/auth/logout` | must work with an already-invalid token |
| `POST /api/auth/register` | **answers 403 by design** — self-registration is closed |
| `POST /api/auth/forgot-password` | pre-authentication; refuses when email is a second factor |
| `POST /api/auth/forgot-password/confirm` | pre-authentication |
| `GET /api/ppt/templates/{id}/preview` · `/thumbnail` | loaded by a sandboxed iframe |
| `GET /api/prototype/templates/{id}/preview` · `/thumbnail` · `/assets/{path}` | same |
| `GET /api/prototype/design-systems/{id}/preview` | same |
| `GET /install/flowin-handoff` · `/command` · `/script` | fetched by `curl … \| bash` before any session exists |
| `GET`/`POST /mcp/handoff` | MCP client transport |
| `POST /api/handoff/receive` | **authenticated by `X-Flowin-API-Key`, not a bearer token** |

Two deserve attention:

**`POST /api/handoff/receive` is not really public.** It carries
`Depends(get_user_via_api_key)` — a long-lived `X-Flowin-API-Key` header, minted on
`/handoff/settings`. It is "public" only in the sense that it takes no JWT. It
deliberately does **not** require a GitHub PAT at this point; `/start` enforces that,
so the user can be prompted after clicking the URL.

**`GET /api/prototype/templates/{id}/assets/{asset_path:path}`** is a wildcard path
parameter on an unauthenticated route — the classic path-traversal shape. The source
states `od_loader.get_template_asset_path` rejects traversal and confines reads to
the template's `assets/` dir. **That claim needs a test, not a comment.**

It is unauthenticated on purpose: the sandboxed iframe must load assets without
propagating the JWT into static requests.

## Every endpoint

The full surface, so a new route shows up as an addition to this table rather than
arriving unlisted. **A** = auth: `P`ublic, `U`ser, `A`dmin.

### `admin` — 6

| A | Method | Path | Returns |
|---|---|---|---|
| A | `GET` | `/api/admin/users` | list[AdminUserResponse] |
| A | `POST` | `/api/admin/users` | AdminUserResponse |
| A | `DELETE` | `/api/admin/users/{user_id}` | 204 No Content |
| A | `POST` | `/api/admin/users/{user_id}/reset-password` | 200 Ok |
| A | `PATCH` | `/api/admin/users/{user_id}/role` | AdminUserResponse |
| A | `PATCH` | `/api/admin/users/{user_id}/tier` | AdminUserResponse |

### `agents` — 9

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/agents/library` | — |
| U | `GET` | `/api/agents/pipelines/{pipeline_type}` | PipelineResponse |
| U | `GET` | `/api/agents/skills` | — |
| U | `POST` | `/api/agents/skills` | — |
| U | `DELETE` | `/api/agents/skills/{agent_id}` | — |
| U | `GET` | `/api/agents/skills/{agent_id}` | SkillResponse |
| U | `DELETE` | `/api/agents/{agent_id}/prompt` | — |
| U | `GET` | `/api/agents/{agent_id}/prompt` | AgentPromptResponse |
| U | `PUT` | `/api/agents/{agent_id}/prompt` | — |

### `analytics` — 1

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/analytics/summary` | AnalyticsSummary |

### `auth` — 14

| A | Method | Path | Returns |
|---|---|---|---|
| U | `POST` | `/api/auth/change-password` | 200 Ok |
| P | `POST` | `/api/auth/forgot-password` | 202 Accepted |
| P | `POST` | `/api/auth/forgot-password/confirm` | 200 Ok |
| P | `POST` | `/api/auth/login` | AuthResponse | AuthChallengeResponse |
| P | `POST` | `/api/auth/login/challenge` | AuthResponse | AuthChallengeResponse |
| P | `POST` | `/api/auth/logout` | 204 No Content |
| U | `GET` | `/api/auth/me` | UserResponse |
| U | `GET` | `/api/auth/mfa` | MfaStatusResponse |
| U | `POST` | `/api/auth/mfa/email/disable` | 200 Ok |
| U | `POST` | `/api/auth/mfa/email/enable` | 200 Ok |
| U | `POST` | `/api/auth/mfa/totp/associate` | 200 Ok |
| U | `POST` | `/api/auth/mfa/totp/verify` | 200 Ok |
| U | `POST` | `/api/auth/refresh` | RefreshResponse |
| P | `POST` | `/api/auth/register` | 403 Forbidden |

### `capabilities` — 1

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/capabilities` | CapabilitiesPalette |

### `chats` — 5

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/chats` | list[ChatSessionResponse] |
| U | `POST` | `/api/chats` | ChatSessionResponse |
| U | `DELETE` | `/api/chats/{chat_id}` | 204 No Content |
| U | `GET` | `/api/chats/{chat_id}` | ChatSessionDetailResponse |
| U | `PUT` | `/api/chats/{chat_id}/messages` | MessageResponse |

### `files` — 1

| A | Method | Path | Returns |
|---|---|---|---|
| U | `POST` | `/api/files/extract-text` | ExtractResponse |

### `handoff` — 3

| A | Method | Path | Returns |
|---|---|---|---|
| P | `POST` | `/api/handoff/receive` | HandoffReceiveResponse |
| U | `GET` | `/api/handoff/{token}` | HandoffSessionView |
| U | `POST` | `/api/handoff/{token}/start` | HandoffStartResponse |

### `hooks` — 1

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/hooks/library` | — |

### `install` — 3

| A | Method | Path | Returns |
|---|---|---|---|
| P | `GET` | `/install/flowin-handoff` | — |
| P | `GET` | `/install/flowin-handoff/command` | — |
| P | `GET` | `/install/flowin-handoff/script` | — |

### `mcp` — 2

| A | Method | Path | Returns |
|---|---|---|---|
| P | `GET` | `/mcp/handoff` | — |
| P | `POST` | `/mcp/handoff` | — |

### `ppt` — 4

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/ppt/templates` | list[PPTTemplateListItem] |
| U | `GET` | `/api/ppt/templates/{template_id}` | PPTTemplateDetail |
| P | `GET` | `/api/ppt/templates/{template_id}/preview` | — |
| P | `GET` | `/api/ppt/templates/{template_id}/thumbnail` | — |

### `prototype` — 10

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/prototype/design-systems` | list[DesignSystemListItem] |
| U | `GET` | `/api/prototype/design-systems/{ds_id}` | DesignSystemDetail |
| P | `GET` | `/api/prototype/design-systems/{ds_id}/preview` | — |
| U | `GET` | `/api/prototype/fetch-url` | — |
| U | `POST` | `/api/prototype/run` | — |
| U | `GET` | `/api/prototype/templates` | list[TemplateListItem] |
| U | `GET` | `/api/prototype/templates/{template_id}` | TemplateDetail |
| P | `GET` | `/api/prototype/templates/{template_id}/assets/{asset_path:path}` | — |
| P | `GET` | `/api/prototype/templates/{template_id}/preview` | — |
| P | `GET` | `/api/prototype/templates/{template_id}/thumbnail` | — |

### `runs` — 23

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/runs` | list[WorkflowRunListResponse] |
| U | `POST` | `/api/runs` | — |
| U | `POST` | `/api/runs/export-pptx` | — |
| U | `POST` | `/api/runs/user_message` | — |
| U | `POST` | `/api/runs/{run_id}/answers` | — |
| U | `POST` | `/api/runs/{run_id}/cancel` | — |
| U | `POST` | `/api/runs/{run_id}/files` | — |
| U | `POST` | `/api/runs/{run_id}/gate` | — |
| U | `POST` | `/api/runs/{run_id}/messages` | — |
| U | `POST` | `/api/runs/{run_id}/resume` | — |
| U | `POST` | `/api/runs/{run_id}/revisions` | — |
| U | `DELETE` | `/api/runs/{workflow_id}` | 204 No Content |
| U | `GET` | `/api/runs/{workflow_id}` | WorkflowRunResponse |
| U | `GET` | `/api/runs/{workflow_id}/artifacts` | — |
| U | `GET` | `/api/runs/{workflow_id}/chain-context` | ChainContextResponse |
| U | `GET` | `/api/runs/{workflow_id}/events` | — |
| U | `GET` | `/api/runs/{workflow_id}/events/stream` | — |
| U | `GET` | `/api/runs/{workflow_id}/exec-runs` | — |
| U | `GET` | `/api/runs/{workflow_id}/family` | RunFamilyResponse |
| U | `GET` | `/api/runs/{workflow_id}/gate-events` | — |
| U | `GET` | `/api/runs/{workflow_id}/hook-runs` | — |
| U | `GET` | `/api/runs/{workflow_id}/summary` | RunSummaryResponse |
| U | `GET` | `/api/runs/{workflow_id}/validation-results` | — |

### `settings` — 11

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/settings/api-keys` | list[ApiKeySummary] |
| U | `POST` | `/api/settings/api-keys` | ApiKeyCreateResponse |
| U | `DELETE` | `/api/settings/api-keys/{key_id}` | 204 No Content |
| U | `DELETE` | `/api/settings/constitution` | — |
| U | `GET` | `/api/settings/constitution` | ConstitutionResponse |
| U | `PUT` | `/api/settings/constitution` | ConstitutionResponse |
| U | `DELETE` | `/api/settings/github-pat` | 204 No Content |
| U | `GET` | `/api/settings/github-pat` | GithubPATResponse | None |
| U | `PUT` | `/api/settings/github-pat` | GithubPATResponse |
| U | `GET` | `/api/settings/preferences` | UserPreferencesResponse |
| U | `PUT` | `/api/settings/preferences` | UserPreferencesResponse |

### `skills` — 1

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/skills/library` | — |

### `user-agents` — 5

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/user-agents` | list[UserAgentResponse] |
| U | `POST` | `/api/user-agents` | UserAgentResponse |
| U | `DELETE` | `/api/user-agents/{agent_id}` | 204 No Content |
| U | `GET` | `/api/user-agents/{agent_id}` | UserAgentResponse |
| U | `PATCH` | `/api/user-agents/{agent_id}` | UserAgentResponse |

### `user-workflows` — 6

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/user-workflows` | list[UserWorkflowResponse] |
| U | `POST` | `/api/user-workflows` | UserWorkflowResponse |
| U | `DELETE` | `/api/user-workflows/{workflow_id}` | 204 No Content |
| U | `GET` | `/api/user-workflows/{workflow_id}` | UserWorkflowResponse |
| U | `PATCH` | `/api/user-workflows/{workflow_id}` | UserWorkflowResponse |
| U | `GET` | `/api/user-workflows/{workflow_id}/workflow.yaml` | — |

### `workflows` — 2

| A | Method | Path | Returns |
|---|---|---|---|
| U | `GET` | `/api/workflows` | list[WorkflowSummary] |
| U | `GET` | `/api/workflows/{workflow_id}` | WorkflowDetail |
---

```gherkin
Feature: The API contract holds

  @sourced
  Scenario: The endpoint inventory matches the snapshot
    When I regenerate capture/API-CONTRACT.json from source
    Then it is identical to the committed snapshot
    # THE regression test of this file. Any diff is a contract change: a renamed
    # route, a dropped auth dependency, a changed status code. Intended changes
    # update the snapshot in the same commit, so the diff is reviewed rather
    # than discovered later.

  @sourced
  Scenario: No endpoint loses its authentication silently
    Given the committed snapshot records 84 user and 6 admin endpoints
    When I regenerate it
    Then no endpoint has moved from "user" or "admin" to "public"
    # The single highest-value assertion here. A dropped Depends(get_current_user)
    # is a one-line diff that no UI test can see.

  @sourced
  Scenario: The public list is exactly eighteen, and each is deliberate
    Then exactly 18 endpoints require no authentication
    And each appears in the table above with a stated reason
    # A NEW public endpoint should fail this and force the reason to be written
    # down before it ships.


Feature: Authentication endpoints

  Scenario: A request with no credentials is answered 401, not 403
    When I call an authenticated endpoint with no Authorization header
    Then the response status is 401
    # FIX-311, already in 13-errors. Restated here because this is the contract
    # file: FastAPI's stock HTTPBearer raises 403 on a missing header while every
    # other auth failure answers 401, so the one case meaning "you never signed
    # in" looked like "you are signed in but not allowed". bearer_scheme is
    # subclassed to fix it.

  @sourced
  Scenario: Registration is permanently closed
    When I POST /api/auth/register
    Then the response status is 403
    # Declared as status_code=HTTP_403_FORBIDDEN on the route itself — not a
    # runtime check. It cannot succeed by configuration.

  @sourced
  Scenario: Login returns either a session or a challenge
    When I POST valid credentials to /api/auth/login
    Then the response is an AuthResponse or an AuthChallengeResponse
    # A union, which is what makes the five-challenge flow in 01-auth possible.
    # A client that assumes AuthResponse breaks on any MFA-enabled account.

  @sourced
  Scenario: A challenge is answered on its own endpoint
    Given a login that returned a challenge
    When I POST the answer to /api/auth/login/challenge
    Then the response is again an AuthResponse or an AuthChallengeResponse
    # Also a union: one challenge can lead to another (SELECT_MFA_TYPE → EMAIL_OTP).

  @sourced
  Scenario: Logout works with an already-invalid token
    Given an expired or revoked token
    When I POST /api/auth/logout
    Then it answers 204 and does not error
    # Public by necessity. A logout that requires a valid session cannot clear a
    # broken one, which is exactly when a user reaches for it.

  @sourced
  Scenario: Password recovery refuses when email is a second factor
    Given the pool uses email MFA
    When I POST /api/auth/forgot-password
    Then it does not send a recovery email
    # 202 ACCEPTED is declared, so the response shape does not reveal whether the
    # address exists. The refusal is correct: AWS disqualifies email as a
    # recovery channel when it is also a second factor. See 09-settings and
    # 11-admin for the path that does work.

  @sourced
  Scenario Outline: Second-factor management requires a session
    Then "<endpoint>" requires an authenticated user

    Examples:
      | endpoint                          |
      | GET  /api/auth/mfa                |
      | POST /api/auth/mfa/email/enable   |
      | POST /api/auth/mfa/email/disable  |
      | POST /api/auth/mfa/totp/associate |
      | POST /api/auth/mfa/totp/verify    |
    # Recorded because an earlier version of _api.py reported ALL FIVE as public.
    # It matched dependency names exactly and missed
    # get_current_user_with_payload. A mislabelled auth requirement in a contract
    # spec is worse than no spec — hence this outline, and the fix in the tool.


Feature: Admin endpoints

  @sourced
  Scenario Outline: Every admin endpoint requires an admin
    Then "<endpoint>" is refused for a non-admin user

    Examples:
      | endpoint                                        |
      | GET    /api/admin/users                         |
      | POST   /api/admin/users                         |
      | DELETE /api/admin/users/{user_id}               |
      | POST   /api/admin/users/{user_id}/reset-password|
      | PATCH  /api/admin/users/{user_id}/role          |
      | PATCH  /api/admin/users/{user_id}/tier          |
    # Six endpoints that create users, delete users, grant admin and reset
    # passwords. 17-theme-and-tiers proves the UI redirects a non-admin away
    # from /admin; that is presentation. This is the control.

  @sourced
  Scenario: Creating a user answers 201 with the created user
    When an admin POSTs to /api/admin/users
    Then the status is 201
    And the body is an AdminUserResponse

  @sourced
  Scenario: Deleting a user answers 204 with no body
    When an admin DELETEs /api/admin/users/{id}
    Then the status is 204
    And the body is empty

  @sourced
  Scenario: Role and tier changes return the updated user
    When an admin PATCHes a user's role or tier
    Then the body is an AdminUserResponse reflecting the change
    # The UI shows a toast (19-toasts-and-dialogs); this is what the toast is
    # reporting.


Feature: Public asset routes

  @sourced
  Scenario: Template previews load without a token
    When I GET a template preview or thumbnail with no Authorization header
    Then it succeeds
    # Deliberate: a sandboxed iframe must load these without propagating the JWT
    # into static requests. Asserting it stops someone "securing" these routes
    # and silently breaking every template gallery.

  @sourced
  @destructive
  Scenario: The asset route refuses path traversal
    When I GET /api/prototype/templates/{id}/assets/../../../etc/passwd
    Then it does not return a file outside the template's assets directory
    And it answers 404
    # A wildcard {asset_path:path} on an UNAUTHENTICATED route is the classic
    # traversal shape. The source says od_loader.get_template_asset_path rejects
    # traversal and confines reads to assets/. That is a comment; this is the
    # test. Cover encoded forms (%2e%2e%2f) and absolute paths too.

  @sourced
  Scenario: A missing asset is a 404, not a 500
    When I GET a nonexistent asset for a real template
    Then the status is 404
    And the message names the asset and the template


Feature: Handoff ingress

  @sourced
  Scenario: Handoff creation is authenticated by API key, not by JWT
    When I POST /api/handoff/receive with a valid X-Flowin-API-Key
    Then a handoff session is created and its URL returned
    # get_user_via_api_key, not get_current_user. "Public" in the inventory means
    # "no bearer token", not "no authentication".

  @sourced
  Scenario: Handoff creation without a valid key is refused
    When I POST /api/handoff/receive with a missing or wrong API key
    Then no session is created
    # This endpoint mints a URL that grants access to a run. It is reachable from
    # the public internet and its only guard is that header.

  @sourced
  Scenario: A GitHub PAT is not required to create a handoff
    Given I have no GitHub PAT saved
    When I POST /api/handoff/receive
    Then it succeeds
    # Deliberate, and stated in the source: /start enforces the PAT instead, so
    # the user can be prompted after clicking the URL. That prompt is the
    # onboarding state specified in 22-handoff-and-gates.


Feature: Ownership

  Scenario: A run is readable only by its owner
    Given a run owned by another user
    When I GET it with my own token
    Then the response is 403 or 404
    And its contents are not returned
    # 23 run endpoints, all user-authenticated. Authentication is not
    # authorization — every one needs an ownership check, and FIX-309 records a
    # case where the check ran AFTER a file read.

  Scenario: A run's files cannot be fetched across an ownership boundary
    Given a run owned by another user
    When I request one of its files with my own token
    Then the response is 403 or 404
    And the file's contents are not returned
```

## Notes for phase 2

- **The snapshot diff is the point.** Wire `_api.py --json` into CI and fail on an
  uncommitted diff. Everything else in this file is a scenario someone must write;
  that one is free and catches the largest class of change.
- **Test the traversal scenario for real.** An unauthenticated wildcard path
  parameter is the one item here that could be a live vulnerability rather than a
  regression risk, and today its only guard is a comment saying it is guarded.
- Ownership is the gap between authentication and authorization. 84 endpoints require
  *a* user; the contract does not say they check *which* user. The two ownership
  scenarios above are the minimum, and FIX-309 is why.
- This file is `@sourced` throughout — extracted from route decorators and
  signatures, not exercised. Verify against a running backend and drop the tags.
