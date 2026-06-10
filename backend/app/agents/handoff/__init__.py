"""Agents for the /flowin-handoff feature.

* :class:`HandoffCoder` — proposes file edits to satisfy the user's task, running on the
  sanctioned deepagents runtime (``create_deep_agent``); supersedes the deleted
  ``CodingAgent`` ``build_model().ainvoke`` bypass (09-06 / D-09 / INV-13). Exported ALSO
  under the legacy name ``CodingAgent`` (an alias) so the retained ``/api/handoff`` pipeline
  + its contract seam bind the same name — the deleted bypass class is gone.
* :class:`TestAgent` — analyses test coverage and quality.
* :class:`ComplianceAgent` — produces a security/best-practices report.
* :func:`classify_task` — LLM-driven coding-vs-test classifier.
"""

from app.agents.handoff.classifier import classify_task
from app.agents.handoff.coder import HandoffCoder
from app.agents.handoff.compliance_agent import ComplianceAgent
from app.agents.handoff.test_agent import TestAgent

# Legacy alias: the handoff pipeline + its contract test bind the name ``CodingAgent``.
# The runtime-bypassing bypass class was DELETED (D-09); ``HandoffCoder`` runs on
# the unified deepagents runtime and takes its place under the same name.
CodingAgent = HandoffCoder

__all__ = [
    "HandoffCoder",
    "CodingAgent",
    "TestAgent",
    "ComplianceAgent",
    "classify_task",
]
