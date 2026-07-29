"""Unit tests for prototype-build's ONE custom precheck hook (required
:root tokens INSIDE the :root block + hash-router wiring signal — the
checks the generic model_graded/precheck.py config cannot express).
"""

from __future__ import annotations

from evals.model_graded.agents.prototype_build.shell_structure_check import check

GOOD_HTML = """<!doctype html>
<html>
<head>
<style>
:root {
  --bg: #ffffff;
  --fg: #1a1a1a;
  --accent: #635bff;
  --surface: #f6f9fc;
  --border: #e3e8ee;
  --muted: #697386;
}
</style>
</head>
<body>
<nav><a href="#/dashboard">Dashboard</a></nav>
<section data-page="dashboard" class="page is-active"></section>
<script>
window.addEventListener('hashchange', () => {});
</script>
</body>
</html>"""


def test_passes_on_well_formed_shell():
    passed, reason = check(GOOD_HTML)
    assert passed is True
    assert "hash router wired" in reason


def test_fails_when_root_block_missing():
    no_root = GOOD_HTML.replace(":root {\n  --bg: #ffffff;\n  --fg: #1a1a1a;\n  --accent: #635bff;\n  --surface: #f6f9fc;\n  --border: #e3e8ee;\n  --muted: #697386;\n}\n", "")
    passed, reason = check(no_root)
    assert passed is False
    assert "no ':root { }' block found" in reason


def test_fails_when_a_root_token_is_missing():
    missing_var = GOOD_HTML.replace("  --muted: #697386;\n", "")
    passed, reason = check(missing_var)
    assert passed is False
    assert "--muted" in reason


def test_fails_when_no_page_sections():
    no_sections = GOOD_HTML.replace('<section data-page="dashboard" class="page is-active"></section>', "")
    passed, reason = check(no_sections)
    assert passed is False
    assert "no <section data-page" in reason


def test_fails_when_no_hash_router_signal():
    no_router = GOOD_HTML.replace(
        "<script>\nwindow.addEventListener('hashchange', () => {});\n</script>\n", ""
    )
    passed, reason = check(no_router)
    assert passed is False
    assert "no hash-router wiring found" in reason
