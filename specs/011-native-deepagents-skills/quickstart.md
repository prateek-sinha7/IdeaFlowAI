# Quickstart: Native `deepagents` Skills

How to exercise and validate the feature. Every step is offline except §4, which is the one live
measurement and is **run by the user**.

---

## 1. Preconditions

- The project venv — **not** a bare `python3`. A bare interpreter resolves `deepagents` to the
  unrelated 0.7.5 install under `/opt/homebrew`:

  ```bash
  source venv/bin/activate
  python -c "import deepagents, deepagents._version as v; print(v.__version__)"   # 0.6.7
  ```
- `source ~/.zshrc` before anything that reaches a provider (the tool shell lacks `MISTRAL_API_KEY`;
  a 401 on every stage is a missing env, not a quota).
- `backend/skills/global/` present (202 dirs) and `poet` among them.
- For §4 on Ollama: `OLLAMA=true` and the `qwen3.5:4b` model pulled.

---

## 2. Setup

```bash
cd backend
python -c "import app.main"                 # import health
pytest tests/agents/ tests/unit/ -q         # baseline BEFORE any edit — record the count
```

Capture the pre-change characterization goldens (plan Phase 0) before touching `factory.py`; they
are the only oracle for R-04.

---

## 3. Exercise the feature — offline

### 3.1 No skills attached ⇒ nothing changes (R-04, acceptance 1)

```bash
pytest tests/agents/characterization -q          # 5 existing + 2 new goldens, byte-identical
pytest tests/agents/test_create_runner.py -k "no_skills" -q
```

Assert in-test that the constructed middleware list contains **no** `SkillsMiddleware` and that the
composed prompt for a `tools: []` agent still carries `_NO_TOOLS_PREAMBLE`.

### 3.2 Two skills attached ⇒ staged once, advertised to all (acceptance 2, 3)

```bash
pytest tests/unit/test_skill_staging.py -q
```

Then inspect a real sandbox:

```bash
python - <<'PY'
from app.agents.sandbox import RunSandbox
from app.agents.skill_staging import stage_skills
sb = RunSandbox("demo-user", "demo-run"); sb.ensure()
d1 = stage_skills(sb, [{"id": "poet", "name": "poet", "content": "Write a two-line rhyme."}])
d2 = stage_skills(sb, [{"id": "poet", "name": "poet", "content": "Write a two-line rhyme."}])
print(d1.sources, [s.id for s in d1.staged], d1.errors, d1.est_tokens)
print("idempotent:", d1 == d2)
print((sb.root / "skills" / "poet" / "SKILL.md").read_text())
PY
```

Expect `["/skills"]`, one staged id, no errors, `est_tokens == 530`, `idempotent: True`, and a file
whose frontmatter carries `name: poet` plus a description (synthesized, never copied — the payload
has no frontmatter).

### 3.3 Text-only agent gets read **and** write (acceptance 4)

```bash
pytest tests/agents/test_create_runner.py -k "text_only_with_skills" -q
```

Assert: `read_file`/`write_file`/`edit_file` bound · `task` and `execute` excluded ·
`_NO_TOOLS_PREAMBLE` **absent** · the same agent with no skills attached keeps today's exact tool
set and prompt.

### 3.4 Sandbox confinement (acceptance 5)

```bash
pytest tests/agents/test_create_runner.py -k "traversal" -q
```

`../escape/SKILL.md` and `/etc/passwd` must both be rejected by the backend under
`virtual_mode=True`.

### 3.5 Catalog hygiene (acceptance 7–10)

```bash
python scripts/skills_audit.py --frontmatter --identity --provenance
pytest tests/unit/test_skills_catalog_hygiene.py -q
```

Expect: 202 entries load · zero `compatible_agents`/`source`/`sourceLabel` · zero descriptions
over 200 · zero identity openings · zero provenance hits. The audit must **not** flag `cursor`
matches — every one in the catalog is a CSS or screen-reader cursor, and the script has a test
pinning that exclusion.

### 3.6 Event payload (acceptance 11)

```bash
pytest tests/agents -k "agent_skills_event" -q
```

The `agent_skills` event must carry the advertised set, `skills_load_errors`, and
`estimated_tokens`, and must be emitted **after** runner construction.

### 3.7 D-02 watch (acceptance 12)

Run the text-only `user_stories` pipeline with one skill attached and assert every agent produced a
non-empty deliverable — i.e. no agent wrote a file *instead of* streaming its answer.

---

## 4. Live validation — run this yourself (acceptance 6, D-01)

The first measurement of whether progressive disclosure actually fires. Not a regression check —
**record the numbers**, both models, into `build-summary.md`.

1. Attach `poet` to a `hello_html` run (attach it in the UI — skills are your experiment dial).
2. Frontier model: confirm `poet` is advertised to all three agents, `writer` emits a `read_file`
   against `/skills/poet/SKILL.md`, and the page carries the two-line rhyme rather than the default line.
3. Repeat with `OLLAMA=true` and `qwen3.5:4b`.
4. Record the activation rate for each. A `qwen3.5:4b` failure is a finding to act on — there is no
   fallback by design (C-03).

---

## 5. Validation scenarios (summary)

| Scenario | Expected |
|---|---|
| Run, no skills | Prompt byte-identical · no `SkillsMiddleware` · tool sets unchanged |
| Run, 2 skills | 2 staged files · every agent advertises both · ~662 tok/agent |
| Same run, second agent constructed | No re-write, no duplicate, no error |
| `tools: []` agent + skills | fs read+write bound · no anti-fabrication preamble |
| Path escape attempt | Rejected by the backend |
| Disk skill, no attached skills | Eager `=== SKILLS ===` block still present, byte-identical |
| 10 skills attached | Warning logged at >8,000 tok/agent only; run never blocked |

---

## 6. Rollback / cleanup

- **Code**: the change is confined to `factory.py`, `deep_agent_runner.py`, `engine.py`,
  `context.py`, plus the new `skill_staging.py` — revert the commit range. There is no feature flag
  by design (C-03); rollback is `git revert`, not a config toggle.
- **Catalog**: the 202-file edit is a separate commit and can be reverted independently of the
  runtime change.
- **Disk**: staged skills live inside the run sandbox and disappear with `RunSandbox.cleanup()`.
  To clear by hand: `rm -rf <RUNS_ROOT>/<user>/<run>/skills`.
- **Database**: nothing to roll back — no migration.
