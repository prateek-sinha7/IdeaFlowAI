# Implementation Plan: Applying Advisor Prompt Edits

**Spec**: [`specs/007-prompt-versioning/spec.md`](spec.md)
**Created**: 2026-07-30
**Status**: Planned

---

## Technical Context

- **Runtime**: Python 3.11 (`backend/pyrightconfig.json`), stdlib only for the new module.
- **Framework**: none involved — this is a CLI feature in `backend/evals/grading/`, not a
  FastAPI surface.
- **Database**: none. Prompts are files and stay files.
- **Deployment**: developer machine. Nothing ships to a server; nothing runs in CI beyond the
  new offline unit tests.
- **Model**: no model call in the `apply-advice` / `revert` path. Zero tokens.

## Architecture Decisions

### AD-01 — No runtime code is touched

`loader.load_agent_spec` opens `agent_dir / "AGENT.md"` by literal name (`loader.py:144`), and
`loader.list_agent_ids` — the scan that builds `PIPELINE_AGENTS` at import time
(`registry.py:57-79`) — matches the same literal name (`loader.py:201`). `AGENT.vN.md` files are
therefore invisible to the engine, kernel, registry, resolver and manifests.

**Consequence for delivery**: the diff for this feature must not contain a single file under
`backend/agents/` or `backend/app/`. That is a reviewable, mechanical property, and it is the
whole backward-compatibility argument (spec §3).

### AD-02 — Persist the advisor's structured output *(new work the spec assumed existed)*

`prompt_advisor.advise_run` builds a typed `PromptAdvice` (pydantic, `prompt_advisor.py:60-68`)
and then **discards it** — `_render_advice` turns it into markdown and only
`reports/prompt_advice_<token>.md` is written (`prompt_advisor.py:158-160`). There is no
structured artifact on disk.

`apply-advice` needs the structure — `current_text` must be matched verbatim, and re-parsing it
out of rendered markdown fenced blocks would be exactly the fuzzy behaviour R-06 forbids.

**Decision**: add a JSON sidecar `reports/prompt_advice_<token>.json` written from the same
`PromptAdvice` object, next to the existing markdown. Additive, ~4 lines, no behaviour change to
the advisor. The markdown stays the human artifact; the JSON is what `apply-advice` reads.

**Back-compat**: run folders graded before this exists have only the `.md`. `apply-advice`
against one of those fails with exit 2 and names the fix — `grade.sh advise <run-id>`, which
re-advises an existing run without re-dispatching any agent (one judge-model call per stage).

### AD-03 — Split frontmatter by hand; never round-trip the YAML

R-03 requires frontmatter preserved byte-for-byte. `python-frontmatter` (already a dependency —
`loader.py` uses it) can parse, but `frontmatter.dumps()` re-serialises the YAML and will
reorder keys, restyle quotes and drop comments. That would silently rewrite the engine's
contract while claiming to have edited only the body.

**Decision**: treat `AGENT.md` as text. Split once on the closing `---` delimiter, keep the
prefix (frontmatter block + delimiter) as an opaque string, edit only the suffix, and
concatenate. `frontmatter` is used at most to *validate* that the prefix still parses after the
write — never to produce it.

### AD-04 — Insertion semantics for `action: add`

`PromptEdit.current_text` is empty for `add` (`prompt_advisor.py:49-51`), so an add carries no
anchor except `section` ("heading or anchor text"). An undefined insertion point is the most
likely source of a silently misplaced edit, so it is pinned here:

1. If `section` matches **exactly one** markdown heading line (`#`…`######`, compared on the
   heading text, trimmed), insert `proposed_text` as a new paragraph immediately after that
   heading's existing content block.
2. Else, if `section` occurs **exactly once** as a literal substring of the body, insert
   immediately after the paragraph containing it.
3. Else — no match, or more than one — **fail the whole command** (exit 9). No appending to the
   end of the file as a fallback: an edit in the wrong place is worse than no edit.

### AD-05 — All-or-nothing writes

R-06 says a failed edit writes nothing. Implementation: compute the fully-edited body in memory
across every edit first; only if all succeed do we (a) write the archive, then (b) write
`AGENT.md`. Archive first so that a crash between the two leaves the old body recoverable.

### AD-06 — Pure module, thin CLI

`prompt_edits.py` is pure: text in, text out, no I/O and no imports from the grading package —
matching the four existing pure modules in the grading design (`stage_input`, `scoring`,
`compare`, `precheck`; spec 005 §3). File reading/writing lives in the `grade_runner` command
functions. This is what makes the risky logic (anchor matching, frontmatter splitting) testable
in milliseconds with no fixtures.

## Delivery Strategy

Four phases, each independently verifiable. Phases 1–2 are the feature; 3 is the safety net; 4
is documentation.

| Phase | Delivers | Verified by |
|---|---|---|
| **P0 — Advice persistence** | JSON sidecar from `PromptAdvice` (AD-02) | Unit test: advise → `.json` exists and round-trips to an equal model |
| **P1 — Pure edit engine** | `prompt_edits.py`: frontmatter split, apply add/remove/modify, archive numbering, revert | Offline unit tests, incl. every failure mode in R-04/R-06 and AD-04 |
| **P2 — CLI** | `apply-advice` + `revert` in `grade_runner.py` and `grade.sh`, diff printing, exit codes | CLI tests against a temp agent folder |
| **P3 — Runtime-invisibility guard** | Test asserting `PIPELINE_AGENTS` and agent count unchanged with `AGENT.vN.md` present (R-10) | pytest |
| **P4 — Docs** | `docs/README.md` runbook entry; advisor's markdown footer points at the new command instead of "after editing the AGENT.md" | Read |

**Sequencing note**: P1 has no dependency on P0 and can be built and tested first against
hand-written `PromptAdvice` fixtures. P2 needs both.

## File Changes

| File | Action | Purpose |
|---|---|---|
| `backend/evals/grading/model/prompt_edits.py` | **new** | Pure: split/apply/archive/revert (AD-03, AD-04, AD-06) |
| `backend/evals/grading/model/prompt_advisor.py` | modify | Write the JSON sidecar (AD-02); update the markdown footer (P4) |
| `backend/evals/grading/artifacts.py` | modify | Path helper for `prompt_advice_<token>.json` — artifacts.py is the sole owner of run-folder paths (spec 005 §3) |
| `backend/evals/grading/grade_runner.py` | modify | `apply-advice` / `revert` subcommands, arg parsing, diff output, exit codes |
| `backend/evals/grading/grade.sh` | modify | Two command arms + help text |
| `backend/evals/grading/docs/README.md` | modify | Runbook |
| `backend/tests/unit/test_grading_prompt_edits.py` | **new** | P1 unit tests |
| `backend/tests/unit/test_grading_apply_advice_cli.py` | **new** | P2 CLI tests |
| `backend/tests/agents/test_loader.py` | modify | R-10 invisibility assertion |

**Not touched, deliberately**: anything under `backend/agents/` (except the test above) or
`backend/app/`. See AD-01.

## Risks & Mitigations

| Risk (spec §8) | Mitigation in this plan |
|---|---|
| An edit lands in the wrong place | AD-04 pins insertion semantics; AD-05 makes writes all-or-nothing; exit 9 on any ambiguity |
| Frontmatter corrupted → registry/DAG break | AD-03 — no YAML round-trip; frontmatter is an opaque string. Post-write validation re-parses it |
| Archive files confuse the runtime | AD-01 by construction; P3 asserts it |
| Advisor structure unavailable | AD-02 — new JSON sidecar; clear exit-2 message pointing at `grade.sh advise` for old runs |
| Archives accumulate | Small text files; deferred — a `grade.sh check` warning can be added if it ever matters |
| Score can't yet rank prompts (008) | Out of this plan's control. `apply-advice` costs nothing and reverts in one command, so the loop is safe to use before 008 lands; only the *judgement* waits |

## Open items carried into design

- Archive numbering when a gap exists (`v1`, `v3` present, `v2` deleted by hand): use
  `max(N) + 1`, never fill gaps — decided here, recorded in `data-model.md`.
- Whether `revert` should also restore the advisor footer state: no. Revert restores the prompt
  body only.
