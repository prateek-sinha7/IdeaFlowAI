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
  * { box-sizing: border-box; }
  body { margin: 0; font-family: var(--font-body); background: var(--bg); color: var(--fg); display: grid; grid-template-columns: 180px 1fr; grid-template-rows: 56px 1fr; min-height: 100vh; }
  .sidebar { grid-column: 1; grid-row: 1 / 3; background: var(--bg); border-right: 1px solid var(--border); padding: 16px; position: sticky; top: 0; height: 100vh; }
  .topbar { grid-col
… (inline HTML truncated for readability; full framed message is 9482 chars)
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
