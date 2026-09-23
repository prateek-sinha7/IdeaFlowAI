export const meta = {
  name: 'conditional-gates-014-remaining',
  description: 'Fix the two precisely-diagnosed test bugs (T27, T33) V4 found, re-verify V4, then run V6 — spec 014 conditional gates remainder only',
  phases: [
    { title: 'Fix T27/T33', detail: 'two already-diagnosed regression-test bugs, not implementation bugs' },
    { title: 'Re-verify V4', detail: 'Phase 4 gate — AC-05/AC-06/AC-11 already confirmed PASS, just re-run after fixes' },
    { title: 'V6', detail: 'Phase 5 acceptance, AC-07/AC-08' },
  ],
}

// ---------------------------------------------------------------------------
// This is a SEPARATE, focused successor to workflow.js, scoped ONLY to the
// items that were not confirmed done as of the last full run: T27, T33 (their
// OWN regression tests have bugs; the implementations they guard are already
// correct, confirmed by V4's real end-to-end harnesses), V4 (needs
// re-verification after the two fixes land), and V6 (still correctly blocked
// on V4). Built this way instead of resuming workflow.js because that script's
// non-deterministic concurrent scheduler does not reliably cache-hit already-
// done work across separate process launches (observed directly this session:
// a stop+resume caused ~10 already-done tasks to be silently, wastefully
// redispatched) — a small graph containing only the real remaining work avoids
// that entirely, and is cheap enough that a full run costs almost nothing.
// ---------------------------------------------------------------------------

const NODES = {
  T27: {
    kind: 'task', model: 'opus', phase: 'Fix T27/T33', deps: [],
    files: ['backend/tests/unit/test_rest_run_launch.py'],
    prompt: `Fix two specific, already-diagnosed bugs in backend/tests/unit/test_rest_run_launch.py (spec 014 conditional gates, T27's regression test). Do NOT touch backend/app/api/run_commands.py's _launch_run_core itself - it is already correct, confirmed by a separate V4 validation pass.

1. test_launch_run_core_is_plain_async_function_decoupled_from_fastapi FAILS: its "expected" param set is stale - missing parent_run_id_override, owner_id_override, workspace_id_override, trigger_depth, which T28 correctly added to _launch_run_core's signature (R-15/R-18 threading). Update the expected param set to include these four.

2. test_launch_run_core_called_directly_matches_http_endpoint_shape FAILS with TypeError: unhashable type: 'AgentSpec'. Root cause: the test does [load_agent_spec(aid) for aid in get_pipeline_agents("user_stories")], but get_pipeline_agents already returns list[AgentSpec] - passing an AgentSpec into load_agent_spec(agent_id: str) crashes on "agent_id in _SPEC_CACHE" (a plain, unhashable @dataclass). Fix: use get_pipeline_agents(...) directly as the agents= arg, remove the erroneous re-map through load_agent_spec.

After fixing, run: cd backend && python3.11 -m pytest tests/unit/test_rest_run_launch.py -v
Report the exact diff and confirm both named tests now pass.`,
  },

  T33: {
    kind: 'task', model: 'opus', phase: 'Fix T27/T33', deps: [],
    files: ['backend/tests/agents/test_conditional_trigger_budget_t33.py'],
    prompt: `Fix one specific, already-diagnosed bug in backend/tests/agents/test_conditional_trigger_budget_t33.py (spec 014 conditional gates, T33's regression test). Do NOT touch KernelServices.run_trigger_workflow itself - its (run_id, resolved_workflow_id) tuple return is deliberate and correct (needed by T29 for the SSE payload's diverted_to_workflow), confirmed by a separate V4 validation pass.

test_triggered_run_spend_visible_in_triggering_runs_workspace_aggregate FAILS every run: "triggered_run_id = await ks.run_trigger_workflow(...)" doesn't unpack the tuple - it gets assigned the whole (run_id, resolved_workflow_id) tuple, which then gets used as a DB filter value, crashing with sqlite3.ProgrammingError: type 'tuple' is not supported.

Fix: unpack correctly, e.g. "triggered_run_id, _resolved_workflow_id = await ks.run_trigger_workflow(...)". Production code (engine.py's own call site) already does this correctly - only this test doesn't.

After fixing, run: cd backend && python3.11 -m pytest tests/agents/test_conditional_trigger_budget_t33.py -v
Report the exact diff and confirm the test now passes.`,
  },

  V4: {
    kind: 'validator', model: 'sonnet', phase: 'Re-verify V4', deps: ['T27', 'T33'],
    guards: ['T27', 'T28', 'T29', 'T30', 'T31', 'T32', 'T33'],
    prompt: `You are re-verifying Validator V4 for Phase 4 (cross-workflow triggering), spec 014 conditional gates. A prior V4 run already confirmed AC-05, AC-06, AC-11, and the full-codebase TERMINAL_STATES grep sweep (T31) all PASS against the real production code - re-run the existing harnesses to reconfirm nothing regressed, do not re-derive from scratch:
- cd backend && python3.11 -m pytest tests/agents/test_conditional_divert_v4_validation.py -v   (AC-05, AC-11)
- cd backend && python3.11 -m pytest tests/agents/test_conditional_trigger_depth_v4_ac06.py -v  (AC-06)

The only items that were open: T27's and T33's own regression tests were failing on bugs in the TESTS themselves (now fixed by a prior task in this run). Run them now and confirm they pass:
- cd backend && python3.11 -m pytest tests/unit/test_rest_run_launch.py -v
- cd backend && python3.11 -m pytest tests/agents/test_conditional_trigger_budget_t33.py -v

Report PASS/FAIL per test file, and state your overall verdict as either "VERDICT: PASS" (if all four are green) or "VERDICT: FAIL" naming exactly which test file still fails and why.`,
  },

  V6: {
    kind: 'validator', model: 'sonnet', phase: 'V6', deps: ['V4'],
    guards: ['T35', 'T36', 'T37', 'T38'],
    prompt: `You are Validator V6 for Phase 5 (acceptance) of spec 014 (conditional gates). Guards: T35, T36, T37, T38.

Distinct from V5, which only checked the type contract - this validator checks the two ACs Phase 5 actually owns.

Verify AC-07: using the composer UI, author all three outcome kinds end-to-end - a trigger: step forward branch, a trigger: step backward loop, and a trigger: workflow divert - using the existing agent node (T35's editor) plus the one new external-pipeline reference node (T36); save, and confirm the emitted manifest's route: blocks match what was drawn, via the full-manifest path (T37).

Verify AC-08: run a workflow that diverts and confirm run history (T38) shows the two linked cards, each linking to the other, in BOTH the live case (stream open when the divert fires) and the historical case (fresh page load afterward). Phase 4's cross-workflow trigger mechanism is now confirmed working end-to-end (V4 passed) so this AC should be genuinely exercisable now - if it still fails, name the specific defect, do not assume Phase 4 is still the blocker without checking.

Report PASS/FAIL per AC with the specific evidence for each (the actual serialized manifest content, or a description of what you observed - not "looks right"). If ANY fail, return FAIL naming the specific task(s) to reopen.`,
  },
}

// ---------------------------------------------------------------------------
// Scheduler - same shape as workflow.js: dependency-graph executor, 4-way
// concurrency cap, file-collision serialization, bounded fix-and-reverify
// loop on validator FAIL (opus fixer for attempts 1-2, technical-lead
// escalation - also opus - for attempt 3 onward, per the Opus escalation
// exception in ~/.claude/CLAUDE.md).
// ---------------------------------------------------------------------------

const MAX_PARALLEL = 4
const MAX_FIX_ATTEMPTS = 5

const state = {}
const results = {}
const fixAttempts = {}
for (const id of Object.keys(NODES)) state[id] = 'pending'

function isReady(id) {
  const node = NODES[id]
  return state[id] === 'pending' && node.deps.every((d) => state[d] === 'done')
}

function filesInFlight() {
  const set = new Set()
  for (const [id, s] of Object.entries(state)) {
    if (s === 'running') {
      for (const f of NODES[id].files || []) set.add(f)
    }
  }
  return set
}

function collidesWithRunning(id) {
  const inFlight = filesInFlight()
  return (NODES[id].files || []).some((f) => inFlight.has(f))
}

async function runNode(id) {
  const node = NODES[id]
  state[id] = 'running'
  log(`-> ${id} [${node.model}] (${node.phase}) starting`)

  const label = node.kind === 'validator' ? `validate:${id}` : `task:${id}`
  const report = await agent(node.prompt, {
    label,
    phase: node.phase,
    model: node.model,
  })

  if (node.kind === 'task') {
    state[id] = report ? 'done' : 'error'
    results[id] = report
    log(`${state[id] === 'done' ? 'OK' : 'FAILED'} ${id}`)
    return
  }

  fixAttempts[id] = fixAttempts[id] || 0
  const text = String(report || '')
  const passed = /\bPASS\b/i.test(text) && !/\bFAIL\b/i.test(text.split('\n')[0] || '')
  const explicitFail = /\bFAIL\b/i.test(text)

  if (passed && !explicitFail) {
    state[id] = 'done'
    results[id] = report
    log(`VALIDATOR PASS ${id}`)
    return
  }

  log(`VALIDATOR FAIL ${id} (attempt ${fixAttempts[id] + 1}/${MAX_FIX_ATTEMPTS + 1})`)
  if (fixAttempts[id] >= MAX_FIX_ATTEMPTS) {
    state[id] = 'error'
    results[id] = report
    log(`VALIDATOR ${id} EXHAUSTED FIX ATTEMPTS - PHASE BLOCKED`)
    return
  }
  fixAttempts[id]++

  const escalate = fixAttempts[id] > 2
  const priorAttempts = Object.keys(results)
    .filter((k) => k.startsWith(`${id}-fix-`))
    .map((k) => `--- Prior attempt ${k.split('-fix-')[1]} ---\n${results[k]}`)
    .join('\n\n')

  const fixReport = await agent(
    (escalate
      ? `ESCALATION: two prior fix attempts already failed to clear this validator. Do not just try a ` +
        `third variation of the same guess - diagnose why the prior attempts didn't work first.\n\n` +
        `Prior fix attempts and their own reports:\n${priorAttempts}\n\n`
      : '') +
    `A validator for spec 014 (conditional gates) reported FAIL against tasks it guards: ${node.guards.join(', ')}.\n\n` +
    `Validator's full report:\n${text}\n\n` +
    `Read the validator's report carefully, identify EXACTLY which guarded task's work is deficient and why, ` +
    `then fix ONLY that specific problem in the codebase. Do not re-do unrelated work. ` +
    `Do not touch tasks not named as the cause of the failure. Report exactly what you changed and why it addresses the validator's specific complaint.`,
    escalate
      ? { label: `escalate:${id}`, phase: node.phase, model: 'opus', agentType: 'technical-lead' }
      : { label: `fix:${id}`, phase: node.phase, model: 'opus' }
  )
  results[`${id}-fix-${fixAttempts[id]}`] = fixReport

  await runNode(id)
}

async function scheduler() {
  const active = new Map()

  while (true) {
    const remaining = Object.keys(NODES).filter((id) => state[id] !== 'done' && state[id] !== 'error')
    if (remaining.length === 0) break

    const anyRunning = active.size > 0
    const anyReady = remaining.some((id) => isReady(id) && !collidesWithRunning(id))
    if (!anyRunning && !anyReady) {
      const stuck = remaining.filter((id) => state[id] === 'pending')
      log(`DEADLOCK: ${stuck.length} task(s) can never become ready: ${stuck.join(', ')}`)
      break
    }

    while (active.size < MAX_PARALLEL) {
      const next = Object.keys(NODES).find(
        (id) => isReady(id) && !collidesWithRunning(id) && !active.has(id)
      )
      if (!next) break
      const p = runNode(next).then(() => { active.delete(next) })
      active.set(next, p)
    }

    if (active.size === 0) break

    await Promise.race(active.values())
  }

  await Promise.all(active.values())
}

phase('Fix T27/T33')
phase('Re-verify V4')
phase('V6')

await scheduler()

const done = Object.keys(NODES).filter((id) => state[id] === 'done')
const errored = Object.keys(NODES).filter((id) => state[id] === 'error')

log(`Finished: ${done.length}/${Object.keys(NODES).length} done, ${errored.length} error(s)`)
if (errored.length) {
  log(`Blocked/failed nodes: ${errored.join(', ')} - see their reports for what to fix.`)
}

return {
  done,
  errored,
  results,
  summary: `${done.length}/${Object.keys(NODES).length} remaining nodes done. ` +
    (errored.length ? `Blocked at: ${errored.join(', ')}.` : 'Spec 014 fully green.'),
}
