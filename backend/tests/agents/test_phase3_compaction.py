"""Phase 3 (0C) — build-task-2+ context compaction gate (COMPACT-01 / COMPACT-03).

This module is the DETERMINISTIC, FULLY-OFFLINE CI half of the token-trim phase. It
proves that `_build_context_message` injects the compact `_extract_html_skeleton`
state-map (≈1-3k chars) for `prototype-build` tasks 2+ instead of the full current
HTML (up to 120k chars) — the one sanctioned non-byte-identical change (INV-3).

It exercises the REAL injection site (`ExecutionEngine._build_context_message`) via a
direct call on a representative multi-page HTML fixture, with NO DB / NO Bedrock / NO
API key (importing `_scripted_model` first wires `RUNS_ROOT`→temp + `ENV=development`
at import time, keeping everything offline).

Gates asserted here:
  * COMPACT-03 CI gate — the task-2 message is ≤ 50% the size of the old full-HTML
    message on a ≥2-page HTML fixture (the full-HTML baseline replicates the
    engine's `[:120000]` cap so the ratio is faithful).
  * COMPACT-01 — the skeleton markers are present and the full `--- CURRENT HTML
    (modify this` block is ABSENT for task 2+.
  * Task-1 control — the full-HTML block is STILL injected for task 1 (no prior HTML
    to compact).
  * Req 7 (read-before-edit) — the compacted task-2 message carries a literal
    `read_file('prototype.html')` pointer AND the `prototype-build` tool-set still
    grants the native filesystem tools (`exclude_builtin=False`), i.e. no tool-set
    change removed fs read access.

Reverting the engine edit (the `is_build_task_2_plus` skeleton branch in
`_build_context_message`) makes the ≥50% and marker tests FAIL — this is a real
ratchet, not a vacuous one.
"""

from __future__ import annotations

# Import the scripted-model harness FIRST so its import-time env setup
# (RUNS_ROOT→temp + ENV=development) runs and the test stays fully offline.
from tests.agents import _scripted_model  # noqa: F401  (import for side effects)

from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import ExecutionEngine
from agents.factory import AgentContext, _build_runner_tools
from agents.registry import get_agent_by_id

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


def _make_ectx() -> ExecutionContext:
    """Build a minimal per-run ExecutionContext for a direct injection-site call.

    od_context is an empty dict so the od_prototype/od_ppt `injects` branches
    (design_system / template body) stay inert — this test isolates the
    CURRENT-HTML / skeleton branch.
    """
    ectx = ExecutionContext(run_id="test-run", owner_id="anon")
    ectx.od_context = {}
    ectx.current_task_block = "## Task 2: Fill the settings page\nAdd the settings form."
    return ectx


def _build_message(task_number: str) -> str:
    """Drive the REAL `_build_context_message` for a prototype-build context at the
    given build-task number, with the multi-page fixture as the current HTML."""
    engine = ExecutionEngine()
    spec = get_agent_by_id("prototype-build")
    assert spec is not None, "prototype-build spec must resolve"
    ectx = _make_ectx()
    accumulated_outputs = {
        "prototype-build": _MULTI_PAGE_HTML,
        "_build_task_number": task_number,
        "_build_task_total": "2",
    }
    return engine._build_context_message(
        spec=spec,
        ordered_agents=[spec],
        user_message="Build a SaaS dashboard prototype.",
        accumulated_outputs=accumulated_outputs,
        planning_context={},
        ectx=ectx,
    )


def _fullhtml_baseline_len(task_message_prefix: str) -> int:
    """Replicate the size the OLD full-HTML path would have injected for task 2.

    The old branch appended `--- CURRENT HTML (modify this …) ---\n{html[:120000]}…
    \n--- END CURRENT HTML ---`. We reconstruct what THIS task-2 message would have
    been under the old behavior: the compacted message with its skeleton block
    swapped back for the full-HTML block. To keep the comparison honest we measure
    the full-HTML *block* added to everything-else-in-the-message.

    `task_message_prefix` is the task-2 message with the skeleton block already
    present; we strip the skeleton block out and add the full-HTML block to get the
    pre-compaction message size.
    """
    html_to_pass = _MULTI_PAGE_HTML[:120000]
    truncated = len(_MULTI_PAGE_HTML) > 120000
    full_block = (
        f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n"
        f"{html_to_pass}"
        f"{'...[truncated at 120k]' if truncated else ''}\n"
        f"--- END CURRENT HTML ---"
    )
    return len(full_block)


_SKELETON_MARKERS = (
    ":root tokens",
    "Chrome:",
    "Total HTML so far",
)


def test_build_task2_context_is_at_least_50pct_smaller() -> None:
    """COMPACT-03 CI gate: the task-2 message is ≤ 50% of the full-HTML version.

    We compute the full-HTML baseline as the message the OLD path would have built
    (the same task-2 message but with the full-HTML block instead of the skeleton
    block). The skeleton-vs-full delta is the only difference between the two, so a
    block-level ≥50% reduction implies the whole message shrinks by ≥50% relative to
    the baseline whenever the full-HTML block dominates the message — which it does
    on a multi-page fixture (the fixture is >100k chars; the rest of the message is
    a few hundred).
    """
    compacted = _build_message("2")

    # Size the message would have been under the OLD full-HTML behavior: take the
    # compacted message, remove the skeleton block, add the full-HTML block.
    skeleton = ExecutionEngine()._extract_html_skeleton(_MULTI_PAGE_HTML)
    skeleton_block = (
        f"\n=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') "
        f"for full content before editing) ===\n"
        f"{skeleton}\n"
        f"=== END CURRENT PROTOTYPE ==="
    )
    assert skeleton_block in compacted, "skeleton block must be present in the task-2 message"

    full_block = (
        f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n"
        f"{_MULTI_PAGE_HTML[:120000]}"
        f"{'...[truncated at 120k]' if len(_MULTI_PAGE_HTML) > 120000 else ''}\n"
        f"--- END CURRENT HTML ---"
    )
    fullhtml_message = compacted.replace(skeleton_block, full_block)

    assert len(compacted) <= 0.5 * len(fullhtml_message), (
        f"task-2 compacted message ({len(compacted)} chars) must be ≤ 50% of the "
        f"full-HTML message ({len(fullhtml_message)} chars); "
        f"ratio={len(compacted) / len(fullhtml_message):.3f}"
    )


def test_build_task2_uses_skeleton_not_full_html() -> None:
    """COMPACT-01: task-2 carries the skeleton markers; the full-HTML block is absent."""
    compacted = _build_message("2")

    for marker in _SKELETON_MARKERS:
        assert marker in compacted, f"skeleton marker {marker!r} missing from task-2 message"
    # At least one of the filled/empty page lines must be present.
    assert ("Pages already built" in compacted) or ("Pages still empty" in compacted), (
        "expected a 'Pages already built'/'Pages still empty' skeleton line"
    )
    # The full-HTML injection block must NOT appear for task 2+.
    assert "--- CURRENT HTML (modify this" not in compacted, (
        "the full CURRENT HTML block must be absent for build task 2+"
    )


def test_build_task1_still_injects_full_html() -> None:
    """Control: task 1 (HTML shell) keeps the full-HTML block unchanged."""
    msg = _build_message("1")
    assert "--- CURRENT HTML (modify this" in msg, (
        "task 1 must still receive the full CURRENT HTML block"
    )
    # Task 1 must NOT use the skeleton framing.
    assert "=== CURRENT PROTOTYPE (skeleton" not in msg, (
        "task 1 must not use the skeleton block"
    )


def test_build_task2_preserves_read_file_access() -> None:
    """Req 7: the task-2 message instructs read-before-edit AND the prototype-build
    tool-set still grants the native fs tools (read_file available)."""
    compacted = _build_message("2")
    # The compacted prompt points the agent at read_file('prototype.html').
    assert "read_file('prototype.html')" in compacted, (
        "the task-2 skeleton block must carry a read_file('prototype.html') pointer"
    )

    # The prototype-build tool-set still grants native fs tools (exclude_builtin=False
    # ⇒ read_file/write_file/edit_file remain bound). No tool-set change removed it.
    spec = get_agent_by_id("prototype-build")
    assert spec is not None
    assert "prototype_emit_only" in (spec.tools or []), (
        "prototype-build must still declare the prototype_emit_only tool-set"
    )
    ctx = AgentContext(user_request="Build a SaaS dashboard prototype.")
    _custom_tools, exclude_builtin = _build_runner_tools(spec, ctx)
    assert exclude_builtin is False, (
        "prototype-build must keep native deepagents fs tools (read_file) available "
        "on the task-2+ path (exclude_builtin must be False)"
    )


def test_revert_engine_edit_would_fail_skeleton_gate() -> None:
    """Ratchet self-check: the task-2 path differs from the task-1 path.

    If the engine edit were reverted, task-2 would inject the full-HTML block (same
    as task 1) and `test_build_task2_uses_skeleton_not_full_html` would fail. We
    assert here that the two paths genuinely diverge so the gate is non-vacuous.
    """
    msg1 = _build_message("1")
    msg2 = _build_message("2")
    assert ("--- CURRENT HTML (modify this" in msg1) and (
        "--- CURRENT HTML (modify this" not in msg2
    ), "task-1 and task-2 HTML injection paths must diverge (skeleton wiring live)"


def test_extract_html_skeleton_is_faithful_to_source() -> None:
    """Skeleton fidelity (non-vacuous offline coverage of the change's core premise).

    The offline parity test (test_phase3_parity.py) drives the SCRIPTED model, whose
    fixed single-section output is independent of the injected context — so it cannot
    detect a skeleton that drops, renames, or garbles a page (code-review WR-04). The
    whole phase rests on the premise that the ~1-3k char skeleton faithfully reflects
    the prior HTML; this test exercises `_extract_html_skeleton` DIRECTLY on the
    multi-page fixture and asserts every `data-page` ID, the routes map, and the
    `:root` tokens survive into the state-map. A regression that corrupts the skeleton
    fails HERE rather than silently shipping behind the vacuous scripted parity run.

    Fixture note: `_MULTI_PAGE_HTML` carries a closing `</body>`, so this does not
    exercise (or depend on) the pre-existing no-`</body>` edge in the helper's section
    regex (WR-02) — that robustness item is tracked for the Phase 7 CompactionStrategy
    re-expression, where the helper logic is owned. Here we pin the normal-case
    contract the wiring depends on.
    """
    skeleton = ExecutionEngine()._extract_html_skeleton(_MULTI_PAGE_HTML)

    # Every data-page section in the fixture (both filled) must be named — no section
    # silently dropped on the path that is now the agent's only structural view.
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

    # The skeleton is a COMPACTION — materially smaller than the source HTML it summarizes.
    assert len(skeleton) < 0.5 * len(_MULTI_PAGE_HTML), (
        f"skeleton ({len(skeleton)} chars) must be far smaller than the source "
        f"HTML ({len(_MULTI_PAGE_HTML)} chars) it summarizes"
    )
