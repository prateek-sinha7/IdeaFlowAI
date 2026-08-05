# Contracts — API / Interaction: The Grading Dashboard

## HTTP / REST / RPC surface: **NONE**

This feature exposes **no** HTTP endpoint, no RPC method, no GraphQL field, and no WebSocket
message. It is an offline static-file renderer. Nothing is served, and nothing listens.

The contracts that do exist are three: a **Python API**, a **CLI**, and the **generated page
contract** (paths, URL fragments, DOM hooks). All three are consumed inside this repo, so they are
versioned by the code, not by a wire protocol.

---

## 1. Python API — `evals.grading.site`

```python
def build_site(runs_root: Path, *, force: bool = False) -> Path: ...
def build_run_pages(run_dir: Path) -> Path: ...
def export_run(run_dir: Path, *, max_bytes: int = 8 * 1024**2) -> Path: ...
```

### `build_site(runs_root, *, force=False) -> Path`

| | |
|---|---|
| **Does** | Scans every `<workflow>/<run>/` under `runs_root`, classifies each run, renders the dashboard and every run's pages |
| **Returns** | Path to `runs_root / "index.html"` |
| **Skips** | A run whose `reports/run.html` is newer than its `artifacts/`, `run_summary.json`, and `prompts/` — unless `force=True` |
| **Raises** | `FileNotFoundError` if `runs_root` does not exist. **Never** raises for a single malformed run — that run is classified `error`, badged, and the build continues |
| **Side effects** | Writes only `index.html` and files under each run's `reports/`. Touches nothing else |
| **Cost** | Free. No model call, no dispatch, no network |
| **Determinism** | Same inputs ⇒ byte-identical outputs |

### `build_run_pages(run_dir) -> Path`

| | |
|---|---|
| **Does** | Renders `reports/run.html` plus one `reports/<agent_token>.html` per stage with a `score` artifact |
| **Returns** | Path to `run.html` |
| **Raises** | `FileNotFoundError` when `run_summary.json` is absent. A missing *optional* artifact omits its section — never raises |
| **Degrades** | `compute_overall() is None` ⇒ the page states nothing was gradable rather than showing a grade |

### `export_run(run_dir, *, max_bytes=8MB) -> Path`

| | |
|---|---|
| **Does** | Renders one self-contained file: run page + all stage pages as in-page tabs, previews inlined as sandboxed `srcdoc` |
| **Returns** | Path to `reports/<dataset_run_id>.export.html` |
| **Budget** | Previews inlined largest-value-first until `max_bytes`; the remainder become **labelled placeholders** naming the `src/` path. Never a silent omission |
| **Guarantee** | Grade, phase table, and row scores are **identical** to that run's `run.html` (shared section builders; asserted by test) |

### Consumed contracts (upstream — this feature must not restate their logic)

| Called | Contract relied on |
|---|---|
| `grades.compute_overall(run_dir)` | Returns `{score, grade, counted, failed_cells, stages}` or **`None`**. `None` is a legal, expected value |
| `grades.letter_grade(score)` | A++ ≥97, A+ ≥93, A ≥90, B ≥80, C ≥70, D ≥60, E ≥50, else F |
| `compare.group_by_prompt(runs)` | Groups by `system_prompt_hash`, chronological by first-seen, with met/not-met against baseline |
| `compare.noise_band(runs)` | 2σ, floor 1.0 (0.01 for `precheck_pass_rate`) |
| `code_grader.read_findings(run_dir, token)` | `{deliverable_file, findings: {row_id: {...}}}` or falsy |
| `code_grader.blended_score(judge, code)` | 0.7 / 0.3, tolerating either being `None` |
| `scoring.judge_errored(grade)` / `judge_error_reason(grade)` | Judge-failure detection |
| `artifacts.*` | Sole owner of every run-folder path |
| `render.*` | Number/flag/hash formatting, `DASH` for absent values |

### Provided contract (downstream)

`markdown_report.write_report(run_dir)` calls `site.builder.rebuild_for_run(run_dir)` at its end,
**best-effort**: any exception is caught and logged as a warning. Its return value is unchanged
(the markdown path), so existing callers are unaffected.

**Invariant**: a failure in this feature can never fail a grading run or prevent the markdown
report from being written.

---

## 2. CLI contract — `grade.sh dashboard`

```
./evals/grading/grade.sh dashboard [--force] [--export <run-id>] [--open]
```

| Flag | Effect |
|---|---|
| *(none)* | Incremental rebuild of the dashboard and all run pages |
| `--force` | Re-render every run, ignoring the mtime skip |
| `--export <run-id>` | Additionally write that run's single-file export |
| `--open` | Open `index.html` in the default browser after building |

| | |
|---|---|
| **Cost** | **Free** — listed with `report`, `code`, `compare`, `runs`, not with the `[LIVE]` commands |
| **Exit codes** | `0` success (including when some runs were classified `error`); `2` usage error; `1` unrecoverable (e.g. `.runs/` missing) |
| **stdout** | Runs scanned, rendered, skipped; the `index.html` path; export path when requested |
| **stderr** | One line per run classified `error`, naming the file and reason |
| **Help** | A usage line added to the `grade.sh` header block that `help` prints (`sed -n '2,57p'`) |

Existing commands `run` / `rejudge` / `code` / `report` additionally print the rebuilt dashboard and
run-page paths beside the markdown path. No existing flag, argument, or exit code changes.

---

## 3. Generated page contract

### Paths

| Page | Path |
|---|---|
| Dashboard | `.runs/index.html` |
| Run | `.runs/<workflow>/<dataset_run_id>/reports/run.html` |
| Stage | `.runs/<workflow>/<dataset_run_id>/reports/<agent_token>.html` |
| Export | `.runs/<workflow>/<dataset_run_id>/reports/<dataset_run_id>.export.html` |

`<agent_token>` is `agent_id.replace("-", "_")` — the same form the artifact filenames use, so a
stage page sits beside its own artifacts under one naming rule.

### URL fragment contract (deep links)

| Fragment | Meaning |
|---|---|
| `#run=<dataset_run_id>` | Dashboard: highlight/scroll to that run |
| `#view=<view-id>` | Dashboard: open that view (`trend`, `prompts`, `dimensions`, `matrix`, `cost`) |
| `#stage=<agent_token>` | Export/run page: select that tab |
| `#row=<row_id>` | Stage page: scroll to and expand that row |
| `#stage=<t>&row=<r>` | Both, combined |

Fragments are **read on load** and **written on interaction**, so any state a reader reaches is
linkable. Unknown or stale fragment values are ignored silently — a link to a deleted row must not
break the page.

### Structural guarantees (asserted by test)

| # | Guarantee |
|---|---|
| G1 | No `src`/`href` to a remote host; no `fetch(`; no `XMLHttpRequest` |
| G2 | Every preview `<iframe>` has `sandbox` **without** `allow-scripts` and **without** `allow-same-origin` |
| G3 | Inlined data lives in `<script type="application/json">` with `</` neutralised |
| G4 | Every interpolated model string is HTML-escaped |
| G5 | Output is byte-deterministic across renders |
| G6 | No score is computed in JavaScript — JS only sorts, filters, and toggles |
| G7 | Every charted value also appears as text (table or title) |

### Browser support

Current Chrome, Safari, Firefox, Edge, opened via `file://`. No polyfill, no transpilation, no
feature requiring a secure context.

---

## 4. Versioning & compatibility

- **Backward compatible with older run folders**: any absent input omits its section. A run folder
  predating captured `prompts/` renders fully, with the prompt-diff control disabled and the reason
  shown.
- **No compatibility burden on generated output**: pages are disposable and reproducible, so their
  markup is free to change between commits without migration.
- **Breaking change policy**: removing or renaming a `site` public function, a CLI flag, or a
  fragment key is a breaking change to this contract and requires updating this file in the same
  commit.
