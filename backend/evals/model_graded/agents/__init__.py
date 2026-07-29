"""One folder per agent onboarded onto the model-graded branch.

Each ``agents/<agent_id>/`` folder holds only data — ``scenarios/*.yaml``,
each carrying its own ``precheck:`` config and ``rubric:`` text — plus, at
most, one narrow custom precheck hook (declared via the scenario's
``precheck_module:`` field) for a check the generic, shared
``model_graded/precheck.py`` config cannot express. Onboarding a new agent
should not require more Python than that one optional hook.
"""
