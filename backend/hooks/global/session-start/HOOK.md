---
id: session-start
name: Session Context Loader
description: Loads previous session state and detects package manager on new session start. Ensures continuity across sessions.
event: SessionStart
trigger: Every new agent session
compatible_agents:
  - domain-analyst
  - requirements-analyst
  - app-user-stories
  - epic-architect
  - app-code-generator
tags:
  - session
  - context
  - memory
  - continuity
---

## Session Context Loader

Loads previous session state and detects package manager on new session start. Ensures continuity across sessions.

### Trigger
Every new agent session

### Compatible Agents
domain-analyst, requirements-analyst, app-user-stories, epic-architect, app-code-generator

### Tags
session, context, memory, continuity
