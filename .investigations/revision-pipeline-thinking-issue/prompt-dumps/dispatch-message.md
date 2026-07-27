<!-- DISPATCH MESSAGE (the user turn the revision agent receives)
     The frontend sends the FRAMED request below; the previous_run
     provider seeds prototype.html into the sandbox, stashes the
     instruction, and slims the message to the SLIMMED form — that
     slimmed text is what the model actually gets as its user turn.
-->

## 1. What the frontend sends (framed)

```
=== REVISION REQUEST ===
Make the Save button on Settings actually save
=== END REQUEST ===

=== EXISTING PROTOTYPE HTML ===
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Acme Admin</title>
<style>
  :root {
    --bg: #fafaf7; --fg: #1a1a18; --accent: #c96442;
    --surface: #ffffff; --border: #e2e0da; --muted: #6b6a66;
    --font-body: system-ui, sans-serif;
  }
  body { margin: 0; font-family: var(--font-body); background: var(--bg); color: var(--fg); }
  .topbar { padding: 12px 20px; background: var(--surface); border-bottom: 1px solid var(--border); }
  .topbar h1 { margin: 0; font-size: 16px; }
  .layout { display: flex; }
  .sidebar { width: 180px; padding: 16px; border-right: 1px solid var(--border); }
  .nav-item { display: block; padding: 8px 10px; color: v
… (inline HTML truncated for readability; full framed message is 3235 chars)
```

## 2. Extracted instruction (→ ctx.revision_instruction)

```
Make the Save button on Settings actually save
```

## 3. SLIMMED user turn — what the model receives (199 chars)

```
=== REVISION REQUEST ===
Make the Save button on Settings actually save
=== END REQUEST ===

The current prototype is in the workspace file `prototype.html`. Call read_file to read it before editing.
```
