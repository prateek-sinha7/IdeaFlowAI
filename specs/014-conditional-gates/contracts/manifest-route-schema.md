# Contract: `route:` manifest key (workflow-authoring interface)

The interface workflow authors (human or the composer UI, R-25) write against. Enforced by
`agents/workflows/compiler.py::_compile_route` (Phase 1 of plan.md).

## Shape

```yaml
- agent: <any agent id>
  instance_id: <existing field, unchanged>
  produces: ["route_decision"]      # REQUIRED if this step is any route's condition_agent (R-27)
  gates:
  - conditional                     # REQUIRED if `route:` is declared (R-03)
  route:
    condition_agent: <step id>      # OPTIONAL — default: this step's own id (R-05)
    outcomes:
      <condition value>:
        trigger: step | workflow    # REQUIRED
        target: <step id | workflow id | "self">   # REQUIRED
      <condition value 2>:
        trigger: ...
        target: ...
    default_next: <step id>         # OPTIONAL — default: run terminates if no outcome matches
    loop_max_iterations: 5          # OPTIONAL — default 5 (R-07)
    trigger_max_depth: 5            # OPTIONAL — MUST equal 5 in v1 (R-19, clarified); compiler
                                     # rejects any other declared value
```

## Compile-time guarantees (what a workflow author can rely on)

1. **Strict keys.** `route:` accepts exactly `condition_agent`, `outcomes`, `default_next`,
   `loop_max_iterations`, `trigger_max_depth` — any other key is a compile error (INV-5, no-DSL).
   Each `outcomes[...]` entry accepts exactly `trigger`, `target`.
2. **Gate/route consistency (R-03).** `route:` present without `"conditional"` in `gates:` is a
   compile error. `"conditional"` in `gates:` without a non-empty `route.outcomes` is a compile
   error. Never a silent no-op either direction.
3. **Every target resolves (R-10).** `trigger: step` targets are checked against the compiled
   step-id set of THIS workflow. `trigger: workflow` targets are checked against real saved
   workflow ids, or the literal `"self"`. `default_next` is checked the same way as a `step`
   target. An unresolvable reference is a compile error naming the offending step and target —
   never a runtime 404 or silent no-op.
4. **Decision source is declared (R-27).** `route.condition_agent` (or the step itself, when
   unset) MUST declare `produces: ["route_decision"]`. A `conditional` gate whose decision
   source never produces the required typed artifact is a compile error, not a confusing
   runtime "gate found nothing to read."
5. **`trigger_max_depth` is fixed (R-19, clarified 2026-08-20).** The ONLY valid declared value
   in v1 is `5` (equal to the default — omitting the key is equivalent to declaring it).
   Declaring any other integer is a compile error. This will change in a future spec if the
   ceiling is ever raised; until then, treat the field as effectively constant.
6. **No DSL, ever.** `outcomes` values are pure data — `target` is always a plain string id,
   never an expression, template, or conditional syntax. The gate resolves WHICH outcome
   applies at runtime by matching a typed decision value; the manifest never encodes the
   condition logic itself (INV-5).

## Runtime contract (what the gate does with valid config)

Given a compiled `route.outcomes = {"pass": {trigger: step, target: D}, "fail": {trigger: step,
target: analyse}}`:

1. Read `condition_agent`'s (or self's) `route_decision` typed artifact.
2. `json.loads` the content; extract `parsed["decision"]`.
3. Match against `outcomes` keys.
4. **Match found** → `GateOutcome(GATE_ROUTE, detail={"trigger": ..., "target": ...})`.
5. **No match, `default_next` set** → engine advances to `default_next` (same as a normal
   forward step, no special routing).
6. **No match, `default_next` unset** → the run terminates at this step (same "nowhere to go"
   shape as R-13's stop-and-hand-off).
7. Malformed JSON, or JSON with no `"decision"` key → treated identically to "no match" (step
   5/6 above) — never a crash, never silently ignored (an observable event/log line should
   record this, exact mechanism confirmed during Phase 1 implementation).

## Example (from the reference fixtures)

```yaml
# backend/agents/workflows/ex_A2_branch/workflow.yaml
- agent: custom-agent
  instance_id: pick
  produces: ["route_decision"]
  gates:
  - conditional
  route:
    outcomes:
      english: {trigger: step, target: say_hello}
      spanish: {trigger: step, target: say_hola}
    # no default_next — unrecognised decision terminates here
```
