# `datasets/` — the rows a run is driven by

One file per dataset, free-form filename, each carrying its own `dataset_id`. A run config
names the file it wants:

```yaml
dataset: datasets/ten-industries.json
```

Relative paths resolve against the workflow folder; an absolute path works for a scratch
dataset outside the repo.

| File | `dataset_id` | Rows |
|---|---|---|
| `ten-industries.json` | `ten-industries` | 12 — 11 real briefs across distinct verticals, plus one negative test |

## Why datasets are not named after an agent

They used to be `<agent_token>_dataset.json`, which quietly asserted that a dataset belongs
to one agent. It does not. The `output.json` a stage generates uses the **same envelope as a
dataset file**, deliberately — so promoting one stage's output into the next stage's input is
a copy. Under the old naming that promotion was also a rename, and the file's name claimed
ownership that the content did not have.

Binding a dataset to an agent happens in the **run config**, where it belongs, because the
same dataset can legitimately drive different agents.

## `for_agent` — an advisory guard

Decoupling introduces one footgun: nothing stops you handing `prototype-plan`'s generated
specs to `prototype-specify`, which would produce confident nonsense. So a dataset may
declare its intended consumer:

```json
{ "dataset_id": "ten-industries", "for_agent": "prototype-specify", "rows": [...] }
```

Optional, and validated only when present — a generated output that genuinely suits several
stages simply omits it. When it is present and does not match the agent being run, the run
fails loudly.

## Row contract

`id` (stable across every stage — never suffix it per agent), `industry`, `tags`, `prompt`,
and optional `expect: fail` for a negative test. Full contract in
[`../../../_templates/dataset.json.template`](../../../_templates/dataset.json.template).
