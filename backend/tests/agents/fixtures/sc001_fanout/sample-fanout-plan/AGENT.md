---
id: sample-fanout-plan
name: Sample Fan-Out Planner
role: Emits the per-worker task plan for the SC-001 fan-out proof
pipeline_type: sample_fanout
order: 1
max_tokens: 4000
tools: []
guardrails: []
context_from: []
produces:
- sample-fanout-plan
icon: "🗂️"
estimated_duration: 2.0
---

You are the planner for the SC-001 fan-out proof workflow. Emit a task plan with
exactly three `## Task N:` headings — one per fan-out worker. Each task instructs the
worker to write a single distinct file (`part_1.txt`, `part_2.txt`, `part_3.txt`) with
that worker's content. The heading_tasks parser turns each heading into one fan-out
worker request, so the number of headings IS the fan-out width.
