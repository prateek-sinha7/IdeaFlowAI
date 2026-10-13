"""The persisted run row's token usage (run_commands._apply_terminal_output_columns).

Run c4cbd381 kept 55 of its 63 wave workers in ``agent_outputs`` — one "current
agent" slot, interleaved parallel events — and its saved cache reads came out short
(81.7M for 86.2M). Rows are now keyed by (agent_id, task_id), and the run totals and
cost come from the engine's pipeline_complete.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.capabilities.token_usage import USAGE_VERSION
from app.api.run_commands import _apply_terminal_output_columns


def _usage(i: int, o: int, cr: int, cw: int, model: str = "m-sonnet") -> dict:
    return {
        "input_tokens": i,
        "output_tokens": o,
        "total_tokens": i + o,
        "cache_read_tokens": cr,
        "cache_write_tokens": cw,
        "model_id": model,
        "usage_version": USAGE_VERSION,
    }


def _wr() -> SimpleNamespace:
    return SimpleNamespace(
        output=None,
        deliverable_mimetype=None,
        deliverable_filename=None,
        agent_outputs=None,
        model_id=None,
        token_usage=None,
        completed_at=None,
        duration=None,
    )


STEP = "custom-agent:us-write"
EVENTS = [
    ("agent_start", {"agent_id": STEP}),
    # three parallel members, interleaved
    ("agent_start", {"agent_id": STEP, "task_id": "k1", "task_author_id": "EPIC-01a"}),
    ("agent_start", {"agent_id": STEP, "task_id": "k2", "task_author_id": "EPIC-01b"}),
    (
        "tool_call",
        {"agent_id": STEP, "task_id": "k2", "tool": "write_file", "args": {"p": 2}},
    ),
    ("agent_start", {"agent_id": STEP, "task_id": "k3", "task_author_id": "EPIC-01c"}),
    (
        "tool_call",
        {"agent_id": STEP, "task_id": "k1", "tool": "write_file", "args": {"p": 1}},
    ),
    (
        "agent_complete",
        {"agent_id": STEP, "task_id": "k2", **_usage(200, 20, 2000, 50)},
    ),
    ("agent_chunk", {"agent_id": STEP, "task_id": "k1", "chunk": "one"}),
    (
        "agent_complete",
        {"agent_id": STEP, "task_id": "k1", **_usage(100, 10, 1000, 40)},
    ),
    (
        "agent_complete",
        {"agent_id": STEP, "task_id": "k3", **_usage(300, 30, 3000, 60, "m-haiku")},
    ),
    ("agent_complete", {"agent_id": STEP, "duration": 9.0}),
]


def test_every_parallel_member_keeps_its_own_row() -> None:
    wr = _wr()
    _apply_terminal_output_columns(wr, EVENTS, model_id=None, duration_seconds=None)
    rows = json.loads(wr.agent_outputs)
    members = {r.get("task_author_id"): r for r in rows if r.get("task_id")}
    assert set(members) == {"EPIC-01a", "EPIC-01b", "EPIC-01c"}
    assert members["EPIC-01a"]["output"] == "one"
    assert [t["args"] for t in members["EPIC-01a"]["tool_calls"]] == [{"p": 1}]
    assert [t["args"] for t in members["EPIC-01b"]["tool_calls"]] == [{"p": 2}]
    assert members["EPIC-01c"]["model_id"] == "m-haiku"
    # without pipeline_complete: totals are the members' sums, cache reads apart
    tu = json.loads(wr.token_usage)
    assert tu["total_input_tokens"] == 600 and tu["total_output_tokens"] == 60
    assert tu["total_tokens"] == 660
    assert (
        tu["total_cache_read_tokens"] == 6000 and tu["total_cache_write_tokens"] == 150
    )
    assert tu["usage_version"] == USAGE_VERSION


def test_run_totals_and_cost_come_from_pipeline_complete() -> None:
    wr = _wr()
    pc = (
        "pipeline_complete",
        {
            "final_output": "done",
            "total_input_tokens": 900,
            "total_output_tokens": 90,
            "total_tokens": 990,
            "total_cache_read_tokens": 7000,
            "total_cache_write_tokens": 170,
            "estimated_cost_usd": 1.5,
            "estimated_cost_full_usd": 2.5,
            "usage_version": USAGE_VERSION,
        },
    )
    _apply_terminal_output_columns(
        wr, [*EVENTS, pc], model_id="m", duration_seconds=None
    )
    tu = json.loads(wr.token_usage)
    assert (
        tu["total_input_tokens"],
        tu["total_output_tokens"],
        tu["total_tokens"],
    ) == (900, 90, 990)
    assert tu["total_cache_read_tokens"] == 7000
    assert (tu["estimated_cost_usd"], tu["estimated_cost_full_usd"]) == (1.5, 2.5)


def test_an_old_pipeline_complete_is_written_in_the_current_meaning() -> None:
    wr = _wr()
    old = (
        "pipeline_complete",
        {
            "total_input_tokens": 91842427,
            "total_output_tokens": 794633,
            "total_cache_read_tokens": 86207163,
            "total_cache_write_tokens": 5632290,
        },
    )
    _apply_terminal_output_columns(wr, [old], model_id="m", duration_seconds=None)
    tu = json.loads(wr.token_usage)
    # run c4cbd381: 92.6M "total" before, 6.43M now — cache reads kept apart
    assert tu["total_input_tokens"] == 5635264
    assert tu["total_tokens"] == 6429897
    assert tu["total_cache_read_tokens"] == 86207163
    assert tu["estimated_cost_usd"] == 19.637218
    assert tu["estimated_cost_full_usd"] == 95.815592


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        ({"estimated_cost_usd": 7.5}, (7.5, 95.815592)),
        ({"estimated_cost_full_usd": 8.5}, (19.637218, 8.5)),
    ],
    ids=["full-cost-missing", "metered-cost-missing"],
)
def test_apply_terminal_output_columns_reprices_only_missing_cost_when_partial_cost_is_authoritative(
    provided: dict[str, float], expected: tuple[float, float]
) -> None:
    wr = _wr()
    terminal = (
        "pipeline_complete",
        {
            "total_input_tokens": 91842427,
            "total_output_tokens": 794633,
            "total_cache_read_tokens": 86207163,
            "total_cache_write_tokens": 5632290,
            **provided,
        },
    )

    _apply_terminal_output_columns(wr, [terminal], model_id="m", duration_seconds=None)

    usage = json.loads(wr.token_usage)
    assert (
        usage["estimated_cost_usd"],
        usage["estimated_cost_full_usd"],
    ) == expected
