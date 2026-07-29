"""Resolve a `./file.py:func` reference to the callable it names.

One shared mechanism for a rubric's `validate:`, a stage's `adapter:`, and a
`seed_files` derivation hook. Loading by path rather than dotted module keeps a
hook co-located with the config that names it and needs no `__init__.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable


def load_callable(reference: str, *, relative_to: Path) -> Callable:
    """Resolve ``'./file.py:func'`` to the function, relative to a config file.

    ``relative_to`` is the config file that declared the reference (its parent
    directory is the base). Raises ValueError naming the file and function on any
    failure — a hook that cannot load must fail at config-load time, never
    silently at grading time.
    """
    path, function_name = _split_reference(reference, relative_to=relative_to)
    module = _load_module(path, function_name)

    function = getattr(module, function_name, None)
    if function is None:
        raise ValueError(
            f"hook reference '{reference}': file '{path}' defines no '{function_name}'"
        )
    if not callable(function):
        raise ValueError(
            f"hook reference '{reference}': '{function_name}' in '{path}' is not callable"
        )
    return function


def _split_reference(reference: str, *, relative_to: Path) -> tuple[Path, str]:
    """Split ``'./file.py:func'`` into an absolute file path and a function name."""
    path_text, separator, function_name = reference.rpartition(":")
    if not separator or not path_text.strip() or not function_name.strip():
        raise ValueError(
            f"hook reference '{reference}' is malformed: "
            "expected 'path/to/file.py:function_name'"
        )

    path = Path(path_text.strip())
    if not path.is_absolute():
        path = relative_to.parent / path
    return path.resolve(), function_name.strip()


def _load_module(path: Path, function_name: str):
    """Execute the file at ``path`` as an anonymous module, by path not by dotted name."""
    if not path.is_file():
        raise ValueError(
            f"hook file '{path}' does not exist (looking for '{function_name}')"
        )

    spec = importlib.util.spec_from_file_location(f"grading_hook_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ValueError(
            f"hook file '{path}' is not importable as Python "
            f"(looking for '{function_name}')"
        )

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        raise ValueError(
            f"hook file '{path}' failed to import "
            f"(looking for '{function_name}'): {error}"
        ) from error
    return module
