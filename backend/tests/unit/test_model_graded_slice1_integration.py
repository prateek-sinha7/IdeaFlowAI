"""Slice 1 integration check (task T6): driver + scenario_discovery +
generic precheck + prototype-specify's custom hook compose correctly
end to end, offline (scripted response, no report/judge involvement).
"""

from __future__ import annotations

import pytest

from evals.model_graded.precheck import run_precheck
from evals.model_graded.scenario_discovery import discover_all_scenarios

GOOD_RESPONSE = """<spec>
## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| dashboard | `#/dashboard` | overview | stat row | Yes |
| invoices | `#/invoices` | invoice history | log list | No |
| customers | `#/customers` | customer list | table | No |
| subscriptions | `#/subscriptions` | plan mgmt | table | No |
| settings | `#/settings` | config | form | No |

## Page Specifications

### Dashboard (`#/dashboard`)
content

### Invoices (`#/invoices`)
content

### Customers (`#/customers`)
content

### Subscriptions (`#/subscriptions`)
content

### Settings (`#/settings`)
content
</spec>"""


@pytest.fixture()
def prototype_specify_scenario():
    scenarios = discover_all_scenarios()
    return scenarios["billing_console"]


def test_generic_precheck_and_custom_hook_both_pass_on_good_response(
    prototype_specify_scenario,
):
    generic_passed, _ = run_precheck(GOOD_RESPONSE, prototype_specify_scenario.precheck_config)
    custom_passed, _ = prototype_specify_scenario.precheck_module(GOOD_RESPONSE)

    assert generic_passed is True
    assert custom_passed is True


def test_combined_precheck_fails_when_only_custom_hook_catches_dangling_nav(
    prototype_specify_scenario,
):
    # Retargets the "settings" table row to a route with NO matching page
    # section, while keeping the section COUNT unchanged (5 sections) — so
    # only the custom hook's cross-reference check can catch this, not the
    # generic (count-only) precheck.
    dangling_response = GOOD_RESPONSE.replace(
        "| settings | `#/settings` | config | form | No |",
        "| settings | `#/settings-v2` | config | form | No |",
    )
    generic_passed, _ = run_precheck(dangling_response, prototype_specify_scenario.precheck_config)
    custom_passed, custom_reason = prototype_specify_scenario.precheck_module(dangling_response)

    # Generic check (wrapper/section-count/forbidden) has no idea about nav
    # cross-referencing — only the custom hook catches this defect.
    assert generic_passed is True
    assert custom_passed is False
    assert "#/settings-v2" in custom_reason


def test_combined_precheck_fails_when_only_generic_check_catches_missing_wrapper(
    prototype_specify_scenario,
):
    unwrapped = GOOD_RESPONSE.replace("<spec>\n", "").replace("\n</spec>", "")
    generic_passed, generic_reason = run_precheck(
        unwrapped, prototype_specify_scenario.precheck_config
    )
    custom_passed, _ = prototype_specify_scenario.precheck_module(unwrapped)

    assert generic_passed is False
    assert "not wrapped" in generic_reason
    assert custom_passed is True  # nav cross-reference is still satisfied
