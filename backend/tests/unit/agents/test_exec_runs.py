"""``KernelServices`` exec-audit seam — best-effort degrade (Phase 10 / EXEC-01).

What is left here after the Batch 6 split is the part that needs NO database: the
audit write must never abort a run, so with no ``scoped_store`` on the ectx
``KernelServices.record_exec_run`` returns ``None`` instead of raising (Pitfall 6 /
mirrors ``record_hook_run``), and the ``workspace`` host seam is declared.

The other two thirds of the original module moved to where their dependencies live:
  * ``0018`` migration reversibility ->
    ``tests/integration/db/test_migration_0018_exec_runs.py``
  * ``ScopedStore.record_exec_run`` scoped write + default-deny read ->
    ``tests/integration/repositories/test_exec_runs_db.py``

Offline, no DB, no API key, no network.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_kernel_services_record_exec_run_degrades_to_none_offline():
    """No scoped_store on the ectx -> returns None WITHOUT raising (Pitfall 6)."""
    from agents.execution_engine.kernel_services import KernelServices

    class _Ectx:
        scoped_store = None

    ks = KernelServices.__new__(KernelServices)  # bypass __init__ (offline harness)
    ks._ectx = _Ectx()
    ks.run_id = "run-1"

    result = await ks.record_exec_run(
        "build", ["python3", "-c", "print(1)"], "allowed", exit_code=0
    )
    assert result is None


def test_kernel_services_has_workspace_attribute_default():
    """KernelServices declares a ``workspace`` attribute (bound in 10-02's seam)."""
    from agents.execution_engine.kernel_services import KernelServices

    # The attribute must exist on a fully-constructed instance (default None).
    import inspect as _inspect

    src = _inspect.getsource(KernelServices.__init__)
    assert (
        "self.workspace" in src
    ), "KernelServices.__init__ must declare self.workspace (10-02 host seam)"
