---
id: post-quality-gate
name: Quality Gate
description: Runs lint, typecheck, and test suite after every file edit. Blocks progression if quality checks fail.
event: PostToolUse
trigger: After Edit / Write / MultiEdit
compatible_agents:
  - app-code-compliance
  - app-test-compliance
  - app-code-generator
  - app-feature-implementation
  - mulesoft-code-compliance
  - dotnet-code-compliance
tags:
  - lint
  - typecheck
  - quality
  - ci
---

## Quality Gate

Runs lint, typecheck, and test suite after every file edit. Blocks progression if quality checks fail.

### Trigger
After Edit / Write / MultiEdit

### Compatible Agents
app-code-compliance, app-test-compliance, app-code-generator, app-feature-implementation, mulesoft-code-compliance, dotnet-code-compliance

### Tags
lint, typecheck, quality, ci
