"""
Decide which CI areas a pull request changed (F-15 path filter).

ci.yml's `changes` job runs this as a plain script on the runner's system
Python (`python3 backend/tools/ci/change_scope.py`) after a sparse checkout of
this one file, so it must stay stdlib-only, Python 3.10-compatible, and import
nothing from `tools.ci` (whose package `__init__` needs third-party modules).

Input (environment):
    EVENT_NAME         github.event_name
    F_<NAME>           dorny/paths-filter output for each FILTER_NAMES entry,
                       e.g. F_BACKEND. Only read on `pull_request`.
    GITHUB_OUTPUT      file the step outputs are appended to

Policy (the skip-as-success rules live in tools/ci/signal_registry.py, on
`Signal.path_filter_area`):

* any event other than `pull_request`, or a PR that touches `.github/**`,
  `ci/**` or the shared CI tooling the gated jobs execute
  (`backend/tools/ci/**`, `backend/tools/__init__.py`, `backend/uv.lock`,
  `backend/pyproject.toml`) — the `workflows` filter — runs EVERYTHING;
* on a PR every filter value must be exactly "true" or "false". Anything else
  raises ValueError, so the job fails, ci-evidence passes no filtered area, and
  every skipped job counts as SKIPPED (a failure). Fail closed;
* a Docker-input change (`docker`) forces both image scans.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

#: The dorny/paths-filter filter keys ci.yml declares, in declaration order.
FILTER_NAMES = ("workflows", "backend", "frontend", "infra", "docker", "backend_image")

#: The areas a signal can be filtered by. Must equal
#: signal_registry.PATH_FILTER_AREAS (asserted by test_change_scope.py).
AREAS = ("backend", "frontend", "infra", "backend_image", "frontend_image")

#: Container-scan matrix components, in matrix order.
_CONTAINER_COMPONENTS = ("backend", "frontend")


@dataclass(frozen=True)
class ScopeDecision:
    """The resolved scope for one evaluation."""

    backend: bool
    frontend: bool
    infra: bool
    docker: bool
    workflows: bool
    backend_image: bool
    frontend_image: bool
    security_legs: tuple[str, ...]
    container_components: tuple[str, ...]
    filtered_areas: tuple[str, ...]


def _full_scope() -> ScopeDecision:
    """Everything runs; nothing is filtered."""
    return ScopeDecision(
        backend=True,
        frontend=True,
        infra=True,
        docker=True,
        workflows=True,
        backend_image=True,
        frontend_image=True,
        security_legs=("secrets", "iac"),
        container_components=_CONTAINER_COMPONENTS,
        filtered_areas=(),
    )


def _parse_filters(filters: dict[str, str]) -> dict[str, bool]:
    """Parse every FILTER_NAMES value strictly; raise ValueError otherwise."""
    parsed: dict[str, bool] = {}
    for name in FILTER_NAMES:
        raw = filters.get(name)
        if raw == "true":
            parsed[name] = True
        elif raw == "false":
            parsed[name] = False
        else:
            raise ValueError(
                f"path filter '{name}' must be 'true' or 'false', got {raw!r}; "
                f"refusing to filter anything"
            )
    return parsed


def resolve_scope(event_name: str, filters: dict[str, str]) -> ScopeDecision:
    """
    Resolve the scope for one evaluation.

    Args:
        event_name: github.event_name.
        filters: FILTER_NAMES -> "true"/"false" from dorny/paths-filter. Ignored
            unless the event is `pull_request`.

    Raises:
        ValueError: a pull request filter value is missing or not exactly
            "true"/"false".
    """
    if event_name != "pull_request":
        return _full_scope()
    if filters.get("workflows") == "true":
        return _full_scope()

    f = _parse_filters(filters)
    backend_image = f["docker"] or f["backend_image"]
    frontend_image = f["docker"] or f["frontend"]
    areas = {
        "backend": f["backend"],
        "frontend": f["frontend"],
        "infra": f["infra"],
        "backend_image": backend_image,
        "frontend_image": frontend_image,
    }
    images = {"backend": backend_image, "frontend": frontend_image}
    return ScopeDecision(
        backend=f["backend"],
        frontend=f["frontend"],
        infra=f["infra"],
        docker=f["docker"],
        workflows=f["workflows"],
        backend_image=backend_image,
        frontend_image=frontend_image,
        security_legs=("secrets", "iac") if f["infra"] else ("secrets",),
        container_components=tuple(c for c in _CONTAINER_COMPONENTS if images[c]),
        filtered_areas=tuple(area for area in AREAS if not areas[area]),
    )


def _bool(value: bool) -> str:
    """GitHub expression-friendly boolean."""
    return "true" if value else "false"


def format_outputs(decision: ScopeDecision) -> list[str]:
    """Render the decision as `key=value` lines for $GITHUB_OUTPUT."""
    return [
        f"backend={_bool(decision.backend)}",
        f"frontend={_bool(decision.frontend)}",
        f"infra={_bool(decision.infra)}",
        f"docker={_bool(decision.docker)}",
        f"workflows={_bool(decision.workflows)}",
        f"backend_image={_bool(decision.backend_image)}",
        f"frontend_image={_bool(decision.frontend_image)}",
        f"security_legs={_compact_json(decision.security_legs)}",
        f"container_components={_compact_json(decision.container_components)}",
        f"filtered_areas={','.join(decision.filtered_areas)}",
    ]


def _compact_json(values: tuple[str, ...]) -> str:
    """A JSON list with no whitespace, for `fromJSON()` in the workflow."""
    return json.dumps(list(values), separators=(",", ":"))


def main() -> int:
    """Read the environment, write $GITHUB_OUTPUT, and log the decision."""
    event_name = os.environ.get("EVENT_NAME", "")
    filters = {name: os.environ.get(f"F_{name.upper()}", "") for name in FILTER_NAMES}
    try:
        decision = resolve_scope(event_name, filters)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 1

    lines = format_outputs(decision)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("::error::GITHUB_OUTPUT is not set")
        return 1
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write("".join(f"{line}\n" for line in lines))

    print(f"Change scope for event '{event_name}':")
    for line in lines:
        print(f"  {line}")
    if decision.filtered_areas:
        print(
            "Unchanged areas (their jobs are skipped and reported FILTERED): "
            + ", ".join(decision.filtered_areas)
        )
    else:
        print("Nothing is filtered: every job runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
