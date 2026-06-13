---
phase: 19-prompt-and-deliverable-adherence
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - backend/agents/capabilities/validators/api_prefix.py
  - backend/agents/capabilities/post_steps/api_prefix_audit.py
  - backend/agents/capabilities/registry.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/workflows/app_builder/workflow.yaml
  - backend/agents/prompts/app-code-generator/AGENT.md
  - backend/agents/prompts/app-test-implementation/AGENT.md
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 19: Code Review Report

**Reviewed:** 2026-06-13
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 19 lands three durable structural backstops (ISS-004 chunk sanitizer, ISS-005
`api_prefix` validator + event-free post_step, ISS-006 shared prompt contract). I
scrutinized the highest-risk item — the live-stream `_ChunkStreamSanitizer` — hardest,
including hand-traced span-straddle, false-positive prose, flush behavior, the probe gate,
and per-stream isolation. **No BLOCKERs.** The sanitizer is content-lossless on join, the
probe gate cleanly bypasses tool-using agents, the buffer is per-invocation-local (no
fan-out cross-talk), and at flush a benign held tail is returned verbatim — so no
user-visible data loss exists. All 110 Phase-19 tests pass.

The findings below are quality/robustness concerns: (1) the chunk sanitizer perturbs
chunk *boundaries* for tool-less agents whose legitimate prose contains `<` at delta
boundaries (lossless on join, but coalesced/suppressed deltas — a behavioral change vs the
pre-phase raw stream); (2) the `api_prefix` validator's URL regex flags **external** URLs
(package/registry/release URLs in Dockerfiles + CI YAML) as `/api/v1` violations, polluting
the audit rows; (3) dead/duplicate branches in `_is_violation`; plus doc/test-comment
mismatches.

INV-3 safety holds for all three items (goldens normalize chunk text and pin only
post-sanitized output; the post_step is event-free; the prompt edits are body-only and the
scripted model ignores prompt bodies). SC-001 holds (sanitizer keys on the generic
tool-less probe; validator keys on the declared capability; no workflow/agent-name
branching in the kernel).

## Warnings

### WR-01: Chunk sanitizer perturbs chunk boundaries for tool-less agents emitting `<` mid-stream

**File:** `backend/agents/execution_engine/engine.py:227-235` (`_ChunkStreamSanitizer._hold_from_index`), applied at `:2619-2621`
**Issue:** The partial-opener guard holds ANY trailing proper-prefix of `<function_calls>`/`<invoke` — which includes a bare `<`. For a tool-less agent (e.g. `domain-analyst`, or any text-only agent that streams HTML/JSX/Markdown/inequalities), every chunk that ends on a `<` boundary causes the tail to be held and merged into the next emission. I hand-traced this: with deltas `['Use the ', '<', 'Button> component and the ', '<', 'Input> field.']` the emitted stream is `['Use the ', '', '<Button> component and the ', '', '<Input> field.', '']` — **lossless on join** (no data loss; the final `<` tail is flushed verbatim because `_strip_fabricated_tool_xml` no-ops a benign partial), but the *per-chunk granularity is changed* (empty deltas suppressed, chunks coalesced). This is a real behavioral change to the live UI token stream for tool-less agents whose legit output contains `<` at delta boundaries — which is common (any HTML/JSX/comparison operator). The `test_clean_stream_passes_through_unchanged_for_toolless_agent` test only exercises a stream with NO `<` at boundaries, so it does not catch this.

INV-3 is unaffected (goldens normalize chunk text), and there is no data loss, so this is a WARNING not a BLOCKER. But the CONTEXT's "tool-less clean stream → chunk-identical" intent is only met for streams without boundary `<`.
**Fix:** Tighten the partial-opener hold to fire only on a *meaningfully disambiguating* prefix rather than a single `<`. E.g. require the held trailing prefix to be at least the length where it can only be a tool-XML opener (`<i`/`<f` and longer for `<invoke`/`<function_calls`), and never hold on a lone `<`:
```python
# Only hold a trailing partial opener once it is unambiguous (len >= 2),
# so a lone "<" (common in legit HTML/JSX/prose) is never buffered.
for opener in _TOOL_XML_OPENERS:
    for plen in range(len(opener) - 1, 1, -1):  # stop at 2, not 1
        if text.endswith(opener[:plen]):
            ...
```
This still buffers `<i`/`<f`+ (the real split-opener case the test covers) while letting a lone `<` pass through, preserving chunk granularity for ordinary prose. (A lone `<` followed in the next delta by `function_calls>`/`invoke` is still caught because the joined text re-scans for the complete/partial opener.)

### WR-02: `api_prefix` validator flags external (non-app) URLs as `/api/v1` violations

**File:** `backend/agents/capabilities/validators/api_prefix.py:77` (`_ENDPOINT_RES[0]`), `:87-97` (`_is_violation`)
**Issue:** The URL regex `https?://[^/\s]+(/[A-Za-z0-9_\-/]*)` matches the path of **any** http(s) URL, including external ones that legitimately have nothing to do with the app's API surface. Verified against realistic infra lines:
- `RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash` → flags `/setup_20`
- `RUN wget https://github.com/foo/bar/releases/download/v1/tool` → flags `/foo/bar/releases/download/v1/tool`
- `- https://registry.terraform.io/providers/hashicorp/aws` → flags `/providers/hashicorp/aws`

These are normal Dockerfile/CI-YAML content. The validator is event-free and only writes a `validation_results` audit row (not gating, not in the stream), so this is **audit-row noise, not a functional break** — hence WARNING. But it materially undermines the "deterministic backstop" value: an infra step that correctly uses `/api/v1` everywhere can still record a pile of false P2 issues from unrelated download URLs.
**Fix:** Constrain the URL arm to app-local hosts (so external package/registry URLs are skipped). The healthcheck/smoke surface the CONTEXT targets is localhost/service-name:
```python
# Only app-local hosts: localhost / 127.0.0.1 / 0.0.0.0 / a docker-compose
# service name (no dot, i.e. not a public FQDN) / $HOST-style placeholders.
re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|[A-Za-z0-9_-]+)(?::\d+)?(/[A-Za-z0-9_\-/]*)"
)
```
Excluding hosts containing a `.` (FQDN) drops `deb.nodesource.com`, `github.com`, `registry.terraform.io` while keeping `localhost:8080/health` and `app:3000/users`.

### WR-03: `_ENDPOINT_RES` misses common healthcheck/smoke shapes the docstring claims to cover

**File:** `backend/agents/capabilities/validators/api_prefix.py:70-80`
**Issue:** The module docstring (`:11-14`, `:70-72`) advertises coverage of "healthcheck paths, nginx `location`, smoke `curl`" and a "bare healthcheck path option (`--health-cmd` / `test:` `/health`)". But `_ENDPOINT_RES` only has two patterns: an http(s) URL and an nginx `location`. A docker-compose `test:` healthcheck or a `--health-cmd` that names a **bare path** without an `http://` prefix (e.g. `test: ["CMD", "wget", "-qO-", "/health"]`, or a path-only env reference) is NOT matched — a real false-negative against the validator's own stated heuristic. The validator therefore silently passes infra that violates the `/api/v1` rule via a bare-path healthcheck, which is exactly the shape ISS-005 exists to catch.
**Fix:** Either add a third regex for a bare-path healthcheck token (e.g. a `/path` argument inside a `test:`/`HEALTHCHECK`/`--health-cmd` context), or correct the docstring to state only http-URL + nginx-location are scanned so the contract matches the implementation. Given the deterministic-backstop intent, prefer adding the pattern:
```python
# A bare path argument in a healthcheck (compose `test:` / Docker --health-cmd):
re.compile(r"(?:--health-cmd|HEALTHCHECK|test:)[^\n]*?\s(/[A-Za-z0-9_\-/]+)"),
```
(scope it to the healthcheck context so it doesn't match arbitrary `/path` tokens).

### WR-04: Held-tail flush at stream end is untested for the data-loss case it guards

**File:** `backend/agents/execution_engine/engine.py:275-286` (`flush`), `:2694-2701`
**Issue:** The CONTEXT's load-bearing safety property is "the buffer flushes at stream end (no lost final chunk)". The four `test_chunk_sanitizer.py` tests cover split-strip, tool-use bypass, single-chunk strip, and clean pass-through — but **none asserts the flush path emits a legitimately-held trailing tail**. The one scenario where a tool-less stream ends with the buffer holding a benign partial opener (e.g. a final delta `"final answer: x <"`, or `"see <i"`) is exactly where a regression in `flush()`/`_strip_fabricated_tool_xml` would silently swallow real trailing content. The current code is correct (I verified `_strip_fabricated_tool_xml("final answer: 3 <") == "final answer: 3 <"`), but it is unpinned — a future change to the held-tail handling could drop content with the suite still green.
**Fix:** Add a test: a tool-less stream whose final delta leaves a benign partial-opener tail held (`['Result is ', 'x <i']` with no completing delta), and assert the joined emitted output equals the joined input (the tail survives the flush). Pair it with a test where the final held tail IS an unterminated `<function_calls>` opener and assert it is stripped — pinning both directions of the flush contract.

## Info

### IN-01: Duplicate and dead branches in `_is_violation`

**File:** `backend/agents/capabilities/validators/api_prefix.py:92,95-96`
**Issue:** Line 92 tests `p == API_PREFIX` twice in one `or` chain (`p == API_PREFIX or p.startswith(API_PREFIX + "/") or p == API_PREFIX`). Separately, lines 95-96 (`if p == "/": return False`) are dead: `"/"` is already the first entry of `_EXEMPT_PREFIXES` (line 84) and returns at line 90. The accompanying comment ("nginx default catch-all") is therefore unreachable.
**Fix:** Drop the duplicate `or p == API_PREFIX` and delete the dead `if p == "/"` block (it is fully subsumed by the `_EXEMPT_PREFIXES` membership check).

### IN-02: `Issue.validator` field is dead — never read or set per-instance

**File:** `backend/agents/capabilities/validators/api_prefix.py:46-49,161-169`
**Issue:** `Issue` declares `validator: str = "api_prefix"`, but every construction site (`:161`) sets only `severity` + `message`, and no consumer reads `issue.validator` (the audit payload at `:207` uses only `severity`/`message`). It is unused scaffolding.
**Fix:** Remove the `validator` field, or actually thread it into the recorded payload if per-issue provenance is intended. (Low priority — harmless, just dead surface.)

### IN-03: Test-module docstring names the wrong tool-using agent

**File:** `backend/tests/agents/test_chunk_sanitizer.py:23` (docstring) vs `:47` (constant)
**Issue:** The module docstring claims SC-001 is proven "using a real tool-less (`domain-analyst`) vs tool-using (`app-code-generator`) agent", but the actual `_TOOLUSING_AGENT` constant is `"prototype-revision-agent"` (line 47). Harmless doc drift, but misleading to a future reader auditing the SC-001 proof.
**Fix:** Update the docstring to name `prototype-revision-agent` (the agent actually exercised), or switch the constant to `app-code-generator` if that was the intended fixture.

### IN-04: Comment cites a stale post_step seam line number

**File:** `backend/agents/capabilities/post_steps/api_prefix_audit.py:11`; `backend/tests/agents/test_api_prefix_validator.py:266`
**Issue:** Both reference the post_step invocation as "engine.py:~1720" / ":~1666-1668" (CONTEXT), but the actual seam is `engine.py:1889-1891` (`post_step_name = getattr(step, "post_step", None); ... _registry.resolve("post_step", post_step_name).run(step, ectx)`). Stale line citations rot; a `~` hedge mitigates but the numbers are materially off.
**Fix:** Update the inline citations to the current seam (`engine.py:1889-1891`), or drop the precise line number in favor of a symbol reference (`the declared-post_step invocation in _run_step`).

### IN-05: `_INFRA_GLOBS` will not match a nginx `*.conf` placed directly under a `conf.d/` only via recursive glob — confirm intent

**File:** `backend/agents/capabilities/validators/api_prefix.py:55-65`
**Issue:** The globs pair each top-level pattern with a `**/`-recursive twin (`"*.conf"` + `"**/*.conf"`), which is correct and covers nested dirs. This is fine — flagged only to note that `.github/workflows/*` is **non-recursive** and has no `**/` twin, so a workflow file in a nested subdir under `.github/workflows/` (rare but possible with reusable-workflow layouts) is missed. Almost certainly not a real gap for the infra-generator's flat output, but worth a one-line confirmation.
**Fix:** If nested workflow dirs are a concern, add `".github/workflows/**/*"`. Otherwise no action — documenting for completeness.

---

_Reviewed: 2026-06-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
