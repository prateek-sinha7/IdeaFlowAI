"""
Concurrency contract for ``.github/workflows/ci.yml`` (F-24).

The old group inferred "is this a trusted intent?" from ``github.event_name``.
In a CALLED workflow the ``github`` context belongs to the caller, so the deploy
gate (a ``workflow_call`` made from a ``push`` to ``staging``) resolved to the
same ``branch-refs/heads/staging`` group as CI's own push run, with
``cancel-in-progress: true``: one commit started two runs that cancelled each
other. The group now keys on the explicit ``inputs.intent_id`` instead.

The expression is evaluated here with a small, self-tested interpreter for the
subset GitHub expressions use in that block. Whether GitHub resolves ``inputs``
inside a called workflow's workflow-level ``concurrency`` exactly as documented is
only provable by a live run (needs-live-run): push to ``staging`` and confirm two
separate ci.yml runs both complete.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

# ---------------------------------------------------------------------------
# A small GitHub-expression interpreter (no eval)
# ---------------------------------------------------------------------------

_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<op>==|!=|&&|\|\||[()!,])|(?P<id>[A-Za-z_][A-Za-z0-9_.\-]*))"
)


def _tokenise(source: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(source):
        if source[position:].strip() == "":
            break
        match = _TOKEN.match(source, position)
        if match is None:
            raise ValueError(f"cannot tokenise {source[position:]!r}")
        kind = match.lastgroup or ""
        tokens.append((kind, match.group(kind)))
        position = match.end()
    return tokens


def _truthy(value: Any) -> bool:
    """GitHub truthiness: '', null, 0 and false are falsy."""
    return not (value is None or value is False or value == "" or value == 0)


def _to_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return math.nan


def _equals(left: Any, right: Any) -> bool:
    """GitHub ``==``: same type compares directly (strings case-insensitively),
    different types are compared as numbers (so ``null == ''`` is true)."""
    if isinstance(left, str) and isinstance(right, str):
        return left.lower() == right.lower()
    if type(left) is type(right):
        return bool(left == right)
    return _to_number(left) == _to_number(right)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format(template: str, *args: Any) -> str:
    """``format()`` with the doubled-brace escape (``{{`` and ``}}``)."""
    out: list[str] = []
    index = 0
    while index < len(template):
        pair = template[index : index + 2]
        if pair in ("{{", "}}"):
            out.append(pair[0])
            index += 2
            continue
        match = re.match(r"\{(\d+)\}", template[index:])
        if match:
            out.append(_as_text(args[int(match.group(1))]))
            index += match.end()
            continue
        out.append(template[index])
        index += 1
    return "".join(out)


class _Parser:
    """Recursive descent over: || , && , == != , ! , primary."""

    def __init__(self, source: str, context: dict[str, Any]) -> None:
        self.tokens = _tokenise(source)
        self.position = 0
        self.context = context

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _take(self) -> tuple[str, str]:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def _accept(self, text: str) -> bool:
        token = self._peek()
        if token is not None and token[0] == "op" and token[1] == text:
            self.position += 1
            return True
        return False

    def parse(self) -> Any:
        value = self._or()
        if self._peek() is not None:
            raise ValueError(f"unexpected trailing token {self._peek()!r}")
        return value

    def _or(self) -> Any:
        value = self._and()
        while self._accept("||"):
            right = self._and()
            value = value if _truthy(value) else right
        return value

    def _and(self) -> Any:
        value = self._equality()
        while self._accept("&&"):
            right = self._equality()
            value = right if _truthy(value) else value
        return value

    def _equality(self) -> Any:
        value = self._unary()
        while True:
            if self._accept("=="):
                value = _equals(value, self._unary())
            elif self._accept("!="):
                value = not _equals(value, self._unary())
            else:
                return value

    def _unary(self) -> Any:
        if self._accept("!"):
            return not _truthy(self._unary())
        return self._primary()

    def _primary(self) -> Any:
        if self._accept("("):
            value = self._or()
            if not self._accept(")"):
                raise ValueError("missing closing parenthesis")
            return value
        kind, text = self._take()
        if kind == "str":
            return text[1:-1].replace("''", "'")
        if kind == "num":
            return float(text) if "." in text else int(text)
        if kind != "id":
            raise ValueError(f"unexpected token {text!r}")
        if text in ("true", "false"):
            return text == "true"
        if text == "null":
            return None
        if self._accept("("):
            args: list[Any] = []
            if not self._accept(")"):
                args.append(self._or())
                while self._accept(","):
                    args.append(self._or())
                if not self._accept(")"):
                    raise ValueError("missing closing parenthesis in call")
            if text != "format":
                raise ValueError(f"unsupported function {text!r}")
            return _format(*args)
        return _lookup(self.context, text)


def _lookup(context: dict[str, Any], path: str) -> Any:
    """Dotted context lookup; an absent key is null, as in GitHub."""
    current: Any = context
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def evaluate(expression: str, context: dict[str, Any]) -> Any:
    """Evaluate one expression body (the text inside ``${{ }}``)."""
    return _Parser(expression, context).parse()


_TEMPLATE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)


def render(template: str, context: dict[str, Any]) -> str:
    """Replace each ``${{ ... }}`` in ``template`` with its text value."""
    return _TEMPLATE.sub(
        lambda m: _as_text(evaluate(m.group(1), context)), str(template)
    )


# ---------------------------------------------------------------------------
# Workflow fixtures
# ---------------------------------------------------------------------------


def _ci() -> dict[Any, Any]:
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))


def _concurrency() -> dict[str, Any]:
    return _ci()["concurrency"]


def _context(
    *,
    event_name: str,
    ref: str = "refs/heads/main",
    pr_number: int | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    github: dict[str, Any] = {
        "repository": "org/repo",
        "event_name": event_name,
        "ref": ref,
        "event": {},
    }
    if pr_number is not None:
        github["event"] = {"pull_request": {"number": pr_number}}
    return {"github": github, "inputs": inputs or {}}


def _resolve(context: dict[str, Any]) -> tuple[str, str]:
    block = _concurrency()
    return render(block["group"], context), render(block["cancel-in-progress"], context)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_concurrency_group_cancels_older_head_when_pull_request() -> None:
    group, cancel = _resolve(_context(event_name="pull_request", pr_number=42))
    assert group == "ci-org/repo-pr-42"
    assert cancel == "true"


def test_concurrency_group_is_branch_keyed_when_push() -> None:
    group, cancel = _resolve(_context(event_name="push", ref="refs/heads/main"))
    assert group == "ci-org/repo-branch-refs/heads/main"
    assert cancel == "true"


def test_concurrency_group_is_intent_keyed_when_workflow_dispatch() -> None:
    group, cancel = _resolve(
        _context(event_name="workflow_dispatch", inputs={"intent_id": "manual-1"})
    )
    assert group == "ci-org/repo-intent-manual-1"
    assert cancel == "false"


def test_concurrency_group_is_intent_keyed_when_called_from_push() -> None:
    """deploy.yml's gate: the caller's event is `push`, the input is explicit."""
    group, cancel = _resolve(
        _context(
            event_name="push",
            ref="refs/heads/staging",
            inputs={"intent_id": "deploy-123", "advisory_signals": ""},
        )
    )
    assert group == "ci-org/repo-intent-deploy-123"
    assert cancel == "false"


def test_concurrency_group_is_non_cancelling_when_reusable_default_intent() -> None:
    """A caller that omits intent_id gets the `reusable` default and never cancels."""
    group, cancel = _resolve(
        _context(
            event_name="push", ref="refs/heads/dev", inputs={"intent_id": "reusable"}
        )
    )
    assert group == "ci-org/repo-intent-reusable"
    assert cancel == "false"


def test_push_run_and_gate_call_use_different_groups_when_staging_is_pushed() -> None:
    """The collision F-24 describes: one commit, two runs, must not cancel each other."""
    own_group, own_cancel = _resolve(
        _context(event_name="push", ref="refs/heads/staging")
    )
    gate_group, gate_cancel = _resolve(
        _context(
            event_name="push",
            ref="refs/heads/staging",
            inputs={"intent_id": "deploy-99"},
        )
    )
    assert own_group != gate_group
    assert gate_cancel == "false"
    assert own_cancel == "true"


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_intent_id_is_declared_when_workflow_is_dispatched_or_called() -> None:
    triggers = _ci()[True]
    assert "intent_id" in triggers["workflow_dispatch"]["inputs"]
    assert "intent_id" in triggers["workflow_call"]["inputs"]
    assert triggers["workflow_dispatch"]["inputs"]["intent_id"]["required"] is True


def test_group_tests_the_explicit_input_first_when_inferring_intent() -> None:
    """No `github.event_name` inference may come before the `inputs.intent_id` test."""
    group = re.sub(r"\s+", " ", _concurrency()["group"])
    body = _TEMPLATE.findall(group)[-1].strip()
    assert body.startswith("inputs.intent_id != ''"), body
    assert group.index("inputs.intent_id") < group.index("github.event_name")


def test_cancel_expression_requires_no_intent_when_cancelling() -> None:
    cancel = re.sub(r"\s+", " ", str(_concurrency()["cancel-in-progress"]))
    assert "inputs.intent_id == ''" in cancel


def test_deploy_gate_passes_a_unique_intent_when_calling_ci() -> None:
    """Without a unique input the gate would share the `reusable` group."""
    deploy = yaml.safe_load(DEPLOY_YML.read_text(encoding="utf-8"))
    gate = deploy["jobs"]["gate"]
    assert gate["uses"] == "./.github/workflows/ci.yml"
    intent = str(gate["with"]["intent_id"])
    assert "github.run_id" in intent
    assert intent.strip() != ""


# ---------------------------------------------------------------------------
# Interpreter self-tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("'a' && 'b' || 'c'", "b"),
        ("'' && 'b' || 'c'", "c"),
        ("null || 'x'", "x"),
        ("inputs.missing == ''", True),
        ("inputs.missing != ''", False),
        ("'ABC' == 'abc'", True),
        ("!false", True),
        ("format('{0}-{1}', 'a', 'b')", "a-b"),
        ("format('{{0}}-{0}', 'a')", "{0}-a"),
        ("format('p-{0}', inputs.missing)", "p-"),
        ("(true || false) && 'yes'", "yes"),
    ],
)
def test_interpreter_follows_github_semantics_when_evaluating(
    expression: str, expected: Any
) -> None:
    assert evaluate(expression, {"inputs": {}}) == expected


def test_render_substitutes_booleans_as_text_when_template_is_whole_expression() -> (
    None
):
    assert render("${{ 1 == 1 }}", {}) == "true"
    assert render("a-${{ 'x' }}-b", {}) == "a-x-b"
