"""agents/capabilities/context_providers/repo.py — the ``repo`` ContextProvider (REPO-03 / R-F).

Surfaces the brownfield context (the targeted ``ContextPack``) to agents as
injected context blocks. Satisfies the ``ContextProvider`` port (``name`` +
``async load(ctx) -> dict[str, str]``), mirroring ``previous_run.py:115``.

Ownership gate (V4 / L16 / T-09-03-ID): when a parent/source run is read for the
pack, ``ScopedStore.assert_owns`` is called and a cross-owner ``PermissionError``
PROPAGATES out of ``load`` — it is NEVER swallowed (the highest-risk
information-disclosure boundary: an agent must never see another owner's repo
context). Any OTHER error degrades gracefully (a missing pack must not break the
run) — only the ownership denial always wins.

Import purity (import-linter): the store is reached via ``getattr(ctx,
'scoped_store')`` and the pack via the ``ctx.runner`` handle — no ``app.*`` /
kernel import. The ``ContextPack`` capability is resolved through the registry
(the legal kernel->capability direction).
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)


@register("context_provider", "repo")
class RepoProvider:
    """Surface the targeted repo ContextPack to agents (``name='repo'``).

    Returns a ``dict[str, str]`` of named context blocks: a ``repo_context`` block
    with the target file + selected neighbors. The effect is injected context, not
    a sandbox seed.
    """

    name = "repo"

    async def load(self, ctx: Any) -> dict[str, str]:
        # ── Ownership gate (L16 / T-09-03-ID) — BEFORE surfacing any context ─────
        # If the pack is sourced from a recorded source run, the owner must own it.
        # A cross-owner PermissionError PROPAGATES (never swallowed).
        scoped_store = getattr(ctx, "scoped_store", None)
        source_run_id = getattr(ctx, "repo_source_run_id", None)
        if scoped_store is not None and source_run_id:
            try:
                await scoped_store.assert_owns(source_run_id)
            except PermissionError:
                raise  # cross-owner denial — propagate (L16, never swallow)
            except Exception as authz_exc:  # noqa: BLE001 — fail closed on uncertain authz
                logger.warning(
                    "repo provider: assert_owns failed for source run %s (%s) — "
                    "FAILING CLOSED: surfacing no repo context",
                    source_run_id, authz_exc,
                )
                return {}

        # ── Build / read the targeted ContextPack via the registry capability ────
        pack = self._resolve_pack(ctx)
        if not pack or not pack.get("files"):
            return {}

        target = pack.get("target")
        neighbors = pack.get("neighbors", [])
        files = pack.get("files", {})

        lines = [f"## Repo Context (target: {target})", ""]
        for rel in [target, *neighbors]:
            content = files.get(rel)
            if content is None:
                continue
            lines.append(f"### {rel}")
            lines.append(content.rstrip())
            lines.append("")
        return {"repo_context": "\n".join(lines).rstrip() + "\n"}

    @staticmethod
    def _resolve_pack(ctx: Any) -> dict[str, Any] | None:
        """Build the ContextPack via the registered capability (kernel->cap, legal)."""
        # A pre-built pack stashed on ctx takes precedence (the engine may build it).
        prebuilt = getattr(ctx, "context_pack", None)
        if isinstance(prebuilt, dict) and prebuilt.get("files"):
            return prebuilt
        try:
            from agents.capabilities.registry import CapabilityRegistry, discover

            discover()
            pack_cap = CapabilityRegistry().resolve("context_pack", "default")
        except Exception as exc:  # noqa: BLE001 — no pack capability → no context
            logger.warning("repo provider: could not resolve context_pack (%s)", exc)
            return None
        target = getattr(ctx, "context_pack_target", None)
        return pack_cap.build(ctx, target=target)
