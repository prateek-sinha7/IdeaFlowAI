"""Drift guards: the live e2e tier must not re-type app facts that have since changed.

QA-KB-122 / ISS-1158 (+ siblings ISS-1185..1189). Five intentional app commits touched no
tests/integration/e2e file, so the tier rotted. These parse the e2e tree as text (no browser,
no network), like test_entitlement_parity.py, and are red until the e2e tree is repaired.
"""

from __future__ import annotations

import ast
import glob
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_E2E = _ROOT / "tests/integration/e2e"
_SUITES = _E2E / "suites"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


@pytest.mark.issue("ISS-1158")
def test_e2e_create_user_bodies_only_send_fields_the_api_accepts():
    """ISS-1158 - CreateUserRequest is extra=forbid; a "password" key is a 422."""
    tree = ast.parse(_text(_ROOT / "backend/app/api/admin.py"))
    fields = next(
        {s.target.id for s in n.body if isinstance(s, ast.AnnAssign)}
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "CreateUserRequest"
    )
    bad = []
    for f in (_E2E / "conftest.py", _SUITES / "24_api_contract/test_api_contract.py"):
        for d in ast.walk(ast.parse(_text(f))):
            if isinstance(d, ast.Dict):
                keys = {
                    k.value
                    for k in d.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                if {"email", "tier", "is_admin"} <= keys and keys - fields:
                    bad.append(f"{f.name}:{d.lineno} {sorted(keys - fields)}")
    assert not bad, bad


@pytest.mark.issue("ISS-1158")
def test_e2e_composer_locators_match_the_rail():
    """ISS-1158 - AGENT_SUBTABS and the step caption regex follow CanvasConfigRail / stepKind."""
    comp = ast.parse(_text(_E2E / "framework/locators/composer.py"))
    pinned = next(
        ast.literal_eval(n.value)
        for n in comp.body
        if isinstance(n, ast.Assign)
        and getattr(n.targets[0], "id", "") == "AGENT_SUBTABS"
    )
    tsx = _text(
        _ROOT / "frontend/src/components/workflow/composer/CanvasConfigRail.tsx"
    )
    block = tsx[tsx.index('{ id: "overview"') : tsx.index('{ id: "config"') + 60]
    assert list(pinned) == re.findall(r'label:\s*"([^"]+)"', block)
    assert 'r"Agent · step 1 of' not in _text(
        _SUITES / "04_composer_canvas/test_composer_canvas.py"
    )


@pytest.mark.issue("ISS-1158")
def test_e2e_catalog_titles_use_the_manifest_label():
    """ISS-1158 - ppt_v2 is titled "(Depth)", not "(Detailed)"."""
    assert "Pitch an idea (Detailed)" not in _text(
        _E2E / "framework/locators/home_catalog.py"
    )


@pytest.mark.issue("ISS-1158")
def test_e2e_has_no_strict_xfail_on_bugs_seen_to_xpass():
    """ISS-1158 - these five strict markers XPASSed on 2026-10-09 (strict turns that into a failure)."""
    stale = {"ISS-796", "ISS-923", "ISS-1033", "ISS-213", "ISS-190"}
    found = []
    for f in glob.glob(str(_SUITES / "**/*.py"), recursive=True):
        for i, ln in enumerate(_text(Path(f)).splitlines(), 1):
            m = re.search(r'xfail\(reason="(ISS-\d+)[^"]*"[^)]*strict=True', ln)
            if m and m.group(1) in stale:
                found.append(f"{Path(f).name}:{i} {m.group(1)}")
    assert not found, found


@pytest.mark.issue("ISS-1185")
def test_e2e_create_user_dialog_tests_match_the_invitation_dialog():
    """ISS-1185 - the dialog has no password input and its button reads 'Send Invitation'."""
    page = _text(_ROOT / "frontend/src/app/admin/page.tsx")
    assert (
        'type="password"'
        not in page[
            page.index("Create user modal") : page.index("Delete confirm modal")
        ]
    )
    bad = []
    for f in glob.glob(str(_SUITES / "11_admin/*.py")):
        for i, ln in enumerate(_text(Path(f)).splitlines(), 1):
            if (
                'input[type="password"]' in ln and "fill" in ln
            ) or 'name="Create User"' in ln:
                bad.append(f"{Path(f).name}:{i}")
    assert not bad, bad


@pytest.mark.issue("ISS-1186")
def test_e2e_admin_reset_tests_do_not_assert_the_deleted_reset_contract():
    """ISS-1186 - no break-glass refusal and no requires_new_password_at_next_login answer exist any more."""
    src = _text(_SUITES / "11_admin/test_admin.py")
    assert "cannot be reset here" not in src
    assert "requires_new_password_at_next_login" not in src


@pytest.mark.issue("ISS-1187")
def test_e2e_disposable_user_does_not_promise_a_password_it_never_set():
    """ISS-1187 - creation is invitation-only; returning accounts.PASSWORD needs something that sets it."""
    src = _text(_E2E / "conftest.py")
    body = src[src.index("def make(") :]
    body = body[: body.index("make.admin_page")]
    assert (
        '"password": accounts.PASSWORD' not in body or "admin_set_user_password" in src
    )


@pytest.mark.issue("ISS-1188")
def test_e2e_does_not_pin_run_or_workflow_ids_as_literals():
    """ISS-1158/1188 - pinned ids vanished when the dev DB was reseeded (14ce62c59)."""
    pat = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    found = []
    for f in glob.glob(str(_E2E / "**/*.py"), recursive=True):
        for i, ln in enumerate(_text(Path(f)).splitlines(), 1):
            for u in pat.findall(ln):
                if (
                    u != "00000000-0000-0000-0000-000000000000"
                    and not ln.lstrip().startswith(("#", '"""'))
                    and "=" in ln.split(u)[0]
                ):
                    found.append(f"{Path(f).name}:{i}")
    assert not found, found


@pytest.mark.issue("ISS-1189")
def test_e2e_iss802_counts_only_the_version_list_request():
    """ISS-1189 - the clarifications read (?kind=clarifications) is a different request."""
    src = _text(
        _SUITES / "07_run_detail/test_iss802_steps_agent_artifacts_duplicate_request.py"
    )
    line = next(l for l in src.splitlines() if "artifact_calls = [" in l)
    assert "kind" in line or "?" in line


@pytest.mark.issue("ISS-1194")
@pytest.mark.xfail(reason="ISS-1194 unfixed", strict=True)
def test_e2e_run_history_chip_callers_skip_before_clicking_an_absent_chip():
    """ISS-1194 - a chip is dropped at count 0 (WorkflowHistory.tsx:1284), so a test that clicks
    `.chip(` with no `pytest.skip(` before it times out instead of skipping with a reason."""
    red = []
    for f in sorted(glob.glob(str(_SUITES / "**/*.py"), recursive=True)):
        tree = ast.parse(_text(Path(f)))
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            calls = [
                c
                for c in ast.walk(fn)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            ]
            chips = [c.lineno for c in calls if c.func.attr == "chip"]
            if not chips:
                continue
            first = min(chips)
            if not any(c.func.attr == "skip" and c.lineno < first for c in calls):
                red.append(f"{Path(f).name}:{fn.lineno} {fn.name}")
    assert not red, red
