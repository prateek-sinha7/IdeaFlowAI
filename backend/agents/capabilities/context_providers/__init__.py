"""agents.capabilities.context_providers — the ``ContextProvider`` capabilities.

Two providers decompose the engine's L12 od/template/example injection branches
and the L4 revision parent-run seeding into declared capabilities (PARITY-03):

  * ``opendesign``   — composes the ``{block-name -> content}`` map the L12 od /
    template / example branches inject today (engine.py:3306-3386). The heavy
    ``od_loader`` reads ride the boundary ``od_context`` dict + the runner handle
    (Assumption A6) — the capability imports no ``app.*`` (import-linter).
  * ``previous_run`` — seeds the parent run's spec/design/tasks into this run's
    sandbox (revision), ownership-checked via ``ScopedStore.assert_owns`` BEFORE
    seeding; a cross-owner ``PermissionError`` PROPAGATES (INV-8 / L16).

Each satisfies the ``ContextProvider`` port (``name`` attr + ``async def
load(self, ctx) -> dict[str, str]``) and reaches kernel/app primitives only
through ``ctx.runner`` / ``ctx.scoped_store`` (the object-typed seams).
"""
