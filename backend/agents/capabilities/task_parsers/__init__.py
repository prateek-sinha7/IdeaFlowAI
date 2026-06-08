"""agents.capabilities.task_parsers — TaskParser capability implementations (Phase 7).

Adapters that turn raw planner text into canonical ``agents.workflows.plan.Task``
objects (the ``TaskParser`` port in ``capabilities.base``). Phase 7 lands the first
impl, ``heading_tasks`` (lifted verbatim from the engine's ``_count_plan_tasks`` /
``_extract_task_block`` staticmethods — INV-12 move-don't-copy).

Import-direction constraint (import-linter): these modules MAY import
``agents.workflows.plan`` (pure typed data) but MUST NOT import
``agents.execution_engine`` or ``app.*`` — capabilities reach kernel/app
primitives only via the object-typed ``ctx.runner`` handle.
"""
