"""agents/execution_engine/trigger_port.py — the kernel's port for triggered runs.

A ``trigger: workflow`` conditional-gate outcome (spec 014 R-12) makes
``KernelServices.run_trigger_workflow`` mint and spawn a NEW, independent
``WorkflowRun``. Two parts of that are application concerns the kernel does not
own:

  * resolving a saved ``user_workflow_id`` against the caller's own rows — the
    owner-scoped ``_owned`` lookup plus ``launch_run``'s Case 2 / Case 3
    branching; and
  * minting + spawning the run — ``_launch_run_core``, the SAME core the HTTP
    launch handler uses.

Both live in ``app.api.run_commands``, and the kernel must not import ``app.api``
(import-linter contract "kernel imports only capability ports (scaffold)"). This
module is the port between them: ``app.api.run_commands`` registers its adapter
here when it is imported — the adapter-registers-into-a-kernel-registry wiring
app-side capabilities already use. ``app.main`` imports that module at startup,
so every process that runs the engine has the adapter wired. An unwired port is
a loud ``RuntimeError`` at trigger time, never a silent skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

#: ``(workflow_ref, owner_id, parent_run_id) -> (pipeline_type, agents | None, compiled | None)``
#: for a saved ``user_workflow_id``. Raises for an unknown / cross-owner id.
#: ``parent_run_id`` caps the row's compile trust at the firing run's (ISS-1164).
SavedWorkflowResolver = Callable[[str, str, str], tuple[str, Any, Any]]

#: Keyword-only mint-and-spawn; returns the launch result dict (carries ``run_id``).
TriggeredRunLauncher = Callable[..., Awaitable[dict]]


@dataclass(frozen=True)
class TriggerLaunchPort:
    """The app-layer operations a workflow trigger needs (see module docstring)."""

    resolve_saved_workflow: SavedWorkflowResolver
    launch_run: TriggeredRunLauncher


_registered: TriggerLaunchPort | None = None


def register_trigger_launch_port(port: TriggerLaunchPort) -> None:
    """Install the app-layer adapter (called by ``app.api.run_commands`` at import)."""
    global _registered
    _registered = port


def get_trigger_launch_port() -> TriggerLaunchPort:
    """Return the registered adapter, or raise if the app layer never wired one."""
    if _registered is None:
        raise RuntimeError(
            "No trigger launch port is registered. app.api.run_commands registers "
            "it at import; a 'trigger: workflow' outcome cannot mint a run without it."
        )
    return _registered
