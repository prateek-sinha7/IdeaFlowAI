---
phase: 15-live-pass-prompt-contract-closure
reviewed: 2026-06-13T00:50:36Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/agents/prompts/od-ppt-validator/AGENT.md
  - backend/agents/prompts/app-sdlc-governance/AGENT.md
  - backend/agents/prompts/dotnet-sdlc-governance/AGENT.md
  - backend/agents/prompts/mulesoft-sdlc-governance/AGENT.md
  - backend/agents/prompts/app-infra-generator/AGENT.md
  - backend/tests/agents/test_prompt_contracts.py
findings:
  critical: 0
  warning: 4
  info: 2
  total: 6
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-06-13T00:50:36Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the five Phase-15 prompt-body edits (od-ppt-validator deck re-emission contract, the three sdlc-governance anti-fabrication contracts, app-infra-generator /api/v1 path contract) and the new durable pin suite `test_prompt_contracts.py`.

What was verified and held up:

- All 11 new tests pass (`python3.11 -m pytest tests/agents/test_prompt_contracts.py` — 11 passed, 0.81s). Adjacent suites unaffected: `test_characterization_od_ppt.py`, `test_loader.py`, `test_context_message_oracle.py` — 56 passed.
- Every pinned token was confirmed against the actual `prompt_body` bytes: "exactly ONE <artifact>", "complete corrected HTML deck", "even when you change nothing", contract-above-checklist ordering, single `## OUTPUT CONTRACT` heading; "You have NO tools" / `<function_calls>` / `<invoke>` / `write_todos` / "Begin your response DIRECTLY with" in all three governance bodies; per-pipeline tail lines ("fenced block" vs "the first Markdown heading"); the defused "Read the concrete choices" phrase is absent (body says "Use the concrete choices"); `/api/v1` literal count is 8 (gate >= 6), "API PATH CONTRACT" precedes "OUTPUT FORMAT", concrete `curl /api/v1/health` and `location /api/v1/` examples present.
- Frontmatter is semantically unchanged on all five agents (od-ppt-validator `tools: [workspace]` intact per the documented intent; orders 3/15/13/13/10 and pipeline_types match the freeze test).
- The composition test makes ZERO edits to `_scripted_model.py` / `live_harness.py`; `_ScriptedTurn(texts=…, usage=…)` and `ScriptedFakeChatModel([…])` match the helper signatures; the per-agent callable model matches `drive_engine_pipeline`'s documented factory mode; the `od_context` seed is byte-identical to `_scripted_model._drive`'s. The stock golden-frozen validator script (`"Validation passed. No P0 issues.\n<artifact>…"`) is untouched — the contract-shaped validator is a per-test model only.
- The validator contract's "Preserve the incoming artifact's identifier, type, and title attributes" is satisfiable live: od-ppt-composer's contract emits `<artifact identifier="…" type="text/html" title="…">`. `unwrap_artifact` (`agents/capabilities/deliverables/_artifact.py:34-38`) is first-match and attribute-tolerant (`<artifact[^>]*>`), confirming the exactly-ONE-artifact rationale.

Defects found are all in contract wording self-consistency (the exact axis this phase exists to close) and in pins that are weaker than their own documented intent. No Critical issues.

## Warnings

### WR-01: od-ppt-validator gives a live model contradictory instructions when a P0/P1 defect is not minimally patchable

**File:** `backend/agents/prompts/od-ppt-validator/AGENT.md:39-61`
**Issue:** Three instructions collide on non-trivial defects:

- Line 39: "Run each check. **Fix P0 failures before emitting.** P1 issues are best-effort."
- Line 59: "Be a SURGEON. **Do not rewrite.** Do not redesign. **Do not change content**, colors, or layout."
- Line 60 scopes fixes to "a minimal patch (e.g., add missing `active` class, remove stray fence)".

Two concrete contradiction cases a live model will hit:

1. **Missing navigation script / slide counter (P0, lines 44-45):** "fix before emitting" requires *writing new JS/markup*, which is not a minimal patch and arguably a rewrite. The prompt never says what to do when a P0 defect exceeds a minimal patch — emit the broken deck as-is, or synthesize the fix? A live model can resolve this either way, including by rewriting the deck (the exact failure mode the SURGEON rule exists to prevent).
2. **P1 content checks (lines 53-54):** "No Lorem ipsum / Placeholder / TBD / empty slide bodies" — any best-effort fix here *requires inventing content*, directly violating "Do not change content."

The contract correctly guarantees one complete artifact regardless, so the resolver path is safe — but deck *bytes* under these branches are unspecified, which is precisely the live-model-ambiguity class this phase set out to close.
**Fix:** Add one disambiguation line to `## RULES`, e.g.:

```markdown
- If a defect cannot be fixed with a minimal patch (e.g., the deck has no
  navigation script at all), do NOT attempt a rewrite — re-emit the deck
  as-is, in full. The output contract outranks the checklist.
- P1 content fixes never invent new content: leave placeholder text in
  place rather than authoring replacement copy.
```

### WR-02: app-sdlc-governance — "state the assumption" has no permitted location under the begin-directly / no-prose contract

**File:** `backend/agents/prompts/app-sdlc-governance/AGENT.md:35,44-46,123`
**Issue:** Line 35 mandates "Begin your response DIRECTLY with the first `filename:` fenced block — no preamble, no plan, no narration before it," and line 123 mandates "Output ONLY the fenced file blocks above. No prose outside the blocks." But lines 44-46 instruct: "where something is unstated, NEVER ask the user — pick the conventional choice, **state the assumption**, and proceed." The prompt never says *where* to state assumptions. The natural live-model resolution is a short assumptions preamble before the first block — which violates the begin-directly contract this phase just added and would regress the exact F4 first-token shape the contract pins. (dotnet/mulesoft are unaffected: their deliverable is a single Markdown document, so assumptions trivially live inside it.)
**Fix:** Anchor the assumption location, e.g. amend line 44-46:

```markdown
where something is unstated, NEVER ask the user — pick the conventional
choice, record the assumption INSIDE the relevant file block (e.g., as an
"Assumptions" note in the ADR's Context section), and proceed.
```

### WR-03: Frontmatter "freeze" pins only 3 of the behavior-bearing fields — guardrails, max_tokens, context_from, injects, and gate can still drift silently

**File:** `backend/tests/agents/test_prompt_contracts.py:146-163`
**Issue:** `test_contract_agents_frontmatter_frozen`'s docstring claims "The five contract agents' frontmatter is byte-stable (bodies-only phase)," and the section header says a future cleanup "cannot silently change behavior." The test asserts only `order` / `pipeline_type` / `tools`. Unpinned fields that directly change runtime behavior for these five agents:

- `guardrails` — dotnet (`[dotnet]`) and mulesoft (`[mulesoft, java-spring]`) inject guardrail blocks into the composed system prompt; dropping them changes the prompt the contract lines live in.
- `context_from` / `consumes` — changing routing changes what "already included in this message as context" (the contract's own premise, line 33) actually contains.
- `max_tokens`, `injects`, `gate` — UI/composition/gating identity.

A "cleanup" that strips `guardrails: [mulesoft, java-spring]` or rewires `context_from` passes this freeze, contradicting both the docstring and the T-15-01 mitigation intent.
**Fix:** Extend the parametrize tuples (or assert per-field from a dict) to cover the remaining behavior-bearing fields:

```python
spec = load_agent_spec(agent_id)
assert spec.order == order
assert spec.pipeline_type == pipeline_type
assert list(spec.tools) == tools
assert list(spec.guardrails) == guardrails
assert list(spec.context_from) == context_from
assert spec.max_tokens == max_tokens
assert spec.gate == gate
```

Alternatively, soften the docstring to "identity/ordering/tool grants only" — but pinning the fields is the durable option and matches the module's stated purpose.

### WR-04: Anti-fabrication pin is weaker than the properties its own comments declare load-bearing (exactly-once terseness; Pitfall-5 negative assertion)

**File:** `backend/tests/agents/test_prompt_contracts.py:94-111`
**Issue:** Two documented properties are not actually asserted:

1. Line 94-95's comment: "forbidden tokens named exactly once, tersely — Pitfall 7." The test asserts presence only (`assert "<function_calls>" in body`). Pitfall 7's stated concern is that *repeating* forbidden tool-XML tokens re-primes fabrication — the very failure F4 fixed. A future edit that repeats `<invoke>`/`<function_calls>` throughout the body passes this pin while reintroducing the priming risk. `assert body.count("<function_calls>") == 1` (and likewise for `<invoke>`, `write_todos`) would pin the documented property.
2. Lines 109-110 cite "Pitfall 5: no filename-block contamination of the migration pipelines," but the dotnet/mulesoft branch only asserts the Markdown-heading line is present — it never asserts `"filename:" not in body` (or "fenced block" absent). A drift that adds app-style `filename:` blocks to the migration prompts (the contamination Pitfall 5 names) passes the pin.

The module's entire stated purpose (docstring, lines 5-9) is durability against future prompt rewrites; pins weaker than their cited pitfalls leave the named regressions open.
**Fix:**

```python
# Pitfall 7: forbidden tokens named exactly once.
for token in ("<function_calls>", "<invoke>", "write_todos"):
    assert body.count(token) == 1

if agent_id != "app-sdlc-governance":
    # Pitfall 5: no filename-block contamination of migration pipelines.
    assert "filename:" not in body
```

## Info

### IN-01: od_context seed duplicated verbatim from `_scripted_model._drive` — drift risk between the two copies

**File:** `backend/tests/agents/test_prompt_contracts.py:225-232`
**Issue:** The six-key `od_context` dict is a byte-for-byte copy of the seed in `_scripted_model._drive` (`_scripted_model.py:572-579`), as the inline comment acknowledges. If `_drive`'s seed gains a required key (e.g., a new inject), this copy silently drifts and the composition test fails with an unrelated `TemplateMissingError`.
**Fix:** Export the seed as a module-level constant in `_scripted_model.py` (e.g., `HARNESS_OD_CONTEXT`) and import it in both places. Exporting a constant does not touch the golden-frozen scripted turns.

### IN-02: Composition test's "narration did NOT win" assertion is structurally tautological; narration magnitude understates the live evidence shape

**File:** `backend/tests/agents/test_prompt_contracts.py:192,244`
**Issue:** Two accuracy nits in an otherwise sound test. (1) `_NARRATION` contains no `<artifact` token (acknowledged at line 191), so the first-match `unwrap_artifact` regex *cannot* select it — the line-244 assertion can only fail if the resolver stops unwrapping entirely, which line 241 already covers. Its real value (leading commentary is stripped, not prepended) is worth stating in the comment. (2) The comment at lines 189-190 says it reproduces the live failure shape ("1,350 chars of narration"); `_NARRATION` is ~66 chars. Shape (narration-first) is reproduced; magnitude is not — harmless for a regex resolver, but the comment overstates fidelity.
**Fix:** Reword the comment to claim shape-fidelity only, and note that line 244 guards the "commentary leaks into final_output" axis rather than the unwrap-selection axis. Optionally pad `_NARRATION` to multi-line, >1 kB to match the evidence shape at zero cost.

---

_Reviewed: 2026-06-13T00:50:36Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
