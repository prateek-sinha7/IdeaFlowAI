# Research — free-tier providers for eval runs

Moved here from `.investigations/free-models/` on 2026-07-29, so the research that chose this
spec's grading provider sits with the spec rather than in a separate investigation folder.

Three documents, written in this order — each derives from the one before:

| Document | Question it answers |
|---|---|
| [`providers.md`](providers.md) | Which providers offer free-tier inference at ≥1,000 req/day? |
| [`model_comparison.md`](model_comparison.md) | How do their models compare to `claude-haiku-4-5` (no thinking)? |
| [`candidate.md`](candidate.md) | Which ones do we actually integrate, and in what order? |

## What came of it

**Mistral won and is in production for grading.** `mistral-small-latest` is the agent under test
and `mistral-large-latest` the judge in all four shipped run configs, because it was the closest
weight-class match to Haiku 4.5 among the free providers surveyed here — see
`backend/app/core/config.py` (`MISTRAL_MODEL_ID`).

**Groq was integrated, then withdrawn.** These documents recommend Groq alongside Mistral, and
that recommendation was acted on under spec [`004`](../../004-mistral-eval-provider/spec.md). It
did not work out: on 2026-07-29 `langchain-groq`, the `GROQ_API_KEY`/`GROQ_MODEL_ID` settings,
the `provider="groq"` branch and its fallback tier were all removed. Spec 004 was retargeted onto
Mistral — the other recommendation from this research, and the one that did work out.

## Reading these safely

- **The Groq recommendations are historical.** They record what was true when the survey was
  written; they are not current guidance. Do not re-integrate from them without redoing the
  comparison.
- **Free-tier rosters and rate limits rotate.** Every figure here has a "verify at the console"
  caveat in its own document. Treat the numbers as of the date each was written.
- **`build_model` today honours exactly one explicit provider: `mistral`.** `anthropic` and
  `bedrock` fall through the implicit chain. Anything in these documents implying a wider
  provider surface is out of date.
- Some path references are pre-move (`backend/tests/evals/`); the hybrid suite now lives at
  `backend/evals/hybrid/`.
