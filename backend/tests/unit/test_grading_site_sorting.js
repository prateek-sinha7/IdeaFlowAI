// Drives the comparator SHIPPED in assets.py — not a copy of it — so this test
// fails if the real sorting logic regresses.
//
// The bug it pins: parseFloat('2026-07-30T15:48:05Z') is 2026, so every
// timestamp in a column compared equal and the column silently never sorted.
const fs = require('fs');
const js = fs.readFileSync(process.argv[2], 'utf8');

const match = js.match(/function asNumber\(value\) \{[\s\S]*?\n  \}/);
if (!match) { console.error('FAIL: asNumber() not found in the shipped script'); process.exit(1); }
const asNumber = eval('(' + match[0].replace(/^function asNumber/, 'function') + ')');

function cmp(dir) {
  return function (xv, yv) {
    const xMissing = xv === null || xv === '';
    const yMissing = yv === null || yv === '';
    if (xMissing && yMissing) return 0;
    if (xMissing) return 1;
    if (yMissing) return -1;
    const xn = asNumber(xv), yn = asNumber(yv);
    const c = (xn !== null && yn !== null) ? xn - yn : String(xv).localeCompare(String(yv));
    return dir === 'desc' ? -c : c;
  };
}

const checks = [];
const eq = (name, got, want) =>
  checks.push([name, JSON.stringify(got) === JSON.stringify(want), got, want]);

const stamps = ['2026-07-30T15:48:05Z', '2026-07-29T18:47:18Z', '2026-07-30T20:46:44Z'];
eq('timestamps ascending', [...stamps].sort(cmp('asc')),
   ['2026-07-29T18:47:18Z', '2026-07-30T15:48:05Z', '2026-07-30T20:46:44Z']);
eq('timestamps descending', [...stamps].sort(cmp('desc')),
   ['2026-07-30T20:46:44Z', '2026-07-30T15:48:05Z', '2026-07-29T18:47:18Z']);
eq('scores sort numerically, not lexically', ['92.5', '7', '100'].sort(cmp('asc')),
   ['7', '92.5', '100']);
eq('missing values sink ascending', ['92.5', '', '7'].sort(cmp('asc')), ['7', '92.5', '']);
eq('missing values sink descending', ['92.5', '', '7'].sort(cmp('desc')), ['92.5', '7', '']);
eq('run ids sort as text', ['260730-b', '260729-a'].sort(cmp('asc')), ['260729-a', '260730-b']);
eq('a timestamp is never treated as a number', asNumber('2026-07-30T15:48:05Z'), null);
eq('a plain number still is', asNumber('92.5'), 92.5);

let failed = 0;
for (const [name, ok, got, want] of checks) {
  if (!ok) { failed++; console.error(`FAIL ${name}\n  got  ${JSON.stringify(got)}\n  want ${JSON.stringify(want)}`); }
}
console.log(failed ? `${failed} failed` : `all ${checks.length} sorting checks passed`);
process.exit(failed ? 1 : 0);
