# LangChain agent definitions
#
# The legacy free-chat stack (AgentOrchestrator + the 7 chat agents) was deleted
# in migration Phase 7b-5; the free-chat path now runs on the dedicated
# ``app.agents.chat_runner.ChatRunner`` over the deepagents runtime. The last
# legacy module ``app.agents.base`` (the old ``BaseAgent``) was deleted in Phase
# 7c after the ``/flowin-handoff`` agents (``app.agents.handoff.*``) were migrated
# onto ``app.agents.model_factory.build_model().ainvoke``. This package no longer
# re-exports any agent classes.

__all__: list[str] = []
