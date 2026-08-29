#!/usr/bin/env node
// Scheduler regression harness for .claude/workflows/bug-hunt.js.
//
// Every scheduler defect this pipeline has shipped was found by a live 40-minute run
// burning real tokens, when a 2-second simulation would have caught it: the waterfall,
// the fix<->verify deadlock, the loader dropping status, prose in statusSet, the poller
// pushing into a finished phase, a blocked worker stranding its bug forever. Run this
// before any launch that follows an edit to the scheduler.
//
//   node bug-hunter/scheduler-sim.mjs
//
// It mirrors the scheduler core -- routing, handoff, claims, pools, termination -- with
// agents replaced by instant fakes. It does NOT import bug-hunt.js (a workflow script is
// self-contained and needs the agent()/parallel() globals), so when you change routing or
// termination in bug-hunt.js, change it here too. Keep it to the invariants; it earns its
// keep by failing, not by being exhaustive.

const FULL_LINE = ['validate', 'analyze', 'test', 'fix', 'verify']
const PHASE = {
  validate: { entry: ['Open', 'LOGGED', 'REOPENED-VALIDATE'] },
  analyze: { entry: ['CONFIRMED'] },
  test: { entry: ['ANALYZED'] },
  fix: { entry: ['TESTED', 'REOPENED'] },
  verify: { entry: ['FIXED'] },
}
const EXIT = {
  validate: ['CONFIRMED', 'FLAKY', 'UNREPRODUCIBLE', 'DUPLICATE', 'Open'],
  analyze: ['ANALYZED', 'DUPLICATE', 'ESCALATED'],
  test: ['TESTED', 'ESCALATED'],
  fix: ['FIXED', 'ESCALATED'],
  verify: ['CLOSED', 'REOPENED', 'ESCALATED'],
}
const SEED_STATUSES = ['REOPENED-VALIDATE','UNREPRODUCIBLE','CONFIRMED','ESCALATED','DUPLICATE','REOPENED','ANALYZED','TESTED','LOGGED','FIXED','CLOSED','FLAKY','Open']
const TERMINAL = new Set(['CLOSED', 'UNREPRODUCIBLE', 'DUPLICATE', 'FLAKY', 'ESCALATED', 'WONTFIX'])
const ADMITTED_ANYWHERE = new Set(Object.values(PHASE).flatMap((x) => x.entry))
const NEXT = { Open: 'CONFIRMED', CONFIRMED: 'ANALYZED', ANALYZED: 'TESTED', TESTED: 'FIXED', REOPENED: 'FIXED', FIXED: 'CLOSED' }
const WAVE = 3
const POLL_MS = 20
const PAUSE_CHECK_MS = 30 // long enough that the poller always samples inside the window
const MAX_REOPENS = 2

// `world` is the scenario knob: how the fake workers misbehave.
async function run(world) {
  const RUN = world.run || FULL_LINE
  const ALL_ENTRY = [...new Set(RUN.flatMap((n) => PHASE[n].entry))]
  const reg = new Map()
  for (let i = 0; i < world.n; i++) reg.set('BUG-' + i, 'Open')

  const inbox = new Map(RUN.map((n) => [n, []]))
  const busy = new Set()
  const finished = new Set()
  const onLine = new Set()
  const retired = new Set()
  const reopens = new Map()
  const stuck = []
  const dropped = []
  const blockedBugs = []
  const dispatched = {}
  // Dispatch order, so a case can assert the line PIPELINES rather than just finishing.
  // Counts alone cannot tell an assembly line from a waterfall: both close every bug.
  const order = []
  // Did the poller ever recover a bug while a phase was still working? That is the whole
  // point of it. Asserting on wall-clock interleaving is luck; this is the property itself.
  let recoveredWhileBusy = false
  // Batches taken off an inbox but not yet accounted for. Tracked separately from `busy`
  // precisely so the harness can catch `busy` being set late or dropped.
  let inFlight = 0
  let endedMidWave = false
  let waiters = []
  let halt = null
  let paused = false
  let lineDone = false

  const bump = () => { waiters.splice(0).forEach((r) => r()) }
  const changed = () => new Promise((r) => waiters.push(r))
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  const routeTo = (s) => RUN.find((n) => PHASE[n] && PHASE[n].entry.includes(s))
  const quiescent = () => busy.size === 0 && RUN.every((n) => inbox.get(n).length === 0)

  function normStatus(raw, phase) {
    const t = String(raw || '')
    let best = null, at = Infinity
    for (const k of EXIT[phase] || SEED_STATUSES) {
      const i = t.indexOf(k)
      if (i >= 0 && i < at) { at = i; best = k }
    }
    return best
  }

  function handOff(b, raw, phase) {
    const status = normStatus(raw, phase)
    if (!status) { dropped.push({ bugId: b.bugId, status: String(raw).slice(0, 60), from: phase || 'seed' }); return false }
    const next = routeTo(status)
    if (!next) {
      retired.add(b.bugId)
      if (!TERMINAL.has(status) && !ADMITTED_ANYWHERE.has(status)) dropped.push({ bugId: b.bugId, status, from: phase || 'seed' })
      return false
    }
    if (status === 'REOPENED' || status === 'REOPENED-VALIDATE') {
      const n = (reopens.get(b.bugId) || 0) + 1
      reopens.set(b.bugId, n)
      if (n > MAX_REOPENS) { stuck.push(b.bugId); retired.add(b.bugId); return false }
    }
    inbox.get(next).push({ ...b, status })
    onLine.add(b.bugId)
    return true
  }

  async function runWave(name, batch) {
    await sleep(name === 'validate' ? 30 : 6) // validate is the long-busy phase
    const results = batch.map((b) => {
      dispatched[name] = (dispatched[name] || 0) + 1
      order.push(name)
      if (world.throwsIn === name && !world.threw) { world.threw = true; throw new Error('wave exploded') }
      if (world.blocks && world.blocks(b.bugId, name)) return { bugId: b.bugId, blocked: true, blockerKind: 'env' }
      // Wrote its Status to the register, then died before returning it. The push handoff
      // cannot see this one at all -- only a poller reading the register can.
      if (world.writesThenBlocks && world.writesThenBlocks(b.bugId, name)) {
        reg.set(b.bugId, NEXT[reg.get(b.bugId)])
        return { bugId: b.bugId, blocked: true, blockerKind: 'env' }
      }
      const next = world.statusFor ? world.statusFor(b, name, reg) : NEXT[reg.get(b.bugId)]
      reg.set(b.bugId, next)
      const raw = world.prose && world.prose(name) ? `${next} — written to bug-hunter/ledger.md (row 7)` : next
      return { bugId: b.bugId, statusSet: raw }
    })
    batch.forEach((b, i) => {
      const r = results[i]
      onLine.delete(b.bugId)
      if (!r || r.blocked || !r.statusSet) { blockedBugs.push({ bugId: b.bugId, phase: name }); return }
      handOff(b, r.statusSet, name)
    })
    bump()
  }

  const loadQueue = async () => { await sleep(4); return { bugs: [...reg].map(([bugId, status]) => ({ bugId, status })) } }

  async function reconcile() {
    try {
      while (!halt && !paused) {
        await sleep(POLL_MS)
        if (halt || paused) break
        const wasQuiet = quiescent()
        const loaded = await loadQueue()
        let found = 0
        for (const b of loaded.bugs) {
          if (!b.status || onLine.has(b.bugId) || retired.has(b.bugId)) continue
          if (!ALL_ENTRY.includes(b.status)) continue
          if (handOff(b, b.status)) found++
        }
        if (found) { if (busy.size > 0) recoveredWhileBusy = true; bump(); continue }
        if (wasQuiet && quiescent()) { if (inFlight > 0) endedMidWave = true; break }
      }
    } finally { lineDone = true; bump() }
  }

  async function runPhase(name) {
    const queue = inbox.get(name)
    let served = 0
    while (!halt && !paused && !lineDone) {
      if (queue.length) {
        busy.add(name)
        const batch = queue.splice(0, WAVE)
        inFlight += batch.length
        try {
          await sleep(PAUSE_CHECK_MS) // the real loop calls a pause-check agent here
          await runWave(name, batch); served += batch.length }
        catch { batch.forEach((b) => onLine.delete(b.bugId)) }
        finally { inFlight -= batch.length; busy.delete(name) }
        continue
      }
      await Promise.race([changed(), sleep(25)])
    }
    finished.add(name)
    bump()
  }

  for (const [bugId, status] of reg) handOff({ bugId }, status)
  await Promise.all([...RUN.map((n) => runPhase(n)), reconcile()])

  const counts = {}
  for (const v of reg.values()) counts[v] = (counts[v] || 0) + 1
  return { counts, stuck, dropped, blockedBugs, dispatched, order, recoveredWhileBusy, endedMidWave, onLine: [...onLine] }
}

// True when some `up` work is still dispatched AFTER `down` has started — i.e. the two
// phases overlapped. A waterfall runs every `up` first, so nothing follows the first `down`.
const overlaps = (order, up, down) => {
  const firstDown = order.indexOf(down)
  return firstDown !== -1 && order.slice(firstDown).includes(up)
}

const CASES = [
  {
    name: 'happy path — every worker returns a bare status',
    world: { n: 9 },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 9 && r.dropped.length === 0 && r.dispatched.validate === 9,
  },
  {
    name: 'prose in statusSet from validate — the poller must carry the line',
    world: { n: 9, prose: (p) => p === 'validate' },
    // dropped must stay empty: normStatus is what keeps prose from falling off the line.
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 9 && r.dispatched.analyze === 9 && r.dropped.length === 0,
  },
  {
    // The defect that started all this: the poller only read the register once the whole
    // line went quiet, so analyze could not start until validate had finished all 73 bugs.
    // Everything still closed -- counts alone never noticed. This asserts the overlap.
    name: 'the line pipelines — analyze runs while validate still has bugs left',
    world: { n: 12 },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 12 && overlaps(r.order, 'validate', 'analyze'),
  },
  {
    // THE defect that started all this: reconcile sat behind `if (!quiescent()) continue`,
    // so a bug the handoff never saw waited until the whole line went quiet -- with validate
    // busy for an hour, that is the whole run. Every bug still closed in the end, so counts
    // never noticed; this asserts the poller recovers work WHILE a phase is still busy.
    // The workers here write their Status and then die, which is the only case the push
    // handoff genuinely cannot cover -- prose alone is caught by normStatus.
    name: 'the poller feeds a starved phase while validate is still working',
    world: { n: 12, writesThenBlocks: (id, ph) => ph === 'validate' && ['BUG-0', 'BUG-1', 'BUG-2'].includes(id) },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 12 && r.recoveredWhileBusy && r.blockedBugs.length === 3,
  },
  {
    name: 'prose from EVERY phase — enum gone, fallback is all that is left',
    world: { n: 6, prose: () => true },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 6 && r.dropped.length === 0,
  },
  {
    name: 'a wave throws — the run must not wedge, the bugs must come back',
    world: { n: 9, throwsIn: 'analyze' },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 9 && r.onLine.length === 0,
  },
  {
    name: 'a blocked worker must not strand its bug in onLine forever',
    world: { n: 6, blocks: (id, ph) => id === 'BUG-0' && ph === 'test' && !CASES[4].world.hit && (CASES[4].world.hit = true) },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 6 && r.blockedBugs.length === 1 && r.onLine.length === 0,
  },
  {
    name: 'verify keeps reopening one bug — the cap fires and the run still ends',
    world: { n: 6, statusFor: (b, name, reg) => (name === 'verify' && b.bugId === 'BUG-0' ? 'REOPENED' : NEXT[reg.get(b.bugId)]) },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 5 && r.stuck.length === 1 && r.stuck[0] === 'BUG-0',
  },
  {
    // A stage of one phase: CONFIRMED routes nowhere because analyze is not in this run.
    // That is the stage ending normally and must NOT be reported as a scheduler defect.
    name: 'a single-phase stage ends cleanly and reports nothing as dropped',
    world: { n: 6, run: ['validate'] },
    expect: (r) => !r.endedMidWave && r.counts.CONFIRMED === 6 && r.dropped.length === 0,
  },
  {
    name: 'a status nobody admits is reported as dropped, not swallowed',
    world: { n: 6, statusFor: (b, name, reg) => (name === 'analyze' && b.bugId === 'BUG-1' ? 'BANANA' : NEXT[reg.get(b.bugId)]) },
    expect: (r) => !r.endedMidWave && r.counts.CLOSED === 5 && r.dropped.length === 1 && r.dropped[0].bugId === 'BUG-1',
  },
]

// A table invariant, not a scenario: today every status a worker can return is either
// TERMINAL or admitted by some phase, which is why handOff's "routes nowhere" defect branch
// is unreachable. Add a status to EXIT without giving some phase an entry for it and that
// branch goes live -- silently, in production. This fails first, right here.
const orphans = [...new Set(Object.values(EXIT).flat())].filter(
  (st) => !TERMINAL.has(st) && !ADMITTED_ANYWHERE.has(st),
)
if (orphans.length) {
  console.log(`FAIL  a status in EXIT is admitted by no phase and is not terminal: ${orphans.join(', ')}`)
  console.log('      Give it a phase entry, or add it to TERMINAL. Until then bugs reaching it leave the line.')
  process.exit(1)
}

let failed = 0
for (const c of CASES) {
  const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error('HUNG (10s)')), 10000))
  let r, err
  try { r = await Promise.race([run(c.world), timeout]) } catch (e) { err = e }
  const ok = !err && c.expect(r)
  if (!ok) failed++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${c.name}`)
  if (!ok) console.log('        ', err ? err.message : JSON.stringify({ counts: r.counts, stuck: r.stuck, dropped: r.dropped, blocked: r.blockedBugs.length, onLine: r.onLine }))
}
console.log(`\n${CASES.length - failed}/${CASES.length} passed`)
process.exit(failed ? 1 : 0)
