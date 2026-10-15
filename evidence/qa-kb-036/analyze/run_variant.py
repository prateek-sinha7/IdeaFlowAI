"""Run selected repo tests with _reconcile_terminal_status swapped for a scratchpad variant.

Never edits the repo: the variant function is compiled from a scratchpad copy and exec'd into the
live app.api.run_commands module namespace at test-setup time. `app` is imported LAZILY (inside the
hook), after tests/conftest.py has pinned DATABASE_URL to a temp SQLite file.
"""
import ast, sys
import pytest

variant, args = sys.argv[1], sys.argv[2:]

class Swap:
    done = False
    def pytest_runtest_setup(self, item):
        if self.done or variant == "none":
            return
        import app.api.run_commands as rc
        tree = ast.parse(open(variant).read())
        fn = next(n for n in tree.body
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "_reconcile_terminal_status")
        exec(compile(ast.Module(body=[fn], type_ignores=[]), variant, "exec"), rc.__dict__)
        self.done = True
        print(f"\n[swap] _reconcile_terminal_status replaced from {variant}")

sys.exit(pytest.main(args, plugins=[Swap()]))
