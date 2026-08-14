---
id: pre-config-protection
name: Config Protection
description: Blocks modifications to linter and formatter config files. Steers the agent to fix code instead of weakening quality gates.
event: PreToolUse
trigger: Before Write / Edit / MultiEdit on config files
compatible_agents:
  - app-code-compliance
  - app-devops
  - mulesoft-code-compliance
  - dotnet-code-compliance
tags:
  - config
  - protection
  - quality
  - lint
---

## Config Protection

Blocks modifications to linter and formatter config files. Steers the agent to fix code instead of weakening quality gates.

### Trigger
Before Write / Edit / MultiEdit on config files

### Compatible Agents
app-code-compliance, app-devops, mulesoft-code-compliance, dotnet-code-compliance

### Tags
config, protection, quality, lint
