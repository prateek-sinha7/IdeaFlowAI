---
id: stop-console-log
name: Console.log Check
description: Warns about console.log statements left in modified files after each response. Keeps production code clean.
event: Stop
trigger: End of each agent response — all edited JS/TS files
compatible_agents:
  - app-code-generator
  - app-feature-implementation
  - html-prototype-builder
tags:
  - console
  - cleanup
  - code-quality
---

## Console.log Check

Warns about console.log statements left in modified files after each response. Keeps production code clean.

### Trigger
End of each agent response — all edited JS/TS files

### Compatible Agents
app-code-generator, app-feature-implementation, html-prototype-builder

### Tags
console, cleanup, code-quality
