"""QA-KB-080 analysis probe: a pytest plugin that widens the fake's run_fanout IN MEMORY.

Lets the repo's own runner (pytest + pytest-asyncio, asyncio_mode=auto, the conftest hooks) execute
tests/agents/test_wave_scheduler_cancel_row.py as if the one-line signature fix were applied,
without editing the test file or any application source.

    cd backend && PYTHONPATH=../evidence/qa-kb-080 .venv/bin/python -m pytest \
        tests/agents/test_wave_scheduler_cancel_row.py -q -p no:cacheprovider \
        -p analysis_pytest_probe_plugin
"""
import asyncio


async def _widened(self, requests, ctx, *, step=None, event_queue=None):
    raise asyncio.CancelledError()
    yield  # pragma: no cover


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    for item in items:
        mod = item.module
        if getattr(mod, "__name__", "").endswith("test_wave_scheduler_cancel_row"):
            mod._CancelMidWaveRunner.run_fanout = _widened
