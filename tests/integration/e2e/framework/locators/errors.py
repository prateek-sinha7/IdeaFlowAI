"""Selectors for screens/13-errors.feature.md.

**Three distinct failures render one byte-identical screen** — an unparseable
URL, a missing run, and a missing workflow. Nothing in the DOM tells them apart,
so every scenario here asserts on the URL it navigated FROM. See S-13-10.

The 404 has no heading element. Match on text.
"""

NOT_FOUND = "Page not found."
NOT_FOUND_BODY = "This URL doesn't exist."
CODE = "404"
EYEBROW = "IT HAPPENS"

ACTIONS = ["Back to dashboard", "Create a workflow", "Sign in"]

NONEXISTENT_UUID = "00000000-0000-0000-0000-000000000000"
