# Adding new tools and capabilities

When the platform gets a new tool set, MCP server or tool, integration scope, validator,
gate, hook, strategy, model or agent, the skill needs three things before an agent will
use it: the name is in the catalog, the schema accepts it, and the docs say when to pick it.
The scripts do the first two. You write the third.

## 1. What each file holds

| File | Holds | Updated by |
|---|---|---|
| `references/catalog.json` | Every name a manifest may use, with trust flags, descriptions, trust caps, models, MCP tools, integration scopes. The validator reads it. | `refresh_catalog.py --source` / `--api`, or by hand |
| `docs/catalog.md` | The same data as tables. The agent reads it. | `refresh_catalog.py` (every mode), never by hand |
| `schema/workflow-manifest.schema.json` | Enum lists for capability names, MCP tools, integration scopes and effort levels, plus the counts and "User trust may not use" sentences in `$comment` text. | `refresh_catalog.py` (every mode except `--check`), via `schema_sync.py` |
| `scripts/catalog_lookup.py` | Nothing of its own: it answers from `references/catalog.json` and the schema at run time, so a refresh reaches it at once. | nothing to do |
| `docs/field-guide.md`, `docs/requirements-analysis.md`, `docs/patterns.md`, `docs/prompt-writing.md` | When to choose the new name and how to configure it. | You |
| `docs/quick-reference.md` | The short form an agent reads in full: recommended model ids, icon names, user-trust limits. | You (`selftest.py` fails when a model id or icon it names is gone) |

A name the agent has never been told about is valid but never chosen. A name that is not in
the catalog is rejected by the validator, even if the docs mention it. Do both.

## 2. Finish the capability on the platform first

| New thing | Manifest field | Platform work |
|---|---|---|
| Tool set | `tools.tool_sets` | `@register("tool", "x", description=...)` imported by `discover()`, **and** add `"x"` to the `tool_sets` of every cap in `permission_caps.py` that may use it. A set missing from a cap is dropped at that trust level. |
| MCP server / tool | `tools.mcp` (`server.tool`) | `@register("mcp_server", ...)` plus a `CATALOG` entry (`exposed_tools`, `powerful`, `scope`) |
| Integration scope | `tools.integrations` | A provider in `PROVIDERS` / `SCOPE_TO_SERVER` in `integration_providers/providers.py` |
| Validator, gate, hook, strategy, task parser, compaction, post-step, deliverable, context or input provider | the matching step or top-level field | `@register("<kind>", "name", user_allowed=..., description=...)` and the module listed in `discover()` |
| Model | `model.model` | An entry in `model_catalog.py` |
| Agent | `agent` | A folder `agents/prompts/<id>/AGENT.md` |
| Step skill | `skills` | A folder `skills/global/<id>/SKILL.md` |

Write a real `description=` on every `@register`. It becomes the text the agent reads in
`catalog.md`, and `refresh_catalog.py` warns about a capability that has none.

## 3. Refresh the skill

**With a backend checkout** (preferred; reads the real registry, trust caps, MCP catalog and
provider table):

```text
cd <backend>
uv run python <skill>/scripts/refresh_catalog.py --source .
```

**From a running server**: `python <skill>/scripts/refresh_catalog.py --api https://host --token ...`.
The API does not expose trust caps, MCP tool lists or integration scopes, so those are kept from
the previous snapshot. A new tool set or MCP tool will look unavailable until you refresh from
source or edit the JSON (section 4).

The script then:
1. rewrites `references/catalog.json` and `docs/catalog.md`;
2. syncs the schema: appends new names to the enum lists, drops removed ones, refreshes the
   counts and trust sentences in `$comment` text (`--no-schema` skips this);
3. prints what changed against the previous snapshot, for example:

```text
Changes since the previous snapshot:
  + tool: pdf_forms
  + trust cap 'trusted' tool_sets: pdf_forms
  + mcp tools: wiki.get_page
  + integration scopes: wiki_read
  -> describe new names in docs/field-guide.md and docs/requirements-analysis.md (docs/extending.md)
```

Use that list as your to-do list for section 5. Integration scopes come from the provider
table, so a scope whose server is missing from the MCP catalog, or whose scope differs from
its server's own scope, is listed with a warning instead of being lost.

Retained names keep their position in the schema's lists and new names are appended in
alphabetical order, so reviews show only the names that changed.

## 4. No backend checkout, or a tool that is not released yet

Edit `references/catalog.json` by hand, then rebuild the other two files:

```text
python <skill>/scripts/refresh_catalog.py --render
```

`--render` checks the JSON first (required keys, shapes, missing descriptions, tool sets that
no trust cap lists, scopes pointing at unknown servers), re-renders `docs/catalog.md`,
syncs the schema, and does not touch the JSON itself. For a new tool set add:

```json
"capabilities": { "tool": { "pdf_forms": {
  "user_allowed": false, "saved_workflow_allowed": false, "bound": true,
  "description": "Fill and read PDF form fields: read_form / fill_form.",
  "process": "", "reads": [".uploads/"], "writes": ["forms/"], "config_schema": {} } } }
```

and add `"pdf_forms"` to `trust.caps.<cap>.tool_sets` for each cap that may use it
(`trusted`, `saved`, `untrusted`). For an MCP tool add its name to
`mcp_servers.<server>.tools`; for a scope add `integration_scopes.<scope>` with
`{"provider", "server", "powerful", "user_allowed"}`.

Only add what the target platform really has. A name the platform does not know passes
validation here and fails at launch.

## 5. Teach the agent when to use it

The catalog makes a name valid. These edits make the agent choose it:

1. `docs/requirements-analysis.md` §2: add a row to the signals table, for example
   "fill PDF forms" -> `tools.tool_sets: ["pdf_forms"]` on the step that fills them.
2. `docs/field-guide.md`: add the grant to the Tools table (when to grant it, which trust
   levels keep it) or the capability to the relevant field row.
3. `docs/prompt-writing.md`: if the step's prompt must call the tool a particular way,
   add a short template for that step role.
4. `docs/patterns.md`: add a pattern when the tool changes how a workflow is shaped. Validate
   the snippet in a manifest (below). `examples/` holds the platform's shipped workflows; to
   refresh one, convert its `workflow.yaml` again (`yaml.safe_load` then `json.dump`, 2-space
   indent) and update `EXAMPLE_ALLOWED_WARNINGS` in `scripts/selftest.py` if a finding changes.
5. `docs/quick-reference.md`: add a row when the name is something most workflows need (a new
   default model, an icon, a deliverable), and a line under "Traps the validator cannot see"
   if the tool has a trap (a required gate, a trust restriction, a file it reads). Keep that
   file short enough for one read (about 15 KB).
6. `scripts/validate_manifest.py`: when a mistake with the new name compiles but misbehaves at
   run time, add a lint and a known-bad case in `scripts/selftest.py`.

## 6. Verify

```text
python <skill>/scripts/refresh_catalog.py --check      # catalog.json, catalog.md and schema agree
python <skill>/scripts/selftest.py                     # all checks pass
python <skill>/scripts/validate_manifest.py my.json --trust user --summary
python <skill>/scripts/validate_manifest.py my.json --trust db
```

In a backend checkout add `--compiler .` to the last two so the platform's own compiler
confirms it. `--check` exits 1 when anything is out of date, so it works as a CI gate.
If you keep a copy of the skill in other workspaces, copy the updated folder again.

## 7. What is generated and what is not

| Generated from the catalog | Hand-written (review after a refresh) |
|---|---|
| Enum lists: context and input providers, deliverable strategies, tool sets, MCP tools, integration scopes, task parsers, strategies, mechanical kinds, gates, validators, hooks, compaction, post-step, `on_conflict`, effort levels | Field `description` text, `examples`, and the `if/then` rules in the schema |
| "Registry kind ... (N names)" counts and "User trust may not use ..." sentences in `$comment` | The rest of each `$comment`, including the list of kinds a manifest cannot name |
| `docs/catalog.md` (including the icon list, from `CATALOG_ICONS` in `validate_manifest.py`) | Everything else under `docs/`, and `examples/` |

An enum whose catalog list is empty is left unchanged, with a warning, so a failed refresh
cannot leave the schema rejecting every value.
