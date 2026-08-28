"""The run's own report: `test-runs/<run>/0-report.html`.

Written at session end from pytest's results, not by parsing the terminal
log. The terminal only ever shows `.sF`; the report carries the skip REASONS,
the failure messages and the per-suite shape, which is what anyone actually
wants the morning after a sweep.

Named `0-report.html` so it sorts above the area folders it summarises.

Self-contained: no CDN, no external font, so it opens from the filesystem
with no network. Theme-aware, because the machine it opens on may be in dark
mode and a white slab at 2am is its own small hostility.
"""

from __future__ import annotations

import html
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

WS = re.compile(r"\s+")


@dataclass
class Case:
    nodeid: str
    suite: str
    scenario: str
    title: str
    outcome: str  # passed | failed | skipped
    reason: str = ""
    error: str = ""
    duration: float = 0.0
    shots: int = 0


@dataclass
class Results:
    """Every case in the session, in the order they ran."""

    cases: list[Case] = field(default_factory=list)
    deselected: int = 0
    base_url: str = ""
    run_name: str = ""
    started: datetime = field(default_factory=datetime.now)

    def add(self, case: Case) -> None:
        self.cases.append(case)

    # ── shaping ──────────────────────────────────────────────────────────────

    def by_suite(self) -> list[dict]:
        buckets: dict[str, list[Case]] = defaultdict(list)
        for c in self.cases:
            buckets[c.suite].append(c)
        rows = []
        for suite in sorted(buckets):
            got = buckets[suite]
            rows.append(
                {
                    "suite": suite,
                    "collected": len(got),
                    "passed": sum(c.outcome == "passed" for c in got),
                    "skipped": sum(c.outcome == "skipped" for c in got),
                    "failed": sum(c.outcome == "failed" for c in got),
                    "secs": sum(c.duration for c in got),
                }
            )
        return rows

    def totals(self) -> dict:
        rows = self.by_suite()
        t = {
            k: sum(r[k] for r in rows)
            for k in ("collected", "passed", "skipped", "failed", "secs")
        }
        t["suites"] = len(rows)
        return t


# ── skip taxonomy ────────────────────────────────────────────────────────────
#
# A skip reason is prose written by whoever wrote the test, so this groups on
# what the reason SAYS is missing. Anything unrecognised lands in the last
# bucket rather than being dropped — an uncategorised skip is still a skip and
# has to appear somewhere.

_BUCKETS = [
    ("Needs a live dispatch", ("live tier", "real llm", "real run", "dispatches a real")),
    ("Needs an auth state this pool cannot mint", ("cognito", "challenge", "mfa", "token")),
    ("Needs a diverted or multi-version run", ("divert", "revised", "version", "family")),
    ("Needs a planted workspace fixture",
     ("workspace", "symlink", " mb", "nested", "ttl", "expires_at")),
]


def bucket_of(reason: str) -> str:
    low = reason.lower()
    for name, needles in _BUCKETS:
        if any(n in low for n in needles):
            return name
    return "Covered elsewhere, or behaviour never established"


# ── rendering ────────────────────────────────────────────────────────────────


def _bar(row: dict) -> str:
    return "".join(
        f'<span class="{cls}" style="flex:{n}" title="{n}"></span>'
        for cls, n in (("p", row["passed"]), ("s", row["skipped"]), ("f", row["failed"]))
        if n
    )


def _suite_rows(rows: list[dict]) -> str:
    return "\n".join(
        '<tr><td class="nm">{s}</td><td class="num">{c}</td><td class="num ok">{p}</td>'
        '<td class="num sk">{k}</td><td class="num fl">{f}</td>'
        '<td class="num dim">{t:.0f}s</td>'
        '<td class="barcell"><div class="bar">{b}</div></td></tr>'.format(
            s=html.escape(r["suite"].replace("_", " ", 1)),
            c=r["collected"], p=r["passed"], k=r["skipped"] or "",
            f=r["failed"] or "", t=r["secs"], b=_bar(r),
        )
        for r in rows
    )


def _failure_cards(cases: list[Case]) -> str:
    failed = [c for c in cases if c.outcome == "failed"]
    if not failed:
        return '<div class="note pass"><b>Nothing failed.</b> Every collected test either passed or skipped with a stated reason.</div>'
    return "\n".join(
        '<div class="card"><div class="cid">{i}</div><div class="ct">{t}</div>'
        '<pre>{e}</pre></div>'.format(
            i=html.escape(c.scenario), t=html.escape(c.title),
            e=html.escape(c.error or "no message captured"),
        )
        for c in failed
    )


def _skip_blocks(cases: list[Case]) -> str:
    counts: Counter = Counter()
    detail: dict[str, Counter] = defaultdict(Counter)
    for c in cases:
        if c.outcome != "skipped":
            continue
        reason = WS.sub(" ", c.reason or "no reason given").strip()
        name = bucket_of(reason)
        counts[name] += 1
        detail[name][reason] += 1
    if not counts:
        return '<div class="note"><b>Nothing was skipped.</b></div>'
    out = []
    for name, total in counts.most_common():
        items = "".join(
            f"<li><b>{n}&times;</b> {html.escape(reason)}</li>"
            for reason, n in detail[name].most_common()
        )
        out.append(
            f'<details><summary><span class="cnt">{total}</span> {html.escape(name)}'
            f"</summary><ul>{items}</ul></details>"
        )
    return "\n".join(out)


def _slowest(cases: list[Case], n: int = 8) -> str:
    ran = sorted((c for c in cases if c.outcome != "skipped"),
                 key=lambda c: -c.duration)[:n]
    if not ran:
        return ""
    return "\n".join(
        '<tr><td class="nm">{i}</td><td>{t}</td><td class="num dim">{d:.1f}s</td></tr>'.format(
            i=html.escape(c.scenario), t=html.escape(c.title), d=c.duration
        )
        for c in ran
    )


TEMPLATE = Path(__file__).parent / "run_report.css.html"


def render(results: Results) -> str:
    rows = results.by_suite()
    t = results.totals()
    ran = t["passed"] + t["failed"]
    rate = (100 * t["passed"] / ran) if ran else 0.0
    css = TEMPLATE.read_text()
    ended = datetime.now()
    return css.replace("{{BODY}}", f"""
  <h1>{html.escape(results.run_name or "Integration run")}</h1>
  <p class="sub">{t['suites']} suite files against <code>{html.escape(results.base_url)}</code>
     &middot; {results.started:%d %b %Y, %H:%M} &rarr; {ended:%H:%M}
     &middot; {results.deselected} deselected</p>

  <div class="kpis">
    <div class="kpi good"><div class="v">{t['passed']}</div><div class="l">Passed</div></div>
    <div class="kpi warn"><div class="v">{t['skipped']}</div><div class="l">Skipped</div></div>
    <div class="kpi {'bad' if t['failed'] else 'good'}"><div class="v">{t['failed']}</div>
      <div class="l">Failed</div></div>
    <div class="kpi"><div class="v">{rate:.0f}%</div><div class="l">Of those run</div></div>
    <div class="kpi"><div class="v">{t['secs'] / 60:.0f}m</div><div class="l">In-test time</div></div>
  </div>

  <h2>Per suite</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>Suite</th><th class="num">Coll</th><th class="num">Pass</th>
      <th class="num">Skip</th><th class="num">Fail</th><th class="num">Time</th><th></th></tr></thead>
    <tbody>{_suite_rows(rows)}</tbody>
    <tfoot><tr><td class="nm">total</td><td class="num">{t['collected']}</td>
      <td class="num ok">{t['passed']}</td><td class="num sk">{t['skipped']}</td>
      <td class="num fl">{t['failed'] or ''}</td>
      <td class="num dim">{t['secs'] / 60:.0f}m</td><td></td></tr></tfoot>
  </table></div>

  <h2>Failures</h2>
  {_failure_cards(results.cases)}

  <h2>Why {t['skipped']} skipped</h2>
  <p class="sub" style="margin-bottom:16px">Grouped by what the reason says is missing.
     A skip names the fixture or run state it waits for; none is silent.</p>
  {_skip_blocks(results.cases)}

  <h2>Slowest scenarios</h2>
  <div class="tablewrap"><table><tbody>{_slowest(results.cases)}</tbody></table></div>
""")


def write(results: Results, run_dir: Path) -> Path:
    out = run_dir / "0-report.html"
    out.write_text(render(results))
    return out
