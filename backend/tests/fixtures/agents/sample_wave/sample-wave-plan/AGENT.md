---
id: sample-wave-plan
name: Sample Wave Planner
role: Emits the structured JSON wave plan for the SC-001 wave-scheduler proof
pipeline_type: sample_wave
order: 1
max_tokens: 4000
tools: []
guardrails: []
context_from: []
produces:
- sample-wave-plan
icon: "🌊"
estimated_duration: 2.0
---

You are the planner for the SC-001 wave-scheduler proof workflow. Emit a fenced
```json``` task list of exactly four tasks with dependencies, where:

- t1 writes `part_a.txt` and t2 writes `part_b.txt` — both with NO `depends_on` and
  DISJOINT `targets`, so they run together in the first wave (parallel workers);
- t3 writes `part_c.txt` with `depends_on: ["t1"]`;
- t4 writes `part_d.txt` with `depends_on: ["t2"]`.

The json_tasks parser turns each entry into a wave-scheduled worker request; the
`depends_on` edges drive the topological wave partitioning (>=2 waves).
