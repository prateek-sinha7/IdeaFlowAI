# Golden Reference: OD Injection Logic

Captured from `od_runner.py` and `od_ppt_runner.py` before deletion.
Used by `test_factory_injects.py` to verify byte-for-byte identical output.

## Prototype Pipeline (`od_runner._compose_system_prompt`)

System prompt composition order (sections joined with `\n\n---\n\n`):

1. **CRITICAL OUTPUT RULES** — hardcoded block (navigation, content quality, design tokens, self-check)
2. **ACTIVE DESIGN SYSTEM: {ds_id}** — `od['ds_body']` (always included for prototype)
3. **CRAFT RULES** — `od['craft_block']` (only when `include_craft=True`, i.e. agents 2+)
4. **ACTIVE TEMPLATE SKILL: {template_id}** — `od['template_body']`
5. **Agent role prompt** — `agent.system_prompt` (old registry) or `agent.prompt_body` (new registry)

Brief Analyst (agent 1): `include_craft=False` → sections 1, 2, 4, 5
SPA Composer (agent 2): `include_craft=True` → sections 1, 2, 3, 4, 5
Craft Linter (agent 3): `include_craft=True` → sections 1, 2, 3, 4, 5
Delivery Validator (agent 4): `include_craft=True` → sections 1, 2, 3, 4, 5

## PPT Pipeline (`od_ppt_runner._compose_ppt_system_prompt`)

System prompt composition order (sections joined with `\n\n---\n\n`):

1. **CRITICAL OUTPUT RULES** — deck-specific hardcoded block
2. **ACTIVE DESIGN SYSTEM: {ds_id}** — `od['ds_body']` (ONLY when `include_design_system=True`)
   - `include_design_system = od["is_design_system_required"]`
   - `is_design_system_required = template.design_system.requires == True OR custom_ds_body provided`
3. **ACTIVE TEMPLATE SKILL: {template_id}** — `od['template_body']` (only when non-empty)
4. **Agent role prompt** — `agent.prompt_body`

Presentation Strategist (agent 1): `include_design_system=False` → sections 1, 3, 4
Deck Engineer (agent 2): `include_design_system=od["is_design_system_required"]`
Deck QA Agent (agent 3): system_prompt = `validator.prompt_body` directly (no composition)

## Key Differences Between Prototype and PPT

| Aspect | Prototype | PPT |
|---|---|---|
| Design system | Always included | Only when `design_system.requires == True` or custom |
| Craft rules | Included for agents 2+ | Not included |
| Agent 3 (validator) | Full composition | Raw `prompt_body` only |
| Registry used | OLD `app.agents.registry` (AgentDefinition with `.system_prompt`) | NEW `agents.registry` (AgentSpec with `.prompt_body`) |

## factory.py `injects` Field Mapping

The `injects` field on AgentSpec declares which injection components to include:
- `"template"` → inject SKILL.md body (section 4 above)
- `"design_system"` → inject DESIGN.md (section 2 above)
- `"craft"` → inject craft rules (section 3 above)

The critical output rules (section 1) are ALWAYS injected when any `injects` value is present.

For `od_ppt` deck agents: design_system injection is conditional on
`template.design_system.requires == True` OR custom_ds_body provided.
This must be preserved in factory.py.
