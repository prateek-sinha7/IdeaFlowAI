# Contract — checkers

The one piece of a scenario that must be code. Everything else is data.

## Signature

```python
def <name>(final_html: str) -> tuple[bool, str]:
    """One sentence: what fact does this establish?"""
```

| | |
|---|---|
| **Input** | The delivered artifact's full text — `LiveRunResult.final_html`, read back from the run sandbox after the agent finishes |
| **Output** | `(passed, reason)` |
| **On success** | `(True, "")` |
| **On failure** | `(False, "<specific, human-first reason>")` |

## Rules

1. **The reason names the thing, not the rule.** `"Save button has no working handler (neither
   inline nor script-bound)"` — not `"check 3 failed"`. That string is what a human reads first
   and often the only thing they read.
2. **Check the artifact, never the model's prose.** The agent's narration is not evidence; a
   claim of "PERFECT!!! completely clean" has been observed alongside a still-broken file.
3. **One function per defect.** Compose them into an aggregate when a scenario covers several,
   and have the aggregate report *which* sub-checks failed rather than a bare `False`.
4. **Accept every legitimate implementation.** A Save button may be wired inline
   (`onclick="save()"` with `save` defined) *or* bound in script
   (`getElementById('save-btn').addEventListener`). Rejecting a valid variant makes the eval
   lie in the expensive direction — it reports a regression that is not there.
5. **Must fail on the raw fixture.** Enforced by `validate_scenario.py`, which runs the checker
   against the unfixed input and requires a failure. A checker that passes on broken input can
   never demonstrate a fix.
6. **No I/O, no network, no model.** Checkers are pure functions of a string. That is what makes
   the verdict free, instant and identical every run.

## Registry

Each phase folder exposes its checkers by name:

```python
CHECKERS = {
    "prototype_multi_issue_repair": prototype_multi_issue_repair,
}
```

A scenario YAML's `checker:` field is a key into this dict. An unknown key fails at discovery,
not mid-run.

## Worked example

```python
def reports_page_reachable(final_html: str) -> tuple[bool, str]:
    """Is there a Reports page — section + route + nav link — actually reachable?"""
    has_section  = bool(re.search(r'<section[^>]*data-page="reports"', final_html))
    has_route    = bool(re.search(r"reports\s*:\s*['\"]#/reports['\"]", final_html))
    has_nav_link = bool(re.search(r'<a[^>]*class="nav-item"[^>]*href="#/reports"', final_html))

    if not has_section:  return False, 'no <section data-page="reports"> in delivered file'
    if not has_route:    return False, "no 'reports' entry in the routes map"
    if not has_nav_link: return False, "no sidebar nav link pointing at #/reports"
    return True, ""
```

Three separate failure reasons rather than one — because "the Reports page is missing" and "the
Reports page exists but nothing links to it" call for completely different fixes.
