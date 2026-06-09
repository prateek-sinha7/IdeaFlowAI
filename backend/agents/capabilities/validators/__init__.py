"""agents.capabilities.validators — kernel-side validator capability package.

Package marker only this plan (08-01). It holds ``severity.py`` — the single
canonical P0–P3 -> CRITICAL/HIGH/MEDIUM/LOW mapping function (VALID-03 single
source) — and, in 08-04, the pure-stdlib registered ``Validator`` impls
(``task_done_when``, ``spec_plan_coverage``). Heavy-dep validators
(``html_static``/``html_render``/``design_quality``) live app-side in
``app/agents/validators/`` (D-04), not here.

Kept import-light on purpose: importing ``agents.capabilities.validators.severity``
must NOT trigger any ``@register``/``discover()`` side-effect or pull heavy deps,
so the 08-02 validation gate can consume ``map_severity`` cleanly BEFORE 08-04's
validator impls land. The ``__init__`` therefore imports nothing.
"""
