"""prototype-specify's model-graded agent folder — the first example onboarded
onto the branch (specs/005-prompt-eval-scoring/). Contains data only
(``scenarios/*.yaml``, each carrying its own ``precheck:`` config and
``rubric:`` text) plus this folder's ONE narrow custom precheck hook,
``nav_cross_reference_check.py`` — the single check (nav-target-to-page-
section cross-referencing) the generic ``model_graded/precheck.py`` config
cannot express, since it needs real parsing, not a count/substring check.
"""
