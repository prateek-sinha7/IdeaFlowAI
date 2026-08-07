---
id: TEST-1-2
type: test
status: done
summary: >-
  1.2 AWS / Bedrock (live runs)
source: .planning/TEST-REGISTER.md#1-2-aws-bedrock-live-runs
---

### 1.2 AWS / Bedrock (live runs)

- **Profile `default`** = acct **473293451041**, region **eu-central-1**, model **Haiku 4.5** (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`) — **working** (use for all live runs). Set `AWS_PROFILE`/`AWS_REGION` before launching uvicorn; restart the backend after any code change (`--reload` reloads source, but a stale long-lived process will not).
- **Profile `hexaware-srini`** = acct 731451715500 — returns `ValidationException: Operation not allowed` on every Bedrock call. **Use it as the deliberate fault-injector** for the model-error path (TS-Q / ISS-016).
