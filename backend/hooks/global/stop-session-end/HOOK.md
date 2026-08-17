---
id: stop-session-end
name: Session State Persistence
description: Persists session state after each response so context survives across sessions. Enables long-running multi-session workflows.
event: Stop
trigger: End of each agent response
compatible_agents:
  - domain-analyst
  - requirements-analyst
  - app-user-stories
  - epic-architect
  - app-code-generator
  - app-feature-implementation
tags:
  - session
  - persistence
  - memory
  - state
---

## Session State Persistence

Persists session state after each response so context survives across sessions. Enables long-running multi-session workflows.

### Trigger
End of each agent response

### Compatible Agents
domain-analyst, requirements-analyst, app-user-stories, epic-architect, app-code-generator, app-feature-implementation

### Tags
session, persistence, memory, state
