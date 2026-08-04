# evals/claude

Working notes for the Claude-driven eval loop — the operating instructions and
findings that came out of running `evals/minimal`, not part of the harness.

Nothing here is imported, executed, or read by any code. Deleting this folder
does not affect a single eval run.

| file | what it is |
|---|---|
| `JUDGE.md` | how to judge a run with an Opus sub-agent panel — severity pricing, K=3 median, spread |
| `OPUS_JUDGE.md` | the panel prompt itself |
| `ADVISE.md` | the prompt-improvement loop: propose, apply, re-run, keep or revert |
| `APPLIED.md` | harness defects found while running the loop, and which were fixed |
| `RESEARCH_WHY_NO_IMPROVEMENT.md` | why ten cycles of prompt edits did not separate from baseline |

The standing scope rule for that loop: it touches **prompts only**. Harness
defects get recorded in `APPLIED.md` rather than fixed mid-loop, so a score
change is never attributable to two things at once.
