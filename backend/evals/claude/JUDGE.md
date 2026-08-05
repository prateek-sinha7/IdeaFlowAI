# Judging a stored eval run with one independent sub-agent per stage

Invoke as: **"Follow JUDGE.md for `<RUN_ID>`"**, where `<RUN_ID>` is a folder under
`evals/minimal/.runs/`. Nothing else is required — this document tells you how to
derive everything else from that one name.

You are the **orchestrator**, not the judge. You prepare the evidence, dispatch one
sub-agent per stage, assemble what they return, and check the arithmetic. **You do not
score anything yourself.** For the single-threaded version, where you *are* the judge,
see `OPUS_JUDGE.md`; this file supersedes it whenever isolation is wanted.

**This is not a panel and gives no redundancy.** Five sub-agents means five *stages*
divided among five agents — **exactly one judge per stage**, same as the single-threaded
version. Nothing is voted on or averaged, and n=1 per stage either way. What the split
buys is context isolation (§0), not a second opinion. Do not describe the result as a
panel, a consensus or a majority; if you want redundancy, see §9.

Nothing is regenerated. Everything is read from disk. Work from `backend/`.

---

## 0. Why sub-agents, and why their context must be empty

Two other judges — `mistral-large-latest` and Bedrock `claude-haiku-4-5` — have already
scored the identical bytes. This is a third opinion on the same evidence, so **the
prompt, the format and the arithmetic are not yours to choose.** Match them or the
comparison is worthless.

The reason for sub-agents rather than one pass is **bias, not speed**. Whoever has been
editing the prompts under test, or has already formed a view of these artifacts, cannot
neutrally score whether the edits worked. So each judge is a **fresh agent with no
conversational history** — never a fork of yours, which would inherit exactly the
context you are trying to exclude.

That constraint is load-bearing. A sub-agent must not be told:

- which prompt version produced the artifacts, or that any version exists
- what changed between versions, or what a change was intended to fix
- what you or any earlier judge found, expected, or suspects
- how any other stage scored, or what a sibling sub-agent is finding
- the deterministic check results (see §2 — these must not move a score)

Give it the rendered prompt, the artifacts it needs, the pricing table, and the output
shape. Nothing else.

---

## 1. Resolve the folder, and clone it if it is not already a judge copy

```bash
cd backend/evals/minimal/.runs && ls -d *<RUN_ID>*
```

A run folder ending `-opusjudge` is yours to write. **A folder without that suffix is
not** — it holds another judge's verdict, already paid for, and overwriting one loses a
comparison. When the name the user gave lacks the suffix, clone it:

```bash
cd backend/evals/minimal/.runs
SRC=<RUN_ID>; cp -R "$SRC" "$SRC-opusjudge" && rm -f "$SRC-opusjudge/judge.json"
```

Dropping the copied `judge.json` matters: it is the *other* judge's answer, and leaving
it there would silently anchor the report. Everything downstream uses `<RUN_ID>-opusjudge`.

Then confirm the run is judgeable and record what produced it:

```bash
cd backend
python3.11 -c "
import hashlib
from evals.minimal import store, run as run_module
RUN='<RUN_ID>-opusjudge'
cfg=store.read_config(RUN)
for stage in ['specify','plan','analyze','build','validate']:
    row=store.read_phase(RUN,'run',stage)[0]
    live='sha256:'+hashlib.sha256(run_module.compose_agent_prompt(cfg['agents'][stage]['agent_id']).encode()).hexdigest()
    print(f\"{stage:9} errored={row.get('errored')} resp={len(row.get('response') or ''):>7} prompt={'live' if row.get('system_prompt_hash')==live else 'DIFFERS from live'}\")
"
```

An errored stage cannot be judged — record it in `errors` (§5) rather than scoring a
blank. The prompt-hash line is for **your** report to the user at the end; it never
reaches a sub-agent.

---

## 2. Fill in the deterministic checks — for the record, not for the judges

`checks_failed` is copied from the run's own `score.json`, never inferred. If the run
was interrupted before `eval.sh` scored every stage, that file will be missing entries;
populate them on the clone (deterministic and free, no dispatch):

```bash
cd backend
for s in specify plan analyze build validate; do
  python3.11 -m evals.minimal.cli checks <RUN_ID>-opusjudge --stage $s
done
```

`rows_ok == rows_checked` → `checks_failed: false`; a short-fall → `true`. Stages with
no HTML deliverable report `skipped` and are always `false`.

**Do not pass any of this to a sub-agent.** It sits beside the score as a fact and is
never folded into it; a judge told in advance that a gate failed will find reasons for
it. You attach these values yourself in §5.

Read the findings yourself, though, and **treat a failure as a hypothesis rather than a
verdict**. `checks.py` derives the expected page id from a route's first segment, so a
correct parameterised detail route — `#/case/:id` resolving to `<section
data-page="case-detail">` — is reported as a dead link. Before repeating any check
result to the user, open the router and confirm whether the page actually activates.
The inverse trap is worse: a prototype whose six sections hold nothing but an `<h1>`
passes both static and render checks, because they verify routing and console errors,
not content.

---

## 3. Render the real judge prompts

Do not improvise a prompt and do not read the rubric and wing it. `judge.py` builds the
prompt the other judges got. Render the same thing — this uses the shipped code, so it
cannot drift:

```bash
cd backend
python3.11 - <<'PY'
import pathlib
from evals.minimal import judge, cli, store

RUN = "<RUN_ID>-opusjudge"
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

Each file is the complete, literal prompt — brief, response, rubric, dimensions,
anchors. `system_prompt=""` is not an omission: `cli.py` calls `judge.judge(...)`
without one, so the other judges saw it empty too.

**Check what the brief block actually contains before dispatching validate.** For that
stage the rubric asks for a before/after comparison, but `row["prompt"]` is usually the
brief alone — no pre-fix HTML:

```bash
awk '/=== BRIEF ===/,/=== END ===/' \
  .runs/<RUN_ID>-opusjudge/judge_prompts/validate.txt | wc -c
```

A few hundred characters means the pre-fix file is absent, and `defect_repair_delta` is
unscoreable from the prompt alone. Supply `artifacts/build.html` to the validate judge
(§4 does this). Say so in your final report: on that one dimension the panel saw more
than Mistral and Bedrock did, so it is better grounded but not strictly comparable.

---

## 4. Dispatch one sub-agent per stage

Launch all five **in a single message** so they run concurrently, each a fresh
general-purpose agent on the strongest available model. The template below is the whole
prompt; substitute `{STAGE}`, `{RUN}`, `{CHARS}`, `{DIMENSIONS}` and `{STAGE_BLOCK}`.

> You are standing in as a judge model for an automated eval. Two other judges
> (mistral-large and Bedrock claude-haiku-4-5) have already scored these identical
> bytes; you are a third independent opinion. Be rigorous and neutral — form your own
> view from the evidence only.
>
> STEP 1. Read this file IN FULL (~{CHARS} — read all of it, across several Read calls
> if needed):
> `.../.runs/{RUN}/judge_prompts/{STAGE}.txt`
> That file is the complete, literal judge prompt: the brief, the agent's full response,
> the rubric, and the dimension list with weights. Answer it exactly as written. The
> response is the evidence — do not skim it.
>
> STEP 2. {STAGE_BLOCK}
>
> STEP 3. Price your findings. The rendered prompt does NOT tell you this, and it
> changes how you must tag. You do not choose the final number; each weakness is priced
> and the score is arithmetic:
>
>       blocking: 45   major: 18   minor: 4   untagged → priced as minor
>       priced[dimension] = max(0, 100 − sum of that dimension's finding costs)
>       score = Σ(priced[id] × weight[id]) / Σ(weight[id])
>
> Tag by what the defect costs a user, not by how it feels to write. Never withhold a
> real finding to protect a score; never inflate a nit. No real defects in a dimension =
> empty list = a legitimate 100. Calibration note, not a thumb on the scale: of the two
> existing judges, one tagged 21 of 23 findings "minor" and awarded 96.8 to a prototype
> that throws a SyntaxError and renders blank. Tag honestly and let the formula land
> where it lands.
>
> Dimensions and weights for this stage (use these ids verbatim, all of them, none
> extra): {DIMENSIONS}
>
> STEP 4. Write your verdict as JSON to
> `.../.runs/{RUN}/judge_prompts/verdict_{STAGE}.json`:
>
>     {"score": <weighted mean of sub_scores, 1dp>,
>      "sub_scores": {"<dim>": <100 − costs>},
>      "sub_scores_judge_self": {"<dim>": <your own raw 0-100, NOT equal to priced>},
>      "findings": {"<dim>": [{"text": "<defect, no prefix, quoting evidence>",
>                              "severity": "blocking|major|minor", "cost": 45|18|4}]},
>      "rationale": "<one substantial paragraph>",
>      "strengths": ["..."],
>      "weaknesses": ["<severity>: <same text, prefix KEPT>"]}
>
> Every dimension must appear in all three maps (use `[]` for a clean dimension). Before
> finishing, verify each sub_score equals 100 minus its findings' costs, that `score`
> reproduces from sub_scores and the weights, and that `weaknesses` has exactly as many
> entries as all findings combined.
>
> Quote specific values from THIS response as evidence — text that would fit any other
> response is a non-answer. Reply with only a two-line summary: the score, and the count
> of findings by severity.

### `{DIMENSIONS}` — verbatim, none extra

| stage | dimensions and weights |
|---|---|
| specify | data_realism 20, brief_intent_match 25, design_system_coherence 15, spec_consistency_completeness 25, interaction_specification 15 |
| plan | page_coverage 40, task_self_containment 40, build_order_coherence 20 |
| analyze | cross_artifact_grounding 40, defect_detection 35, verdict_coherence 25 |
| build | data_realism 40, page_completeness 35, visual_coherence 25 |
| validate | page_completeness 45, defect_repair_delta 35, token_and_chrome_consistency 20 |

A missing dimension invalidates the verdict.

### `{STAGE_BLOCK}` — what each judge must verify rather than assume

Every block ends with the same rule, because both failure directions cost the same:
**do not invent defects — quote the exact text that proves any claim; a finding that
misreads the artifact is as wrong as a missed defect.**

**specify** — Verify before you assert. This is a specification full of numbers,
enumerations and cross-references. Where it states a total, count, sum or average,
recompute it from the items it names and compare. Where it says one section agrees with
another, check both. Where it defines ranges, bands or time buckets, test every seeded
row against them and report any row that falls in none. Use a `python3.11` one-liner via
Bash for arithmetic — never mental arithmetic.

**plan** — The central question is whether ONE sub-agent that CANNOT see any other task
could build each task from its text alone. Check: does any task refer to another's
contents ("as defined in Task N")? Is every shared mechanism — state store, event bus,
router, cross-page channel — given its full contract (exact names, signatures, payload
shapes) by the task that introduces it? If a list task makes N rows navigate to a detail
view, does the detail task supply data for all N or one worked example? Do numbers in
one task match the same numbers in another — recompute sums in Bash.

**analyze** — This stage reviews two upstream artifacts, so check its claims against
them directly: `artifacts/specify.md` and `artifacts/plan.md` (read both). Judge in two
directions, which matter equally. (a) Did it FIND the real disagreements present? Go
looking yourself — recompute every total, check every spec page has a task, test whether
any enumeration is incomplete or any set of ranges leaves members uncovered. Anything
genuinely wrong that it did not flag is a detection miss; "all clear" on a pair that
genuinely disagrees is the worst outcome here. (b) Did it assert anything FALSE? A
report that invents a defect, or recommends fixing what is already correct, manufactures
rework. Also check that a Clear status is earned — the Detail cell carrying the
comparison that justifies it — and that Issues, Risk register, next actions and verdict
follow from the Findings table.

**build** — Inspect mechanically, not by impression. The same HTML is at
`artifacts/build.html`; use Bash/`python3.11` to establish facts. At minimum: for EVERY
`<section data-page="...">`, extract its body and measure the real content — a section
holding only a heading is the single most serious structural defect. Determine whether
content is in the markup or written at runtime by JS render functions, and check both
before calling a page empty (a `<tbody>` filled by JS is populated, not empty); list the
render functions that exist. Are tables and charts backed by real seeded records suited
to the brief's industry? Are displayed totals computed from the data or written as
literals — and if literal, recompute them and check they are even correct. Are colours
applied through `var(--token)`, or are there raw hex/rgba literals outside `:root`?
Count them, and note any literal that is a declared token's own value re-typed. Does
every interactive control change what is rendered, or are some inert — a handler that
never reads its own control, an `alert()` standing in for a feature?

**validate** — One dimension, `defect_repair_delta`, is a comparison against the
prototype BEFORE this agent edited it, which the rendered prompt does not include. It is
supplied: PRE-FIX `artifacts/build.html`, POST-FIX `artifacts/validate.html`. Diff them
and establish with quoted code exactly what changed, then judge both halves: did it
repair what was broken (empty or thin sections filled, dead links wired, sections made
reachable, handlers defined), and did it PRESERVE what already worked? Rewriting or
deleting working content is as much a defect as leaving one unfixed — check for anything
that worked before and does not now, and for any newly introduced error (an identifier
declared twice in one scope is a SyntaxError that kills the entire script). Are the
repairs fixes at the cause, or corrected literals that will drift again? Then inspect
the post-fix artifact mechanically exactly as the **build** block describes. Judge
`token_and_chrome_consistency` on INTERNAL consistency only: no design system is
injected during evals, so keeping the seed token values is correct and must not be
penalised.

---

## 5. Assemble the verdicts

Sub-agents write per-stage fragments; you own the file they land in. Attach the fields
only the orchestrator knows — `row_id`, `checks_failed`, `judge_model`, the zeroed token
counts — and write once at the end to
`evals/minimal/.runs/<RUN_ID>-opusjudge/judge.json`:

```bash
cd backend
python3.11 - <<'PY'
import json, pathlib
RUN  = "<RUN_ID>-opusjudge"
BASE = pathlib.Path("evals/minimal/.runs")/RUN
MODEL = "claude-opus-<version> (claude code, per-stage sub-agent)"
score  = json.loads((BASE/"score.json").read_text())
runjs  = json.loads((BASE/"run.json").read_text())
out = {}
for stage in ["specify","plan","analyze","build","validate"]:
    f = BASE/"judge_prompts"/f"verdict_{stage}.json"
    if not f.exists():
        out[stage] = {"results": [], "errors": [{"row_id": None, "reason": "no verdict"}],
                      "judge_requested": {"provider":"claude-code","model":"opus"}}
        continue
    v = json.loads(f.read_text())
    s = score.get(stage, {})
    row = runjs[stage][0]
    out[stage] = {"results": [{
        "row_id": row["row_id"], "score": v["score"], "judge_model": MODEL,
        "checks_failed": bool(s.get("rows_checked") and s.get("rows_ok") != s.get("rows_checked")),
        "scoring": "severity_priced",
        "sub_scores": v["sub_scores"], "sub_scores_judge_self": v["sub_scores_judge_self"],
        "findings": v["findings"], "rationale": v["rationale"],
        "strengths": v["strengths"], "weaknesses": v["weaknesses"],
        "tokens_in": 0, "tokens_out": 0,
    }], "errors": [], "judge_requested": {"provider":"claude-code","model":"opus"}}
(BASE/"judge.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
print("wrote", BASE/"judge.json")
PY
```

Every field is load-bearing. `sub_scores` holds the **priced** numbers (`100 − costs`),
because these rubrics are `scoring: severity_priced`; `sub_scores_judge_self` holds the
judge's own raw view. Both are stored precisely so the gap between them stays
measurable — **never make them equal**. `weaknesses` is every finding flattened across
dimensions with the severity prefix **kept**; that is what the advisor reads.
`tokens_in`/`tokens_out` are `0` because this package didn't spend them — real numbers
would corrupt the report's cost rollup.

---

## 6. Verify the arithmetic before you believe any of it

A sub-agent that mis-sums its own costs produces a number that looks authoritative and
is not. Check every stage mechanically; do not eyeball it:

```bash
cd backend/evals/minimal
python3.11 - <<'PY'
import json
W={'specify':{'data_realism':20,'brief_intent_match':25,'design_system_coherence':15,'spec_consistency_completeness':25,'interaction_specification':15},
   'plan':{'page_coverage':40,'task_self_containment':40,'build_order_coherence':20},
   'analyze':{'cross_artifact_grounding':40,'defect_detection':35,'verdict_coherence':25},
   'build':{'data_realism':40,'page_completeness':35,'visual_coherence':25},
   'validate':{'page_completeness':45,'defect_repair_delta':35,'token_and_chrome_consistency':20}}
COST={'blocking':45,'major':18,'minor':4}
d=json.load(open(".runs/<RUN_ID>-opusjudge/judge.json")); ok=True
for st,w in W.items():
    r=d[st]["results"]
    if not r: print(f"{st:9} NO RESULT"); ok=False; continue
    r=r[0]; ss=r["sub_scores"]
    if set(ss)!=set(w): print(f"  !! {st} dimensions {set(ss)^set(w)}"); ok=False
    for dim,fs in r["findings"].items():
        exp=max(0,100-sum(f["cost"] for f in fs))
        if exp!=ss.get(dim): print(f"  !! {st}.{dim} priced {ss.get(dim)} != {exp}"); ok=False
        for f in fs:
            if COST[f["severity"]]!=f["cost"]: print(f"  !! {st}.{dim} cost/severity mismatch"); ok=False
    exact=sum(ss[k]*w[k] for k in w)/sum(w.values())
    nf=sum(len(v) for v in r["findings"].values()); nw=len(r["weaknesses"])
    # tolerance 0.051, not 0.05: an exact mean of x.x5 renders as either neighbour at 1dp
    # (half-up gives 24.0, Python's float repr gives 23.9) and both are correct.
    if abs(exact-r["score"])>0.051: print(f"  !! {st} score {r['score']} != {exact:.3f}"); ok=False
    if nf!=nw: print(f"  !! {st} findings {nf} != weaknesses {nw}"); ok=False
    print(f"{st:9} score={r['score']:5} exact={exact:7.3f} findings={nf} checks_failed={r['checks_failed']}")
print("ALL CONSISTENT" if ok else "ERRORS ABOVE — fix before reporting")
PY
```

Anything flagged goes back to that stage's sub-agent to correct — **do not repair a
verdict yourself**, or you have re-introduced the bias the panel exists to remove. Send
it the specific inconsistency and let it re-derive.

---

## 7. Finish, and report honestly

```bash
cd backend && python3.11 -m evals.minimal.cli report
```

The run appears as its own row, keyed by folder name, beside the Mistral and Bedrock
readings of the same artifacts.

When you report to the user, lead with the deterministic checks and the concrete
artifact facts, not the scores — those don't drift, and the scores do. Then state the
limits plainly, every time:

- **n=1 per arm.** `cli compare` refuses a verdict below n=2, so a single-row config
  yields no verdict however large the delta looks.
- **The noise floor is ±4.** Two identical Mistral judgements of identical bytes came out
  3.6 apart on specify and 4.0 apart on plan. Movement inside that band is not evidence.
- **Judges disagree enormously on the same bytes** — on one run Mistral, Bedrock and a
  Claude sub-agent spread across roughly 11 to 97 on a single stage, almost entirely
  through severity tagging rather than what they found. A cross-version comparison is only
  meaningful judge-against-the-same-judge, and **judged by the same method**: a
  single-threaded pass and a per-stage sub-agent are different instruments even on the
  same model, because the sub-agent is told to verify mechanically and cannot carry one
  stage's findings into another.
- **One judge per stage means no variance estimate.** You have a point, not a range. Do
  not call a movement real on the strength of it; see §9.
- **Any dimension where the panel saw more than the other judges** — normally validate's
  `defect_repair_delta`, per §3 — is better grounded but not strictly comparable.
- If several prompts changed at once, **no per-stage attribution is possible**; say so
  rather than implying one.

---

## 8. Do not

- Score anything yourself. You orchestrate; the sub-agents judge.
- Call this a panel, a consensus or a majority. It is one judge per stage.
- Fork your own context into a judge, or tell a judge what you expect, what changed, what
  another stage scored, or what the deterministic checks said.
- Re-run the pipeline, or edit anything under `artifacts/`. That is the evidence;
  changing it destroys the comparison. Do not "fix" the prototypes.
- Edit `run.json`, `config.json` or anything under `logs/`. `score.json` may only be
  populated by `cli checks` on the judge clone, never hand-edited.
- Judge a run whose folder name lacks `-opusjudge`. Those hold the other judges'
  verdicts, already paid for, and overwriting one loses a comparison.

---

## 9. Optional: an actual panel, when you need a variance estimate

Everything above gives one judge per stage. That is enough to *find defects* — the
sub-agents are told to verify mechanically, so their findings are checkable claims about
the artifact, and a finding either survives inspection or it doesn't. It is **not**
enough to call a score movement real, because a single judge gives a point with no
spread, and severity tagging is where judges diverge most.

When the question is "did this change actually move the number", run **K judges on the
SAME stage** (K=3 is usually enough) instead of one:

- Dispatch K identical sub-agents per stage, writing to
  `verdict_<stage>_<k>.json`. Vary nothing but the index — same prompt, same artifacts.
  Do not tell any of them that siblings exist, or they will hedge toward each other.
- Take the **median** `score` and the median per-dimension `sub_score`. Not the mean: one
  judge tagging a single finding `blocking` instead of `major` swings a mean by 9 points
  on a 25-weight dimension.
- Record the **spread** (max − min) beside the median. That is your empirical noise floor
  for this stage, and it replaces the ±4 figure quoted in §7, which came from Mistral
  re-judging identical bytes and does not transfer to a different judge or method.
- Treat a wide spread as a finding in itself. If three judges reading the same file
  disagree by 40 points, the rubric or the severity anchors are underdetermined for that
  stage, and no amount of re-running fixes it.
- Union the findings for the report, but keep the score from the median. A defect only
  one of three judges found is a hypothesis; one all three found is a fact.

Cost is linear: K=3 across five stages is 15 sub-agents per run rather than 5. Do this
for the run you intend to draw a conclusion from, not for every run.
