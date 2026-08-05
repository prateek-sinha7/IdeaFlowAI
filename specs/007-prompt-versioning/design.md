# Execution Design: Applying Advisor Prompt Edits

**Spec**: [`specs/007-prompt-versioning/spec.md`](spec.md)
**Plan**: [`specs/007-prompt-versioning/plan.md`](plan.md)
**Created**: 2026-07-30
**Status**: Designed

---

## Build Slices

### Slice 1 — Foundation: persist the advisor's structure

The advisor currently renders `PromptAdvice` to markdown and discards the object
(`prompt_advisor.py:158-160`). Nothing downstream can read the edits.

Write `reports/prompt_advice_<token>.json` from the same object, with the path owned by
`artifacts.py` (sole owner of run-folder paths). The markdown stays exactly as it is — it is the
human artifact; the JSON is the machine one.

**Done when**: an advised run folder contains both files, and the JSON round-trips back into an
equal `PromptAdvice`.

### Slice 2 — Core logic: the pure edit engine

`model/prompt_edits.py`, pure — text in, text out, no filesystem, no imports from the grading
package. This is where every decision that can silently corrupt a prompt lives, so it is the
part that must be testable without fixtures.

Five functions:

| Function | Contract |
|---|---|
| `split_agent_file(text) -> (prefix, body)` | Splits once on the closing `---`. `prefix` includes the delimiter and is opaque. Raises when there is no terminated frontmatter block — never assumes the whole file is body |
| `apply_edits(body, edits) -> (new_body, refused)` | Applies every edit or raises. Returns refused frontmatter-targeting edits separately (they are skipped, not fatal) |
| `next_archive_number(names) -> int` | `max(N) + 1`; gaps never filled, numbers never reused |
| `render_diff(edits, refused) -> str` | The per-edit output block |
| `validate_result(prefix, new_body)` | Body non-empty; frontmatter still parses |

**Done when**: every rule in `data-model.md` §Validation Rules has a passing test, including
each failure mode.

### Slice 3 — Interface: two commands

`grade_runner.py` gains `apply-advice` and `revert`; `grade.sh` gains two case arms and help
text. These functions own all I/O — read the JSON, read `AGENT.md`, call the pure module, write
in the fixed order.

**Done when**: `quickstart.md` V1–V4, V7, V9 pass against a temp agent folder.

### Slice 4 — Verification and hardening

The R-10 tripwire (archives stay invisible to the registry), the post-write frontmatter
assertion, and the docs. The tripwire is the single most valuable test in this feature: it
guards the property the whole backward-compatibility argument rests on.

**Done when**: V5, V6, V8 pass and `docs/README.md` documents both verbs.

---

## Component Boundaries

```
grade.sh
   └── grade_runner.run_apply_advice / run_revert        ← ALL I/O lives here
          ├── artifacts.advice_json_path(run_dir, token)  ← path ownership
          ├── prompt_edits.split_agent_file()             ← pure
          ├── prompt_edits.apply_edits()                  ← pure
          ├── prompt_edits.next_archive_number()          ← pure
          └── prompt_edits.render_diff()                  ← pure

prompt_advisor._advise_stage
   └── artifacts.write_advice_json()                      ← new, Slice 1
```

**The boundary that matters**: `prompt_edits.py` must not import `pathlib` operations, the
grading package, or anything from `agents.*`. It receives strings and filenames-as-strings and
returns strings. Matching the four existing pure modules in the grading package
(`stage_input`, `scoring`, `compare`, `precheck` — 005 §3), whose purity is asserted by an
existing dependency-graph test.

**Not touched**: everything under `backend/agents/` and `backend/app/`. The only permitted edit
outside `evals/grading/` is one test file.

---

## State Transitions / Flows

### `apply-advice` — happy path

```
AGENT.md  (frontmatter F, body B0)
advice JSON (edits E)

  1. read      → F, B0
  2. compute   → B1 = apply(B0, E)      [in memory; any failure aborts here, nothing written]
  3. validate  → B1 non-empty
  4. write     → AGENT.v<N+1>.md = B0   [archive FIRST]
  5. write     → AGENT.md = F + B1
  6. assert    → re-read: prefix bytes == F, and F still parses
  7. print     → diff + revert command
```

Step 4 precedes step 5 so that an interruption between them leaves the previous body on disk
rather than lost. The reverse order has a window in which both copies of the old body are gone.

### `revert`

```
  1. find      → highest AGENT.vN.md          (none → exit 2)
  2. read      → AGENT.md → F, B_current      (F preserved)
  3. write     → AGENT.md = F + archive body
  4. delete    → AGENT.vN.md
```

Repeated reverts walk back through history. The current body is **not** re-archived on revert —
revert is an undo, not another edit; re-archiving would make the archive list grow while
walking backwards through it.

### Edit application, per edit

```
modify  → find current_text; exactly 1 occurrence? replace : FAIL(9)
remove  → find current_text; exactly 1 occurrence? delete  : FAIL(9)
add     → anchor = section
             unique heading match?     → insert after that heading's block
             else unique substring?    → insert after containing paragraph
             else                      → FAIL(9)
any     → section names a frontmatter field? → REFUSE(10), skip, continue
unknown action → FAIL(9)                      ← loud, never silently dropped
```

---

## Failure Modes

| # | Failure | Detection | Behaviour |
|---|---|---|---|
| F1 | `current_text` absent | Occurrence count 0 | Exit 9; name edit index + action + section; **nothing written** |
| F2 | `current_text` ambiguous | Occurrence count ≥2 | Exit 9, reporting the count |
| F3 | `add` anchor unresolvable | No unique heading and no unique substring | Exit 9. **No end-of-file fallback** — a misplaced add looks applied and is invisible on a skimmed diff |
| F4 | Edit targets frontmatter | `section` matches a known contract field | Exit 10 for that edit; skipped; others still apply |
| F5 | Unknown `action` value | Not in {add, remove, modify} | Exit 9 — a schema extension must fail loudly, not drop an edit |
| F6 | No frontmatter delimiter in `AGENT.md` | Split finds no closing `---` | Raise; never treat the whole file as body |
| F7 | Advice JSON missing (pre-sidecar run) | File absent, markdown present | Exit 2 naming `grade.sh advise <run-id>` as the fix |
| F8 | Resulting body empty | Post-apply check | Abort — `loader.py` rejects an empty body at load time, so this would break the agent |
| F9 | Frontmatter changed after write | Post-write byte comparison | Loud failure; the archive still holds the old body |
| F10 | Interruption between archive and `AGENT.md` write | — | Old body survives in the archive; re-running is safe |
| F11 | Archive number collision | `next_archive_number` uses `max+1` | Cannot occur; asserted by test |

**The failure philosophy**, worth stating because it drives F1–F5: this command edits the file
that determines how every agent behaves. A loud failure costs one re-run. A silent
mis-application costs a debugging session and, if it reaches a graded run, a wrong conclusion
about a prompt. Every ambiguity therefore fails.

---

## Observability Hooks

Modest by design — these are synchronous developer commands, not a service.

- **stdout is the observability surface**: per-edit lines (index, action, section, ± text),
  the archive path written, an explicit "frontmatter unchanged (N fields)" confirmation, and
  the exact `revert` command.
- **The frontmatter confirmation is not decoration.** It is the visible proof of the property
  the design depends on, printed on every run so a regression is noticed without reading a diff.
- **Exit codes carry the failure class** (0 / 2 / 9 / 10) so the commands compose in a script.
- **No new logging config, no metrics, no events.** The grading package's existing `on_event`
  progress mechanism is for long-running graded runs; these commands finish in milliseconds.

---

## Rollback Notes

**Per invocation** — `grade.sh revert <agent>` restores the last archive. `git checkout` on the
`AGENT.md` path discards everything regardless of archive state.

**Feature-level** — delete `prompt_edits.py`, the two `grade.sh` arms, the two `grade_runner`
functions and the `artifacts` path helper. The JSON sidecar can stay (harmless, additive) or go.

**Nothing else to unwind**: no migration, no config, no runtime file, no persisted state beyond
plain text files that only `revert` reads. This is the practical payoff of the zero-runtime-change
decision — the rollback story is "delete the code."

**Archives left behind** after a rollback are inert text files; the loader has never seen them.
