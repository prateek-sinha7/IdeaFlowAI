"""QA-KB-080 analysis probe (sibling): widen _CancelRunner.teardown_isolated_workspace IN MEMORY.

    cd backend && PYTHONPATH=../evidence/qa-kb-080 .venv/bin/python -m pytest \
        tests/unit/agents/test_fanout_cancel.py -q -p no:cacheprovider \
        -p analysis_pytest_probe_plugin_teardown
"""


async def _widened(self, base_workspace, worker_ws, *, delete_branch=True):
    if worker_ws is not None:
        worker_ws.torn_down = True
        self.torn_down.append(worker_ws.index)


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    for item in items:
        mod = item.module
        if getattr(mod, "__name__", "").endswith("test_fanout_cancel"):
            mod._CancelRunner.teardown_isolated_workspace = _widened
