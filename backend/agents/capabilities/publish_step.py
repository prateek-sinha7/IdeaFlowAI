"""agents/capabilities/publish_step.py — the ``mechanical: publish`` step kind (A10).

STABILIZATION.md item A10: every LLM asked to reproduce ``prototype.html`` from a
finished draft has either narrated into the file or re-authored the 60-90 KB
document from memory and truncated it. The ONLY thing that has ever produced a
correct ``prototype.html`` is the deterministic byte-for-byte copy already living
in ``SingleFileResolver.resolve()`` (``publish_from_glob`` / ``_highest_glob_match``)
— but that copy runs invisibly at end-of-run deliverable resolution, never as its
own visible pipeline step. This module is that same copy, callable as a step.

``publish_draft`` is the ONE function a ``mechanical: "publish"`` step's engine
hook calls (see the A10 proposal for the exact call site — this module does not
import ``agents.execution_engine`` or ``app.*``, INV-13). It takes the SAME ``ctx``
shape ``SingleFileResolver.resolve(ctx)`` already reads (``ctx.deliverable`` /
``ctx.runner`` — the D-03 ``KernelServices`` handle), so it re-reads the identical
declared glob a workflow already carries for the end-of-run fallback, just
triggered mid-run as its own step. No model call, no tokens spent: this is a pure
disk copy, and it raises rather than inventing a substitute when there is nothing
to copy.

Now a self-registering ``agents.capabilities.registry`` capability (``kind="mechanical"``)
for the capability palette only; dispatch still bypasses ``registry.resolve("strategy", ...)``
at the engine hook (see ``plan.py:Step.mechanical`` for why) — the engine hook short-circuits
BEFORE strategy resolution.
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from agents.capabilities.deliverables.single_file import _highest_glob_match
from agents.capabilities.registry import register

_DEFAULT_NAME = "prototype.html"


class PublishStepError(Exception):
    """Raised when a ``mechanical: publish`` step has nothing it can publish.

    Always NAMES the declared glob — nothing is ever invented in place of a
    missing/unreadable draft (STABILIZATION.md A10: "the step fails; nothing is
    invented").
    """


def publish_draft(ctx: Any) -> str:
    """Copy the highest-numbered ``deliverable.publish_from_glob`` match onto
    ``deliverable.name``, byte-for-byte, and return its content.

    ``ctx`` is the per-run ``ExecutionContext`` (``ectx``): ``ctx.deliverable`` is
    the compiled ``DeliverableSpec``, ``ctx.runner`` the ``KernelServices`` handle
    exposing ``.sandbox`` (``list_files`` / ``read`` / ``write``). Reuses
    ``_highest_glob_match`` (numeric ``vN`` comparison, ``v10`` > ``v9`` — never
    lexical) rather than re-implementing it (INV-12).

    Raises ``PublishStepError`` — naming the glob — when:
      * ``deliverable.publish_from_glob`` is not declared;
      * no sandbox file matches it;
      * the matched file cannot be read.
    """
    deliverable = getattr(ctx, "deliverable", None)
    glob_pattern = getattr(deliverable, "publish_from_glob", None)
    if not glob_pattern:
        raise PublishStepError(
            "mechanical publish step: the workflow's deliverable.publish_from_glob "
            "is not declared — nothing to publish"
        )
    filename = getattr(deliverable, "name", None) or _DEFAULT_NAME

    runner = ctx.runner
    files, _truncated = runner.sandbox.list_files()
    source_path = _highest_glob_match(files, glob_pattern)
    if source_path is None:
        raise PublishStepError(
            f"mechanical publish step: no file in the sandbox matches "
            f"publish_from_glob={glob_pattern!r} — nothing to publish"
        )

    content = runner.sandbox.read(source_path)
    if content is None:
        raise PublishStepError(
            f"mechanical publish step: matched {source_path!r} for "
            f"publish_from_glob={glob_pattern!r} but it could not be read from "
            f"the sandbox"
        )

    runner.sandbox.write(filename, content)
    return content


@register(
    "mechanical",
    "publish",
    user_allowed=True,
    description="Copies the finished file onto the workflow's deliverable so it shows in Results. Pure code, no AI. Needs the step's publish pattern to match a file the run wrote.",
)
class _PublishRegistryStub:
    """Thin stub for registry purposes only (capability palette discovery).

    The actual strategy dispatch uses MechanicalPublishStrategy per-invocation with
    per-dispatch arguments (spec/index/total/results). This stub is registered for
    the palette and describes the capability; it is never executed.
    """

    name = "publish"


class MechanicalPublishStrategy:
    """A ``strategy``-shaped adapter (``name`` + ``async def run(step, ctx)``) for a
    ``mechanical: publish`` step (A10 proposal).

    Registered for the capability palette only; dispatch still bypasses
    ``registry.resolve("strategy", ...)`` at the engine hook. Constructed PER DISPATCH
    by the engine hook (the proposal, not this module) with the per-invocation wire
    fields the generic ``strategy.run(step, ctx)`` two-arg signature does not carry
    (``spec``/``index``/``total``/the run's shared ``results`` list) — the SAME
    locals the engine's outer per-step dispatch loop already holds. Handed to
    ``_dispatch_step_with_retry`` exactly like a registry-resolved strategy, so
    every GENERIC post-strategy behavior (the ``ectx.last_streamed`` refresh,
    declared pre/post-step gates, ``validators:``, hooks) runs UNCHANGED — only the
    model-invocation guts of ``_run_agent`` are replaced with the deterministic
    copy. Yields the SAME event vocabulary (``agent_start``/``agent_chunk``/
    ``agent_complete``/``agent_error``) with every token count pinned at 0.
    """

    name = "publish"

    def __init__(self, *, spec: Any, index: int, total: int, results: list) -> None:
        self._spec = spec
        self._index = index
        self._total = total
        self._results = results

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        spec = self._spec
        yield {
            "type": "agent_start",
            "data": {
                "agent_id": spec.id,
                "name": spec.name,
                "role": spec.role,
                "icon": spec.icon,
                "index": self._index,
                "total": self._total,
            },
        }
        started = time.time()
        try:
            content = publish_draft(ctx)
        except PublishStepError as exc:
            yield {
                "type": "agent_error",
                "data": {"agent_id": spec.id, "error": str(exc), "recoverable": False},
            }
            return

        yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": content}}

        duration = time.time() - started
        self._results.append(
            {
                "agent_id": spec.id,
                "name": spec.name,
                "role": spec.role,
                "icon": spec.icon,
                "output": content,
                "duration": duration,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            }
        )
        yield {
            "type": "agent_complete",
            "data": {
                "agent_id": spec.id,
                "name": spec.name,
                "duration": round(duration, 2),
                "output_length": len(content),
                "index": self._index,
                "total": self._total,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        }
