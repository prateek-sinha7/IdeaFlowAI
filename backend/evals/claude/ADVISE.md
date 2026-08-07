# Turning judge findings into the next prompt version

Invoke as: **"Follow ADVISE.md"** (optionally naming the runs to learn from).

**Scope — read this first.** The only thing you change is
`prompts/agents/<agent-id>.v<N>.md`, plus the record in `prompts/APPLIED.md`.
You do not touch `run.py`, `judge.py`, `cli.py`, `checks.py`, the configs, the
datasets, the harness, or anything under `backend/agents/`. If the evidence
points at a harness defect, **write it down in `APPLIED.md` and move on** — it is
not yours to fix in this pass.

The loop this document owns:

    pool every advice → audit what the LAST pass did → generalise → write vN+1
    → activate → hand back

Everything happens inside `backend/evals/minimal/`. Work from `backend/`.

Where you sit in the wider loop: the user runs the pipeline on Bedrock, judges
it with `JUDGE.md` (opus, one sub-agent per stage), and then calls you. **You do
not run the eval and you do not run the judge.** Both cost real money or real
time and both are the user's to trigger.

---

## 0. Current state — verify, don't assume

| fact | as of 2026-08-03 |
|---|---|
| live version, all five agents | **v2** (`./activate.sh status` → all OVERRIDDEN) |
| next version to write | **v3** |
| v1 specify prompt hash | `sha256:d0362e2a9d35dd59…` |
| v2 specify prompt hash | `sha256:b82864e14804341f…` |
| artifact-producing model | Bedrock `claude-haiku-4-5`, **thinking off**, 32 768 output cap |

Confirm the first two before writing anything:

```bash
cd backend/evals/minimal/prompts && ./activate.sh status
ls agents/
```

If the live version is not what this table says, the table is stale — trust the
command, and correct the table as part of your pass.

---

## 1. Rebuild the pool

`prompts/advices.json` is a snapshot, not a live view.

```bash
cd backend
python3.11 -m evals.minimal.cli advice
```

**This rebuilds the file from scratch — it does not append.** Any status
annotation in it is destroyed. `prompts/APPLIED.md` exists because of that; read
it before you start and record there anything you deliberately reject.

### `count` is not a generality signal — do not use it as one

Measured on the 2026-08-03 pool: **149 entries across five stages, every single
one `count: 1`.** Two reasons, both structural:

- The pool clusters by **exact string**. The same defect phrased three ways is
  three count-1 entries, so `count` can essentially never exceed 1.
- The "runs" it pools are usually **the same artifacts judged several times**.
  Nine run folders were 3 briefs × 3 judges over byte-identical bytes
  (md5-verified). Distinct rows available: **3**.

So: **cluster semantically by hand, and count distinct briefs, never runs.**
Before you count anything, establish how many *distinct artifact sets* the pool
actually covers:

```bash
cd backend/evals/minimal/.runs
for d in */; do echo -n "$d "; md5 -q "$d/artifacts/build.html" 2>/dev/null; done | sort -k2
```

Rows sharing an md5 are one observation, not several.

---

## 2. Audit the last pass before proposing a new one

This is the step the old document did not have, and the reason advice felt like
it was going nowhere. **Before generalising anything, answer: did the last set of
rules land?** `APPLIED.md`'s applied table is your list of hypotheses; each one
was written to change something observable.

Check them **mechanically**, off the artifacts, with no judge involved. Most
rules in this family reduce to a countable property:

```bash
cd backend/evals/minimal
python3.11 - <<'PY'
import re, glob, os
def facts(p):
    h = open(p, encoding="utf-8", errors="replace").read()
    secs = re.findall(r'<section[^>]*data-page="([^"]+)"[^>]*>(.*?)</section>', h, re.S)
    thin = [n for n, b in secs
            if len(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b)).strip()) < 120
            or len(re.findall(r"<\w+", b)) < 8]
    lits = re.findall(r"#[0-9a-fA-F]{6}\b|rgba?\([^)]*\)",
                      re.sub(r":root\s*\{.*?\}", "", h, flags=re.S))
    return (len(h), len(secs), len(thin), len(lits),
            len(re.findall(r"\balert\s*\(", h)),
            len(re.findall(r"function\s+\w+|const\s+\w+\s*=\s*\(", h)))
for d in sorted(glob.glob(".runs/*/")):
    for stage in ("build", "validate"):
        p = f"{d}artifacts/{stage}.html"
        if os.path.exists(p):
            b, s, t, l, a, f = facts(p)
            print(f"{os.path.basename(d.rstrip('/'))[:50]:52}{stage:9}"
                  f"{b:>7}b sec={s:>2} thin={t:>2} colourlits={l:>3} alert={a:>2} fns={f:>3}")
PY
```

Read the numbers **against the rules `APPLIED.md` claims to have added**, per
brief, v1 vs v2. Worked example from the 2026-08-03 pass, so you know what a
landed rule and a dead rule look like:

| rule added in v2 | metric | fraud | reservations | permits | verdict |
|---|---|---|---|---|---|
| tint tokens — add a token rather than inline a shade | colour literals outside `:root` | 20→8 | 28→2 | 37→7 | **landed** |
| `alert()` is not an implementation | `alert()` calls | 0→0 | 0→0 | 8→0 | **landed** |
| every page has real tables / charts / forms | thin sections | 0→0 | 3→6 | 3→1 | **did not land** |

Write the result of this audit into `APPLIED.md` as a **Previous-pass audit**
section, before you write a single new rule. Then apply the consequence:

- **A rule that landed is finished.** Do not restate it, do not strengthen it, do
  not re-apply advice that criticises the behaviour it already fixed. Advice
  against a fixed defect is the pool being stale, not a recurrence.
- **A rule that did not land is a rule that was written wrong** — see §3's
  cause-level test. Restating it louder has been tried and measured to move the
  score the wrong way. Either rewrite it as a decision procedure or drop it.
- **A metric that got worse** is the most informative thing in the pass. Find out
  why before adding anything. On 2026-08-03 reservations' build collapsed from
  69 KB to 22 KB with all six sections thin, at 8 765 output tokens — the model
  wrote a shell and stopped, which is a budget/mode failure, not a rule the
  prompt was missing.

---

## 3. Why the score may not move even when the prompts improve

Do not conclude "no improvement" from a score table until you have checked all
three of these. On 2026-08-03 all three were active at once, and the v2 sweep was
in fact a large improvement that the score table hid.

### a. Compare the same judge AND the same method, or don't compare

Four instruments have been used on these artifacts, and they are not
interchangeable:

| instrument | notes |
|---|---|
| Bedrock `claude-haiku-4-5` | API judge |
| `mistral-large-latest` | API judge — **saturated**, see below |
| opus, **single-threaded** (`OPUS_JUDGE.md`) | one pass, carries cross-stage context |
| opus, **sub-agent panel** (`JUDGE.md`) | one fresh judge per stage, told to verify mechanically |

The last two are **different instruments on the same model** and their numbers do
not compare. Neither does anything else across rows of that table. Measured on
byte-identical v1 artifacts, the three API/opus judges spread **58 points on
build and 86 points on validate**.

Mistral additionally **saturates**: it returned identical scores (96.8 plan, 91.3
analyze) on two runs whose artifacts differ by 47 KB. It is awarding a house
number in the low 90s, not measuring. Never read a delta off it.

Before quoting any delta, classify every run:

```bash
cd backend
python3.11 -c "
from evals.minimal import store
import json, os
for RUN in sorted(os.listdir('evals/minimal/.runs')):
    try:
        h = store.read_phase(RUN, 'run', 'specify')[0].get('system_prompt_hash')
        p = f'evals/minimal/.runs/{RUN}/judge.json'
        jm = ''
        if os.path.exists(p):
            r = json.load(open(p)).get('specify', {}).get('results', [])
            jm = r[0].get('judge_model', '') if r else 'NO RESULTS'
        print(f'{RUN:62} {str(h)[:20]:22} {jm}')
    except Exception as e:
        print(f'{RUN:62} ERR {e}')
"
```

A valid pair is: **same `judge_model` string, same brief, different prompt hash.**
Anything else is not evidence. If no valid pair exists for the instrument whose
numbers look bad, **say exactly that** — do not report it as a regression.

### b. A missing `judge.json` is not a low score

A run folder with no `judge.json`, or with `"results": []`, was never judged or
was interrupted. It contributes nothing. Check before reading it as anything.

### c. n=1 and the noise floor

`cli compare` refuses a verdict below n=2. Two identical Mistral judgements of
identical bytes came out 3.6 apart on specify and 4.0 apart on plan. Movement
inside ±4 is not evidence. One judge per stage gives you a point, not a range —
see `JUDGE.md` §9 if you need a spread.

**Weight the mechanical facts of §2 above every score in this section.** They do
not drift, they do not saturate, and they do not disagree with themselves.

---

## 4. Read the evidence — three sources, in this order

**a. The deterministic checks** — `.runs/<RUN_ID>/score.json` → `<stage>.reasons`
and `.findings`, plus the mechanical counts from §2. These do not hallucinate and
are domain-independent. **Weight them above any judge prose.**

One known false positive: `checks.py` derives the expected page id from a route's
first segment, so a correct parameterised detail route (`#/case/:id` →
`<section data-page="case-detail">`) is reported as a dead link. Open the router
and confirm the page actually activates before writing a rule against it. Never
write a rule that teaches the agent to satisfy the checker rather than the user —
record the checker defect in `APPLIED.md` instead.

**b. The judge findings** — `.runs/<RUN_ID>/judge.json` → `<stage>.results[].findings`.
Richer than the pooled advice: they carry severity and per-dimension grouping. A
`blocking` or `major` finding recurring across **distinct briefs** outranks a high
`advisory_score` on a single `minor`.

Verify before you believe. A previous pass nearly wrote a rule about unused
`.success-toast` classes; neither artifact contained the string `toast` at all.
Another found "empty `<tbody>` in 46 % of prototypes"; 22 of 24 were populated by
JS at runtime and the real figure was 4 %. **Open the artifact and check the claim
before writing a rule against it.**

**c. The pooled advice** — `prompts/advices.json`, at
`workflows.prototype.stages.<stage>.categories.*.entries`.

| field | meaning |
|---|---|
| `action` | `add` a new instruction, or `remove` wording already in the prompt |
| `description` | the proposed instruction, verbatim |
| `advisory_score` | 0-100, the advisor's own MAY→MUST strength |
| `count` / `runs` | **unusable — see §1** |
| `prompt_state` | `current` = written against the live prompt; `superseded` = against text since replaced |

**Ignore every `superseded` entry.** It criticises a prompt body that no longer
exists; applying it re-fixes something already fixed, or reverts it.

---

## 5. Generalise — this is the actual work

The advice was written from a handful of specific briefs. The prompt runs on
every future brief, in domains nobody has seen. An edit that only helps the rows
that produced it is worse than no edit: it spends prompt budget, and a prompt
dense in one domain's examples leaks that domain into unrelated output.

- **Name the structure, never the subject matter.** "Every status colour resolves
  through a token", not "the fraud queue's badge colours". No noun from any brief
  — no product, company, metric, or page name — may appear in the final prompt.
- **Count distinct briefs, and say so.** Something in 6 of 10 rows across 6
  industries is systemic. Something in 1 row is an anecdote.
- **A single-brief observation earns a rule only when the mechanism is obviously
  general** — a contract violation, a structural rule, an ordering error any
  domain would hit. If it could plausibly be an artefact of that one brief, drop
  it and say you dropped it.
- **Merge duplicates.** Per §1 the pool cannot cluster for you.
- **Prefer few strong rules to many weak ones.** Every line competes for attention
  with the lines already there. The v2 build prompt is already ~15 800 characters
  of system prompt before the brief; adding to it has a real cost.

### The cause-level test — apply it to every candidate

If a defect recurs *despite* a rule already in the prompt, that rule is not the
fix. Find what makes the agent reach for the wrong thing.

Four worked examples from the v1→v2 pass:

1. **"Use ONLY `:root` variables for colors" — broken in 3/3.** The prototypes
   defined solid status tokens, but badges need a *low-alpha wash* of one and no
   token expressed that. `rgba(16,185,129,0.1)` is exactly the file's own
   `--success: #10b981` at 10 %. The agent *had* to write the literal. Fix:
   require the tint to exist as its own token.
2. **"Zero placeholder text" — a page shipped the literal word "placeholder".**
   The rule enumerated banned strings, which invites string-matching. Fix: state
   the property — text that *names* a missing feature instead of being it.
3. **"Every interactive element has a handler" — satisfied while inert.**
   `alert('Sort by X implemented.')` is a handler. Fix: the handler must change
   what is rendered, and must read the control it belongs to.
4. **"Be concise / scannable in under 60 seconds" — this *caused* the dominant
   analyze defect.** The prompt rewarded a short report, so the agent emitted
   status tokens without doing the comparison. Fix: brevity explicitly yields to
   evidence.

### Writing for the model that actually produces the artifacts

The build and validate artifacts come from **`claude-haiku-4-5` with extended
thinking off**, emitting a whole multi-page document against a 32 768-token
output cap. In the eval it receives no `=== CURRENT TASK ===` block, so it takes
the build prompt's **one-shot fallback branch** and must produce every page in a
single pass. Write for that model, in that mode.

What the evidence supports (§2's audit is the test — this is a hypothesis that
has so far matched every data point, not a law):

- **Rules that fire at the moment of the decision land.** *"the moment you are
  about to write a colour literal anywhere outside `:root`, define a token
  instead"* moved its metric 60–93 %. It is checkable while emitting the next
  token.
- **Rules that replace a satisfiable proxy with a property land.** *"`alert()` is
  not an implementation … a control must read its own current value and re-render
  what it governs"* took `alert()` to zero.
- **Rules phrased as goals to hold across a whole document do not land.** *"every
  page MUST have real tables ≥5 rows"* did not move thin-section counts. A model
  with no scratchpad, 25 000 tokens into an emission, is not holding a checklist.
  Prefer converting these into **structure the model fills in** — a labelled
  output skeleton, a per-section contract stated where the section is written —
  over restating them as prose.
- **Do not add length to fix a length problem.** When a stage's failure is that
  it ran out of budget, more instructions make it worse.

---

## 6. Write the new version

Version files live in `prompts/agents/<agent-id>.v<N>.md`. **Create the next N —
never edit an existing version**, or you lose the ability to say which text
produced which score. As of now the live set is `v2`, so you write **`v3`**.

Base it on **the version that was live when the runs you are learning from were
dispatched**:

```bash
cd backend
python3.11 - <<'PY'
import hashlib
from evals.minimal import store, run as run_module
RUN, STAGE = "<RUN_ID>", "<stage>"
cfg = store.read_config(RUN)
row = store.read_phase(RUN, "run", STAGE)[0]
agent = cfg["agents"][STAGE]["agent_id"]
live = hashlib.sha256(run_module.compose_agent_prompt(agent).encode()).hexdigest()
print("run dispatched with:", row.get("system_prompt_hash"))
print("live prompt now    : sha256:" + live)
PY
```

Matching hashes mean the currently-active prompt is what the advice criticises —
copy that one.

```bash
cd backend/evals/minimal
cp prompts/agents/<agent-id>.v2.md prompts/agents/<agent-id>.v3.md
```

Then edit `v3`:

- **Keep the YAML frontmatter byte-identical.** `activate.sh` parses the file with
  `frontmatter.load()` and ships only `.content`; a broken frontmatter block fails
  the load and the activation dies. Verify after editing:
  ```bash
  diff <(awk '/^---$/{n++} n<2' prompts/agents/<agent-id>.v2.md) \
       <(awk '/^---$/{n++} n<2' prompts/agents/<agent-id>.v3.md) && echo "frontmatter identical"
  ```
- Apply `remove` advice by deleting the quoted wording; `add` advice by inserting
  the instruction **where it belongs structurally** — not appended in a heap.
- Check no brief's vocabulary leaked in before you finish.

**Never edit anything under `backend/agents/prompts/`.** That is the canonical
production prompt. This whole mechanism exists so the eval can override it per
user without touching it.

**Unreachable advice.** Some advice targets
`backend/agents/guardrails/html-prototype.md`, which is injected ahead of the body
and is **not** reachable through the `.vN.md` mirror. Record those in `APPLIED.md`
as unreachable. Do not duplicate the rule into the prompt body.

---

## 7. Activate

```bash
cd backend/evals/minimal/prompts
./activate.sh <agent-id> v3      # one agent
./activate.sh status             # confirm
```

**Prefer one agent per pass.** Stages feed each other, so if several change at
once and the score moves, nothing tells you which edit did it — a specify change
shows up in build's score too.

`./activate.sh prototype v3` does all five and refuses unless every agent has a
`v3`. If the user directs a full sweep anyway, do it — and **record the
attribution caveat prominently in `APPLIED.md`**: after a sweep, no per-stage
attribution is possible until the agents are reset and re-activated one at a time
(`./activate.sh <agent-id> reset`).

Undo at any time: `./activate.sh <agent-id> reset`.

---

## 8. Record, then hand back

Write to `prompts/APPLIED.md` — the durable record, because the next
`cli advice` wipes the JSON. It must contain, in this order:

1. **Previous-pass audit** (§2) — which prior rules landed, which did not, which
   metric moved backwards. This is the most valuable section in the file.
2. **Applied** — each rule, with **distinct-brief support** for it, and whether the
   support is deterministic or judge prose.
3. **Rejected, and why.** This matters more than the applied list. Anything you
   dropped as domain-specific, unverifiable, or a checker artefact goes here so
   the next pass does not re-apply it.
4. **Unreachable** — guardrail-targeted advice.
5. **Harness observations** — anything you found that is not a prompt problem.
   Note it; do not fix it.
6. **Line-count delta** v2 → v3, per stage.

Then stop and tell the user what to run. **Do not run the eval yourself** — it
dispatches on Bedrock and costs real money.

```bash
cd backend/evals/minimal
./eval.sh configs/aws_1_fraud_review.yaml --advise
```

...and, once it finishes, remind them the comparison is only readable against a
run judged by **the same instrument** (§3a):

```bash
cd backend
python3.11 -m evals.minimal.cli compare <OLD_RUN_ID>:<stage> <NEW_RUN_ID>:<stage>
```

Read the delta honestly. If the edit matters it should show on the mechanical
counts in §2 too — and those don't drift.

---

## 9. Do not

- Change anything outside `prompts/agents/*.vN.md` and `prompts/APPLIED.md`.
- Run the eval or the judge.
- Edit an existing version file, or anything under `backend/agents/prompts/`.
- Use `count`/`runs` from `advices.json` as a recurrence signal.
- Quote a delta between two different judges, or between the single-threaded and
  sub-agent opus methods.
- Write a rule from a judge finding you have not verified against the artifact.
- Restate a rule that the §2 audit shows already landed.
