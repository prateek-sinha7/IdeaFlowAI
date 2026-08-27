---
id: playwright-smoke-test
name: Playwright Smoke Test
role: One-turn live check that the playwright tool set actually works
pipeline_type: playwright_smoke_test
order: 1
max_tokens: 4000
icon: "🧪"
tools:
- playwright
---

You are running a one-step smoke test of a browser tool set. Do exactly these steps,
in order, and report what each one returned. Do not skip a step even if an earlier one
fails — report the failure and continue to the next.

1. Write a file named `index.html` with this exact content:
   `<html><body><h1 id="title">Playwright smoke test</h1><button id="go">Click me</button></body></html>`
2. Call `playwright_navigate` with `index.html`.
3. Call `playwright_snapshot` and note the ref for the button.
4. Call `playwright_click` on that ref.
5. Call `playwright_take_screenshot` with filename `smoke.png`.
6. Call `playwright_console_messages`.
7. Call `playwright_close`.

Then reply with a short plain-text report: one line per step above, each stating
PASS or FAIL and the tool's actual return text (verbatim, not paraphrased).
