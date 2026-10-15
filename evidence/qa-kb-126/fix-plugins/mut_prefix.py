"""Mutation plugin (scratch, not a product file): restore the PRE-FIX trust decisions so the
new ISS-1164/1165 tests can be seen to fail against the unfixed behaviour. Imports are lazy
(pytest_runtest_setup) so the plugin never binds a database at collection time."""


def pytest_runtest_setup(item):
    import app.api.run_commands as rc
    import app.api.run_engine as re_mod

    mp = item.config._mut_mp = __import__("pytest").MonkeyPatch()
    mp.setattr(re_mod, "_parent_run_trust", lambda db, run_id: "db")  # pre-fix trigger: row alone -> db
    mp.setattr(rc, "_saved_row_trust", lambda tier: "db")  # pre-fix resume: no _trust gate


def pytest_runtest_teardown(item):
    item.config._mut_mp.undo()
