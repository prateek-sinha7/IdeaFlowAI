#!/usr/bin/env python3
"""Build a self-contained shareable HTML report from ledger.md."""
import re, json, pathlib, datetime, html

root = pathlib.Path(__file__).resolve().parent.parent  # tools/ -> bug-hunter/
src = (root / 'ledger.md').read_text()

bugs = []
for block in re.split(r'\n(?=## BUG-)', src):
    m = re.match(r'## (BUG-\S+) — (.+)', block)
    if not m:
        continue
    def field(k):
        mm = re.search(r'\*\*' + k + r':\*\*\s*(.+)', block)
        return mm.group(1).strip().strip('`') if mm else ''
    def section(name):
        mm = re.search(r'### ' + name + r'\n(.*?)(?=\n### |\Z)', block, re.S)
        return mm.group(1).strip() if mm else ''
    bugs.append({
        'id': m.group(1), 'title': m.group(2).strip(),
        'severity': field('Severity') or 'Medium',
        'status': field('Status') or 'Open',
        'cards': field('Issue cards') or field('Issue card') or '',
        'route': field('Route'), 'page': field('Page'),
        'found_by': field('Found by'), 'found_at': field('Found at'),
        'fingerprint': field('Fingerprint'), 'evidence_dir': field('Evidence'),
        'summary': section('Summary'), 'repro': section('Reproduction'),
        'expected': section('Expected'), 'actual': section('Actual'),
        'evidence': section('Evidence'), 'signals': section('Browser Signals'),
    })

order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
bugs.sort(key=lambda b: (order.get(b['severity'], 9), b['id']))
counts = {s: sum(1 for b in bugs if b['severity'] == s) for s in ['Critical', 'High', 'Medium', 'Low']}
areas = {}
for b in bugs:
    a = (b['route'].split('(')[0].strip().strip('`').split('?')[0].rstrip('/') or '/').split('/')
    key = '/' + (a[1] if len(a) > 1 and a[1] else '(root)')
    areas[key] = areas.get(key, 0) + 1
areas = dict(sorted(areas.items(), key=lambda kv: -kv[1]))
now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

TPL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Velocity — Autonomous Bug Hunt Report</title>
<style>
*{box-sizing:border-box}
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2129;--bd:#30363d;--tx:#e6edf3;--dim:#8b949e;
--hi:#f85149;--med:#d29922;--low:#58a6ff;--crit:#da3633;--ok:#3fb950;--acc:#a371f7}
@media(prefers-color-scheme:light){:root{--bg:#fff;--panel:#f6f8fa;--panel2:#eef1f4;--bd:#d0d7de;--tx:#1f2328;--dim:#656d76}}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 24px 80px}
header{border-bottom:1px solid var(--bd);padding-bottom:26px;margin-bottom:26px}
h1{font-size:29px;margin:0 0 6px;letter-spacing:-.02em}
.sub{color:var(--dim);font-size:14px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:26px 0}
.stat{background:var(--panel);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}
.stat .n{font-size:27px;font-weight:650;letter-spacing:-.02em}
.stat .l{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.07em;margin-top:2px}
.n.crit{color:var(--crit)}.n.high{color:var(--hi)}.n.med{color:var(--med)}.n.low{color:var(--low)}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:22px 0 18px;position:sticky;top:0;
background:var(--bg);padding:12px 0;z-index:10;border-bottom:1px solid var(--bd)}
input[type=search]{flex:1;min-width:220px;background:var(--panel);border:1px solid var(--bd);color:var(--tx);
padding:9px 13px;border-radius:8px;font-size:14px}
input[type=search]:focus{outline:2px solid var(--acc);outline-offset:-1px}
button.f{background:var(--panel);border:1px solid var(--bd);color:var(--tx);padding:8px 13px;border-radius:8px;
cursor:pointer;font-size:13px;font-weight:500}
button.f[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:#fff}
button.f:hover{border-color:var(--acc)}
.bug{background:var(--panel);border:1px solid var(--bd);border-left-width:4px;border-radius:10px;margin-bottom:11px;overflow:hidden}
.bug[data-sev=Critical]{border-left-color:var(--crit)}
.bug[data-sev=High]{border-left-color:var(--hi)}
.bug[data-sev=Medium]{border-left-color:var(--med)}
.bug[data-sev=Low]{border-left-color:var(--low)}
summary{cursor:pointer;padding:14px 17px;display:flex;gap:12px;align-items:flex-start;list-style:none}
summary::-webkit-details-marker{display:none}
summary:hover{background:var(--panel2)}
.num{color:var(--dim);font-variant-numeric:tabular-nums;font-size:13px;min-width:26px;padding-top:2px}
.sev{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:3px 8px;
border-radius:20px;white-space:nowrap;margin-top:1px}
.sev.Critical{background:rgba(218,54,51,.16);color:var(--crit)}
.sev.High{background:rgba(248,81,73,.14);color:var(--hi)}
.sev.Medium{background:rgba(210,153,34,.14);color:var(--med)}
.sev.Low{background:rgba(88,166,255,.14);color:var(--low)}
.ttl{flex:1;font-weight:520}
.rt{color:var(--dim);font-size:12.5px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;margin-top:3px;
word-break:break-all;display:block}
.body{padding:4px 17px 20px 17px;border-top:1px solid var(--bd)}
.body h4{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin:18px 0 6px}
.body p,.body li{font-size:14.5px}
.body pre{background:var(--panel2);border:1px solid var(--bd);border-radius:7px;padding:11px 13px;
overflow-x:auto;font-size:12.5px;white-space:pre-wrap;word-break:break-word}
.body ol,.body ul{padding-left:20px;margin:6px 0}
.meta{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--dim);margin-top:16px;
padding-top:13px;border-top:1px solid var(--bd)}
.meta code{background:var(--panel2);padding:2px 6px;border-radius:4px;font-size:11.5px}
.themes{background:var(--panel);border:1px solid var(--bd);border-radius:10px;padding:18px 20px;margin:26px 0}
.themes h3{margin:0 0 12px;font-size:15px}
.themes li{margin-bottom:7px;font-size:14px}
.bars{display:grid;gap:7px;margin-top:10px}
.bar{display:grid;grid-template-columns:150px 1fr 34px;gap:11px;align-items:center;font-size:13px}
.bar .t{background:var(--acc);height:16px;border-radius:4px;min-width:3px;opacity:.8}
.bar .c{color:var(--dim);text-align:right;font-variant-numeric:tabular-nums}
.bar .nm{font-family:ui-monospace,monospace;color:var(--dim);overflow:hidden;text-overflow:ellipsis}
footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--bd);color:var(--dim);font-size:12.5px}
.none{display:none!important}
mark{background:rgba(163,113,247,.3);color:inherit;border-radius:2px}
</style></head><body><div class="wrap">
<header>
<h1>Velocity — Autonomous Bug Hunt</h1>
<div class="sub">__COUNT__ reproducible defects across __PAGES__ application pages · generated __NOW__</div>
</header>

<div class="stats">
<div class="stat"><div class="n">__COUNT__</div><div class="l">Total bugs</div></div>
<div class="stat"><div class="n high">__HIGH__</div><div class="l">High</div></div>
<div class="stat"><div class="n med">__MED__</div><div class="l">Medium</div></div>
<div class="stat"><div class="n low">__LOW__</div><div class="l">Low</div></div>
<div class="stat"><div class="n">__PAGES__</div><div class="l">Pages tested</div></div>
</div>

<div class="themes"><h3>Recurring failure patterns</h3><ul>
<li><b>Save paths that discard or misreport</b> — "Save as my version" drops brief + template on both wizards; built-in "Save as copy" loses the manifest; empty-name and agent-config saves are silent no-ops.</li>
<li><b>Constraints displayed but never enforced</b> — no tier gating on model choice, a 4000-char limit that isn't applied, requirement pills nothing can satisfy, a plan button with no handler.</li>
<li><b>Silent no-op controls</b> — five separate primary actions fire no request and show no feedback.</li>
<li><b>Figures that disagree across surfaces</b> — token totals, agent counts and timestamps differ between list, detail, footer and API.</li>
<li><b>Unsanitised params reaching the router</b> — <code>?mode=../admin</code> escapes its namespace onto the live admin console.</li>
</ul>
<h3 style="margin-top:20px">Bugs by area</h3><div class="bars">__BARS__</div>
</div>

<div class="controls">
<input type="search" id="q" placeholder="Search title, route, or bug id…" autocomplete="off">
<button class="f" data-s="all" aria-pressed="true">All</button>
<button class="f" data-s="High" aria-pressed="false">High</button>
<button class="f" data-s="Medium" aria-pressed="false">Medium</button>
<button class="f" data-s="Low" aria-pressed="false">Low</button>
<button class="f" id="expand" aria-pressed="false">Expand all</button>
</div>

<div id="list">__ROWS__</div>

<footer>
Ledger: <code>bug-hunter/ledger.md</code> · Evidence: <code>bug-hunter/evidence/&lt;page-slug&gt;/&lt;BUG-ID&gt;/</code> ·
State: <code>bug-hunter/hunt-state.md</code><br>
Every bug was found by driving the real application in Google Chrome via Playwright, reproduced at least twice,
and recorded with screenshots. Status of all entries is <b>Open</b> — this hunt observes and documents, it does not fix.
</footer>
</div>
<script>
const list=document.getElementById('list'),q=document.getElementById('q');
let sev='all';
function apply(){
 const t=q.value.toLowerCase().trim();
 list.querySelectorAll('.bug').forEach(el=>{
  const okS = sev==='all'||el.dataset.sev===sev;
  const okT = !t||el.dataset.search.includes(t);
  el.classList.toggle('none',!(okS&&okT));
 });
}
q.addEventListener('input',apply);
document.querySelectorAll('button.f[data-s]').forEach(b=>b.addEventListener('click',()=>{
 sev=b.dataset.s;
 document.querySelectorAll('button.f[data-s]').forEach(x=>x.setAttribute('aria-pressed',x===b));
 apply();
}));
const ex=document.getElementById('expand');
ex.addEventListener('click',()=>{
 const on=ex.getAttribute('aria-pressed')!=='true';
 ex.setAttribute('aria-pressed',on); ex.textContent=on?'Collapse all':'Expand all';
 document.querySelectorAll('.bug').forEach(d=>d.open=on);
});
</script></body></html>"""

def md(s):
    if not s: return ''
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    lines, out, mode = s.split('\n'), [], None
    for ln in lines:
        t = ln.strip()
        if re.match(r'^\d+\.\s', t):
            if mode != 'ol': out.append('<ol>' if mode is None else '</ul><ol>'); mode = 'ol'
            out.append('<li>' + re.sub(r'^\d+\.\s*', '', t) + '</li>')
        elif t.startswith('- '):
            if mode != 'ul': out.append('<ul>' if mode is None else '</ol><ul>'); mode = 'ul'
            out.append('<li>' + t[2:] + '</li>')
        elif not t:
            if mode: out.append('</%s>' % mode); mode = None
        else:
            if mode: out.append('</%s>' % mode); mode = None
            out.append('<p>' + t + '</p>')
    if mode: out.append('</%s>' % mode)
    return '\n'.join(out)

rows = []
for i, b in enumerate(bugs, 1):
    search = ' '.join([b['title'], b['route'], b['id'], b['severity'], b['page']]).lower()
    sec = ''
    for label, key in [('Summary','summary'),('Reproduction','repro'),('Expected','expected'),
                       ('Actual','actual'),('Evidence','evidence'),('Browser signals','signals')]:
        if b[key]:
            sec += '<h4>%s</h4>%s' % (label, md(b[key]))
    rows.append(f"""<details class="bug" data-sev="{html.escape(b['severity'])}" data-search="{html.escape(search)}">
<summary><span class="num">{i}</span><span class="sev {html.escape(b['severity'])}">{html.escape(b['severity'])}</span>
<span class="ttl">{html.escape(b['title'])}<span class="rt">{html.escape(b['route'])}</span></span></summary>
<div class="body">{sec}
<div class="meta"><span>ID <code>{html.escape(b['id'])}</code></span>
<span>Found by <code>{html.escape(b['found_by'])}</code></span>
<span>Fingerprint <code>{html.escape(b['fingerprint'])}</code></span></div>
</div></details>""")

mx = max(areas.values()) if areas else 1
bars = ''.join(
    f'<div class="bar"><span class="nm">{html.escape(k)}</span>'
    f'<span class="t" style="width:{v/mx*100:.0f}%"></span><span class="c">{v}</span></div>'
    for k, v in areas.items())

out = (TPL.replace('__COUNT__', str(len(bugs))).replace('__HIGH__', str(counts['High']))
       .replace('__MED__', str(counts['Medium'])).replace('__LOW__', str(counts['Low']))
       .replace('__PAGES__', '55').replace('__NOW__', now)
       .replace('__BARS__', bars).replace('__ROWS__', '\n'.join(rows)))

dest = root / 'reports' / 'velocity-bug-report.html'
dest.write_text(out)
print(f"{len(bugs)} bugs -> {dest} ({dest.stat().st_size//1024} KB)")

# --- ledger-index.md -------------------------------------------------------
# The lookup table over ledger.md. Status is what every pipeline phase reads to
# decide eligibility, so it belongs here where it can be scanned in one screen
# rather than grepped out of a 445 KB file. Regenerated, never hand-edited.

status_counts = {}
for b in bugs:
    status_counts[b['status'] or 'Open'] = status_counts.get(b['status'] or 'Open', 0) + 1

idx = [
    '# Ledger index — Velocity autonomous hunt',
    '',
    '**Generated by `report.py` — do not hand-edit.** The ledger itself is `ledger.md`;',
    'this is the lookup table over it.',
    '',
    f"**{len(bugs)} bugs** · generated {now}",
    '',
    '**Severity:** ' + ' · '.join(f"{s} {counts[s]}" for s in ['Critical', 'High', 'Medium', 'Low'] if counts[s]),
    '',
    '**Status:** ' + ' · '.join(f"{k} {v}" for k, v in sorted(status_counts.items())),
    '',
    '| # | Sev | Status | Route | Title | Bug ID | Cards |',
    '|---|---|---|---|---|---|---|',
]
for i, b in enumerate(bugs, 1):
    title = b['title'].replace('|', r'\|')
    idx.append(
        f"| {i} | {b['severity']} | {b['status'] or 'Open'} | `{b['route']}` | "
        f"{title} | `{b['id']}` | {b['cards'] or '—'} |"
    )

index_dest = root / 'ledger-index.md'
index_dest.write_text('\n'.join(idx) + '\n')
print(f"{len(bugs)} rows -> {index_dest}")
