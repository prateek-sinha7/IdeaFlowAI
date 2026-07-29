"""Unit tests for prototype-validate's ONE custom precheck hook (no
surviving seed-default :root token values + no empty page sections — the
checks the generic model_graded/precheck.py config cannot express).
"""

from __future__ import annotations

from evals.model_graded.agents.prototype_validate.qa_fixes_check import check

BROKEN_HTML = """<!doctype html>
<html>
<head>
<style>
:root {
  --bg: #fafaf7;
  --fg: #141413;
  --accent: #c96442;
  --surface: #ffffff;
  --border: #e5e5e5;
  --muted: #888888;
}
</style>
</head>
<body>
<section data-page="dashboard" class="page is-active"><div class="card">real content here</div></section>
<section data-page="subscriptions" class="page"></section>
</body>
</html>"""

FIXED_HTML = BROKEN_HTML.replace("#fafaf7", "#ffffff").replace("#141413", "#1a1a1a").replace(
    "#c96442", "#635bff"
).replace(
    '<section data-page="subscriptions" class="page"></section>',
    '<section data-page="subscriptions" class="page"><div class="card">'
    "<table><tr><td>Acme Corp</td><td>Pro</td></tr></table></div></section>",
)


def test_fails_when_seed_default_tokens_survive():
    passed, reason = check(BROKEN_HTML)
    assert passed is False
    assert "--bg: #fafaf7" in reason


def test_fails_when_a_page_is_still_empty():
    only_tokens_fixed = (
        BROKEN_HTML.replace("#fafaf7", "#ffffff")
        .replace("#141413", "#1a1a1a")
        .replace("#c96442", "#635bff")
    )
    passed, reason = check(only_tokens_fixed)
    assert passed is False
    assert "subscriptions" in reason


def test_passes_when_tokens_fixed_and_page_filled():
    passed, reason = check(FIXED_HTML)
    assert passed is True
    assert "no seed-default tokens survived" in reason


def test_fails_when_no_root_block():
    no_root = FIXED_HTML.replace(
        ":root {\n  --bg: #ffffff;\n  --fg: #1a1a1a;\n  --accent: #635bff;\n"
        "  --surface: #ffffff;\n  --border: #e5e5e5;\n  --muted: #888888;\n}\n",
        "",
    )
    passed, reason = check(no_root)
    assert passed is False
    assert "no ':root { }' block found" in reason
