---
id: TEST-1-1
type: test
status: done
summary: >-
  1.1 Run the stack
source: .planning/TEST-REGISTER.md#1-1-run-the-stack
---

### 1.1 Run the stack

```bash
# BACKEND — python3.11, NO venv, port 8000, --reload
cd backend
RUNS_ROOT=/tmp/flowin-runs AWS_PROFILE=default AWS_REGION=eu-central-1 \
  python3.11 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
#   API   http://localhost:8000      WS  ws://localhost:8000/ws/chat      health GET /health
#   one-time dep if missing:  python3.11 -m pip install --user python-frontmatter
#   DB init (sqlite dev):     python3.11 backend/init_db.py   (alembic upgrade head)

# FRONTEND — next dev, port 3000
cd frontend && npm run dev
#   env: NEXT_PUBLIC_API_URL=http://localhost:8000  NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat
```
