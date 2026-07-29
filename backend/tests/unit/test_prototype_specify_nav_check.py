"""Unit tests for prototype-specify's ONE custom precheck hook
(nav-target-to-page-section cross-reference — the one check the generic
model_graded/precheck.py config cannot express). Task T5.
"""

from __future__ import annotations

from evals.model_graded.agents.prototype_specify.nav_cross_reference_check import check

GOOD_SPEC = """<spec>
## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| dashboard | `#/dashboard` | overview | stat row | Yes |
| invoices | `#/invoices` | invoice history | log list | No |

## Page Specifications

### Dashboard (`#/dashboard`)
content here

### Invoices (`#/invoices`)
content here
</spec>"""

DANGLING_SPEC = """<spec>
## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| dashboard | `#/dashboard` | overview | stat row | Yes |
| invoices | `#/invoices` | invoice history | log list | No |

## Page Specifications

### Dashboard (`#/dashboard`)
content here
</spec>"""

NO_TABLE_SPEC = "<spec>\nNo navigation table here at all.\n</spec>"


def test_passes_when_every_nav_target_has_a_page_section():
    passed, reason = check(GOOD_SPEC)
    assert passed is True
    assert "2 nav target(s)" in reason


def test_fails_on_dangling_nav_target():
    passed, reason = check(DANGLING_SPEC)
    assert passed is False
    assert "#/invoices" in reason


def test_fails_when_no_table_routes_found():
    passed, reason = check(NO_TABLE_SPEC)
    assert passed is False
    assert "no routes found" in reason


def test_wrapper_missing_is_not_this_checks_job():
    """Division of labor: the custom hook only checks nav cross-referencing —
    a missing <spec> wrapper is the generic precheck's concern, not this
    one's. This fixture (no wrapper, but a valid nav/section match) should
    still PASS the custom hook."""
    unwrapped = GOOD_SPEC.replace("<spec>\n", "").replace("\n</spec>", "")
    passed, _ = check(unwrapped)
    assert passed is True
