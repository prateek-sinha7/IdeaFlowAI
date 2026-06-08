"""agents.capabilities.strategies — ExecutionStrategy capability implementations.

How a step RUNS (the ``ExecutionStrategy`` port in ``capabilities.base``):
``single_shot`` (one agent, re-yield its events) and ``task_loop`` (the prototype
per-task sub-agent build loop + Both-validation + bounded fix-loop + seed-files
write). Both are behaviour lifts of the engine's dispatch branches (INV-12
move-don't-copy) and drive everything through the object-typed ``ctx.runner``
handle.

Import-direction constraint (import-linter): these modules MAY import
``agents.workflows.plan`` (pure typed data) but MUST NOT import
``agents.execution_engine`` or ``app.*`` — and MUST NOT construct a deep-agent
graph (INV-13). The agent loop, sandbox, and validators are reached ONLY through
``ctx.runner``.
"""
