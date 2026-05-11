# Static analysis and linting

This document describes the static-analysis tooling that runs on the Flowin
codebase. Two classes of bug motivated this setup:

1. **Backend: a lazy import to a deleted module survived a merge.**
   `backend/app/api/websocket.py:480` does
   `from app.agents.pipeline import PipelineExecutor`, but `pipeline.py` was
   removed and only `ppt_pipeline.py` remains. Because the import is inside
   a function it is *lazy* — it doesn't fail at module load, only when the
   websocket pipeline handler is exercised in production.

2. **Frontend: hardcoded `http://localhost:8000` URLs in `fetch()` calls.**
   `frontend/src/components/preview/PPTPreview.tsx` and
   `frontend/src/components/results/FilesTab.tsx` both call `fetch()` with
   a literal localhost URL instead of `ENV.API_URL` from
   `frontend/src/lib/env.ts`. These break every deployed environment.

The tools below catch both classes of bug before they reach review.

## Pinned tool versions

All versions are pinned exactly. Bump deliberately, never with a range.

| Tool        | Version  | Source                                     |
|-------------|----------|--------------------------------------------|
| ruff        | 0.8.4    | `backend/requirements-dev.txt`             |
| pyright     | 1.1.391  | `backend/requirements-dev.txt`             |
| pre-commit  | 4.0.1    | `backend/requirements-dev.txt`             |
| eslint      | 9.39.4   | `frontend/package.json` (already present)  |
| eslint-config-next | 16.2.4 | `frontend/package.json` (already present) |

## Backend: ruff + pyright

Ruff is configured in `backend/pyproject.toml`. It enforces correctness
rules from Pyflakes (`F*`), pycodestyle (`E*`/`W*`), bugbear (`B*`), and
the Pylint *error* subset (`PLE*`). Cosmetic and formatter-style rules are
deliberately disabled: this is a live codebase and we did not want a
cascade of style fixes obscuring real bugs.

**Ruff has one limitation that matters for us: it does not do module
resolution.** Pyflakes only sees symbols within a single file. It cannot
tell that `from app.agents.pipeline import X` references a module that
doesn't exist. That's what `pyright` is for.

Pyright is configured in `backend/pyrightconfig.json`. We run it in the
most permissive mode possible — `typeCheckingMode: "off"` — with **only**
`reportMissingImports` set to `error`. This gives us a pure import-resolution
check without adopting full type-checking on an untyped codebase (which is
a separate, larger project).

### Install backend dev deps

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # runtime deps (so pyright resolves them)
pip install -r requirements-dev.txt      # ruff + pyright + pre-commit
```

### Run backend lints manually

```bash
cd backend
ruff check .            # all-files ruff
ruff check app/api/websocket.py   # single file
pyright                 # all-files pyright (reads pyrightconfig.json)
pyright app/api/websocket.py      # single file
```

**Important.** Run `pip install -r requirements.txt` before pyright.
Without the runtime deps installed pyright will (correctly) flag
`fastapi`, `sqlalchemy`, etc. as unresolved. That is not a bug in the
config — the same check would fail in CI without dependency installation.

We never run `ruff --fix` from automation. Auto-modifying code in a hook
is unsafe; the developer must decide.

## Frontend: ESLint

The frontend uses ESLint 9 flat config (`frontend/eslint.config.mjs`),
extending `eslint-config-next`. We **extend** that config with a single
custom rule: `no-restricted-syntax` banning hardcoded `http://localhost`
and `http://127.0.0.1` URLs inside `fetch(...)` and `axios.*(...)`
call expressions.

The selector is narrow on purpose. `env.ts` and `api.ts` legitimately
mention `http://localhost:8000` as a development fallback — that's the
single source of truth the rest of the codebase should read from. Banning
the literal globally would catch those.

### Run frontend lints manually

```bash
cd frontend
npm install             # if you haven't already
npm run lint            # full eslint, same as CI
npx eslint src/components/preview/PPTPreview.tsx   # single file
```

## Pre-commit hooks

Hooks are defined in `.pre-commit-config.yaml` at the repo root. They run
on `git commit` and re-run in CI. They do not replace CI — they catch
obvious regressions early.

### Install pre-commit locally (once per clone)

```bash
pip install pre-commit==4.0.1
pre-commit install
```

After that, every commit fires:

- **ruff** on changed `backend/**.py` files (from the official
  `astral-sh/ruff-pre-commit` mirror, pinned to `v0.8.4`).
- **pyright** on changed `backend/**.py` files (using the locally-installed
  pyright so it sees your installed deps).
- **eslint** on the whole `frontend/src` tree if any frontend file
  changed (using the project's `npm` install — not a separate eslint).

To run everything against all files (e.g. as a sanity check):

```bash
pre-commit run --all-files
```

To skip the hooks for a single commit when you know you're in the middle
of something half-done:

```bash
git commit --no-verify
```

Don't make that a habit. The hooks exist to catch real bugs.

## Known violations on first run

Adding ruff and the new ESLint rule to a live codebase surfaces a backlog
of pre-existing violations. They are documented here so reviewers don't
panic when CI lights up red after this change lands.

**Backend ruff:** 24 errors (full breakdown via `ruff check . --statistics`):

```
10  E701  multiple-statements-on-one-line-colon
 6  F401  unused-import
 3  E402  module-import-not-at-top-of-file
 3  F841  unused-variable
 1  W291  trailing-whitespace
 1  W293  blank-line-with-whitespace
```

None of them are the deleted-module bug — that one needs pyright.

**Backend pyright:** the deleted-module import at
`app/api/websocket.py:480` is the canonical violation. Other pyright
errors will appear if you haven't installed `requirements.txt`.

**Frontend ESLint:** 67 problems (20 errors, 47 warnings). Of those, 4
errors come from the new `no-restricted-syntax` rule and are the
motivating bug:

- `src/components/preview/PPTPreview.tsx:38, 52`
- `src/components/results/FilesTab.tsx:145, 159`

The remaining 16 errors and 47 warnings pre-date this change and are out
of scope here.
