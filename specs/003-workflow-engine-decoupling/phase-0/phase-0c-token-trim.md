# Phase 0C — Token-trim: wire the HTML-skeleton compaction (detailed plan)

> **Goal:** wire the **dead** `_extract_html_skeleton` (`engine.py:2565-2628`, leak **L13**, Tier #1)
> as the build-task-2+ context, replacing the O(n²) full-HTML re-injection. This is the **one
> sanctioned behavior change** in Phase 0 — it alters the build prompt for tasks 2+, so generated
> edits may differ. It is therefore **NOT** gated on byte-identity but on: (a) the 0A **semantic**
> snapshot staying green (event types/order/structure unchanged), (b) a **measured token reduction**
> on a multi-task build, and (c) **equal-or-better validation pass rate**.
>
> **Accept (003 §25):** equal-or-better validation pass rate; measured token reduction on a
> multi-task build.

Parent: [Phase 0 README](README.md) · Prev: [0B](phase-0b-execution-context.md)

---

## C1. The problem today — O(n²) full-HTML re-injection

The prototype build runs **one sub-agent per task** (`_run_build_task_loop`). For each task, `_build_context_message` injects the **entire current `prototype.html`** into the build prompt (`engine.py:2491-2501`):

```python
current_html = accumulated_outputs.get("prototype-build", "")          # the doc so far
if current_html and not current_html.startswith("[Error:"):
    html_to_pass = current_html[:120000]                               # up to 120k chars
    truncated = len(current_html) > 120000
    parts.append(f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n{html_to_pass}…")
```

For task 1 `current_html` is empty (nothing built yet) → no injection. For **task 2..N** the whole growing document is re-sent every task → the build's input tokens grow ~quadratically with task count, the dominant cost/latency driver on multi-page prototypes. (Today's only mitigation is the task-2+ slimming of DS/template/reference blocks at `engine.py:2386-2458` — but the big payload, the full HTML, is still sent in full.)

## C2. The asset — the skeleton that was built and never wired (L13)

`_extract_html_skeleton(self, html) -> str` (`engine.py:2565-2628`) already produces a compact (~1-3k char) orientation summary from the full HTML:

- `:root` design tokens (the 6 key vars),
- the `const routes = {…}` map,
- `<section data-page>` IDs partitioned into **filled** vs **empty**,
- chrome type (sidebar/topnav),
- total HTML size.

Its own docstring states the intent verbatim: *"instead of passing the full HTML (which grows with every task and causes O(n²) slowdown), extract only what the build agent needs."* It is **dead code** — built, never called (the "token-trim that was never wired", §4 L13). **0C wires it.**

## C3. The change

In `_build_context_message`, for the `prototype-build` current-state injection (`engine.py:2491-2501`), replace the full-HTML block with the skeleton + an explicit instruction to read the file before editing:

```python
# 0C: inject a compact skeleton instead of the full document. The build agent
# edits prototype.html in place on disk (read_file/edit_file) — the loop already
# reads it back each task — so it does NOT need the whole doc inlined; it needs
# orientation (what's built, tokens, routes, chrome) + a pointer to read the file.
current_html = accumulated_outputs.get("prototype-build", "")
if current_html and not current_html.startswith("[Error:"):
    skeleton = self._extract_html_skeleton(current_html)            # L13 now wired (was dead)
    parts.append(
        "\n--- CURRENT PROTOTYPE STATE (summary) ---\n"
        f"{skeleton}\n"
        "Call read_file(file_path=\"prototype.html\") to see the full current document, "
        "then apply MINIMAL edit_file changes for THIS task. Do NOT rebuild from scratch.\n"
        "--- END CURRENT PROTOTYPE STATE ---"
    )
```

Notes:
- This fires only for task 2+ (task 1 has no `current_html`), which is exactly the O(n²) region.
- The build agent already has FS read/write (it edits `prototype.html` in place; the loop reads it back at `engine.py:1561,1595`), and the validation-fix prompts already instruct `read_file("prototype.html")` — so "read the file to edit" is consistent with the existing protocol.
- Keep the task-2+ slimming of DS/template/reference blocks (`engine.py:2386-2458`) unchanged — 0C only swaps the HTML payload.
- After 0B this method already takes `ctx`; 0C edits the `ctx`-aware version (no rework — the [README §4] ordering reason).

## C4. Why this is a behavior change (and what that means for gating)

The build sub-agent for tasks 2+ now sees a **summary + a read instruction** instead of the **full inlined document**. Its generated `edit_file` calls may differ. Therefore:

- **Not** gated on byte-identity (INV-3's sanctioned exception — 003 §25 Phase 0C, §24).
- **Invisible to the scripted-harness snapshots by design:** the `ScriptedFakeChatModel` ignores its input and emits canned output, and `context_message` is a **volatile field normalized out** of the 0A semantic snapshot ([0A §A2]). So under the scripted harness the deliverable bytes and the normalized event stream are **unchanged** — which is the point: it proves 0C introduces **no structural/vocabulary regression**. The *substance* of 0C (smaller context, equal-or-better quality) is validated by the two measurements below, on **real** builds.

So 0C has three gates, in increasing fidelity:

| Gate | Mechanism | What it proves |
|---|---|---|
| **G1 — structure** | re-run 0A semantic snapshots (no `--snapshot-update`) | event types/order/required fields unchanged; no accidental vocab change |
| **G2 — token delta** | deterministic context-size measurement (C5.1) | the injected build-2+ context shrinks materially |
| **G3 — quality** | validation pass-rate eval on real multi-task builds (C5.2) | edits stay equal-or-better (no quality regression from the smaller context) |

## C5. Measurement plan

### C5.1 Token delta (deterministic, automated)

The reduction is in **input/context** tokens, so measure the **injected context string**, not model output. A deterministic test:

1. Build a fixture with a **large, multi-section `prototype.html`** on disk (e.g. an 80k-char doc with 6 `<section data-page>`, `:root` tokens, a routes map) — representative of a mid-build state.
2. Call `_build_context_message` for a `prototype-build` task with `accumulated_outputs["prototype-build"]=<that 80k HTML>` and `_build_task_number="3"`.
3. Measure the size of the returned message **before** (full-HTML branch) vs **after** (skeleton branch) — char count and a token estimate (use the model factory's tokenizer if cheap, else `chars/4` as a documented proxy).
4. **Assert a material reduction** (e.g. the CURRENT-STATE block drops from ~80k chars to ~1-3k; assert >70% reduction of that block, or >50% of the whole message on a large doc). Encode the threshold as the test's acceptance.

A focused unit test (`tests/unit/test_html_skeleton_compaction.py`) can hold both the before/after measurement and the skeleton-correctness checks (C6).

### C5.2 Validation pass-rate (live / measured)

Quality can't be judged by a scripted model. Use a small **live** eval (opt-in, `@pytest.mark.requires_api_key`, or a one-off measurement script run by hand):

1. Pick 3-5 representative briefs that produce **multi-task** prototypes (≥3 tasks).
2. Run each **twice** — once on `HEAD~` (full-HTML) and once on the 0C branch (skeleton) — with a fixed model.
3. For each result run `static_check` + `render_check` and record: P0/P1 issue counts, dead-nav count, render-ok.
4. **Accept iff** the 0C runs are **equal-or-better** (no increase in P0s / dead navs; render-ok preserved) **and** input-token totals are measurably lower.

Record the eval results in the 0C PR description (numbers, not adjectives). This is the real acceptance for G3; G1+G2 are the automated guards.

## C6. Pre-wiring: unit-test the never-run function first

`_extract_html_skeleton` has **never executed** in production — treat it as unverified. Before wiring, add `tests/unit/test_html_skeleton_compaction.py` asserting it on representative HTML:

- extracts the 6 `:root` tokens; handles a missing `:root` (no crash, omits the section);
- parses `const routes = {…}` when present; omits cleanly when absent;
- partitions `<section data-page>` into filled (>100 non-comment chars) vs empty;
- detects chrome (sidebar via `<aside`/`data-od-id="sidebar"`; topnav via class/`data-od-id`);
- returns a bounded (~1-3k char) string on an 80k input;
- no exception on malformed/empty HTML.

Fix any bug the test surfaces in the same change (it's been dead, so a latent bug is plausible — e.g. the routes f-string at `engine.py:2597`).

## C7. Relationship to Phase 2

0C wires the trim **inline** (the dead helper becomes live, called from `_build_context_message`). Phase 2 re-expresses it as a registered **`CompactionStrategy(html_skeleton)`** referenced by the prototype manifest's `compaction: html_skeleton` ([plan §10], [plan §16]), and **deletes the inline copy** — ledger **L13 (0C→2)**: "inline copy removed; only the strategy remains." So in 0C the L13 ledger item stays `pending` (the symbol is now *used*, not deleted); it flips to `done` in Phase 2 when the strategy supersedes it. 0C must keep the skeleton logic in a form that Phase 2 can lift wholesale (don't entangle it further into `_build_context_message` than the single call above).

## C8. Ordered task checklist (0C)

1. Land 0A + 0B first.
2. Add `tests/unit/test_html_skeleton_compaction.py` (C6); fix any latent bug in `_extract_html_skeleton`.
3. Add the deterministic token-delta measurement test (C5.1) — first capturing the **before** (full-HTML) baseline.
4. Make the C3 edit in `_build_context_message` (skeleton + read instruction for task 2+).
5. Run G1: 0A semantic snapshots green (no `--snapshot-update`); deliverable snapshot unchanged under the scripted harness (expected — confirms no structural regression).
6. Run G2: token-delta test passes the reduction threshold.
7. Run G3: the live validation-pass-rate eval (C5.2); record numbers in the PR.
8. Leave ledger **L13** `pending` (the helper is now wired, not deleted; it's removed in Phase 2). Do **not** flip it.
9. Full suite green: `cd backend && python3.11 -m pytest tests/characterization tests/unit tests/agents tests/test_migration_ledger.py -v`.

## C9. Definition of Done (0C)

- [ ] `_extract_html_skeleton` unit-tested and (if needed) fixed; no longer dead.
- [ ] Build-task-2+ context injects the skeleton + a read-file instruction instead of the full document; task 1 unchanged.
- [ ] **G1:** 0A semantic snapshots green; scripted deliverable unchanged (no structural/vocabulary regression).
- [ ] **G2:** measured token reduction on a large multi-task context (threshold met, numbers recorded).
- [ ] **G3:** validation pass-rate equal-or-better on the live multi-task eval (numbers recorded in the PR).
- [ ] Skeleton logic kept liftable for Phase 2's `CompactionStrategy`; L13 left `pending` in the ledger.

## C10. 0C-specific risks

- **R0C-1 Quality regression** — the skeleton omits context the build agent needed inline, so edits get worse. *This is the central risk.* *Mitigation:* G3 gate (equal-or-better pass rate) blocks the merge; the read-file instruction + the agent's existing FS access preserve full-document access on demand; if G3 fails, enrich the skeleton (e.g. include more per-section detail) or abandon 0C until Phase 2's strategy can iterate on it.
- **R0C-2 Agent doesn't read the file** — given only a summary, the model edits blind. *Mitigation:* explicit `read_file("prototype.html")` instruction (mirrors the validation-fix prompts that already work); G3 catches it if it doesn't.
- **R0C-3 Latent bug in the never-run helper** — *Mitigation:* C6 unit test before wiring.
- **R0C-4 Over-coupling to `_build_context_message`** — would make Phase 2's extraction harder. *Mitigation:* keep 0C to the single-call swap in C3; the skeleton body stays a standalone method Phase 2 lifts into the strategy.
- **R0C-5 Token measurement proxy** — `chars/4` is approximate. *Mitigation:* use the real tokenizer if available; the reduction is large enough (~80k→~2k on the payload) that the proxy is conclusive regardless.
