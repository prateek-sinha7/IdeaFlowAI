"""Pre-Phase-7 ``context_message`` ORACLE — stability + current-routed DIVERGENCE.

This is cluster C step 1 (07-08): the oracle is the engine-INDEPENDENT ground truth for
the true pre-Phase-7 (``acd1636``) assembled ``context_message`` bytes
(``tests/agents/characterization/oracle/legacy_context_message.py``). This module:

  1. STABILITY — pins the oracle: ``build_oracle_message`` is byte-stable across calls and
     carries the legacy structural markers the cluster-C regressions (CR-01/CR-02/CR-04)
     dropped: the UNCONDITIONAL ``=== TEMPLATE COMPLIANCE ===`` block on build tasks, the
     BARE ``=== END ACTIVE DESIGN SYSTEM ===`` marker (no ``: {id}`` suffix), the task-2+
     ``=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') ...`` wrapper, and
     the RAW (un-rewrapped) injection parts.

  2. DIVERGENCE — drives a real ``prototype`` build via ``_drive("prototype")``, extracts
     the build-agent ``context_message`` from the emitted ``agent_input`` events, and asserts
     it does NOT yet equal the oracle bytes. This is the drift the 07-06 de-blind MASKED
     (07-REVIEW-DEEP.md systemic[0]: the goldens were regenerated against the POST-refactor
     routed bytes, which had already drifted from the true pre-Phase-7 prompt — so
     "pinned == correct" is false). It is marked ``xfail`` and IS THE 07-09 ACCEPTANCE
     TARGET: 07-09 corrects the engine/provider so the routed build prompt equals the oracle,
     at which point this xfail flips to a hard equality PASS (xpass → 07-09 removes the mark).

GOLDENS ARE NOT TOUCHED HERE (07-08 scope boundary). Because the routed engine has NOT been
corrected yet (that is 07-09), regenerating the five ``golden/*.events.json`` snapshots with
``SNAPSHOT_UPDATE=1`` now would only RE-PIN THE SAME DRIFTED BYTES. So this plan leaves the
five goldens untouched: they remain on the drifted bytes until 07-09 corrects the engine,
at which point 07-09 regenerates them AND asserts the regenerated build-agent
``context_message`` equals the oracle (closing the loop). This module's job is solely to make
the oracle the assertion target and prove today's divergence.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import _drive
from tests.agents.characterization.oracle import (
    AGENT_CLASSES,
    build_oracle_message,
)


# ===========================================================================
# (1) Oracle STABILITY + legacy structural-marker assertions.
# ===========================================================================


def test_oracle_is_byte_stable_across_calls() -> None:
    """``build_oracle_message`` is deterministic — identical bytes on repeated calls."""
    for ac, task in [
        ("prototype-specify", ""),
        ("prototype-plan", ""),
        ("prototype-build", "1"),
        ("prototype-build", "2"),
    ]:
        first = build_oracle_message(ac, task=task)
        second = build_oracle_message(ac, task=task)
        assert first == second, f"oracle bytes for {ac!r}/{task!r} are not stable"
        assert first, f"oracle bytes for {ac!r}/{task!r} are empty"


def test_oracle_build_task_1_has_legacy_structural_markers() -> None:
    """Build task 1 carries the markers CR-01/CR-02/CR-04 dropped from the routed prompt."""
    msg = build_oracle_message("prototype-build", task="1")

    # CR-01: the UNCONDITIONAL TEMPLATE COMPLIANCE block (dropped from the routed prompt).
    assert "=== TEMPLATE COMPLIANCE ===" in msg
    assert "use ONLY its CSS classes from the TEMPLATE SEED" in msg

    # CR-02 / bare END marker: `=== END ACTIVE DESIGN SYSTEM ===` with NO `: {id}` suffix
    # (the routed injector wraps as `=== END ACTIVE DESIGN SYSTEM: default ===`).
    assert "=== END ACTIVE DESIGN SYSTEM ===" in msg
    assert "=== END ACTIVE DESIGN SYSTEM: " not in msg

    # CR-04: injection parts are RAW — the SEED part keeps its own bare envelope and is
    # NOT nested inside a `=== TEMPLATE INJECTION PART N: ... ===` outer wrapper.
    assert "=== TEMPLATE SEED (assets/template.html) ===" in msg
    assert "=== END TEMPLATE SEED ===" in msg
    assert "TEMPLATE INJECTION PART" not in msg

    # The builder (tools=[prototype_emit_only]) DOES get the example.html block.
    assert "=== TEMPLATE EXAMPLE (example.html): " in msg
    assert "=== END TEMPLATE EXAMPLE ===" in msg


def test_oracle_build_task_2_has_skeleton_wrapper_and_suppressions() -> None:
    """Build task 2+ carries the skeleton wrapper + read_file instruction, DS body suppressed."""
    msg = build_oracle_message("prototype-build", task="2")

    # The task-2+ skeleton wrapper with the read_file('prototype.html') instruction.
    assert (
        "=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') "
        "for full content before editing) ===" in msg
    )
    assert "=== END CURRENT PROTOTYPE ===" in msg

    # TEMPLATE COMPLIANCE is still UNCONDITIONAL on task 2+.
    assert "=== TEMPLATE COMPLIANCE ===" in msg

    # is_build_task_2_plus suppresses the DS body, the template body, and the example;
    # ONLY the TEMPLATE SEED injection part survives.
    assert "=== ACTIVE DESIGN SYSTEM:" not in msg
    assert "=== ACTIVE TEMPLATE (SKILL.md):" not in msg
    assert "=== TEMPLATE EXAMPLE (example.html):" not in msg
    assert "=== TEMPLATE SEED (assets/template.html) ===" in msg
    # The non-seed reference part is dropped on task 2+.
    assert "=== TEMPLATE REFERENCE (" not in msg


def test_oracle_planning_agents_get_no_example_html() -> None:
    """Planning agents (tools=[]) get NO example.html — the `_is_builder` gate (both refs)."""
    for ac in ("prototype-specify", "prototype-plan"):
        msg = build_oracle_message(ac, task="")
        assert "=== TEMPLATE EXAMPLE (example.html):" not in msg, (
            f"{ac} must NOT receive the example.html block (acd1636 _is_builder gate)"
        )
        # Planning agents are not builders -> no injection parts and no TEMPLATE COMPLIANCE.
        assert "=== TEMPLATE SEED" not in msg
        assert "=== TEMPLATE COMPLIANCE ===" not in msg
        # They DO get the DS + template body blocks (injects=[template, design_system]).
        assert "=== ACTIVE DESIGN SYSTEM: " in msg
        assert "=== ACTIVE TEMPLATE (SKILL.md): " in msg


def test_oracle_classes_exported() -> None:
    """The oracle exposes the three captured agent classes."""
    assert set(AGENT_CLASSES) == {"prototype-specify", "prototype-plan", "prototype-build"}


# ===========================================================================
# (2) BYTE-EQUALITY — the routed build prompt now EQUALS the oracle (07-09).
#
# 07-09 corrected the engine/provider so the routed prototype-build context_message is
# byte-equal to the pre-Phase-7 (acd1636) oracle. The 07-08 xfail divergence test is now
# a HARD equality PASS. The oracle is a RECONSTRUCTION FUNCTION of (gate logic + ordering
# + wrapper bytes); the comparison feeds it the SAME dynamic inputs the routed path saw
# (the harness od_context, the real get_template_injection_parts / get_example_html bytes,
# the routed planner task body + the agnostic planning/consumed blocks) so equality
# verifies the legacy CONTRACT byte-for-byte over identical content — CR-01 (TEMPLATE
# COMPLIANCE restored), CR-02 (per-injects gate), CR-04 (raw injection parts), WR-03 (bare
# END markers), WR-01 (skeleton wrapper on task 2+).
# ===========================================================================

from agents.execution_engine.od_context import (  # noqa: E402
    get_example_html,
    get_template_injection_parts,
)

# The harness od_context (tests/agents/_scripted_model.py:_drive) — the live bodies the
# routed OD provider composes from. Mirrored here so the oracle assembles from the SAME
# content (NOT the small ORACLE_OD_CONTEXT fixture).
_HARNESS_OD_CONTEXT = {
    "template_body": "## Workflow\nUse .card and .grid classes. Build pages into <section data-page>.",
    "template_id": "web-prototype",
    "ds_id": "default",
    "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;--border:#ddd;--muted:#888;}",
    "craft_block": "Keep markup semantic; wire every nav link.",
    "is_design_system_required": True,
}
_HARNESS_USER_MESSAGE = "Build me a thing for managing tasks."


def _build_agent_context_messages(events: list[dict]) -> list[str]:
    """Extract every ``prototype-build`` ``context_message`` from the agent_input events."""
    out: list[str] = []
    for ev in events:
        if ev.get("type") != "agent_input":
            continue
        data = ev.get("data") or {}
        if data.get("agent_id") == "prototype-build":
            cm = data.get("context_message")
            if isinstance(cm, str):
                out.append(cm)
    return out


def _slice_between(text: str, start_marker: str, end_marker: str) -> str:
    """Return the substring from ``start_marker`` through ``end_marker`` (inclusive)."""
    i = text.index(start_marker)
    j = text.index(end_marker, i) + len(end_marker)
    return text[i:j]


def _extract_consumed_block(text: str) -> str:
    """Return the routed consumed-output PART verbatim (``\\n--- Output from ... {output}``).

    The engine appends the consumed-output block as ONE ``parts`` entry
    (``\\n--- Output from {label} ---\\n{output}``) and the CURRENT TASK block as a
    SEPARATE entry starting with ``\\n``; the ``"\\n".join(parts)`` then places exactly
    ``\\n\\n=== CURRENT TASK ===`` after the consumed text. So the consumed PART is the
    slice from the first ``\\n--- Output from`` up to (not including) that ``\\n\\n=== CURRENT
    TASK ===`` boundary — passed to the oracle as its own part to reproduce the join math.
    """
    i = text.index("\n--- Output from")
    j = text.index("\n\n=== CURRENT TASK ===", i)
    return text[i:j]


@pytest.mark.asyncio
async def test_routed_build_prompt_equals_oracle_byte_for_byte() -> None:
    """07-09 ACCEPTANCE: the routed prototype-build context_message == the oracle bytes.

    Drives a real prototype build and reconstructs the legacy (acd1636) bytes via the
    oracle fed the SAME dynamic inputs the routed path saw — then asserts byte-equality.
    This is the flipped 07-08 xfail (now a hard PASS): the engine is corrected so the
    routed build prompt carries the legacy contract verbatim.
    """
    events = await _drive("prototype")
    assert events, "prototype produced no events"

    routed = _build_agent_context_messages(events)
    assert routed, "no prototype-build agent_input context_message captured"

    # The live dynamic content the routed OD provider read from disk.
    parts = list(get_template_injection_parts("web-prototype") or [])
    example = get_example_html("web-prototype")

    # The agnostic planning + consumed-output blocks the routed path injects (extracted
    # from the routed message itself — they are workflow-agnostic, unchanged by Phase 7,
    # and not part of the cluster-C contract under test).
    planning_block = _slice_between(
        routed[0], "## Planning Context (Deep Planner Analysis)", "## End Planning Context"
    )
    consumed_block = _extract_consumed_block(routed[0])

    # ── Task 1 — no prior HTML → no skeleton block ─────────────────────────────
    oracle_t1 = build_oracle_message(
        "prototype-build",
        task="1",
        od_context=_HARNESS_OD_CONTEXT,
        user_message=_HARNESS_USER_MESSAGE,
        injection_parts=parts,
        example_html=example,
        task_body="## Task 1: Build the HTML shell\nCreate the document skeleton.",
        task_total="2",
        planning_block=planning_block,
        consumed_block=consumed_block,
    )
    assert routed[0] == oracle_t1, (
        "routed prototype-build task-1 context_message != oracle bytes\n"
        f"--- routed ---\n{routed[0]!r}\n--- oracle ---\n{oracle_t1!r}"
    )


@pytest.mark.asyncio
async def test_routed_build_task_2_equals_oracle_byte_for_byte() -> None:
    """07-09 WR-01: the routed task-2 build prompt == the oracle (skeleton block present).

    Task 2+ carries the STANDALONE ``=== CURRENT PROTOTYPE (skeleton — call read_file(
    'prototype.html') ...) ===`` block (WR-01) after the CURRENT TASK block, with the DS /
    template / example bodies suppressed and ONLY the seed injection part — byte-equal to
    the oracle fed the same dynamic content.
    """
    events = await _drive("prototype")
    routed = _build_agent_context_messages(events)
    assert len(routed) >= 2, "expected a second build task (task 2)"

    parts = list(get_template_injection_parts("web-prototype") or [])
    example = get_example_html("web-prototype")

    # The routed task-2 message carries the skeleton block (WR-01); extract its inner
    # content + the agnostic planning/consumed blocks to reconstruct the oracle.
    skel_block = _slice_between(
        routed[1], "=== CURRENT PROTOTYPE (skeleton", "=== END CURRENT PROTOTYPE ==="
    )
    inner_skeleton = skel_block[
        skel_block.index("===\n") + 4 : skel_block.rindex("\n=== END CURRENT PROTOTYPE ===")
    ]
    planning_block = _slice_between(
        routed[1], "## Planning Context (Deep Planner Analysis)", "## End Planning Context"
    )
    consumed_block = _extract_consumed_block(routed[1])

    oracle_t2 = build_oracle_message(
        "prototype-build",
        task="2",
        od_context=_HARNESS_OD_CONTEXT,
        user_message=_HARNESS_USER_MESSAGE,
        injection_parts=parts,
        example_html=example,
        skeleton=inner_skeleton,
        task_body="## Task 2: Fill the dashboard page\nAdd the dashboard content.",
        task_total="2",
        planning_block=planning_block,
        consumed_block=consumed_block,
    )
    assert routed[1] == oracle_t2, (
        "routed prototype-build task-2 context_message != oracle bytes\n"
        f"--- routed ---\n{routed[1]!r}\n--- oracle ---\n{oracle_t2!r}"
    )


@pytest.mark.asyncio
async def test_routed_build_prompt_has_template_compliance_now() -> None:
    """CR-01 restored: the routed build prompt now CARRIES TEMPLATE COMPLIANCE on every task.

    Inversion of the 07-08 ``..._is_missing_template_compliance_today`` test — 07-09
    re-emits the unconditional TEMPLATE COMPLIANCE block, so it is present on every routed
    build task (and the END marker is bare). Also confirms the bare DS END marker (WR-03)
    and the raw injection parts (CR-04) reached the routed prompt.
    """
    events = await _drive("prototype")
    routed = _build_agent_context_messages(events)
    assert routed, "no prototype-build agent_input context_message captured"

    for cm in routed:
        # CR-01: TEMPLATE COMPLIANCE present on every build task.
        assert "=== TEMPLATE COMPLIANCE ===" in cm
        assert "use ONLY its CSS classes from the TEMPLATE SEED" in cm
        # CR-04: injection parts RAW — the SEED keeps its own envelope, NOT nested in a
        # `=== TEMPLATE INJECTION PART N: ... ===` outer wrapper.
        assert "TEMPLATE INJECTION PART" not in cm

    # WR-03: the DS END marker is BARE (task 1 carries the DS block).
    assert "=== END ACTIVE DESIGN SYSTEM ===" in routed[0]
    assert "=== END ACTIVE DESIGN SYSTEM: " not in routed[0]


# ===========================================================================
# (3) LOOP CLOSED — the regenerated goldens pin the ORACLE, not the drift.
# ===========================================================================

import json  # noqa: E402
from pathlib import Path  # noqa: E402

_GOLDEN_DIR = Path(__file__).parent / "characterization" / "golden"


def _golden_build_context_messages(golden_name: str) -> list[str]:
    """Extract the prototype-build context_message(s) from a regenerated golden."""
    path = _GOLDEN_DIR / golden_name
    events = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for ev in events:
        if ev.get("type") != "agent_input":
            continue
        data = ev.get("data") or {}
        if data.get("agent_id") == "prototype-build":
            cm = data.get("context_message")
            if isinstance(cm, str):
                out.append(cm)
    return out


@pytest.mark.parametrize("golden_name", ["prototype.events.json"])
def test_regenerated_golden_build_prompt_equals_oracle(golden_name: str) -> None:
    """T-07-09-02: the regenerated build-agent context_message in the golden == the oracle.

    Closes the cluster-C loop: 07-06 de-blinded the goldens against the DRIFTED routed
    bytes ("pinned == correct" was false); 07-09 corrected the engine, regenerated the
    goldens, and this asserts the build-agent context_message NOW pinned in the golden is
    byte-equal to the pre-Phase-7 (acd1636) oracle — so the goldens pin GROUND TRUTH, not
    the drift. The oracle is fed the same dynamic content the routed path saw; the agnostic
    planning/consumed blocks are extracted from the golden's own bytes.
    """
    golden_msgs = _golden_build_context_messages(golden_name)
    assert golden_msgs, f"{golden_name} has no prototype-build context_message"

    parts = list(get_template_injection_parts("web-prototype") or [])
    example = get_example_html("web-prototype")

    # Task 1 (the first build-agent message in the golden).
    g1 = golden_msgs[0]
    planning_block = _slice_between(
        g1, "## Planning Context (Deep Planner Analysis)", "## End Planning Context"
    )
    consumed_block = _extract_consumed_block(g1)
    oracle_t1 = build_oracle_message(
        "prototype-build",
        task="1",
        od_context=_HARNESS_OD_CONTEXT,
        user_message=_HARNESS_USER_MESSAGE,
        injection_parts=parts,
        example_html=example,
        task_body="## Task 1: Build the HTML shell\nCreate the document skeleton.",
        task_total="2",
        planning_block=planning_block,
        consumed_block=consumed_block,
    )
    assert g1 == oracle_t1, (
        f"{golden_name} task-1 build context_message != oracle (golden still drifted?)\n"
        f"--- golden ---\n{g1!r}\n--- oracle ---\n{oracle_t1!r}"
    )
