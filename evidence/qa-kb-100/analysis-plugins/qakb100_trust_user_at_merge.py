"""READ-ONLY mutation probe (QA-KB-100 analysis), a pytest plugin, NOT application code.

Simulates 'option A' at the one call site that matters: agents/execution_engine/overrides.py:100
(`WorkflowCompiler().compile(parsed, registry, trust="db")`) becoming trust="user". It does that by
swapping the WorkflowCompiler CLASS that merge_override_steps re-imports on every call
(`from agents.workflows.compiler import CompilerError, WorkflowCompiler`, overrides.py:81) for a subclass
that forces trust="user". The engine's own `_WORKFLOW_COMPILER` instance (used by compile_for_run and by
the save path) was built from the ORIGINAL class at import time, so it is untouched.

Imports are lazy (pytest_runtest_setup) so the plugin never binds the app/engine at collection time.
"""
import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # Import the engine FIRST so its module-level `_WORKFLOW_COMPILER = WorkflowCompiler()` is built from
    # the ORIGINAL class; only afterwards swap the class that merge_override_steps re-imports per call.
    import agents.execution_engine.engine  # noqa: F401
    import agents.workflows.compiler as c

    if getattr(c, "_qakb100_patched", False):
        return
    original = c.WorkflowCompiler

    class _UserTrustCompiler(original):
        def compile(self, manifest, registry, *, trust="file"):
            return super().compile(manifest, registry, trust="user")

    c.WorkflowCompiler = _UserTrustCompiler
    c._qakb100_patched = True
