/**
 * A trimmed-but-structurally-faithful copy of
 * `backend/agents/workflows/pdf_to_prototype/workflow.yaml`, built by hand
 * from that file (no YAML parser is a frontend devDependency — see
 * `package.json`). Prompts are shortened to short placeholder strings since
 * this fixture exists to prove STRUCTURAL keys survive the canvas round
 * trip, not prompt bytes.
 *
 * Trimmed to 7 of the file's 15 steps — the ones that each carry a distinct
 * "the canvas doesn't model this" shape: a parent step with an explicit
 * top-level `depends_on`/`strategy` alongside its `subagents` block
 * (`synthesizer`), a `conditional` route with `produces: [route_decision]`
 * (`coverage-check`), plain `produces` (`journey-designer`), `validators` +
 * `fix` + `consumes` + `redoable` (`plan-lead`), `compaction` + `injects`
 * (`shell-builder`), and a self-fanout wave-scheduler step with `fanout` +
 * top-level `task_source` + `on_conflict` and no `subagents` block at all
 * (`screen-builder`) — the exact case STABILIZATION.md calls out as
 * collapsing to `strategy: single_shot` pre-fix.
 */
export const PDF_TO_PROTOTYPE_MANIFEST_FIXTURE = {
  capabilities: { internet: false },
  clarify: { defaults: [], mode: "skip" },
  context_providers: ["opendesign"],
  deliverable: { name: "prototype.html", publish_from_glob: "draft.v*.html", strategy: "single_file" },
  description:
    "Read a set of PDF job aids end to end, agree what they describe, then build an interactive prototype screen by screen with a wave of parallel builders.",
  design_mode: "web",
  display_name: "PDF to Prototype (wave build)",
  icon: "FileStack",
  id: "pdf_to_prototype",
  input_providers: ["pdf_pages"],
  is_beta: false,
  limits: { max_depth: 2, max_subagents: 200, wall_clock_seconds: 7200 },
  name: "PDF to Prototype",
  planner: "skip",
  seed_files: {},
  short_name: "PDF to Prototype v2",
  steps: [
    {
      agent: "custom-agent",
      gates: [],
      instance_id: "reading-planner",
      name: "Doc Splitter",
      prompt: "PROMPT: reading planner — divide documents across 5 readers, write reading-plan.md.",
      strategy: "single_shot",
      tools: { exec: false, read_files: true, write_files: true },
    },
    {
      agent: "custom-agent",
      depends_on: ["custom-agent:reading-planner"],
      gates: [],
      instance_id: "synthesizer",
      name: "Synthesizer",
      prompt: "PROMPT: synthesiser — read every reader's notes, write synthesis.md.",
      strategy: "single_shot",
      subagents: {
        max_parallel: 5,
        mode: "parallel",
        steps: [
          {
            agent: "custom-agent",
            gates: [],
            injects: ["pdf_pages"],
            instance_id: "reader-1",
            name: "Reader 1",
            prompt: "PROMPT: reader 1 — extract and read its share of documents.",
            skills: ["file-extraction"],
            strategy: "single_shot",
            tools: { exec: false, read_files: true, tool_sets: ["file_extract"], write_files: true },
          },
          {
            agent: "custom-agent",
            gates: [],
            injects: ["pdf_pages"],
            instance_id: "reader-2",
            name: "Reader 2",
            prompt: "PROMPT: reader 2 — extract and read its share of documents.",
            skills: ["file-extraction"],
            strategy: "single_shot",
            tools: { exec: false, read_files: true, tool_sets: ["file_extract"], write_files: true },
          },
        ],
      },
      tools: { exec: false, read_files: true, spawn_subagents: true, write_files: true },
    },
    {
      agent: "custom-agent",
      depends_on: ["custom-agent:synthesizer"],
      gates: ["conditional"],
      instance_id: "coverage-check",
      name: "Coverage Check",
      produces: ["route_decision"],
      prompt: "PROMPT: coverage check — judge whether synthesis.md is complete, reply JSON.",
      route: {
        default_next: "journey-designer",
        loop_max_iterations: 3,
        outcomes: {
          complete: { target: "journey-designer", trigger: "step" },
          incomplete: { target: "synthesizer", trigger: "step" },
        },
      },
      strategy: "single_shot",
      tools: { exec: false, read_files: true, write_files: false },
    },
    {
      agent: "custom-agent",
      gates: ["human"],
      instance_id: "journey-designer",
      redoable: true,
      name: "Journey Designer",
      produces: ["journeys"],
      prompt: "PROMPT: journey designer — write journeys.md, the build specification.",
      strategy: "single_shot",
      tools: { exec: false, read_files: true, write_files: true },
    },
    {
      agent: "custom-agent",
      consumes: ["journeys"],
      depends_on: ["custom-agent:journey-designer"],
      fix: { max_attempts: 2 },
      gates: ["validation", "human"],
      instance_id: "plan-lead",
      redoable: true,
      name: "Planner",
      produces: ["prototype-plan", "build_tasks"],
      prompt: "PROMPT: plan-lead — turn journeys.md into build/digest.md + a fenced task list.",
      strategy: "single_shot",
      tools: { exec: false, read_files: true, write_files: true },
      validators: ["spec_plan_coverage"],
    },
    {
      agent: "custom-agent",
      compaction: "html_skeleton",
      consumes: ["prototype-plan"],
      depends_on: ["custom-agent:plan-lead"],
      gates: ["before-human"],
      injects: ["template", "design_system"],
      instance_id: "shell-builder",
      redoable: true,
      name: "Layout Builder",
      prompt: "PROMPT: shell builder — write draft.v1.html, the chrome and empty page sections.",
      strategy: "single_shot",
      tools: { exec: false, read_files: true, tool_sets: ["prototype_emit_only"], write_files: true },
    },
    {
      agent: "custom-agent",
      depends_on: ["custom-agent:shell-builder"],
      fanout: { agent: "self", max_parallel: 5, mode: "parallel" },
      gates: [],
      injects: ["template", "design_system"],
      instance_id: "screen-builder",
      name: "Screen Builder",
      on_conflict: "human_gate",
      produces: ["fragments"],
      prompt: "PROMPT: screen builder — build ONE screen's inner HTML per wave task.",
      strategy: "wave_scheduler",
      task_source: {
        kind: "parsed",
        parser: "json_tasks",
        source_step: "custom-agent:plan-lead",
        spec_step: "custom-agent:journey-designer",
        target: "tasks.json",
      },
      tools: { exec: false, read_files: true, spawn_subagents: true, write_files: true },
    },
  ],
  user_launchable: true,
  version: 1,
};
