"""agents/capabilities/deliverables/single_file.py — the ``single_file`` resolver.

Folds the engine's prototype build branch (engine.py:506-518) AND the prototype
revision branch (:489-504) into ONE deliverable resolver keyed by
``deliverable.name`` — NO workflow-name branch (that name-based dispatch is
L4/L8, deleted in 07-05). The single named file the build loop / revision agent
wrote on disk IS the deliverable; the sandbox is read ONLY through ``ctx.runner``
(the D-03 handle), never a direct ``app.*`` import (Pitfall 4).

Fallback chain (the folded prototype + revision behavior):
  0. when the workflow DECLARES ``deliverable.publish_from_glob`` (a one-``*``
     glob, e.g. ``"draft.v*.html"``): the engine itself finds the HIGHEST-numbered
     match in the sandbox and copies it to ``deliverable.name`` byte-for-byte —
     no model ever performs this copy (a "verbatim copy" step run by an LLM has
     twice re-emitted the document from memory and silently dropped content).
     Undeclared (the default) → this step is a no-op and behavior is unchanged.
  1. ``deliverable.name`` (default ``prototype.html``) read from the sandbox
  2. when a ``previous_run``-seeded ORIGINAL is present (in-place revision): prefer
     the seeded original over a NON-HTML stream and ``<artifact>``-unwrap the chosen
     value — byte-identical to the legacy ``prototype_revision`` branch, so a
     non-HTML confirmation never overwrites the user's prototype
  3. otherwise (forward build) the last-streamed agent output, returned raw.

This also absorbs the L10 readback (engine.py:1902, today gated on the prototype
workflow names) — reading ``deliverable.name`` from the sandbox here replaces
that workflow-name-gated readback (Pitfall 5).
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.deliverables._artifact import (
    strip_pre_document_prose,
    unwrap_artifact,
)
from agents.capabilities.deliverables._format import coerce_to_declared_format
from agents.capabilities.deliverables._mimetype import default_mimetype
from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

_DEFAULT_NAME = "prototype.html"


def _highest_glob_match(files: list[dict], glob_pattern: str) -> str | None:
    """Pick the file whose NUMERIC middle segment is highest against a 1-``*`` glob.

    ``glob_pattern`` is e.g. ``"draft.v*.html"``: split on the single ``*`` into a
    prefix/suffix, then every sandbox path that starts with the prefix, ends with
    the suffix, and has an all-digit remainder in between is a candidate. Compared
    NUMERICALLY (``v10`` > ``v9``), never lexically. No candidates -> ``None``.
    """
    if glob_pattern.count("*") != 1:
        return None
    prefix, _, suffix = glob_pattern.partition("*")
    best: tuple[int, str] | None = None
    for entry in files:
        path = entry["path"]
        if not (path.startswith(prefix) and path.endswith(suffix)):
            continue
        middle = path[len(prefix) : len(path) - len(suffix)]
        if not middle.isdigit():
            continue
        version = int(middle)
        if best is None or version > best[0]:
            best = (version, path)
    return best[1] if best else None


@register(
    "deliverable",
    "single_file",
    user_allowed=True,
    description="Resolve the deliverable as a single named file read back from the run sandbox.",
    config_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Sandbox file name to read back as the deliverable (the extension drives the default mimetype).",
            },
        },
    },
)
class SingleFileResolver:
    """Resolve a single named file from the sandbox (``name='single_file'``).

    Satisfies the ``DeliverableResolver`` port (``name`` + ``resolve``). Resolves
    by ``deliverable.name`` / ``deliverable.strategy`` — never by pipeline name.
    """

    name = "single_file"

    @staticmethod
    def default_mimetype(deliverable_name: str | None) -> str:
        """Default deliverable shape hint (ISS-021): infer from the declared name ext."""
        return default_mimetype("single_file", deliverable_name)

    def resolve(self, ctx: Any) -> Any:
        runner = ctx.runner
        deliverable = getattr(ctx, "deliverable", None)
        filename = getattr(deliverable, "name", None) or _DEFAULT_NAME
        publish_from_glob = getattr(deliverable, "publish_from_glob", None)

        # (0) DECLARED mechanical publish: the engine, not a model, copies the
        # highest-numbered versioned draft onto the deliverable name, byte-for-byte.
        # Undeclared workflows (publish_from_glob is None) skip this entirely —
        # zero behavior change for every other single_file workflow.
        if publish_from_glob:
            files, _truncated = runner.sandbox.list_files()
            source_path = _highest_glob_match(files, publish_from_glob)
            if source_path:
                content = runner.sandbox.read(source_path)
                if content is not None:
                    runner.sandbox.write(filename, content)
                    logger.info(
                        "single_file: published %s -> %s (%d bytes) via "
                        "publish_from_glob=%r",
                        source_path,
                        filename,
                        len(content),
                        publish_from_glob,
                    )
                    return content
            else:
                logger.warning(
                    "single_file: publish_from_glob=%r matched no file in the "
                    "sandbox — leaving %s as whatever earlier steps produced",
                    publish_from_glob,
                    filename,
                )

        # (1) The named file the build loop / revision agent wrote IS the deliverable.
        built = runner.sandbox.read(filename)
        if built:
            return built

        last_streamed = getattr(ctx, "last_streamed", "") or ""
        original = getattr(ctx, "revision_original_html", "") or ""

        # (2) Revision fallback — a previous_run-seeded ORIGINAL means this run edits
        # an existing artifact in place. Byte-identical to the legacy
        # ``prototype_revision`` branch (engine.py@acd1636:489-504): prefer the
        # seeded original when the stream is NOT HTML (so a non-HTML confirmation
        # never overwrites the user's prototype), and unwrap an ``<artifact>`` tag.
        # Keyed on the ORIGINAL's presence — never on a pipeline-type name (INV-1).
        if original:
            streamed = last_streamed.strip()
            looks_like_html = (
                streamed[:60].lower().lstrip().startswith(("<!doctype", "<html"))
            )
            chosen = streamed if looks_like_html else (original or streamed)
            logger.warning(
                "single_file: %s not written by agent — fell back to %s",
                filename,
                "streamed HTML" if looks_like_html else "seeded original",
            )
            return unwrap_artifact(chosen)

        # (3) Forward-build fallback — no seeded original; the streamed output IS the
        # deliverable (matching the legacy forward prototype branch), minus any
        # reasoning prose the agent streamed ahead of the document (ISS-737).
        if last_streamed.strip():
            logger.warning(
                "single_file: %s not written by agent — falling back to streamed output",
                filename,
            )
            # QA-SG-014 / ISS-776: this fallback is the agent's raw text, but
            # default_mimetype() has already promised text/html off the declared
            # .html name — render the declared format so the bytes match the
            # label instead of mislabeling markdown as HTML.
            return coerce_to_declared_format(
                strip_pre_document_prose(last_streamed), filename
            )

        return ""
