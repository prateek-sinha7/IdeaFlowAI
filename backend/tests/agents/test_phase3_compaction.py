"""Phase 3 (0C) — build-task-2+ HTML-skeleton compaction gate (COMPACT-01 / COMPACT-03).

This module is the DETERMINISTIC, FULLY-OFFLINE CI half of the token-trim phase. It
proves the ``html_skeleton`` CompactionStrategy capability
(``HtmlSkeletonCompaction.compact``) produces the compact ≈1-3k char state-map (≥50%
reduction — PARITY-04 / COMPACT-03) that the ``task_loop`` strategy injects for
``prototype-build`` tasks 2+ instead of the full current HTML (up to 120k chars).

Post-07-05: the engine's per-pipeline context builder and its inline
``_extract_html_skeleton`` helper were DELETED (L12 / L13). The build-task-2+ skeleton
INJECTION now lives in the ``task_loop`` strategy (routing covered by
``test_strategies.py::test_task_loop_requests_html_skeleton_compaction_for_task_2``) and
the 5-pipeline characterization suites; the skeleton EXTRACTION + the ≥50% reduction gate
live with the capability and are pinned here (the verbatim lift's single home is
``agents/capabilities/compaction/html_skeleton.py``).

Gates asserted here:
  * COMPACT-03 / PARITY-04 — the skeleton is ≤ 50% the size of the source HTML on a
    ≥2-page fixture (the deterministic reduction gate, now measured against the capability).
  * Skeleton fidelity — every ``data-page`` id, the routes map, and the ``:root`` tokens
    survive into the state-map (a regression that drops/garbles a page fails HERE).
"""

from __future__ import annotations

# Import the scripted-model harness FIRST so its import-time env setup
# (RUNS_ROOT→temp + ENV=development) runs and the test stays fully offline.
from tests.agents import _scripted_model  # noqa: F401  (import for side effects)

from agents.capabilities.compaction.html_skeleton import HtmlSkeletonCompaction

# ── A representative MULTI-PAGE prototype HTML fixture ────────────────────────
# At least two `<section data-page>` elements with real filled content, a `:root`
# token block (--bg/--fg/--accent/--surface/--border/--muted), and a `const routes`
# map — sized large enough that the full-HTML block (capped at 120k) is a realistic
# input-token proxy. (The committed 84-byte scripted golden is far too small.)
_FILLER = (
    "<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Pellentesque euismod, nisl eget ultricies aliquam, nunc nisl "
    "aliquet nunc, eget aliquam nisl nunc eget nisl. Curabitur "
    "vehicula, justo eget posuere tincidunt, velit metus.</p>\n"
) * 60  # generous body so each filled section is substantial

_MULTI_PAGE_HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
:root {{
  --bg: #0f172a;
  --fg: #f8fafc;
  --accent: #38bdf8;
  --surface: #1e293b;
  --border: #334155;
  --muted: #94a3b8;
  --font-sans: "Inter", system-ui, sans-serif;
}}
body {{ background: var(--bg); color: var(--fg); font-family: var(--font-sans); }}
.topnav {{ display: flex; gap: 1rem; padding: 1rem; background: var(--surface); }}
</style>
</head>
<body>
<nav class="topnav" data-od-id="topnav">
  <a href="#dashboard" data-active="true">Dashboard</a>
  <a href="#settings">Settings</a>
</nav>

<section data-page="dashboard">
  <h1>Dashboard</h1>
  <div class="cards">
    <article class="card"><h2>Revenue</h2><strong>$128,400</strong></article>
    <article class="card"><h2>Active users</h2><strong>9,213</strong></article>
    <article class="card"><h2>Churn</h2><strong>1.8%</strong></article>
  </div>
  {_FILLER}
</section>

<section data-page="settings">
  <h1>Settings</h1>
  <form class="settings-form">
    <label>Display name <input type="text" value="Ada Lovelace"></label>
    <label>Email <input type="email" value="ada@example.com"></label>
    <label>Notifications <input type="checkbox" checked></label>
    <button type="submit">Save changes</button>
  </form>
  {_FILLER}
</section>

<script>
const routes = {{
  dashboard: "#dashboard",
  settings: "#settings",
}};
function navigate(page) {{ location.hash = routes[page]; }}
</script>
</body>
</html>
"""


def test_html_skeleton_is_faithful_to_source() -> None:
    """Skeleton fidelity — every page / route / token survives into the state-map.

    The whole phase rests on the premise that the ~1-3k char skeleton faithfully
    reflects the prior HTML; this exercises the ``html_skeleton`` capability DIRECTLY
    on the multi-page fixture and asserts every ``data-page`` id, the routes map, and
    the ``:root`` tokens survive. A regression that corrupts the skeleton fails HERE.
    """
    skeleton = HtmlSkeletonCompaction().compact(_MULTI_PAGE_HTML)

    # Every data-page section in the fixture (both filled) must be named — no section
    # silently dropped on the path that is the agent's only structural view for task 2+.
    built_line = next(
        (ln for ln in skeleton.splitlines() if ln.startswith("Pages already built")),
        "",
    )
    assert built_line, "skeleton must report the filled sections via a 'Pages already built' line"
    assert "dashboard" in built_line and "settings" in built_line, (
        f"both data-page ids must appear in the built-pages line, got: {built_line!r}"
    )

    # Routes map and :root design tokens are carried into the skeleton.
    assert "Routes map" in skeleton, "skeleton must carry the routes map"
    assert ":root tokens" in skeleton, "skeleton must carry the :root design tokens"


def test_html_skeleton_reduction_gate() -> None:
    """COMPACT-03 / PARITY-04: the skeleton is ≤ 50% of the source HTML it summarizes.

    The preserved 0C deterministic reduction gate, measured directly against the
    ``html_skeleton`` capability (its single home after the engine copy was deleted in
    07-05). A regression that bloats the skeleton — or reverts the compaction — fails here.
    """
    skeleton = HtmlSkeletonCompaction().compact(_MULTI_PAGE_HTML)
    assert len(skeleton) <= 0.5 * len(_MULTI_PAGE_HTML), (
        f"skeleton ({len(skeleton)} chars) must be ≤ 50% of the source HTML "
        f"({len(_MULTI_PAGE_HTML)} chars) — PARITY-04 / COMPACT-03 reduction gate"
    )
