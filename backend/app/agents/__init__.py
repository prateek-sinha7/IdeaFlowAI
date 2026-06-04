# LangChain agent definitions
#
# The legacy free-chat stack (AgentOrchestrator + the 7 BaseAgent chat agents)
# was deleted in migration Phase 7b-5; the free-chat path now runs on the
# dedicated ``app.agents.chat_runner.ChatRunner`` over the deepagents runtime.
# This package no longer re-exports any agent classes. ``BaseAgent`` survives in
# ``app.agents.base`` solely for the live ``/flowin-handoff`` subsystem
# (``app.agents.handoff.*``), which imports it directly from the module.

__all__: list[str] = []
