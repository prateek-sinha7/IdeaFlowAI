---
id: stop-format-typecheck
name: Format + Typecheck on Stop
description: Batch formats (Biome/Prettier) and typechecks all JS/TS files edited in the response. Runs once at Stop instead of after every edit.
event: Stop
trigger: End of each agent response — all edited JS/TS files
compatible_agents:
  - app-code-generator
  - app-feature-implementation
  - app-ux-design
  - html-prototype-builder
  - prototype-polisher
tags:
  - format
  - typecheck
  - typescript
  - prettier
  - biome
---

## Format + Typecheck on Stop

Batch formats (Biome/Prettier) and typechecks all JS/TS files edited in the response. Runs once at Stop instead of after every edit.

### Trigger
End of each agent response — all edited JS/TS files

### Compatible Agents
app-code-generator, app-feature-implementation, app-ux-design, html-prototype-builder, prototype-polisher

### Tags
format, typecheck, typescript, prettier, biome
