"""Scratch pytest plugin for the QA-KB-099 analysis. Lives OUTSIDE the repo.

Adds @pytest.mark.allow_io to ONE test at collection time, which is exactly what a
decorator edit would do, so the real tests/unit/conftest.py::_unit_io_guard sees the same
marker it would see after the "add allow_io" fix. No repo file is touched.
"""
import pytest

TARGET = "test_sigterm_reaches_the_lifespan_shutdown_half_while_a_stream_is_live"


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.name == TARGET:
            item.add_marker(pytest.mark.allow_io("QA-KB-099 analysis probe (scratch plugin)"))
