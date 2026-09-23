"""Selectors, one module per spec area.

    from framework.locators import auth as L
    page.fill(L.EMAIL, ...)

A package rather than one flat `locators.py` because there are 312 addressable
controls across 24 areas — and a package rather than a `locators.py` inside each
`suites/<area>/` folder, because 24 files all named `locators` collide the
moment two of them are importable at once.

Module names mirror the spec files: `01-auth.feature.md` -> `auth.py`.
`shell.py` is the exception — the chrome that wraps every screen, belonging to
no single area.
"""
