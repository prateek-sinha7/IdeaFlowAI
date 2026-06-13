---
phase: 19-prompt-and-deliverable-adherence
fixed_at: 2026-06-13T17:17:08Z
review_path: .planning/phases/19-prompt-and-deliverable-adherence/19-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 19: Code Review Fix Report

**Fixed at:** 2026-06-13T17:17:08Z
**Source review:** .planning/phases/19-prompt-and-deliverable-adherence/19-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 — all 4 Warnings (WR-01..04) + the 4 trivial Info items (IN-01..04).
- Fixed: 8
- Skipped: 0
- Deferred (not actioned): IN-05 (documentation-only "confirm intent" note — no code change requested; the `.github/workflows/**/*` recursive twin is not needed for the infra-generator's flat output).

Every fix carries an executable pinning test (WR-04 and IN-* doc-only items
excepted where noted). INV-3 re-proven: the 5 characterization goldens stay
byte/event-identical (NO SNAPSHOT_UPDATE — incl. the `app_builder` golden:
the post_step is event-free and the chunk sanitizer is a no-op on goldens),
`lint-imports` 4 kept / 0 broken, zero migrations. SC-001 holds: the sanitizer
keys on opener-token structure + the generic tool-less probe; the validator
keys on infra-file content + the declared capability — no workflow/agent-name
branch introduced (grep gate 0).

## Fixed Issues

### WR-01: Chunk sanitizer perturbs chunk boundaries for tool-less agents emitting `<` mid-stream

**Files modified:** `backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_chunk_sanitizer.py`
**Commit:** 1baeb3c0
**Applied fix:** Tightened step (2) of `_ChunkStreamSanitizer._hold_from_index`
so the trailing-partial-opener hold only fires on a prefix of length ≥ 2
(`range(len(opener) - 1, 1, -1)` — stop at 2, never 1). A lone `<` — common in
legit tool-less prose (HTML/JSX tags, `a < b`) — is therefore never buffered, so
ordinary tool-less streams keep per-chunk byte-identical granularity. A lone `<`
followed by `function_calls>`/`invoke` in the next delta is still caught: the
joined text re-scans for the complete/partial opener on the next `feed`. Pinned by
`test_lone_lt_and_html_at_boundaries_chunk_identical_for_toolless_agent` (a
tool-less stream with `<`, `<div>`, `a < b` at chunk boundaries → emitted ==
input, chunk-boundary-identical). All 7 chunk-sanitizer tests + the 5 goldens green.

### WR-02: `api_prefix` validator flags external (non-app) URLs as `/api/v1` violations

**Files modified:** `backend/agents/capabilities/validators/api_prefix.py`, `backend/tests/agents/test_api_prefix_validator.py`
**Commit:** e43ce55c
**Applied fix:** Constrained the URL arm of `_ENDPOINT_RES` to app-local hosts —
`https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|[A-Za-z0-9_-]+)(?::\d+)?(/path)`.
The dotless `[A-Za-z0-9_-]+` token matches a docker-compose service name but a host
containing a `.` (FQDN: `deb.nodesource.com`, `github.com`, `registry.terraform.io`)
fails to match — so external package/registry/release URLs are no longer scanned,
killing the audit-row noise that undermined the deterministic backstop. Pinned by
`test_external_urls_yield_zero_issues` (nodesource + github + terraform → 0 issues)
and `test_bare_app_healthcheck_url_is_flagged` (`http://localhost:8080/health` → 1).

### WR-03: `_ENDPOINT_RES` misses the bare healthcheck shapes the docstring claims to cover

**Files modified:** `backend/agents/capabilities/validators/api_prefix.py`, `backend/tests/agents/test_api_prefix_validator.py`
**Commit:** 18c761c2
**Applied fix:** Implemented the bare-path healthcheck coverage the docstring
advertised (preferred over down-scoping the docstring — it is the real infra
endpoint site ISS-005 exists to catch). Added a third regex
`(?:--health-cmd|HEALTHCHECK|test:)[^\n]*?(?:\s|")(/path)` scoped to the
healthcheck CONTEXT (a non-capturing delimiter keeps the path in group(1); the lazy
`[^\n]*?` captures the first path token after the keyword) so a path-only
`test: ["CMD","wget","-qO-","/health"]` is flagged while arbitrary `/path` tokens
elsewhere are not. Pinned by `test_bare_path_compose_healthcheck_is_flagged`
(bare `/health` → 1 issue) and `test_bare_path_healthcheck_under_api_v1_is_clean`
(`/api/v1/health` → 0). The pre-existing `HEALTHCHECK CMD curl http://.../health`
test still yields exactly one issue (no duplicate match).

### WR-04: Held-tail flush at stream end is untested for the data-loss case it guards

**Files modified:** `backend/tests/agents/test_chunk_sanitizer.py`
**Commit:** b0627909
**Applied fix:** Added two tests pinning both directions of the flush contract — the
CONTEXT's load-bearing safety property. `test_never_closed_opener_flushed_and_stripped_at_stream_end`
drives a tool-less stream whose final delta opens a `<function_calls>` that NEVER
closes before EOF and asserts the legit prefix survives while the never-closed opener
is stripped at flush (no leak). `test_benign_held_tail_survives_flush_no_content_loss`
ends on a benign held tail (`<f`) and asserts join(emitted) == join(input) — the
tail is flushed verbatim, nothing silently swallowed. Test-only (no source change).

### IN-01..04: Dead branches, unused field, stale citations, wrong test-docstring agent

**Files modified:** `backend/agents/capabilities/validators/api_prefix.py`, `backend/agents/capabilities/post_steps/api_prefix_audit.py`, `backend/tests/agents/test_chunk_sanitizer.py`, `backend/tests/agents/test_api_prefix_validator.py`
**Commit:** 22de51a6
**Applied fix:**
- **IN-01:** removed the duplicate `or p == API_PREFIX` and the dead `if p == "/"`
  block in `_is_violation` (`"/"` is already `_EXEMPT_PREFIXES[0]`, returned by the
  membership check above); the unreachable "nginx default catch-all" comment is gone.
- **IN-02:** dropped the unused `Issue.validator` field (no construction site set it,
  no consumer read it; the audit payload uses only `severity`/`message`).
- **IN-03:** fixed the `test_chunk_sanitizer` module docstring to name the agent
  actually exercised (`prototype-revision-agent`, not `app-code-generator`).
- **IN-04:** re-pinned the stale `engine.py:~1720` post_step seam citations (in
  `api_prefix_audit.py` and `test_api_prefix_validator.py`) to the actual seam in
  `_run_step`, `engine.py:1889-1891`.

## Verification

- `tests/agents/test_chunk_sanitizer.py` — 7 passed (4 original + WR-01 + 2× WR-04 pins)
- `tests/agents/test_api_prefix_validator.py` — 12 passed (6 original + 2× WR-02 + 2× WR-03 pins)
- The 5 characterization goldens (prototype / od_prototype / prototype_revision / od_ppt / app_builder) — byte/event-identical, NO SNAPSHOT_UPDATE (engine.py + validator both touched; INV-3 holds)
- `tests/agents/test_prompt_contracts.py` + `tests/agents/test_registry_capabilities.py` — passed
- Combined Phase-19 set + goldens — **127 passed**
- `/opt/homebrew/bin/lint-imports` — 4 contracts kept, 0 broken
- SC-001 grep gate — 0 workflow/agent-name branches in the changed sanitizer hold logic + validator (the sole `app_builder` token is an INV-3 rationale comment, not a branch)

## Skipped Issues

None — all in-scope findings were fixed. IN-05 was a documentation-only "confirm
intent" note (no code change requested); the infra-generator's flat output does not
need a `.github/workflows/**/*` recursive twin, so no action taken.

---

_Fixed: 2026-06-13T17:17:08Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
