# Error Handling and Degradation Strategy

## Design Philosophy

> No error should interrupt the user's creative flow. Degrade gracefully, don't stop.

## Error Classification and Degradation Matrix

### Type A: Missing Environment

| Error Scenario | Detection Method | Degradation Strategy | User Notification |
|----------|---------|---------|---------|
| Python 3 unavailable | `python3 --version` fails | Skip gacha.py, randomly pick from 10 preset direction categories | "The gacha engine requires Python 3; switched to the built-in random selection" |

### Type B: Optional Dependency Unavailable

| Error Scenario | Detection Method | Degradation Strategy | User Notification |
|----------|---------|---------|---------|
| Image-generation skill not installed | Check whether the skill exists | Output the full prompt text + instructions for manual image-generation platforms | "No usable image-generation skill was detected; the prompt has been output for manual use" |
| Image-generation skill call failed | Skill returns an error | Retry once; if it still fails, output the prompt text | "Image generation failed; the prompt has been output for manual use" |

### Type C: Runtime Exceptions

| Error Scenario | Degradation Strategy | User Notification |
|----------|---------|---------|
| gacha.py output format is malformed | Randomly pick from 10 preset direction categories | "Failed to parse the gacha result; switched to the built-in random selection" |
| Any unexpected error | Log the error message, skip this step, continue the main flow | "Ran into a problem: [brief error description]. Skipped and continuing" |

## Unified Error Message Format

```markdown
> [Warning] **[Step Name] has degraded**
> Reason: [what happened]
> Impact: [what functionality is limited]
> Fallback: [what is being used as a stopgap]
> Fix: [how to restore full functionality]
```

Example:

```markdown
> [Warning] **Avatar generation has degraded**
> Reason: No usable image-generation skill was detected
> Impact: Cannot automatically generate the avatar image
> Fallback: The full prompt has been output; copy it into Gemini / ChatGPT to generate manually
> Fix: Install and enable a vetted image-generation skill in the current environment
```

## Key Principles

1. **The text solution is the core value; the avatar is a nice-to-have** — a failure in an auxiliary feature must never interrupt the main flow
2. **Degradation messages must be actionable** — don't just say "an error occurred," say "how to fix it"
3. **One degraded step doesn't affect later steps** — if Step 5 degrades, Step 6 still runs normally
