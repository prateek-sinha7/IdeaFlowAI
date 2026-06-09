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
# (2) DIVERGENCE — the current routed build prompt does NOT equal the oracle.
# ===========================================================================


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


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=False,
    reason=(
        "07-09 ACCEPTANCE TARGET: the CURRENT routed build prompt has DRIFTED from the true "
        "pre-Phase-7 (acd1636) bytes — CR-01 (TEMPLATE COMPLIANCE dropped), CR-02 (DS block "
        "leaks past the per-injects gate + `: {id}` END suffix), CR-04 (injection parts "
        "double-wrapped), and the missing skeleton/CURRENT-HTML block. This xfail is the "
        "07-09 acceptance target: once 07-09 corrects the engine/provider so the routed "
        "build prompt equals the oracle, this flips to a hard equality PASS (the mark is "
        "removed and the goldens are re-pinned to oracle ground truth)."
    ),
)
async def test_current_routed_build_prompt_diverges_from_oracle() -> None:
    """DRIVE a real prototype build; assert the routed build prompt != the oracle (today).

    XFAIL by design (07-08). This proves the drift the 07-06 de-blind masked is real and
    tracked. 07-09 turns this into a hard equality pass after correcting the engine.
    """
    events = await _drive("prototype")
    assert events, "prototype produced no events"

    routed = _build_agent_context_messages(events)
    assert routed, "no prototype-build agent_input context_message captured"

    # The first build task is task 1. Compare against the task-1 oracle. The equality
    # is EXPECTED TO FAIL today (the engine is still drifted) — hence xfail. When 07-09
    # corrects the engine this assertion passes and the test xpasses (then de-marked).
    oracle_task_1 = build_oracle_message("prototype-build", task="1")
    assert routed[0] == oracle_task_1, (
        "the current routed prototype-build context_message EQUALS the oracle — if this "
        "passes BEFORE 07-09 corrects the engine, the oracle likely captured the DRIFTED "
        "bytes (re-examine the capture, T-07-08-01) rather than the true acd1636 prompt."
    )


@pytest.mark.asyncio
async def test_routed_build_prompt_is_missing_template_compliance_today() -> None:
    """Positive proof of ONE concrete drift: the routed build prompt drops TEMPLATE COMPLIANCE.

    Unlike the xfail above (full byte equality), this is a hard PASS today asserting a
    SPECIFIC documented regression (CR-01) is present in the live routed prompt — so the
    divergence is not vacuous and is pinned to a named finding. 07-09 restores the block;
    when it does, THIS test must be updated to assert the block IS present (tracked in the
    07-09 plan).
    """
    events = await _drive("prototype")
    routed = _build_agent_context_messages(events)
    assert routed, "no prototype-build agent_input context_message captured"

    # CR-01: the oracle has it on every build task; the drifted routed prompt does not.
    assert "=== TEMPLATE COMPLIANCE ===" in build_oracle_message("prototype-build", task="1")
    assert all("=== TEMPLATE COMPLIANCE ===" not in cm for cm in routed), (
        "the routed build prompt now CONTAINS TEMPLATE COMPLIANCE — CR-01 may already be "
        "fixed; if so this is 07-09 work and this assertion should be inverted."
    )
