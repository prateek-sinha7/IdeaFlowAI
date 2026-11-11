"""Namespaced connector tool names: ``<connector_key>__<tool_name>``.

The connector key is lowercase alphanumerics, the tool name keeps the provider's
spelling. The whole name is at most 64 characters (a common model-provider limit).
The adapter's own ``tool_name_prefix`` is not used because it joins with one
underscore, which cannot be parsed back unambiguously.
"""

from __future__ import annotations

import re
from typing import Final

SEPARATOR: Final = "__"
MAX_TOOL_NAME_LENGTH: Final = 64

_KEY_RE = re.compile(r"^[a-z][a-z0-9]{1,31}$")
_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_BOUND_RE = re.compile(r"^([a-z][a-z0-9]{1,31})__([A-Za-z0-9][A-Za-z0-9_-]*)$")


def format_tool_name(connector_key: str, source_name: str) -> str:
    """Return the bound tool name for ``source_name`` of ``connector_key``.

    Raises:
        ValueError: the key or source name breaks the naming rule, or the result
            is longer than 64 characters.
    """
    if not _KEY_RE.match(connector_key):
        raise ValueError("invalid connector key")
    if not _SOURCE_RE.match(source_name):
        raise ValueError("invalid tool name")
    name = f"{connector_key}{SEPARATOR}{source_name}"
    if len(name) > MAX_TOOL_NAME_LENGTH:
        raise ValueError("tool name is too long")
    return name


def parse_tool_name(name: str) -> tuple[str, str] | None:
    """Split a bound name into ``(connector_key, source_name)``, or ``None`` if invalid.

    The connector key never contains an underscore, so the first ``__`` is the
    separator even when the source name contains one.
    """
    if len(name) > MAX_TOOL_NAME_LENGTH:
        return None
    match = _BOUND_RE.match(name)
    if match is None:
        return None
    return match.group(1), match.group(2)
