# Installing the skill and attaching it to an agent

The skill is self-contained: `SKILL.md`, `schema/`, `docs/`, `examples/`, `references/`
and `scripts/` travel together. Nothing in it reads files outside its own folder, except
the manifest you ask it to validate and an optional platform checkout or server you point
the refresh script at.

## 1. Install

Copy the whole `velocity-workflow-creator/` folder into the skills directory of the agent
that will use it:

| Agent host | Location |
|---|---|
| Kiro (workspace) | `<workspace>/.kiro/skills/velocity-workflow-creator/` |
| Kiro (all workspaces) | `~/.kiro/skills/velocity-workflow-creator/` |
| Claude Code (project) | `<project>/.claude/skills/velocity-workflow-creator/` |
| Claude Code (user) | `~/.claude/skills/velocity-workflow-creator/` |
| Any other agent | Anywhere readable; load `SKILL.md` as instructions and give the agent file access to the folder and a shell with Python 3.10+. |

Optional packages (the scripts work without them):

```text
python -m pip install -r <skill>/scripts/requirements.txt
```

Check the install:

```text
python <skill>/scripts/selftest.py
```

It must end with `N/N checks passed` (all checks, no failures).

## 2. Keep the catalog current

`references/catalog.json`, `docs/catalog.md` and the enum lists in
`schema/workflow-manifest.schema.json` are a snapshot of one platform version (agents,
capabilities, trust flags, models, skills, MCP tools, integration scopes, workflows).
Refresh all three together when the target platform changes:

```text
# from a Velocity backend checkout, using the backend's own interpreter
uv run python <skill>/scripts/refresh_catalog.py --source .

# or from a running server (bearer token in VELOCITY_API_TOKEN)
python <skill>/scripts/refresh_catalog.py --api https://velocity.example.com

# after editing references/catalog.json by hand: rebuild catalog.md and the schema
python <skill>/scripts/refresh_catalog.py --render

# report drift between the three files without changing anything (CI-safe)
python <skill>/scripts/refresh_catalog.py --check
```

A refresh prints the names added and removed since the last snapshot. Adding a new tool, MCP
tool or capability is covered step by step in `extending.md`.

With a backend checkout available, add the real compiler to every validation:

```text
uv run python <skill>/scripts/validate_manifest.py my.workflow.json --trust user --compiler .
uv run python <skill>/scripts/selftest.py --compiler .
```

## 3. Attach to an agent

The skill is the agent's method; the agent supplies the conversation. Any agent that can
read files, ask the user questions and run Python can use it.

**Kiro.** Skills under `.kiro/skills/` are discovered automatically and activated when a
request matches the skill's description ("create a workflow for ...", "design a Velocity
workflow manifest", "turn these requirements into a workflow JSON"). You can also ask for
it by name: "use the velocity-workflow-creator skill". Activate it again for every request
that creates or changes a workflow, even later in the same conversation: a `/` prefix in a
later message does not always load it, and a model working from memory of an earlier turn
skips the reference reads and the lookups (run 6d4ebb3b).

**Launching the scripts.** Use `python` or `py -3`; in a backend checkout `uv run python`
also works. On Windows `python3` is a Microsoft Store alias that exits 9009, so do not use
it. `<skill>` is the absolute skill folder from the activation result; from the workspace
root the relative form is `.kiro\skills\velocity-workflow-creator`, and from `backend\` it
is `..\.kiro\skills\velocity-workflow-creator`.

**Claude Code subagent.** Save as `.claude/agents/workflow-architect.md`:

```markdown
---
name: workflow-architect
description: Designs Velocity workflow manifests (workflow JSON) from requirements. Use when someone asks to create, design, convert or improve a custom Velocity workflow.
model: sonnet
tools: Read, Write, Edit, Bash, Grep, Glob, Skill
---

You are the Workflow Architect. Load the velocity-workflow-creator skill before any other
tool call and follow its numbered procedure in order, one step at a time: read
docs/problem-decomposition.md in full and write the Workflow Brief (goal as an outcome,
done-when conditions), triage the complexity and decompose the goal into verifiable parts
at the depth the tier allows, ask only functional questions (at most 5 per round, 2 rounds;
decide internal matters and record them as assumptions), read
docs/quick-reference.md and docs/prompt-writing.md in full, run scripts/catalog_lookup.py
overview and example, write the Step Plan, write every prompt to the prompt standard, write
<id>.workflow.json, then run scripts/validate_manifest.py at the target trust until it
reports VALID with no unexplained warnings. Do this again for every request, even later in
the same conversation. Never invent agent, capability, model, skill or MCP names: look them
up with scripts/catalog_lookup.py. Report the context loaded, the Workflow Brief, the
triage, the decomposition, the Step Plan, requirement coverage, each decision with its rule, the checklist answers and how to
run it.
```

**Any other agent (generic system prompt).**

```text
You design Velocity workflow manifests. The skill folder at <path> is your method:
read <path>/SKILL.md first and follow its procedure in order, again for every request.
Read <path>/docs/problem-decomposition.md in full before the Brief, and triage and
decompose the goal before you plan any step. Ask functional questions only.
Read <path>/docs/quick-reference.md and <path>/docs/prompt-writing.md in full. Look up every
name, field rule and example step with python <path>/scripts/catalog_lookup.py (overview,
example, field, search, kind, models, icons);
do not read the schema or catalog files whole, they are too large for one read. Validate
every manifest with: python <path>/scripts/validate_manifest.py <file> --trust <target> --summary
```

## 4. Operating contract

| | |
|---|---|
| Input | Requirements as text or a file path. Optional: target trust (`user`, `db`, `file`), output folder, answers to earlier questions, "no questions" mode. |
| Method | Mandatory problem decomposition before design (`problem-decomposition.md`): goal and done-when, complexity triage, breakdown by tier, self-audit. |
| Questions | Functional only (outcome, scope, business rules), at most 5 per round and 2 rounds, each with options and a recommended default. Internal choices are decided and recorded as assumptions. |
| Non-interactive callers | When the caller cannot answer (another agent, a batch job), use the defaults, write the assumptions and the unanswered functional questions (as risks) into the response and into `<id>.design.md` next to the manifest. |
| Output | `<id>.workflow.json` (schema-valid, validated at the target trust), plus a design summary in the response (Brief, triage, decomposition, Step Plan). Optional exports via `scripts/export_manifest.py`. |
| Never | Invent names, put secrets in prompts, grant privileges a step does not need, or ship a manifest the validator rejects. |
