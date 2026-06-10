"""agents/runtime — kernel-side runtime port layer (Phase 09 / RUNTIME-01).

The hexagonal port boundary for workspace provisioning + isolation. The kernel
depends ONLY on the ``typing.Protocol`` ports in ``base.py``; the concrete
``LocalSandboxRuntime`` (and a future ECS-backed runtime) lives app-side and is
reached via the ``ctx.runner`` handle, never imported by the kernel. The 4th
import-linter contract locks ``agents.runtime ↛ [agents.execution_engine, app]``.
"""
