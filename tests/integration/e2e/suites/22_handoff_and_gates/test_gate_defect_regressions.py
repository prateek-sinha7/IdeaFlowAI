"""Browser regressions for ISS-131 / ISS-072 / ISS-090, driven through the real UI.

Every test here is `@live`: each one launches (or composes-then-launches) a real
pipeline against a real model and drives it to a real human gate. The tier is
deselected by default (`pytest.ini` carries `-m "not live"`), exactly like
`suites/25_pipeline_smoke/test_pipeline_smoke.py` — these only execute under an
explicit `-m live`, and were written but NOT executed by the agent that wrote them
(no live run may be started without the user's own go-ahead for the session).

These do not carry `@pytest.mark.scenario` — they are defect regressions tied to
`.knowledge/cards/*ISS-131*`, `*ISS-072*`, `*ISS-090*`, not Gherkin scenario
implementations, so `capture/_scenarios.py`'s bidirectional link does not apply to
them (see the suite's own `test_handoff_and_gates.py` for the scenario-linked
tests). They carry `@pytest.mark.issue(...)` per the test-writer contract instead.

**Selectors below were confirmed live** (real Chrome, `qa-admin@flowinqa.com`,
against a running dev stack) before this file was written, not guessed:

  * `/create/prototype` → "Advanced" → a "Use my version" checkbox. CHECKED by
    default, it substitutes a saved/customised roster that hides most of the
    built-in pipeline's steps from the "Review gates" picker (only 2 of 5 agents
    show). UNCHECKING it restores the ORIGINAL 5-agent manifest — this is what
    makes `prototype-build` (the `task_loop` step ISS-090 is about) and
    `prototype-analyze` (the gate ISS-072 is about) selectable at all. The close
    button on that modal carries no name/testid/aria-label; closed via a JS
    `querySelectorAll` index, matching this repo's own documented quirk pattern
    for unlabeled elements (`accountMenuItemClickability` /
    `darkModeClickTextFail` in `bug-hunter/velocity.json`).
  * Once unchecked, "Review gates" exposes real checkboxes
    `input[name="review-gate-<agent-id>"]` for all five prototype steps.
  * **"Continue" on this wizard LAUNCHES the run immediately** — there is no
    separate template/design-system step first, unlike the dashboard-card flow
    `framework.live.launch()` drives. Confirmed live (and immediately cancelled,
    0/5 agents run, nothing billed beyond the cheap clarify pass) — recorded here
    so nobody repeats that surprise.
  * The composer (`/workflows/new`) Config tab has a "Gate" combobox
    ("No gate" / "Conditional gate" / "Human gate") and a "Fan out over a list"
    switch, disabled until an earlier step exists. Toggling both on the SAME step
    is exactly ISS-131's composed reproduction — confirmed live: the sidebar's
    "Declared capabilities" chip shows `human` and the toolbar's agent-count
    strip increments its "review gates" counter to 1.
  * Gate action testids (`framework/live.py` + `frontend/src/components/chat/
    InlineGateActions.tsx`): `chat-gate-actions`, `chat-gate-approve`,
    `chat-gate-request-changes` (opens the redo composer),
    `chat-gate-redo` (submits it), `chat-gate-update-specs`.
"""

from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import expect

from framework import api, live, settings
from framework.locators import home_catalog as HOME
from framework.locators import run_detail as RD

pytestmark = pytest.mark.live

GATE_ACTIONS = live.GATE_ACTIONS
GATE_APPROVE = live.GATE_APPROVE
REQUEST_CHANGES = '[data-testid="chat-gate-request-changes"]'
REDO_SUBMIT = '[data-testid="chat-gate-redo"]'
REDO_INSTRUCTIONS = 'textarea[name="redo-instructions"], [data-testid="redo-instructions"]'
UPDATE_SPECS = '[data-testid="chat-gate-update-specs"]'

BRIEF = "Say hello to the world. Keep it to one short sentence."


def _stamp(tag: str) -> str:
    return f"{BRIEF} [{tag}-{int(time.time() * 1000) % 10_000_000}]"


def _close_advanced_modal(page) -> None:
    """The modal's close icon carries no name/testid/aria-label — closed by
    index, matching this repo's own documented quirk pattern for unlabeled
    elements rather than guessing a brittle CSS path."""
    page.evaluate("document.querySelectorAll('.fixed.inset-0.z-50 button')[1].click()")
    page.wait_for_timeout(settings.SETTLE_MS // 2)


def launch_prototype_with_gates(page, gate_agent_ids: list[str], tag: str) -> str:
    """Launch the built-in `prototype` pipeline with specific steps gated for
    human review, via the REAL wizard — never `POST /api/runs`, which skips the
    launch assembly (template/roster/gates) a user's launch performs.

    Returns the new run's id. Leaves the page on `/runs/<id>/stream`.
    """
    page.goto("/create/prototype")
    expect(page.locator('textarea[name="brief"]')).to_be_visible(timeout=30_000)

    page.get_by_role("button", name=re.compile("Advanced")).click()
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    use_my_version = page.get_by_role("checkbox", name="Use my version")
    if use_my_version.is_checked():
        use_my_version.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)
    _close_advanced_modal(page)

    page.get_by_role("button", name=re.compile("Review gates")).click()
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    for agent_id in gate_agent_ids:
        page.locator(f'input[name="review-gate-{agent_id}"]').check(force=True)

    page.fill('textarea[name="brief"]', _stamp(tag))
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Continue").click()

    live.wait_for_url_containing(page, "/runs/")
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


# ===========================================================================
# ISS-131 / FIX-424 — a declared human gate silently dropped on a composed
# fan-out step
# ===========================================================================


def compose_and_launch_fanout_with_declared_gate(page, tag: str) -> str:
    """Build the ISS-131 reproduction — a two-step custom workflow whose SECOND
    step both fans out over the first step's task list AND declares a human
    gate — then launch it through the real UI.

    Not reachable from any first-party file manifest (the card's own finding):
    `sample_fanout` / `sample_wave` are the only two `fanout_batch`/`wave_scheduler`
    workflows, and both are `user_launchable: false` (their agents have no
    `AGENT.md` on disk — launching either 404s building the roster). This
    composed selection is the only way in the card names.

    The manifest is built via a direct `POST /api/user-workflows`, not the
    composer UI: confirmed live that the composer's "Fan out over a list"
    toggle and "Gate" dropdown, set on the SAME step, do not reliably persist
    together through "Save workflow" — three separate saves with both fields
    visibly correct in the DOM (`aria-checked="true"`, `<select>.value ===
    "human"`) each round-tripped `strategy: "single_shot"` to the server
    (`gates: ["human"]` DID persist). That looks like its own composer defect,
    separate from ISS-131, and out of scope here to chase further — the shape
    below is the exact JSON `POST /api/user-workflows` accepts (captured from
    the composer's own outbound payload before the flake), so authoring this
    way exercises the same runtime manifest a working composer save would
    have produced. The LAUNCH below is real UI, which is what actually drives
    the engine path this defect is about.
    """
    page.goto("/dashboard")
    expect(page.get_by_text(HOME.HEADING)).to_be_visible(timeout=30_000)

    specify_id = "1-specify"
    worker_id = "2-worker"
    resp = api.json_body(
        page,
        "POST",
        "/api/user-workflows",
        {
            "name": f"ISS-131 fanout gate {tag}-{int(time.time() * 1000) % 10_000_000}",
            "base_pipeline_type": "custom",
            "agent_ids": [specify_id, worker_id],
            "manifest": {
                "steps": [
                    {
                        "agent": "custom-agent",
                        "instance_id": specify_id,
                        "name": "Task Planner",
                        "prompt": "List exactly two tasks as '## Task 1: ...' "
                        "and '## Task 2: ...' headings.",
                        "tools": {"read_files": True, "write_files": True, "exec": False},
                        "gates": [],
                        "strategy": "single_shot",
                        "depends_on": [],
                    },
                    {
                        "agent": "custom-agent",
                        "instance_id": worker_id,
                        "name": "Fanout Worker",
                        "prompt": "Say hello for the task described above.",
                        "tools": {"read_files": True, "write_files": True, "exec": False},
                        "gates": ["human"],
                        "strategy": "fanout_batch",
                        "task_source": {
                            "kind": "parsed",
                            "parser": "heading_tasks",
                            "source_step": f"custom-agent:{specify_id}",
                        },
                        "depends_on": [f"custom-agent:{specify_id}"],
                    },
                ],
                "deliverable": {"strategy": "streamed_text", "name": "output.md"},
                "planner": "skip",
                "clarify": {"mode": "skip", "defaults": []},
            },
        },
    )
    workflow_id = resp["id"]

    page.goto(f"/workflows/{workflow_id}/run")
    expect(page.locator('textarea[name="brief"]')).to_be_visible(timeout=30_000)
    page.fill('textarea[name="brief"]', _stamp(tag))
    page.wait_for_timeout(600)
    page.get_by_role("button", name=re.compile("Run|Continue")).first.click()

    live.wait_for_url_containing(page, "/runs/")
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


@pytest.mark.issue("ISS-131")
@pytest.mark.destructive
@pytest.mark.timeout(600)
def test_a_composed_fanout_steps_declared_human_gate_still_pauses_the_run(page, shot):
    """ISS-131 — a fan-out step that both declares `gates: [human]` and runs a
    spawn-only strategy must still pause for review. Pre-fix it sailed straight
    past with nothing emitted to say the gate was dropped.
    """
    with shot("composed-fanout-launched", "When I launch the composed fan-out workflow"):
        run_id = compose_and_launch_fanout_with_declared_gate(page, "iss131")

    live.wait_until(
        page,
        lambda p: live.at_gate(p) or live.is_done(p),
        "the declared human gate to open",
        timeout_ms=300_000,
    )

    with shot("declared-gate-fires", "Then the declared gate pauses the run"):
        assert live.at_gate(page), (
            f"run {run_id} never paused at the fan-out worker's declared human gate "
            f"(ISS-131) — it went straight to {live.status(page)!r} instead"
        )
        expect(page.locator(GATE_ACTIONS)).to_be_visible()


# ===========================================================================
# ISS-072 / FIX-420 — one "Update the Specs" click must cost two approvals,
# not three
# ===========================================================================


@pytest.mark.issue("ISS-072")
@pytest.mark.destructive
@pytest.mark.timeout(600)
def test_one_update_the_specs_click_costs_two_gates_not_three(page, shot):
    """ISS-072 — clicking "Update the Specs" at the analyze gate must reopen
    exactly ONE further gate (the re-opened analyze gate), not two (the
    suppressed in-pass re-run plus the re-opened gate). One click, two total
    approvals for the cycle (outer + re-opened), never three.
    """
    with shot("prototype-launched", "When I launch prototype with the analyze step gated"):
        run_id = launch_prototype_with_gates(page, ["prototype-analyze"], "iss072")

    live.wait_until(page, live.at_gate, "the analyze gate to open", timeout_ms=300_000)
    with shot("analyze-gate-open", "Then the outer analyze gate is open"):
        expect(page.locator(GATE_ACTIONS)).to_be_visible()
        expect(page.locator(UPDATE_SPECS)).to_be_visible()

    page.locator(UPDATE_SPECS).click()
    page.wait_for_timeout(settings.SETTLE_MS)

    gate_reopenings = 0
    deadline = time.time() + 300
    was_at_gate = False
    while time.time() < deadline and not live.is_done(page):
        now_at_gate = live.at_gate(page)
        if now_at_gate and not was_at_gate:
            gate_reopenings += 1
            with shot(
                f"gate-reopen-{gate_reopenings}",
                f"Then gate firing #{gate_reopenings} after Update the Specs",
            ):
                pass
            if gate_reopenings > 1:
                break
            live.approve(page)
        was_at_gate = now_at_gate
        page.wait_for_timeout(3000)
        page.reload()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert gate_reopenings == 1, (
        f"run {run_id}: one 'Update the Specs' click reopened the gate "
        f"{gate_reopenings} time(s) before completion; expected exactly 1 (the "
        "re-opened analyze gate) — the suppressed in-pass re-run (ISS-072) must "
        "not fire a second, redundant gate"
    )


# ===========================================================================
# ISS-090 / FIX-422 — `redoable` enforced on the way OUT: a task_loop step's
# per-task gate must not offer "Request changes"
# ===========================================================================


@pytest.mark.issue("ISS-090")
@pytest.mark.destructive
@pytest.mark.timeout(600)
def test_a_per_task_build_gate_offers_no_request_changes_control(page, shot):
    """ISS-090 (way out) — `prototype-build` runs as a `task_loop` (one worker
    per task); a gate on it fires once per task and must publish
    `redoable: false`, so the UI renders no "Request changes" control there.
    `prototype-specify` (a plain `single_shot` step, gated as the control) must
    still show the control at its own gate, immediately before it in the same
    run — proving the absence is specific to the per-task dispatch, not a
    blanket regression.
    """
    with shot(
        "prototype-launched-two-gates",
        "When I launch prototype with specify AND build gated",
    ):
        run_id = launch_prototype_with_gates(
            page, ["prototype-specify", "prototype-build"], "iss090"
        )

    # Gate 1: prototype-specify — single_shot, the control. Must show Request changes.
    live.wait_until(page, live.at_gate, "the specify gate to open", timeout_ms=300_000)
    with shot("specify-gate-has-redo", "Then the specify gate offers Request changes"):
        expect(page.locator(GATE_ACTIONS)).to_be_visible()
        expect(page.locator(REQUEST_CHANGES)).to_be_visible()
    live.approve(page)

    # Gate 2 (first occurrence): prototype-build's per-task gate. Must NOT.
    live.wait_until(
        page,
        lambda p: live.at_gate(p) or live.is_done(p),
        "the per-task build gate to open",
        timeout_ms=300_000,
    )
    assert live.at_gate(page), (
        f"run {run_id} completed without ever gating prototype-build; nothing to "
        "assert the missing control against"
    )
    with shot(
        "build-gate-hides-redo",
        "Then the per-task build gate offers no Request changes control",
    ):
        expect(page.locator(GATE_ACTIONS)).to_be_visible()
        assert page.locator(REQUEST_CHANGES).count() == 0, (
            f"run {run_id}: the per-task build gate rendered a Request changes "
            "control (ISS-090) — redoable must be false for a build_task_number "
            "dispatch, and the FE must hide the button when it is"
        )


# ===========================================================================
# ISS-090 / FIX-422 — the "way in": _run_review_gate must refuse a redo the
# firing never advertised. NOT a UI-drivable test: the fix's whole point is
# that the button above never renders, so no ordinary click can reach this
# path — it needs a scripted/replayed POST, which is what the fix's own
# language ("a replayed or scripted response") describes. Proven instead at
# backend/tests/integration/test_gate_redo_enforcement.py, over the real
# `POST /api/runs/{run_id}/gate` HTTP ingress (not a direct engine-method call).
# ===========================================================================
