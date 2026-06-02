"""agents/prototype — Prototype pipeline module.

All prototype-related code lives here:

  pipeline.py      — PrototypePipeline: the Spec Kit-style orchestrator
                     (specify → plan → task-runner → validate)
  context.py       — load_prototype_context(): loads template + DS + craft
  artifact_store.py — PrototypeArtifactStore: shared HTML store across agents
  tools.py         — LangChain tools: read_template_seed, emit_artifact, etc.
  agents/          — AGENT.md prompts for all 4 prototype agents
  guardrail.md     — html-prototype guardrail (symlinked from agents/guardrails/)

Entry point used by the execution engine:
    from agents.prototype.pipeline import PrototypePipeline
"""
