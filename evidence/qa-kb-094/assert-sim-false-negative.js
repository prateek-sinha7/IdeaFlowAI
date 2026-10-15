// Executes the REAL assertion block of a .http runner (extracted verbatim) against a synthetic /events stream.
const fs = require('fs');
const file = process.argv[2];
const lines = fs.readFileSync(file, 'utf8').split('\n');
const h = lines.findIndex(l => /^### \d+\. Assertions/.test(l));
const open = lines.findIndex((l, i) => i > h && l === '{{');
let close = lines.length - 1; while (lines[close] !== '}}') close--;
const body = lines.slice(open + 1, close).join('\n');
const out = [];
const apiLine = (m, lvl) => out.push((lvl === 'error' ? 'ERR ' : 'ok  ') + m);
const req = () => apiLine;                                   // require('./lib/api-line.js') -> apiLine
const ev = (type, data) => ({ type, data });
const A = (id) => 'custom-agent:' + id;
// A CORRECTLY ROUTED run (human answered {"decision":"spanish"}, gate read ask, routed to say-hola) where the
// pick-language MODEL replied with prose "Hola" -- the case ADR-0026 says must still route.
const events = [
  ev('review_gate_ready', { gate_key: 'k' }),
  ev('agent_start', { agent_id: A('ask') }), ev('agent_complete', { agent_id: A('ask') }),
  ev('agent_start', { agent_id: A('pick-language') }), ev('agent_chunk', { agent_id: A('pick-language'), chunk: 'Hola' }), ev('agent_complete', { agent_id: A('pick-language') }),
  ev('agent_skipped', { agent_id: A('say-hello') }), ev('agent_skipped', { agent_id: A('say-hallo') }),
  ev('agent_start', { agent_id: A('say-hola') }), ev('agent_chunk', { agent_id: A('say-hola'), chunk: 'Hola, mundo!' }), ev('agent_complete', { agent_id: A('say-hola') }),
  ev('pipeline_complete', {}),
];
new Function('require', 'response', body)(req, { parsedBody: { events } });
console.log(out.join('\n'));
