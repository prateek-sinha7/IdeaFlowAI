# Prompts — what's actually running, in one place

## `agents/*.vN.md` — versioned prompts you edit and test HERE

Each prototype agent's prompt lives here as `<agent-id>.v1.md`, `.v2.md`, etc.
`v1` is always a snapshot of whatever's canonical in
`backend/agents/prompts/<id>/AGENT.md` at the time it was copied. To try a
change: copy the latest version to the next number
(`cp prototype-build.v1.md prototype-build.v2.md`), edit the body, then
activate it:

```bash
./activate.sh prototype-build v2      # dispatch prototype-build with v2
./activate.sh status                  # which agents currently have a version active
./activate.sh prototype-build reset   # back to canonical AGENT.md
```

**No code in `evals/minimal/*.py` changes for any of this.** `run.py` and
`judge.py` already build every dispatch under the fixed eval user id
(`eval-minimal`), and `agents.factory._compose_system_prompt` already reads
that user's saved override before falling back to the canonical `AGENT.md`
body (`app/agents/prompt_overrides.py` — the same per-user override store the
product's prompt editor UI writes to, just scoped to a synthetic eval-only
user id so it can never collide with a real user's saved override).
Activating a version writes it there; `eval run`/`eval score --advise` pick it
up on the very next call, with zero eval.sh or run.py changes.

Once a version's report looks good, **you** decide it's stable and manually
copy its body into `backend/agents/prompts/<id>/AGENT.md` — that promotion is
never automatic. Then reset the override (canonical now matches what you just
promoted) and, if you want the mirror's `v1` to reflect the new baseline,
re-copy it:

```bash
./activate.sh prototype-build reset
cp backend/agents/prompts/prototype-build/AGENT.md evals/minimal/prompts/agents/prototype-build.v1.md
```

## `judge_prompt.md` — the real thing, not a copy

Unlike the agent prompts, this one IS live: `judge.py`'s `build_judge_prompt()`
loads and fills this file at call time. Editing it changes the next judge
call — no copy-drift possible, because there's only one copy.

## `advise_prompt.md` — the real advisor prompt

Also live, not a copy: `judge.py`'s `advise()` fills this from the report's
own weakness/strength clustering plus `run.compose_agent_prompt()`'s REAL
current system prompt, and proposes an edit. Opt-in only —
`eval score <run> --stage X --advise` — one extra model call, never run
automatically by `score` or `eval.sh`.

Pool every run's advisor output into `advices.json` with
`python3.11 -m evals.minimal.cli advice [--summary]` — free, no model call.

## The free "Advice" card is separate

The report's own "Advice" card (every stage page, always there) makes **zero
model calls**. It clusters `weaknesses`/`strengths` that `judge.py` already
returned — exact-text grouping, counted and sorted, done entirely in
`report.js`. There's nothing here because there's no prompt to show.
