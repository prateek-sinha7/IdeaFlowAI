"""agents/capabilities/validators/api_prefix.py — the ``api_prefix`` infra validator (19-02 / ISS-005).

A pure-stdlib, KERNEL-side registered ``Validator`` (no heavy dep → it lives here,
not app-side; mirrors the ``spec_plan_coverage`` D-05 placement call). It closes
ISS-005: the ``/api/v1`` standard lived ONLY as prose in three AGENT.md bodies
(``grep /api/v1 *.py`` = 0) — a prompt is a flaky enforcement mechanism, so a live
Haiku infra-generator run could silently drop the prefix from the infra it
templated. This validator is the DETERMINISTIC backstop.

Heuristic (stdlib only): glob the run sandbox for the infra files an
infra-generator writes (``Dockerfile*``, ``*.yml``/``*.yaml``, nginx ``*.conf``,
``.github/workflows/*``); regex-scan each for app-endpoint references — healthcheck
paths, nginx ``location`` blocks (incl. ``^``-anchored regex-locations), smoke ``curl``
URLs, and the ``path:`` route of a k8s ``httpGet`` probe / Ingress rule — that are NOT
under the single ``API_PREFIX`` (``/api/v1``) constant. An nginx ``proxy_pass`` target
is INTERNAL upstream routing (not the public surface) and is excluded, and unrelated
YAML ``path:`` keys (``hostPath``/``mountPath``/CI cache) are NOT swept up: detection
stays conservative, preferring a missed audit row to a false one. Each violation is a
P2 (``MEDIUM``) ``Issue``.
Absent/empty sandbox or unreadable file → no issues (the check degrades, never
crashes). It reads ONLY within the run sandbox root (path-traversal safety via the
sandbox's own ``path_for`` / ``root``; mirror ``spec_plan_coverage``'s confinement).

Severity maps through the SINGLE imported ``map_severity`` (08-01, VALID-03 single
source) — no local mapping. Each run writes a ``validation_results`` row via the
handle (best-effort), exactly like ``spec_plan_coverage``.

SC-001: keys on infra-file CONTENT + the declared capability — NEVER on a
workflow/agent name (no workflow-id or agent-id literal). Import
purity (import-linter): stdlib + the capability base/registry/severity ONLY — no
``app.*`` / ``execution_engine`` import (same surface as ``spec_plan_coverage``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.capabilities.registry import register
from agents.capabilities.validators.severity import map_severity  # single source (08-01)


# THE single API-prefix literal — a real module-level constant (per CONTEXT / SC-001),
# so the standard lives in exactly one place, never scattered across the regexes.
API_PREFIX = "/api/v1"


@dataclass
class Issue:
    severity: str
    message: str


# The infra-file globs an infra-generator writes. Confined to the sandbox root
# (relative globs only — never absolute, never ``..``): Dockerfiles, compose/CI YAML,
# nginx confs, and GitHub workflow files.
_INFRA_GLOBS = (
    "Dockerfile*",
    "**/Dockerfile*",
    "*.yml",
    "**/*.yml",
    "*.yaml",
    "**/*.yaml",
    "*.conf",
    "**/*.conf",
    ".github/workflows/*",
)

# App-endpoint reference shapes. Each captures the referenced path so the message can
# name the offending endpoint. Every regex below is a LINEAR single pass (no nested
# quantifiers → no catastrophic backtracking, T-19-02-02): the only multi-line scoping
# (k8s httpGet probe / Ingress rule) is done by a line-oriented Python scan in
# ``_iter_endpoint_paths`` rather than a multi-line regex, so a pathological infra file
# can never make a bounded-but-lazy line-hopping group blow up.
#
# An APP-LOCAL http(s)://host[:port]/path URL (curl/healthcheck/smoke). WR-02: the host
# is constrained to app-local references — ``localhost`` / ``127.0.0.1`` / ``0.0.0.0`` /
# a docker-compose service name (a bare ``[A-Za-z0-9_-]+`` token with NO dot, i.e. NOT a
# public FQDN). Hosts containing a ``.`` (``deb.nodesource.com``, ``github.com``,
# ``registry.terraform.io``) are EXTERNAL package/registry/release URLs that have nothing
# to do with the app's API surface, so they are NOT scanned (they were audit-row noise
# that undermined the deterministic backstop). The host alternation consumes ``host[:port]``
# so the capture begins at the URL PATH's first ``/`` — never the ``//`` of the scheme
# separator. A match preceded on its line by ``proxy_pass`` is dropped in the scan (see
# ``_iter_endpoint_paths``): an nginx ``proxy_pass`` target is INTERNAL upstream routing,
# not the public ``/api/v1`` surface, so flagging it would be a false positive.
_URL_RE = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|[A-Za-z0-9_-]+)(?::\d+)?(/[A-Za-z0-9_\-/]*)"
)
# nginx: location [=|~|~*|^~] [^]/path {  — the optional ``\^?`` consumes the regex-location
# anchor (``location ~ ^/users/``) so the capture still begins at the leading ``/`` of the
# path (without it the ``^`` blocked the ``/`` capture and a regex-location violation was
# a false NEGATIVE).
_LOCATION_RE = re.compile(r"\blocation\s+(?:[=~^*]+\s+)?\^?(/[A-Za-z0-9_\-/]*)")
# WR-03: a bare healthcheck path with NO ``http://`` prefix — a docker-compose ``test:``
# array, a Docker ``HEALTHCHECK``, or a ``--health-cmd`` that names a path-only endpoint
# (e.g. ``test: ["CMD", "wget", "-qO-", "/health"]``). Scoped to the healthcheck CONTEXT
# (the regex must see one of those tokens first) so it does NOT match arbitrary ``/path``
# tokens elsewhere in the file. The leading whitespace/quote delimiter is NON-capturing so
# the path stays in group(1); ``[^\n]*?`` is lazy so the FIRST path token after the
# healthcheck keyword (the endpoint) is captured.
_HEALTHCHECK_RE = re.compile(
    r"(?:--health-cmd|HEALTHCHECK|test:)[^\n]*?(?:\s|\")(/[A-Za-z0-9_\-/]+)"
)
# A YAML ``path:`` key whose value is an ABSOLUTE path. On its own this is too broad (it
# would also catch ``hostPath``/``mountPath``/actions-cache filesystem paths), so the scan
# only yields it when it is inside an ``httpGet:`` probe block OR is the route of an Ingress
# rule (signalled by a sibling ``pathType:`` line) — the two infra-generator YAML forms
# (k8s probes + Ingress) that the docstring covers but the URL/location/healthcheck arms
# missed entirely (a ``/api/v1`` violation in a probe/ingress path was a false NEGATIVE).
# ``\bpath:`` requires a word boundary so ``hostPath:`` / ``subPath:`` are not matched.
_PATH_VALUE_RE = re.compile(r"""\bpath:\s*["']?(/[A-Za-z0-9_\-/]+)""")
_HTTPGET_RE = re.compile(r"\bhttpGet:")
_PATHTYPE_RE = re.compile(r"\bpathType:")
# A ``proxy_pass`` keyword (nginx upstream routing) — used to suppress the URL arm on the
# same line (its target is internal, not the public API surface).
_PROXY_PASS_RE = re.compile(r"\bproxy_pass\b")

# How many lines after an ``httpGet:`` key a ``path:`` value is still treated as that
# probe's route. k8s probe blocks are 2–4 keys deep; 8 is a safe, bounded window.
_HTTPGET_PROXIMITY = 8


def _line_prefix(text: str, start: int) -> str:
    """Return the text on the SAME line as ``start``, up to (not including) ``start``."""
    line_start = text.rfind("\n", 0, start) + 1
    return text[line_start:start]


def _iter_endpoint_paths(text: str):
    """Yield every endpoint path referenced in ``text`` (one ``str`` per reference).

    Linear: each regex is a single non-backtracking pass and the httpGet/Ingress scoping
    is a one-pass line walk — no multi-line nested quantifier (T-19-02-02). The yielded
    paths are NOT yet violation-checked; the caller applies ``_is_violation``.
    """
    # URL arm — drop any match whose line is an nginx ``proxy_pass`` (internal upstream
    # routing, NOT the public surface → flagging it would be a false positive).
    for m in _URL_RE.finditer(text):
        if _PROXY_PASS_RE.search(_line_prefix(text, m.start())):
            continue
        yield m.group(1)
    # nginx ``location`` blocks (incl. regex-locations with a ``^`` anchor).
    for m in _LOCATION_RE.finditer(text):
        yield m.group(1)
    # Bare (scheme-less) healthcheck paths, scoped to the healthcheck keyword.
    for m in _HEALTHCHECK_RE.finditer(text):
        yield m.group(1)
    # k8s ``httpGet:`` probe paths + Ingress-rule paths, scoped by a line walk so unrelated
    # ``path:`` keys (hostPath / mountPath / actions cache) are never swept up.
    lines = text.splitlines()
    httpget_window = 0
    for idx, line in enumerate(lines):
        if _HTTPGET_RE.search(line):
            httpget_window = _HTTPGET_PROXIMITY
            continue
        pm = _PATH_VALUE_RE.search(line)
        if pm:
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            if httpget_window > 0 or _PATHTYPE_RE.search(next_line):
                yield pm.group(1)
        if httpget_window > 0:
            httpget_window -= 1

# Endpoint paths that are NOT application API surface — infra/static roots that
# legitimately live outside ``/api/v1`` (so flagging them would be a false positive).
_EXEMPT_PREFIXES = ("/", "/static", "/_next", "/assets", "/favicon.ico", "/metrics")


def _is_violation(path: str) -> bool:
    """Return ``True`` iff ``path`` is an app endpoint NOT under ``API_PREFIX``."""
    p = path.rstrip("/") or "/"
    # ``/`` (the nginx default catch-all) is the first ``_EXEMPT_PREFIXES`` entry, so the
    # membership check below already returns for it — no separate root branch needed.
    if p in _EXEMPT_PREFIXES or p.startswith("/static") or p.startswith("/_next"):
        return False
    if p == API_PREFIX or p.startswith(API_PREFIX + "/"):
        return False
    return True


def _infra_files(sandbox: Any) -> list[Path]:
    """Return the infra files within the sandbox root (confined; degrade on failure)."""
    root = getattr(sandbox, "root", None)
    if root is None:
        return []
    try:
        root_path = Path(root)
        if not root_path.is_dir():
            return []
    except (OSError, TypeError):
        return []

    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in _INFRA_GLOBS:
        try:
            for candidate in root_path.glob(pattern):
                # Confinement: a resolved path that escapes the sandbox root is never
                # read (path-traversal safety, T-19-02-01).
                try:
                    resolved = candidate.resolve()
                except OSError:
                    continue
                if resolved == root_path.resolve() or str(resolved).startswith(
                    str(root_path.resolve()) + "/"
                ):
                    if resolved.is_file() and resolved not in seen:
                        seen.add(resolved)
                        found.append(resolved)
        except OSError:
            continue
    return found


@register("validator", "api_prefix", user_allowed=True)
class ApiPrefixValidator:
    """Flags infra endpoints lacking the ``/api/v1`` prefix (``name='api_prefix'``).

    Satisfies the ``Validator`` port structurally (``name`` + ``async validate``).
    """

    name = "api_prefix"

    async def validate(self, target: Any) -> list[Issue]:
        """Flag each app endpoint NOT under ``API_PREFIX`` (one P2 ``Issue`` each)."""
        runner = getattr(target, "runner", None)
        sandbox = getattr(runner, "sandbox", None)

        issues: list[Issue] = []
        for infra_file in _infra_files(sandbox):
            try:
                text = infra_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # An unreadable file degrades to "no issues from this file" — never
                # crashes (degrade-not-crash, like spec_plan_coverage on absent text).
                continue
            rel = _rel_name(infra_file, sandbox)
            for path in _iter_endpoint_paths(text):
                if _is_violation(path):
                    issues.append(
                        Issue(
                            severity="P2",
                            message=(
                                f"infra file '{rel}' references endpoint "
                                f"'{path}' not under {API_PREFIX}"
                            ),
                        )
                    )

        await _record(target, "api_prefix", issues)
        return issues


def _rel_name(infra_file: Path, sandbox: Any) -> str:
    """Return the file path RELATIVE to the sandbox root (names only the run's own paths)."""
    root = getattr(sandbox, "root", None)
    if root is None:
        return infra_file.name
    try:
        return str(infra_file.relative_to(Path(root).resolve()))
    except (ValueError, OSError):
        return infra_file.name


_SEVERITY_ORDER = ("P0", "P1", "P2", "P3")


def _worst_label(issues: list[Issue]) -> str | None:
    for sev in _SEVERITY_ORDER:
        if any(i.severity == sev for i in issues):
            return map_severity(sev)
    return None


async def _record(target: Any, validator: str, issues: list[Issue]) -> None:
    """Write a ``validation_results`` row via the handle (best-effort, D-10)."""
    runner = getattr(target, "runner", None)
    if runner is None:
        return
    record = getattr(runner, "record_validation_result", None)
    if record is None:
        return
    severity = _worst_label(issues)
    step = getattr(target, "step", "") or ""
    attempt = int((getattr(target, "task_meta", None) or {}).get("attempt", 0))
    payload = [{"severity": i.severity, "message": i.message} for i in issues]
    await record(step, validator, severity=severity, attempt=attempt, issues=payload)
