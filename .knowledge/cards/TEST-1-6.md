---
id: TEST-1-6
type: test
status: done
area: [sse, workflow, agents]
summary: >-
  1.6 Commands cheat-sheet (backend + FE unit gates)
source: .planning/TEST-REGISTER.md#1-6-commands-cheat-sheet-backend-fe-unit-gates
---

### 1.6 Commands cheat-sheet (backend + FE unit gates)

```bash
# ── BACKEND offline suite (full pytest HANGS offline — Postgres/Bedrock/Chromium-gated; use these) ──
cd backend
# 5 characterization goldens (byte + event parity)
python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py -q
# Targeted offline parity+gate suite (~35s) = CI backend:characterization
python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py \
  tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -q     # 44 passed, 7 skipped
# SC-001 zero-engine-edit proofs
python3.11 -m pytest tests/agents/test_sc001_nonprototype_task_loop.py tests/agents/test_sc001_fanout.py -q
# Hexagonal boundary (4 contracts kept / 0 broken)
lint-imports                                  # binary: /opt/homebrew/bin/lint-imports
# Avoid offline: anything *_live*, -m requires_api_key, tests/integration (Postgres)

# ── FRONTEND unit (vitest — NOT in CI; 102 pass / 7 known-fail baseline) ──
cd frontend && npm test
npx tsc --noEmit          # CI frontend:typecheck      npm run lint   # CI frontend:lint
```

---

## 2. Backend test suites (pytest / API / WS-contract)

These are the kernel guarantees from the IMPLEMENTATION-REGISTER. Most are **backend-only** (no UI). They are the trust floor under every UI test in §3. **All rows below are 🟢 OFFLINE-green + characterization-locked unless noted**; re-run the §1.6 suite before any release. Deep rationale per row lives in the cited `_register-parts/` file.
