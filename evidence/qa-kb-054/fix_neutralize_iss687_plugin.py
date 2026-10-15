"""Mutation probe: run with the ISS-687/976/978 fix switched off (_own_plan_roster -> set()).
App modules are imported lazily in runtest_setup, after the test conftest configured the env."""
import pytest

_MP = {}


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    import app.api.run_engine as run_engine
    import app.api.user_workflows as user_workflows

    mp = pytest.MonkeyPatch()
    mp.setattr(run_engine, "_own_plan_roster", lambda _p: set())
    mp.setattr(user_workflows, "_own_plan_roster", lambda _p: set())
    _MP[item.nodeid] = mp


def pytest_runtest_teardown(item, nextitem):
    mp = _MP.pop(item.nodeid, None)
    if mp is not None:
        mp.undo()
