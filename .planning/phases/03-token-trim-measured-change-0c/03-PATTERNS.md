# Phase 3: Token-Trim (measured change) [0C] - Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 1 modified (engine) + 3-4 created/touched (tests + goldens)
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/agents/execution_engine/engine.py` (`_build_context_message`, task-2+ branch) | engine / sequencer | transform (prompt compaction) | `_extract_html_skeleton` :2616-2679 (same file) + `_slim_revision_message` :2586-2603 | exact (in-file helper to wire) |
| `backend/tests/agents/test_phase3_*.py` — ≥50% gate test (D-02) | test | transform-assertion | `test_characterization_prototype.py` + `_scripted_model._drive`/`_build_context_message` | role-match |
| `backend/tests/agents/test_phase3_*.py` — pages/routes + validation parity (D-03/Req6) | test | transform-assertion | `test_characterization_prototype.py` :37-42 | role-match |
| `backend/tests/agents/characterization/golden/prototype.html` + `od_prototype.html` | golden fixture | file-I/O (snapshot) | existing goldens + `SNAPSHOT_UPDATE=1` mechanism | exact |
| `backend/tests/agents/test_phase3_token_delta_live.py` — opt-in live delta (D-04) | test (live, opt-in) | request-response (real model) | `test_deep_agent_runner_hitl_live.py` :1-75 | exact (gating pattern) |

---

## Pattern Assignments

### `backend/agents/execution_engine/engine.py` — `_build_context_message` task-2+ edit (Req 1, COMPACT-01/L13)

**Analog (the helper to wire):** `_extract_html_skeleton` at `engine.py:2616-2679`. It is a `self`-method on `ExecutionEngine`, takes `html: str`, returns a `"\n".join(lines)` string. Output markers it emits (all must be asserted present by the gate test):
- `":root tokens (current):"` (line 2642)
- `"Routes map:"` (line 2648)
- `"Pages already built (N): ..."` (line 2666)
- `"Pages still empty (N): ..."` (line 2668)
- `"Chrome: <type> (copy chrome from any filled page — do NOT rewrite it)"` (line 2674)
- `"Total HTML so far: N chars across M sections"` (line 2677)

**The exact block to REPLACE** (`engine.py:2526-2536`, inside `if spec.id == "prototype-build":`):
```python
            # Pass current HTML for modification
            current_html = accumulated_outputs.get("prototype-build", "")
            if current_html and not current_html.startswith("[Error:"):
                html_to_pass = current_html[:120000]
                truncated = len(current_html) > 120000
                parts.append(
                    f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n"
                    f"{html_to_pass}"
                    f"{'...[truncated at 120k]' if truncated else ''}\n"
                    f"--- END CURRENT HTML ---"
                )
```

**The branch flag (already computed, ride it — no new state):** `engine.py:2428`
```python
is_build_task_2_plus = (spec.id == "prototype-build" and task_num_str not in ("", "1"))
```

**Target shape** — keep the empty/`[Error:` guard (D-01 edge case / engine.py:2528); on `is_build_task_2_plus` emit the skeleton block with a distinct marker + a `read_file('prototype.html')` pointer (D-01); on task 1 keep the full-HTML block unchanged:
```python
            current_html = accumulated_outputs.get("prototype-build", "")
            if current_html and not current_html.startswith("[Error:"):
                if is_build_task_2_plus:
                    skeleton = self._extract_html_skeleton(current_html)
                    parts.append(
                        f"\n=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') "
                        f"for full content before editing) ===\n"
                        f"{skeleton}\n"
                        f"=== END CURRENT PROTOTYPE ==="
                    )
                else:
                    html_to_pass = current_html[:120000]
                    truncated = len(current_html) > 120000
                    parts.append(
                        f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n"
                        f"{html_to_pass}"
                        f"{'...[truncated at 120k]' if truncated else ''}\n"
                        f"--- END CURRENT HTML ---"
                    )
```

**Conventions to replicate:**
- `self._extract_html_skeleton(...)` — it is an instance method; call it on `self`. Do NOT change its extraction logic (D-66 discretion: leave as-is unless pages/routes parity surfaces a gap).
- Marker wording/casing is Claude's discretion (D-01) but MUST be visually distinct from `--- CURRENT HTML ---` AND carry the `read_file('prototype.html')` pointer.
- Keep the `=== TEMPLATE COMPLIANCE ===` block (engine.py:2542-2547) for task-2+ (D-67 — keep, low token cost). Do NOT touch it.
- No `AGENT.md` edit (Req 7 already satisfied by `prototype-build/AGENT.md` lines 40/78).
- Commit scope: `engine` (per backend/CLAUDE.md).
- L13 stays `☐`: only *call* the helper; do NOT delete it, do NOT add a vulture allow-list entry.

---

### `backend/tests/agents/test_phase3_*.py` — ≥50% deterministic gate (Req 2, D-02)

**Analog imports/offline-drive** from `test_characterization_prototype.py:15-33` + `_scripted_model.py`:
```python
from __future__ import annotations
import pytest
from tests.agents._scripted_model import _drive
from tests.agents.characterization import golden_path
```

**Two viable constructions (D-02 allows either; the planner picks):**

1. **Direct `_build_context_message` call** — exercises the real injection site (faithful to Req 2 wording). Construct an `ExecutionEngine()`, a `prototype-build` spec, an `ectx` with `current_task_block`, and an `accumulated_outputs` dict with the page-rich golden HTML as `"prototype-build"` and `"_build_task_number": "2"` (the task-2 trigger — see `engine.py:2427-2428`). Call the method twice (once monkeypatched to force the old full-HTML path, once with the skeleton path) and compare lengths.

2. **Fixture = the `prototype.html` golden** (D-02a) — but note the *committed* golden is tiny (84 bytes, from the scripted 2-task build). For a meaningful ≥50% ratio on a "≥2-page HTML", the test must supply a representative multi-page HTML literal/fixture (the scripted golden is too small to be a realistic input-token proxy). Build a multi-`<section data-page>` HTML string inline.

**Assertion shape (Req 2 acceptance):**
```python
assert len(compacted_task2_message) <= 0.5 * len(fullhtml_task2_message)
```
where `fullhtml_task2_message` is the size the old path would inject (full HTML capped at 120k — replicate the `[:120000]` cap from engine.py:2529).

**Marker-presence + absence assertions (Req 1 acceptance):**
```python
assert "=== CURRENT PROTOTYPE (skeleton" in compacted   # or chosen marker
assert "--- CURRENT HTML (modify this" not in compacted  # full block absent task-2+
for marker in (":root tokens", "Pages already built", "Pages still empty",
               "Chrome:", "Total HTML so far"):
    assert marker in compacted
```

**Conventions:** offline only (no DB/Bedrock/API key) — `_scripted_model.py` already sets `RUNS_ROOT`→temp + `ENV=development` at import (lines 53-57). `@pytest.mark.asyncio` only if using `_drive`; a direct `_build_context_message` call needs no async. Test placement is Claude's discretion (D-64): new `tests/agents/test_phase3_*.py` or extend a characterization module. Commit scope `tests`.

---

### `backend/tests/agents/test_phase3_*.py` — pages/routes + validation parity (Req 6, D-03)

**Analog:** `test_characterization_prototype.py:37-42` (offline drive + final-output extraction):
```python
@pytest.mark.asyncio
async def test_prototype_deliverable_byte_snapshot() -> None:
    events = await _drive("prototype")
    assert events, "prototype produced no events"
    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("prototype.html", deliverable)
```

**Pattern to replicate:** derive the `data-page` ID set and `routes` map keys from the produced deliverable and assert they equal the pre-0C set; assert validation-pass event outcome/count is equal-or-better (zero net-new failures). Reuse the same regexes `_extract_html_skeleton` uses (engine.py:2645 `const routes\s*=\s*\{...\}`; engine.py:2652 `<section[^>]+data-page=["']([^"']+)["']`) so the assertion and the helper agree on what a "page" / "route" is.

**Conventions:** drive via `_drive("prototype")` and `_drive("od_prototype")` (alias → same path, covered automatically — `_scripted_model.py:354`). `extract_final_output(events)` (characterization/__init__.py:60) pulls the deliverable off the `pipeline_complete.final_output` event — more stable than reading disk. Commit scope `tests`.

---

### `golden/prototype.html` + `golden/od_prototype.html` — deliverable re-baseline (Req 5, D-03)

**Mechanism:** `SNAPSHOT_UPDATE=1` (characterization/__init__.py:31-34, 93-95). Under the env var, `assert_deliverable_snapshot` WRITES the golden instead of asserting; the non-empty guard still fires first (line 88).

**Re-baseline recipe (backend/CLAUDE.md):**
```bash
cd backend
SNAPSHOT_UPDATE=1 python3.11 -m pytest \
  tests/agents/test_characterization_prototype.py \
  tests/agents/test_characterization_od_prototype.py -v
# then review + commit ONLY the two changed goldens
git diff --name-only tests/agents/characterization/golden/
```

**Constraint (Req 5 acceptance):** `git diff` must touch EXACTLY `golden/prototype.html` + `golden/od_prototype.html`. The `*.events.json` semantic goldens must NOT change (Req 4 — `test_prototype_event_snapshot` / `test_od_prototype_event_snapshot` pass with no golden edit). `prototype_revision.html`, `od_ppt.html`, `app_builder.txt` byte-goldens stay identical.

**Caveat for the planner:** the scripted build (`_scripted_model.py:269-281`) writes a fixed single-section HTML, so the scripted deliverable bytes may be IDENTICAL before/after the skeleton swap (the scripted model ignores prompt content). If so, the re-baseline is a no-op diff — document that in SUMMARY; the *real* byte change is proven by the live delta (D-04), not the scripted golden. Confirm empirically during execution.

---

### `backend/tests/agents/test_phase3_token_delta_live.py` — opt-in live delta (Req 3, D-04)

**Analog:** `test_deep_agent_runner_hitl_live.py:1-75` — copy the opt-in/SSO gating verbatim.

**Gating pattern to replicate:**
```python
import os, pytest
# module constant for the opt-in env var
_RUN_LIVE_HINT = (
    "LIVE token-delta evidence is opt-in. To run it:\n"
    "    aws sso login --profile personal-sso\n"
    "    RUN_LIVE_BEDROCK=1 AWS_PROFILE=personal-sso "
    "python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py -v -s"
)
def _aws_creds_resolve() -> tuple[bool, str]: ...   # STS probe, copy from analog
# skip unless RUN_LIVE_BEDROCK=1 AND creds resolve
```

**Conventions to replicate:**
- Two gates BOTH required: `os.environ.get("RUN_LIVE_BEDROCK") == "1"` AND `_aws_creds_resolve()` true (analog lines 18-21, 67-75). Otherwise `pytest.skip(_RUN_LIVE_HINT)`.
- Run the multi-task build (with vs without compaction) against a real model; log accumulated `input_tokens` totals (sourced from `usage` events — backend/CLAUDE.md data-flow, `usage_metadata` in `_scripted_model.py:131-135`).
- Evidence-only, NEVER a CI gate (the CI gate is the D-02 test). Copy the measured delta + reproduction command into `03-*-SUMMARY.md` as COMPACT-03 evidence (Req 3 acceptance). Fallback: documented manual-run procedure in SUMMARY if no live run available.
- Commit scope `tests`.

---

## Shared Patterns

### Offline determinism (apply to ALL gating tests)
**Source:** `_scripted_model.py:53-57` (RUNS_ROOT temp + ENV=development at import) + `_drive` (lines 325-453).
All Req-2/Req-4/Req-6 tests run with no DB/Bedrock/API key. Import `from tests.agents._scripted_model import _drive` and let module import set the env. The scripted `prototype-plan` emits exactly 2 tasks (`_scripted_model.py:198-209`) → the task-2 build is exercised automatically.

### od_prototype = alias of prototype (one edit covers both)
**Source:** `_scripted_model.py:354` `_OD_ALIAS_FOR_LOOKUP = {"od_prototype": "prototype", ...}` and `registry._OD_ALIAS_BASE`.
Drive both with `_drive("prototype")` and `_drive("od_prototype")`; the single `is_build_task_2_plus` edit applies to both. Re-baseline both goldens.

### Snapshot split (held vs re-baselined)
**Source:** characterization/__init__.py (deliverable byte snapshot) + `_normalize.py` (semantic event snapshot, imported in `test_characterization_prototype.py:25-33`).
- Semantic event snapshot (`*.events.json`) → HELD GREEN, no edit (Req 4).
- Deliverable byte snapshot (`*.html`) → re-baselined for prototype/od_prototype ONLY (Req 5). 0C is the one phase allowed to move deliverable bytes (INV-3 exception).

### Edge-case guard (keep current behavior)
**Source:** `engine.py:2528` `if current_html and not current_html.startswith("[Error:")`.
On empty / `[Error:`-prefixed HTML, emit NO skeleton block and NO full HTML (D-65) — exactly as the current guard skips the block.

---

## No Analog Found

None. Every file has a strong in-repo analog (the helper is already written; the test harness, gating, and snapshot mechanisms all exist).

## Metadata

**Analog search scope:** `backend/agents/execution_engine/engine.py`, `backend/tests/agents/`, `backend/tests/agents/characterization/`
**Files scanned:** engine.py (target sections), `_scripted_model.py`, `characterization/__init__.py`, `test_characterization_prototype.py`, `test_characterization_od_prototype.py`, `test_deep_agent_runner_hitl_live.py`, `golden/` listing, `backend/CLAUDE.md`
**Pattern extraction date:** 2026-06-07
