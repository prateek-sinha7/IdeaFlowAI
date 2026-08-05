# Contracts — Integrations: The Grading Dashboard

## Summary: **NONE**

No external service, no third-party API, no event, no message queue, no background job, no webhook,
no scheduled task, no telemetry, no outbound network call of any kind.

This is recorded explicitly rather than omitted, because "no integrations" is a **design
requirement** of this feature, not an accident of its current scope.

| Integration class | Status |
|---|---|
| External HTTP APIs | None |
| LLM / model providers (Anthropic, Bedrock, Mistral) | **None — this feature never calls a model** |
| Databases (Postgres, etc.) | None |
| Message queues / brokers | None |
| Background jobs / schedulers / cron | None |
| Webhooks (in or out) | None |
| Object storage / S3 / CDN | None |
| Auth providers | None |
| Telemetry / analytics / crash reporting | None |
| Package dependencies added | **None** — stdlib only |
| Browser network requests from generated pages | **None** — asserted by test |

---

## 1. Why this is a requirement, not a coincidence

Three properties of this feature depend on having no integrations:

1. **Free and offline.** Every other command in the grading harness is annotated free or `[LIVE]`
   because live ones spend tokens. `dashboard` must be permanently, unambiguously free — the
   rendering path must never be able to call a model.
2. **Opens by double-click.** A generated page that fetches anything is broken under `file://`
   (browsers block `fetch()`/XHR against opaque origins). No network access is what makes the
   double-click requirement satisfiable.
3. **Shareable without leaking.** The one-file export is sent to people. A page that phoned home —
   for a font, a script, an analytics beacon — would disclose that the report was opened, and to
   whom. Zero outbound requests means the export discloses nothing beyond its own content.

**Enforcement**: a test greps generated output for remote `src`/`href`, `fetch(`, and
`XMLHttpRequest` and fails the build on any hit (G1 in the API contract). This is a gate, not a
guideline.

---

## 2. Internal module contracts (in-repo, not integrations)

The only cross-boundary dependencies are Python imports inside `backend/evals/grading/`. They are
listed here for completeness; each is detailed in [`api-contract.md`](api-contract.md) §1.

| Direction | Module | Contract |
|---|---|---|
| consumes | `grades` | `compute_overall`, `letter_grade`, `GRADE_BANDS` (extracted from `markdown_report`, re-exported there) |
| consumes | `compare` | `group_by_prompt`, `noise_band`, `AGGREGATE_METRICS`, `HEADLINE_METRIC` |
| consumes | `code.code_grader` | `read_findings`, `blended_score` |
| consumes | `model.scoring` | `judge_errored`, `judge_error_reason` |
| consumes | `artifacts` | Every run-folder path and every artifact read |
| consumes | `render` | Value formatting, `DASH` |
| **provides** | `markdown_report.write_report` | Calls `site.builder.rebuild_for_run()` **best-effort**; return value unchanged |
| **provides** | `grade_runner` | New `dashboard` subcommand; run/code/report output prints the site paths |

**The one behavioural invariant across this boundary**: a failure inside `site/` can never fail a
grading run, and can never prevent the markdown report from being written. All three existing
`write_report` call sites already wrap the call in `try/except` with an explicit *"rendering is
never load-bearing"* comment; the site build additionally catches its own exceptions.

---

## 3. Filesystem contract

The filesystem is the only external resource touched.

### Reads

Everything under `<grading root>/.runs/<workflow>/<dataset_run_id>/`: `run_summary.json`,
`grade_config.resolved.yaml`, `artifacts/*.json`, `prompts/*.md`, `src/**`, `logs/**`,
`reports/prompt_advice_*.{md,json}`. Read-only, via `artifacts.*` helpers exclusively.

### Writes

| Path | When |
|---|---|
| `.runs/index.html` | Every build |
| `<run>/reports/run.html` | Run's artifacts newer than the page, or `--force` |
| `<run>/reports/<agent_token>.html` | ″ |
| `<run>/reports/<dataset_run_id>.export.html` | `--export` only |

**Nothing else is written, moved, renamed, or deleted.** In particular: no artifact, no
`superseded/` entry, no `src/` file, no log, and no existing markdown report is modified. The
append-only guarantee of a run folder (`artifacts.guard_append_only`) is untouched because this
feature never writes to `artifacts/`.

### Version control

Generated HTML lives inside `.runs/`, which is gitignored — consistent with every other run
artifact. Nothing this feature produces is committed. (Task: confirm no `.gitignore` rule
inadvertently un-ignores `*.html`.)

---

## 4. Security posture

| Concern | Position |
|---|---|
| Untrusted input | Judge rationales and agent deliverables are **untrusted HTML** and are treated as such: one `_esc()` choke point, `</`-neutralised inline JSON, previews in `sandbox`ed iframes without `allow-scripts` or `allow-same-origin` |
| Secrets | None read, none embedded. Config is read from `grade_config.resolved.yaml`, which carries model ids and options — no credentials. **Task-level check**: confirm no API-key-shaped value can reach a page |
| Outbound data | Zero. No page makes any request |
| Code execution | None. Generated JS only sorts, filters, and toggles; preview iframes cannot execute scripts |
| Sharing | The export contains whatever the run contained — briefs, model outputs, prompts. Anyone sharing one should know it carries the full system prompt. **Noted on the export page itself** |

That last point is the only genuine disclosure consideration in this feature: a one-file export
embeds the captured system prompts, which are the intellectual content of the agents. The page
states this so nobody discovers it after sending one.
