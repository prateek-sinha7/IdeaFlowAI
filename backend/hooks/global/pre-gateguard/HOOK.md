---
id: pre-gateguard
name: "GateGuard: Fact Force"
description: Blocks the first Edit/Write per file and demands investigation (importers, data schemas, user instructions) before allowing changes.
event: PreToolUse
trigger: Before first Edit / Write / MultiEdit on each file
compatible_agents:
  - app-code-generator
  - app-feature-implementation
  - mulesoft-feature-coding
  - dotnet-feature-coding
  - dotnet-modernization
tags:
  - safety
  - investigation
  - gateguard
  - pre-check
---

## GateGuard: Fact Force

Blocks the first Edit/Write per file and demands investigation (importers, data schemas, user instructions) before allowing changes.

### Trigger
Before first Edit / Write / MultiEdit on each file

### Compatible Agents
app-code-generator, app-feature-implementation, mulesoft-feature-coding, dotnet-feature-coding, dotnet-modernization

### Tags
safety, investigation, gateguard, pre-check
