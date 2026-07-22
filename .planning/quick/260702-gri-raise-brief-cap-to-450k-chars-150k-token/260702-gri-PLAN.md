---
phase: quick-260702-gri
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/core/config.py
  - backend/app/api/file_extract.py
  - backend/tests/unit/test_brief_max_chars.py
  - frontend/src/lib/constants.ts
  - frontend/src/app/workflow/prototype/templates/page.tsx
  - frontend/src/app/workflow/ppt/templates/page.tsx
  - frontend/src/components/workflow/IdeaInputPage.tsx
autonomous: true
requirements: [260702-gri]

must_haves:
  truths:
    - "settings.BRIEF_MAX_CHARS == 450000 (single source for planner + clarify + upload extraction cap)"
    - "file_extract._MAX_TEXT_CHARS derives from settings.BRIEF_MAX_CHARS (== 450000), not a separate literal"
    - "All three frontend attach sites slice at one shared ATTACH_MAX_CHARS == 450000 constant"
    - "A brief <= cap reaches the planner/clarify in full (no 'chars omitted'); a brief > cap is still head+tail sampled"
    - "The 4 stable characterization goldens stay byte/event-identical with NO snapshot update"
  artifacts:
    - path: "backend/app/core/config.py"
      provides: "BRIEF_MAX_CHARS = 450_000 (single source of truth)"
      contains: "BRIEF_MAX_CHARS: int = 450_000"
    - path: "backend/app/api/file_extract.py"
      provides: "_MAX_TEXT_CHARS sourced from settings.BRIEF_MAX_CHARS"
      contains: "settings.BRIEF_MAX_CHARS"
    - path: "frontend/src/lib/constants.ts"
      provides: "shared ATTACH_MAX_CHARS = 450000"
      contains: "ATTACH_MAX_CHARS"
    - path: "backend/tests/unit/test_brief_max_chars.py"
      provides: "value-agnostic brief-cap regression tests + 450k value pin"
  key_links:
    - from: "backend/app/api/file_extract.py"
      to: "backend/app/core/config.py"
      via: "from app.core.config import settings"
      pattern: "from app.core.config import settings"
    - from: "frontend/src/app/workflow/prototype/templates/page.tsx"
      to: "frontend/src/lib/constants.ts"
      via: "import ATTACH_MAX_CHARS"
      pattern: "ATTACH_MAX_CHARS"
---

<objective>
Raise the input-brief character cap from 64k to 450,000 chars (~150k tokens — safe under
Haiku's 200k window) and align the ingest caps (backend upload extraction + the three frontend
attach slices) so an uploaded/attached brief can actually reach the new limit. Establish one
single source of truth on each side: backend = `settings.BRIEF_MAX_CHARS`; frontend = one shared
`ATTACH_MAX_CHARS` constant.

Rationale (state in-repo via the config comment): Haiku context = 200k tokens; target ~150k
tokens for the brief. chars→tokens varies (prose ~4, code/HTML ~3, minified ~2.5). 450,000 chars
= ~150k tokens for dense content, ~112k for prose, and never overflows 200k even for minified
content (worst case ~180k + scaffolding < 200k) — the safe choice. Planner + clarify are each a
single LLM call, so the cost is a one-time ~150k input tokens — fine.

Purpose: Uploaded/attached briefs are currently whittled to 64k before they ever reach the
planner/clarify LLM; three separate hardcoded caps drift independently. This unifies them and
lifts the ceiling to the decided value.

Output: config.py (450k value + updated comment), file_extract.py (single-sourced cap + fixed
stale docstrings), a shared frontend constant, three attach sites re-pointed at it, and updated
value-agnostic tests.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@CLAUDE.md
@backend/CLAUDE.md
@backend/app/core/config.py
@backend/app/api/file_extract.py
@backend/tests/unit/test_brief_max_chars.py
@frontend/src/app/workflow/prototype/templates/page.tsx
@frontend/src/app/workflow/ppt/templates/page.tsx
@frontend/src/components/workflow/IdeaInputPage.tsx
</context>

<scope_guardrails>
ONLY these files may change: backend `config.py`, `file_extract.py`, `test_brief_max_chars.py`
(and any file_extract test IF one is found — none exists today, verified), the 3 FE attach sites,
and a shared FE constant module.

DO NOT touch:
- the revision re-ingest slices (40k / 60k) — separate follow-up, out of scope
- the cross-pipeline-context slice (4k) — out of scope
- `_MAX_FILE_BYTES` (10 MB binary size limit) in file_extract.py — leave unchanged
- any planner/clarify slice LOGIC — only the cap VALUE/source changes; head+tail sampling and
  the "chars omitted" marker behavior stay exactly as-is

Do not widen scope beyond the above. This task is fully specified; apply exactly.
</scope_guardrails>

<tasks>

<task type="auto">
  <name>Task 1: Backend single source of truth — raise BRIEF_MAX_CHARS to 450k and source the upload cap from it</name>
  <files>backend/app/core/config.py, backend/app/api/file_extract.py</files>
  <action>
In `backend/app/core/config.py`: change the `BRIEF_MAX_CHARS: int = 64_000` field (currently
line ~113) to `BRIEF_MAX_CHARS: int = 450_000`. Rewrite the preceding comment block (lines
~104-113) so it states the new intent accurately: 450,000 chars ≈ ~150k tokens for dense
content (~112k for prose), safe under Haiku's 200k window even for minified content; this is now
the SINGLE source of truth for the planner analyze prompt + stored `planning_context.user_request`,
the ClarifyEngine brief_sample, AND the upload/attach ingest cap (`file_extract._MAX_TEXT_CHARS`).
Keep the note that briefs beyond the ceiling are still head+tail sampled (planner) / head-capped
(clarify + storage). Do not change any other setting.

In `backend/app/api/file_extract.py`:
  - Add `from app.core.config import settings` to the imports (the app/api → app/core dependency
    is allowed by import-linter). There is no existing settings import in this file.
  - Change `_MAX_TEXT_CHARS = 64_000` (line ~32) to `_MAX_TEXT_CHARS = settings.BRIEF_MAX_CHARS`
    and update its inline comment to note the extracted-upload text cap now tracks the brief cap
    (single source).
  - Fix BOTH stale docstrings that reference "16,000": the module docstring (line ~12-13, "Text
    is capped at 16,000 chars…") and the endpoint docstring (line ~91, "Returns up to 16,000
    characters…"). Make them accurate — the extracted text is capped at `settings.BRIEF_MAX_CHARS`
    characters (~450,000). Do not invent behavior; just correct the number/wording.
  - Leave `_MAX_FILE_BYTES = 10 * 1024 * 1024` (10 MB) unchanged. Leave the `truncated`/slice
    logic (`text[:_MAX_TEXT_CHARS]`, `len(text) > _MAX_TEXT_CHARS`) unchanged — it tracks the
    constant automatically.
  </action>
  <verify>
    <automated>cd backend && python3.11 -c "from app.core.config import settings; from app.api import file_extract; assert settings.BRIEF_MAX_CHARS == 450000, settings.BRIEF_MAX_CHARS; assert file_extract._MAX_TEXT_CHARS == 450000, file_extract._MAX_TEXT_CHARS; print('OK')"</automated>
  </verify>
  <done>
Import smoke prints OK: `settings.BRIEF_MAX_CHARS == 450000` and
`file_extract._MAX_TEXT_CHARS == 450000`, no ImportError. No "16,000" or "64_000"/"64,000"
literal remains in file_extract.py. `_MAX_FILE_BYTES` unchanged.
  </done>
</task>

<task type="auto">
  <name>Task 2: Frontend single shared attach cap — add ATTACH_MAX_CHARS = 450000 and re-point all three attach sites</name>
  <files>frontend/src/lib/constants.ts, frontend/src/app/workflow/prototype/templates/page.tsx, frontend/src/app/workflow/ppt/templates/page.tsx, frontend/src/components/workflow/IdeaInputPage.tsx</files>
  <action>
No general FE constants module exists today (`frontend/src/lib/` has `env.ts`, `entitlements.ts`,
etc. but no `constants.ts`) — create `frontend/src/lib/constants.ts` exporting a single
`export const ATTACH_MAX_CHARS = 450000;` with a one-line comment tying it to the backend
`BRIEF_MAX_CHARS` (~150k tokens, safe under Haiku's 200k window). This is the single frontend
source of truth for the attach slice.

In each of the three attach sites, import `ATTACH_MAX_CHARS` from `@/lib/constants` (match the
existing path-alias import style in that file) and replace the hardcoded slice
`content.slice(0, 64000)` with `content.slice(0, ATTACH_MAX_CHARS)`:
  - `frontend/src/app/workflow/prototype/templates/page.tsx` (~line 478)
  - `frontend/src/app/workflow/ppt/templates/page.tsx` (~line 443)
  - `frontend/src/components/workflow/IdeaInputPage.tsx` (~line 541)

Same-site consistency fix (in-scope — same attach handler, avoids a now-wrong user-facing
number): in each of the three files, the binary-upload branch shows a truncation note with a
hardcoded literal `[Content truncated to 64,000 chars]` (~lines 489 / 455 / 553). This fires on
the backend `res.truncated` flag, whose cap is now 450k. Replace the literal `64,000` with
`${ATTACH_MAX_CHARS.toLocaleString()}` (yields "450,000") so the message tracks the shared
constant. Do NOT alter any other slice in these files (no revision 40k/60k, no 4k
cross-pipeline slice — none of those live at these exact lines, but confirm you touched only the
64000 attach slice + its adjacent truncation note).
  </action>
  <verify>
    <automated>cd frontend && grep -rn "slice(0, 64000)\|truncated to 64,000" src/app/workflow/prototype/templates/page.tsx src/app/workflow/ppt/templates/page.tsx src/components/workflow/IdeaInputPage.tsx | grep -c . | grep -qx 0 && echo "no 64000 attach literals remain" && grep -c "ATTACH_MAX_CHARS" src/lib/constants.ts</automated>
  </verify>
  <done>
`frontend/src/lib/constants.ts` exists and exports `ATTACH_MAX_CHARS = 450000`. All three attach
sites import it and slice with it; no `slice(0, 64000)` or `truncated to 64,000` literal remains
in the three files. The revision (40k/60k) and cross-pipeline (4k) slices are untouched.
  </done>
</task>

<task type="auto">
  <name>Task 3: Make the brief-cap tests value-agnostic + pin the new 450k value; confirm no file_extract test needs updating</name>
  <files>backend/tests/unit/test_brief_max_chars.py</files>
  <action>
Update `backend/tests/unit/test_brief_max_chars.py` so it is value-agnostic (derive from
`settings.BRIEF_MAX_CHARS`, never re-hardcode 64000/2000/3000), except the deliberate value pin:

  - `test_full_brief_reaches_planner_uncut`: build the brief so its length is
    `settings.BRIEF_MAX_CHARS // 2` chars (well under the cap) — e.g. repeat a fixed phrase and
    slice to `settings.BRIEF_MAX_CHARS // 2`. Keep the assertions: `len(brief) <= settings.BRIEF_MAX_CHARS`,
    the full brief text appears verbatim in the built prompt, and `"chars omitted" not in prompt`.
  - `test_full_user_request_reaches_clarify_uncut`: build `user_request` at
    `settings.BRIEF_MAX_CHARS // 2` chars; keep the brief_sample slice logic mirroring
    `clarify_engine.py` (`user_request[: settings.BRIEF_MAX_CHARS]`); assert the sample equals the
    full user_request (no cut). Replace any bare `2000` literal in the assertion with a
    settings-derived comparison (the sample is the full request, so `len(brief_sample) == len(user_request)`).
  - `test_ceiling_still_enforced_above_cap`: build the brief at `settings.BRIEF_MAX_CHARS + 10_000`
    chars; assert `"chars omitted" in prompt`, the raw brief is NOT embedded whole, and the prompt
    stays bounded (`len(prompt) < len(brief) + 5000`).
  - `test_planner_and_clarify_share_single_source_of_truth`: this is the ONE intentional value
    pin — change the stale `assert settings.BRIEF_MAX_CHARS == 64_000` to
    `assert settings.BRIEF_MAX_CHARS == 450_000` and update the docstring/comment from "(64k)" to
    "(450k)". (This guards the decided value and matches the import smoke.)

Also update the module docstring's "<= 64k" reference to be value-agnostic ("<= settings.BRIEF_MAX_CHARS").

Then confirm task #5 from the spec is a no-op: search `backend/tests/` for any file_extract /
`_MAX_TEXT_CHARS` cap assertion. Verified during planning that none exists — if the grep below
returns nothing, no additional test edit is required; if it unexpectedly finds one, update that
literal to `settings.BRIEF_MAX_CHARS` too and note it.
  </action>
  <verify>
    <automated>cd backend && grep -rn "_MAX_TEXT_CHARS\|extract-text\|file_extract" tests/ ; python3.11 -m pytest tests/unit/test_brief_max_chars.py -v</automated>
  </verify>
  <done>
`tests/unit/test_brief_max_chars.py` passes; no remaining hardcoded `64000`/`64_000` (except the
intentional `== 450_000` value pin), and no lingering bare `2000`/`3000` cap literals. The grep
confirms whether any file_extract cap test exists (none expected).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → /api/files/extract-text | Untrusted uploaded binary crosses into extraction |
| user brief → planner/clarify LLM call | Untrusted large text crosses into a single LLM input |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-gri-01 | Denial of Service | file_extract extraction cap raised 64k→450k | accept | `_MAX_FILE_BYTES` (10 MB binary) is UNCHANGED and remains the primary ingress guard; the char cap only bounds extracted text length. Larger extracted text is a single Haiku call (~150k input tokens max), not a loop — one-time, bounded cost. |
| T-gri-02 | Denial of Service | planner/clarify input on oversized briefs | mitigate | Behavior unchanged: briefs beyond `BRIEF_MAX_CHARS` are still head+tail sampled (planner) / head-capped (clarify + storage), proven by `test_ceiling_still_enforced_above_cap`. Input stays bounded regardless of raw brief size. |
| T-gri-03 | Tampering | INV-3 characterization goldens | mitigate | 4 stable goldens (prototype, od_prototype, prototype_revision, app_builder) run with NO snapshot update; short golden briefs make the 450k cap a no-op → byte/event-identical. od_ppt excluded (known-environmental). |

No package installs in this task — no supply-chain (T-*-SC) checkpoint required.
</threat_model>

<verification>
Run all offline (do NOT run the full pytest suite — it hangs offline on Chromium/Bedrock/Postgres gates):

1. Import smoke: `cd backend && python3.11 -c "from app.core.config import settings; from app.api import file_extract; assert settings.BRIEF_MAX_CHARS == 450000; assert file_extract._MAX_TEXT_CHARS == 450000; print('OK')"`
2. Brief-cap tests: `cd backend && python3.11 -m pytest tests/unit/test_brief_max_chars.py -v`
3. Clarify parse test: `cd backend && python3.11 -m pytest tests/unit/test_clarify_json_parse.py -v`
4. INV-3 goldens (byte/event-identical, NO SNAPSHOT_UPDATE — do NOT set any snapshot-update env; do NOT run od_ppt):
   `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -v`
5. Import boundaries: `/opt/homebrew/bin/lint-imports` → expect 4 contracts kept / 0 broken.
6. Frontend types: `cd frontend && npx tsc --noEmit` — the three touched files (+ new constants.ts) must be clean. Pre-existing unrelated errors elsewhere may remain; NOTE them, do not fix them.
</verification>

<success_criteria>
- `settings.BRIEF_MAX_CHARS == 450000`; `file_extract._MAX_TEXT_CHARS` derives from it (== 450000).
- No stale "16,000" / "64,000" / "64_000" literal remains in config.py or file_extract.py (except intentional new comment prose about the change history if any).
- One shared FE `ATTACH_MAX_CHARS = 450000` constant; all three attach sites slice with it; no `slice(0, 64000)` or `[Content truncated to 64,000 chars]` literal remains in the three files.
- `test_brief_max_chars.py` passes and is value-agnostic (single intentional `== 450_000` pin).
- 4 characterization goldens byte/event-identical (no snapshot update); `test_clarify_json_parse.py` passes.
- `lint-imports` = 4 kept / 0 broken.
- `npx tsc --noEmit` clean for the touched FE files (pre-existing unrelated errors noted, not fixed).
- Commit: `feat(config): raise brief cap to 450k chars (~150k tokens) + align upload/attach ingest caps`
</success_criteria>

<output>
Update `.planning/STATE.md` and mark this quick task complete after verification passes.
Commit with: `feat(config): raise brief cap to 450k chars (~150k tokens) + align upload/attach ingest caps`
</output>
