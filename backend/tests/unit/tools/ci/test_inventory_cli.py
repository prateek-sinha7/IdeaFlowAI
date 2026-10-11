"""Unit tests for ``tools.ci.inventory_cli.cmd_verify_execution``'s skip rule.

The mandatory partitions reject every skip EXCEPT a tracked known bug: an
``xfail(strict=True)`` that carries an ``issue`` marker. It still runs every time
and fails (XPASS strict) the moment the bug is fixed. A plain skip, a non-strict
xfail, and a strict xfail with no issue card all stay rejected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tools.ci.inventory_cli import cmd_verify_execution

_NODE = "tests/x.py::t"


def _run(tmp_path: Path, node: dict) -> int:
    """Write a one-node inventory + execution record and verify the offline partition."""
    inventory = tmp_path / "inventory.json"
    execution = tmp_path / "execution.json"
    inventory.write_text(json.dumps({"partitions": {"offline": [_NODE]}}))
    execution.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "nodeid": _NODE,
                        "terminal_count": 1,
                        "skip_reason": None,
                        "xfailed": False,
                        "strict_xfail": False,
                        "issues": [],
                        **node,
                    }
                ]
            }
        )
    )
    args = argparse.Namespace(
        inventory=str(inventory), execution=str(execution), partition="offline"
    )
    return cmd_verify_execution(args)


def test_verify_execution_accepts_a_strict_issue_linked_xfail(tmp_path) -> None:
    rc = _run(
        tmp_path,
        {
            "outcomes": {"skipped": 1},
            "xfailed": True,
            "strict_xfail": True,
            "issues": ["ISS-104"],
            "skip_reason": "xfail: ISS-104 unfixed",
        },
    )
    assert rc == 0


@pytest.mark.parametrize(
    "node",
    [
        pytest.param(
            {"outcomes": {"skipped": 1}, "skip_reason": "Skipped: no chromium"},
            id="plain-skip",
        ),
        pytest.param(
            {
                "outcomes": {"skipped": 1},
                "xfailed": True,
                "strict_xfail": False,
                "issues": ["ISS-104"],
            },
            id="non-strict-xfail",
        ),
        pytest.param(
            {"outcomes": {"skipped": 1}, "xfailed": True, "strict_xfail": True},
            id="strict-xfail-without-issue",
        ),
        pytest.param(
            {
                "outcomes": {"skipped": 1},
                "xfailed": False,
                "strict_xfail": True,
                "issues": ["ISS-104"],
            },
            id="plain-skip-on-a-strict-xfail-node",
        ),
    ],
)
def test_verify_execution_rejects_any_other_skip(tmp_path, node) -> None:
    assert _run(tmp_path, node) == 1


def test_verify_execution_rejects_a_strict_xfail_that_xpassed(tmp_path) -> None:
    """XPASS(strict) is reported as failed — the fix-landed signal must stay red."""
    rc = _run(
        tmp_path,
        {"outcomes": {"failed": 1}, "strict_xfail": True, "issues": ["ISS-104"]},
    )
    assert rc == 1


def test_verify_execution_passes_a_plain_pass(tmp_path) -> None:
    assert _run(tmp_path, {"outcomes": {"passed": 1}}) == 0
