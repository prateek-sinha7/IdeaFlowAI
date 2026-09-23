# Contract: `pipeline_diverted` SSE/websocket event (frontend interface)

The interface the frontend's live-run stream consumer (and any other SSE listener) codes
against. Emitted by `engine.py` (Phase 4 of plan.md), through the same generic event-forward
path `pipeline_cancelled` already uses.

## When it fires

Exactly once, at the moment a `trigger: "workflow"` route outcome fires and the triggering
run's `WorkflowRun.status` transitions to `"diverted"` (R-14/R-28). Never fires for a
`trigger: "step"` outcome (in-workflow routing has no terminal event of its own — the run's
dispatch loop simply continues, same as any other step transition).

## Shape

```json
{
  "type": "pipeline_diverted",
  "data": {
    "pipeline_run_id": "<the triggering run's id>",
    "diverted_to_run_id": "<the newly-minted run's id>",
    "diverted_to_workflow": "<the target workflow id, or the SAME id if target was \"self\">"
  }
}
```

## Guarantees

1. **Additive, never a repurposed existing type (INV-3, decision-log #18).** Existing
   `pipeline_complete`/`pipeline_cancelled` handlers are unaffected by this event's
   introduction — a listener that only checks `event.type === "pipeline_complete"` for
   "did this run finish successfully" will correctly NOT match a diverted run, rather than
   silently misreading it as a normal completion.
2. **Terminal for THIS run's stream.** No further events follow a `pipeline_diverted` on the
   SAME `pipeline_run_id`'s stream — the triggering run's dispatch loop has ended (R-13).
3. **The new run is a SEPARATE stream.** `diverted_to_run_id` is a pointer, not an inline
   continuation — a frontend consumer that wants to follow the triggered run's own progress
   must open/subscribe to that id's OWN stream. `pipeline_diverted` carries no events from the
   new run.
4. **`diverted_to_workflow` is always resolvable.** Even when the manifest declared `target:
   "self"`, this field reports the actual workflow id (never the literal string `"self"`) — so
   a frontend consumer never needs to special-case the sentinel value.

## Consumer contract (what R-20's run-history UI does with this)

- **Live case**: a run-view subscribed to `pipeline_run_id`'s stream, on receiving
  `pipeline_diverted`, renders the terminal state as "Diverted to `{diverted_to_workflow}` →"
  with a link to `diverted_to_run_id`, rather than the normal "Completed" treatment.
- **Historical case** (page load after the fact, no live stream): the same rendering is driven
  by `WorkflowRun.status == "diverted"` + `parent_run_id` lookups — the event is a LIVE-only
  convenience, not the sole source of truth. A page that never saw the live event (because the
  browser wasn't open when it fired) must be able to reconstruct the same UI purely from
  persisted `WorkflowRun` rows.

## Non-goals

- No `pipeline_diverted` analog exists for the triggered run's own "I was spawned by a divert"
  moment — that run's OWN stream just starts normally at its own step 0; the "← Continued from
  `{parent}`" breadcrumb (R-20) is reconstructed from `parent_run_id`, not from a dedicated
  event on the child's stream.
- No event carries progress/status of the triggered run back to the triggering run's stream —
  by design (R-13, stop-and-hand-off; no wait, no merge). See spec.md §5.1 examples B2/B3 for
  the deferred synchronous-wait alternative this contract deliberately does not support.
