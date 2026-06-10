"""app/agents/repo_index/ — the optional tree-sitter symbol index (REPO-02).

App-side capability package (the heavy ``tree_sitter`` dependency lives behind
this module ONLY — REPO-02 acceptance: "tree-sitter is imported only behind the
repo_index capability"). Importing this package fires the ``@register`` in
``index`` so ``discover()`` binds ``("repo_index", "tree_sitter")``. Mirrors the
``app/agents/runtime`` / ``app/agents/validators`` discovery precedent: the
registry IMPORTS this package; the impl imports the kernel PORT — the legal
app->ports direction, never the reverse.
"""

from __future__ import annotations

from . import index  # noqa: F401 — import for the @register side effect

__all__ = ["index"]
