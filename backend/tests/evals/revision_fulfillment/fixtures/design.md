# Design — mini fixture

**Template**: Admin Shell (mini)
**Design system**: Acme Warm

## Tokens (`:root`)

- `--bg: #fafaf7`
- `--fg: #1a1a18`
- `--accent: #c96442`
- `--surface: #ffffff`
- `--border: #e2e0da`
- `--muted: #6b6a66`
- `--font-body: system-ui, sans-serif`

## Rules

- All colors via `var(--*)` tokens; no new raw hex outside `:root`.
- Nav items use `.nav-item`; pages are `<section data-page>` toggled by the
  hash router (`routes` map + `route()`).
