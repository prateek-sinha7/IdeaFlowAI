# Judging a stored eval run with the real judge prompt

You are standing in for the judge model. Two other judges —
`mistral-large-latest` and Bedrock `claude-haiku-4-5` — have already scored the
identical bytes. This is a third opinion on the same evidence, so **the prompt,
the format and the arithmetic are not yours to choose.** Match them or the
comparison is worthless.

Nothing is regenerated. You read what is on disk and write a verdict back.
Work from `backend/` as the working directory.

---

## 1. Render the real judge prompt

Do not improvise a prompt and do not read the rubric and wing it. `judge.py`
builds the prompt the other judges got by filling `prompts/judge_prompt.md` with
that stage's brief, response, rubric text, dimension list and score anchors.
Render the same thing — this uses the shipped code, so it cannot drift:

```bash
cd backend
python3.11 - <<'PY'
import pathlib
from evals.minimal import judge, cli, store

RUN = "<RUN_ID>"          # e.g. 260803-162918-prototype_aws_1_fraud_review-opusjudge
out = pathlib.Path("evals/minimal/.runs")/RUN/"judge_prompts"
out.mkdir(exist_ok=True)
for stage in store.list_phases(RUN):
    row = store.read_phase(RUN, "run", stage)[0]
    upstream = cli._upstream_files(RUN, stage).get((row["row_id"], row.get("repeat", 0)))
    text = judge.build_judge_prompt(
        system_prompt="", prompt=row.get("prompt", ""),
        response=row["response"], rubric=cli._load_rubric(stage),
        upstream=upstream)
    (out/f"{stage}.txt").write_text(text, encoding="utf-8")
    print(f"{stage:9} {len(text):>8,} chars  row_id={row['row_id']}")
PY
```

That writes five files under `.runs/<RUN_ID>/judge_prompts/`. Each one is the
complete, literal prompt — agent system prompt, brief, response, rubric,
dimensions, anchors. `system_prompt=""` is not an omission: `cli.py` calls
`judge.judge(...)` without one, so the other judges saw it empty too.

**Read each file and answer it as written.** That is the whole task. The rest of
this document only says where to put the answer.

They are large — validate is ~85k characters, because the response is the entire
prototype HTML. Read the file fully before scoring; that document is the evidence.

---

## 2. The one thing the prompt doesn't tell you

The rendered prompt asks for per-dimension scores with evidence. It does **not**
explain what happens to your findings afterwards, and that changes how you should
tag them.

**You do not choose the final number.** Each weakness you report is priced, and
the score is arithmetic on those prices:

| severity prefix | cost |
|---|---|
| `blocking: ` | 45 |
| `major: ` | 18 |
| `minor: ` | 4 |
| untagged | priced as `minor` |

```
priced[dimension] = max(0, 100 − sum of that dimension's finding costs)
score             = Σ(priced[id] × weight[id]) / Σ(weight[id])
```

So **prefix every weakness with its severity**, and tag by what the defect costs
a user rather than by how it feels to write. This exists because judges reliably
find real defects and just as reliably refuse to deduct for them.

Weights, for checking your arithmetic:

| stage | dimensions and weights |
|---|---|
| specify | data_realism 20, brief_intent_match 25, design_system_coherence 15, spec_consistency_completeness 25, interaction_specification 15 |
| plan | page_coverage 40, task_self_containment 40, build_order_coherence 20 |
| analyze | cross_artifact_grounding 40, defect_detection 35, verdict_coherence 25 |
| build | data_realism 40, page_completeness 35, visual_coherence 25 |
| validate | page_completeness 45, defect_repair_delta 35, token_and_chrome_consistency 20 |

Use every dimension id verbatim, none extra. A missing dimension invalidates the
verdict.

A calibration note, not a thumb on the scale: the two existing judges differ
almost entirely in severity tagging, not in what they found. Mistral tagged 21 of
23 findings `minor` and gave 96.8 to a page that throws a SyntaxError and renders
blank. Tag honestly and let the formula land where it lands.

---

## 3. Where the answer goes

One file, all five stages, written once at the end:
`evals/minimal/.runs/<RUN_ID>/judge.json`

```json
{
  "specify": {
    "results": [
      {
        "row_id": "<from run.json>",
        "score": 72.4,
        "judge_model": "claude-opus-<version> (claude code)",
        "checks_failed": false,
        "scoring": "severity_priced",
        "sub_scores":            {"data_realism": 96, "brief_intent_match": 78},
        "sub_scores_judge_self": {"data_realism": 88, "brief_intent_match": 84},
        "findings": {
          "data_realism": [
            {"text": "amounts are round to the nearest 100 across every row",
             "severity": "minor", "cost": 4}
          ],
          "brief_intent_match": []
        },
        "rationale": "one paragraph on the overall verdict",
        "strengths": ["...", "..."],
        "weaknesses": ["minor: amounts are round to the nearest 100 across every row"],
        "tokens_in": 0,
        "tokens_out": 0
      }
    ],
    "errors": [],
    "judge_requested": {"provider": "claude-code", "model": "opus"}
  },
  "plan": {}, "analyze": {}, "build": {}, "validate": {}
}
```

Every field is load-bearing:

- **`sub_scores` holds the PRICED numbers** (`100 − costs`), because these
  rubrics are `scoring: severity_priced`. `sub_scores_judge_self` holds the raw
  numbers you gave in the prompt's own reply format. Both are stored precisely so
  the gap between them stays measurable — do not make them equal.
- **`score`** is the weighted mean of `sub_scores`, per the formula above.
- **`findings`** is keyed by dimension id; each entry carries `text` (prefix
  stripped), `severity`, `cost`. The report's severity chart counts these.
- **`weaknesses`** is every finding flattened across dimensions with the prefix
  **kept** — this is what the advisor reads.
- **`tokens_in` / `tokens_out` are 0.** This package didn't spend them; real
  numbers here would corrupt the report's cost rollup.
- **`checks_failed`** is copied from the run's own `score.json` (`<stage>` →
  `rows_ok` for that row). Never infer it, and never let it move your score — it
  sits beside the number as a fact, never folded in.
- `errors` stays `[]` unless a stage genuinely cannot be judged; then put
  `{"row_id": "...", "reason": "..."}` there and leave it out of `results`.

---

## 4. Finish

```bash
cd backend
python3.11 -m evals.minimal.cli report
```

The run appears as its own row, keyed by folder name, beside the Mistral and
Bedrock readings of the same artifacts.

Before you call it done: five stages present, every rubric dimension covered in
each, and every `score` reproducible from its own `sub_scores` and the weight
table. If a number doesn't reproduce, your arithmetic is wrong — not the table.

---

## 5. Do not

- Re-run the pipeline, or edit anything under `artifacts/`. That is the evidence;
  changing it destroys the comparison. Do not "fix" the prototypes.
- Edit `run.json`, `config.json`, `score.json`, or anything under `logs/`.
- Judge a run whose folder name lacks `-opusjudge`. Those hold the other judges'
  verdicts, already paid for, and overwriting one loses a comparison.
