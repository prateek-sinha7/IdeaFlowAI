# Research Notes: Applying Advisor Prompt Edits

All findings are from reading the current working tree on 2026-07-30, not from memory.

---

## Decision Log

### R-01 — Are `AGENT.vN.md` files really invisible to the runtime?

- **Options**: (a) assume so; (b) verify by reading the load path; (c) add a filter to be safe.
- **Chosen**: (b), verified — no filter needed.
- **Evidence**: `loader.load_agent_spec` builds `agent_file = agent_dir / "AGENT.md"`
  (`loader.py:144`) and errors if absent (`:153`). `loader.list_agent_ids` iterates
  `_PROMPTS_DIR.iterdir()`, skips non-directories, and again tests `agent_dir / "AGENT.md"`
  (`loader.py:201`) — it never globs. `registry._discover_pipeline_agents()` (`registry.py:57-79`)
  is built on `list_agent_ids`, and `PIPELINE_AGENTS` is computed once at import (`registry.py:78`).
- **Consequence**: the 7 zero-byte `AGENT.v2.md` files already sitting in the prototype folders
  have been inert since they were created. Confirmed independently: the string `AGENT.v2` appears
  nowhere in the codebase.

### R-02 — Does the advisor persist anything machine-readable?

- **Options**: (a) read an existing JSON; (b) parse the rendered markdown; (c) add a JSON sidecar.
- **Chosen**: (c).
- **Evidence**: `PromptAdvice` / `PromptEdit` are pydantic models (`prompt_advisor.py:46-68`),
  but `_advise_stage` renders straight to markdown and writes only
  `reports/prompt_advice_<token>.md` (`prompt_advisor.py:158-160`). The parsed object is not
  persisted; nothing else in the package writes advice.
- **Rationale for rejecting (b)**: `_render_advice` (`:321`) writes `current_text` and
  `proposed_text` into fenced code blocks and truncates *other* fields via
  `render.truncate(..., limit=220)`. Round-tripping prose out of rendered markdown is precisely
  the fuzzy behaviour R-06 exists to forbid.
- **Cost of (c)**: ~4 lines. The advisor already holds the object.

### R-03 — How should frontmatter be preserved byte-for-byte?

- **Options**: (a) `frontmatter.loads` + `frontmatter.dumps`; (b) manual text split.
- **Chosen**: (b).
- **Rationale**: `python-frontmatter` is already a dependency and `loader.py` uses `loads` for
  reading, which is fine. But `dumps` re-serialises through PyYAML: key order, quoting style,
  block scalars and comments are all at its discretion. `AGENT.md` frontmatter is the engine's
  contract (`id`, `pipeline_type`, `order`, `produces`, `consumes`, `tools`, `gate`, `injects`,
  `model`), so a cosmetic reserialisation would produce a large, alarming diff on a command that
  claims to have edited only prose — and in the worst case a semantic change.
- **Implementation**: split the raw text once on the closing `---`; keep the prefix opaque.
  Re-parse the written file with `frontmatter.loads` afterwards purely as an assertion.

### R-04 — What does an `add` edit anchor to?

- **Finding**: `PromptEdit.current_text` defaults to `""` and is documented "empty for add"
  (`prompt_advisor.py:49-51`). The only locator is `section`, described as "heading or anchor
  text" (`:48`) — i.e. sometimes a heading, sometimes arbitrary quoted prose.
- **Chosen**: the three-step deterministic rule in `plan.md` AD-04 (unique heading → unique
  substring → fail). Explicitly **no** end-of-file fallback.
- **Rationale**: an `add` that silently lands at the bottom of a 9 KB prompt looks applied,
  changes behaviour unpredictably, and is invisible in a diff review that skims. Failing is
  cheap; the developer re-runs `grade.sh advise` or edits by hand.

### R-05 — Reuse the existing comparison machinery rather than build A/B

- **Chosen**: reuse.
- **Evidence**: rows already carry `system_prompt_hash` (`artifacts.py:115`,
  `model_grader.py:795`); `compare.compare_runs` diffs runs with a noise guard
  (`compare.py:41`, `noise_band` `:93`, `SIGMA_MULTIPLIER = 2.0`); `compare.group_by_prompt`
  (`:61`) groups runs by prompt for `grade.sh history`.
- **Consequence**: this spec adds no measurement code at all.

### R-06 — Where do the new commands live?

- **Chosen**: extend `grade.sh` / `grade_runner.py`.
- **Rationale**: consistent with the existing verb set (`run`, `report`, `compare`, `history`,
  `rejudge`, `advise`, `code`) and with the standing project instruction to extend the main
  pipeline rather than build sibling implementations. `artifacts.py` remains the sole owner of
  run-folder paths, so the JSON sidecar path is added there rather than composed inline.

---

## Unknowns

- **Advisor edit quality is unmeasured.** No live graded run has exercised `prompt_advisor` end
  to end in this working tree, so the real-world hit rate of `current_text` matching verbatim is
  unknown. If it turns out to be poor, R-06's strict matching will surface it immediately as
  loud failures rather than silent misplacement — which is the intended failure direction, but
  may mean the first few runs need hand-editing.
- **Multi-stage advice.** `advise_run` advises several stages in one run. `apply-advice` as
  specified takes a single `--agent`. Whether applying to all advised agents at once is wanted is
  not yet known; deferred rather than guessed.
- **Interaction with `grade.sh rejudge`/`--from-run --replace`.** The advisor's own footer
  suggests re-grading a single stage from a prior run. Whether `apply-advice` should print that
  exact follow-up command (with the run id filled in) is a small UX call left to design.

## References

- `backend/evals/grading/model/prompt_advisor.py` — `PromptEdit` schema (`:46`), rendering
  (`:321`), persistence (`:158`)
- `backend/agents/loader.py` — `load_agent_spec` (`:129`), `list_agent_ids` (`:182`),
  `_SPEC_CACHE` (`:121`)
- `backend/agents/registry.py` — `_discover_pipeline_agents` (`:57`), `PIPELINE_AGENTS` (`:78`)
- `backend/evals/grading/artifacts.py` — path ownership, `compute_system_prompt_hash` (`:115`)
- `backend/evals/grading/compare.py` — `compare_runs` (`:41`), `noise_band` (`:93`),
  `group_by_prompt` (`:61`)
- [`specs/005-prompt-eval-scoring/spec.md`](../005-prompt-eval-scoring/spec.md) — the grading
  system's design and its "pure module" convention
- [`specs/008-grading-calibration/spec.md`](../008-grading-calibration/spec.md) — why the score
  is not yet trustworthy for judging an applied edit
- `backend/CLAUDE.md` — AGENT.md schema table and the agent-authoring workflow
