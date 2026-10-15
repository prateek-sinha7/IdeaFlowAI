"""Scratch pytest plugin for the QA-KB-099 analysis (sibling probe). Lives OUTSIDE the repo; a copy is kept in evidence/qa-kb-099/analysis-plugins/.

Adds @pytest.mark.allow_io to ONE test at collection time, which is what a decorator edit would do.
"""
import pytest

TARGET = "test_run_finalization_failed_is_emitted_on_a_degraded_finalization"


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.name == TARGET:
            item.add_marker(pytest.mark.allow_io("QA-KB-099 analysis probe (scratch plugin)"))
