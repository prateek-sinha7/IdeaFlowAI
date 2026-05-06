# IdeaFlow AI — Production Deployment Guide

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Environment Modes](#environment-modes)
3. [AI Provider Configuration](#ai-provider-configuration)
4. [Environment Switching Guide](#environment-switching-guide)
5. [AWS Services Required](#aws-services-required)
6. [Phase-by-Phase Implementation](#phase-by-phase-implementation)
7. [Docker Setup](#docker-setup)
8. [AWS Bedrock Setup](#aws-bedrock-setup)
9. [Database Migration (PostgreSQL)](#database-migration)
10. [CI/CD Pipeline](#cicd-pipeline)
11. [Cost Estimation](#cost-estimation)

---

## Architecture Overview

```
+------------------------------------------------------------------+
|                    AWS CLOUD (Production)                          |
+------------------------------------------------------------------+
|                                                                    |
|   [Route 53] --> [CloudFront CDN] --> [S3 / Amplify]              |
|       (DNS)          (HTTPS)          (Next.js Frontend)          |
|                                                                    |
|                         |                                          |
|                         v                                          |
|   [Application Load Balancer] (WebSocket + HTTP)                  |
|                         |                                          |
|                         v                                          |
|   [ECS Fargate Cluster]                                           |
|   +------------------+  +------------------+  +----------------+  |
|   | FastAPI Task 1   |  | FastAPI Task 2   |  | Task N (auto)  |  |
|   | (Backend + WS)   |  | (Backend + WS)   |  | (auto-scale)   |  |
|   +------------------+  +------------------+  +----------------+  |
|          |                      |                     |            |
|          v                      v                     v            |
|   +------------+    +----------------+    +-------------------+   |
|   | RDS        |    | ElastiCache    |    | AWS Bedrock       |   |
|   | PostgreSQL |    | (Redis)        |    | (Claude Models)   |   |
|   +------------+    +----------------+    +-------------------+   |
|                                                                    |
|   +------------------+  +----------------+  +------------------+  |
|   | Secrets Manager  |  | CloudWatch     |  | S3 Artifacts     |  |
|   | (credentials)    |  | (logs/metrics) |  | (PPTX, JSON)     |  |
|   +------------------+  +----------------+  +------------------+  |
|                                                                    |
+------------------------------------------------------------------+
```

### Local Development Architecture

```
+------------------------------------------+
|         LOCAL MACHINE                     |
+------------------------------------------+
|                                           |
|   [Browser localhost:3000]                |
|          |                                |
|          v                                |
|   [Next.js Dev Server :3000]              |
|          |                                |
|          v                                |
|   [FastAPI + Uvicorn :8000]               |
|          |                                |
|          v                                |
|   [SQLite dev.db]  [Mock/Anthropic/Bedrock]
|                                           |
+------------------------------------------+
```

---

## Environment Modes

The application supports **3 environments** with **3 AI providers**:

### Environments

| Environment | Database | AI Provider | Use Case |
|-------------|----------|-------------|----------|
| `local` | SQLite | Mock (no API key) | Office laptop, restricted network |
| `development` | PostgreSQL (Docker) | Anthropic API key | Personal laptop, testing with real AI |
| `production` | RDS PostgreSQL | AWS Bedrock | AWS deployment, production users |

### AI Providers

| Provider | Config Value | Auth Method | When to Use |
|----------|-------------|-------------|-------------|
| `mock` | `AI_PROVIDER=mock` | None | No API key, demo/testing |
| `anthropic` | `AI_PROVIDER=anthropic` | `ANTHROPIC_API_KEY=sk-...` | Personal testing with your API key |
| `bedrock` | `AI_PROVIDER=bedrock` | AWS IAM credentials | Production on AWS |

---

## AI Provider Configuration

### Provider Decision Flow

```
                    +------------------+
                    | AI_PROVIDER env  |
                    +------------------+
                           |
              +------------+------------+
              |            |            |
              v            v            v
        +---------+  +-----------+  +---------+
        |  mock   |  | anthropic |  | bedrock |
        +---------+  +-----------+  +---------+
              |            |            |
              v            v            v
        Simulated    Direct Claude   AWS Bedrock
        responses    API (sk-...)    (IAM role)
        (no cost)    (your bill)    (AWS bill)
```

### Configuration Examples

**Mock Mode (Office Laptop — no API key needed):**
```env
# backend/.env
ENV=local
AI_PROVIDER=mock
DATABASE_URL=sqlite:///./dev.db
SECRET_KEY=dev-secret-key
```

**Anthropic Direct (Personal Laptop — your API key):**
```env
# backend/.env
ENV=development
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
ANTHROPIC_MODEL=claude-haiku-4-20250514
DATABASE_URL=postgresql://ideaflow:password@localhost:5432/ideaflow
SECRET_KEY=your-strong-secret-key
REDIS_URL=redis://localhost:6379
```

**AWS Bedrock (Production — IAM auth, no API key):**
```env
# backend/.env
ENV=production
AI_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
DATABASE_URL=postgresql://ideaflow:pass@rds-endpoint:5432/ideaflow
SECRET_KEY=production-secret-from-secrets-manager
REDIS_URL=redis://elasticache-endpoint:6379
CORS_ORIGINS=["https://ideaflow.yourdomain.com"]
```

---

## Environment Switching Guide

### Quick Switch Commands

```bash
# === OFFICE LAPTOP (Mock Mode) ===
# No setup needed — just run:
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev

# === PERSONAL LAPTOP (Anthropic API Key) ===
# 1. Set your .env:
cp env-templates/.env.development backend/.env
# 2. Edit backend/.env and add your ANTHROPIC_API_KEY
# 3. Start Docker services:
docker-compose -f docker-compose.dev.yml up -d postgres redis
# 4. Run migrations:
cd backend && alembic upgrade head
# 5. Start servers:
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev

# === PERSONAL LAPTOP (AWS Bedrock) ===
# 1. Configure AWS credentials:
aws configure sso  # or set AWS_PROFILE
# 2. Set your .env:
cp env-templates/.env.production backend/.env
# 3. Start full stack:
docker-compose up
```

### Environment File Templates

Create these in `env-templates/` directory:

```
env-templates/
├── .env.local          # Office laptop (mock)
├── .env.development    # Personal laptop (Anthropic key)
├── .env.production     # AWS production (Bedrock)
└── .env.frontend       # Frontend env vars
```

---

## AWS Services Required

### Core Services

| Service | Purpose | Tier | Monthly Cost |
|---------|---------|------|-------------|
| **ECS Fargate** | Run FastAPI containers | 0.5 vCPU, 1GB RAM x 2 tasks | ~$30-60 |
| **ECR** | Docker image registry | 1 repo | ~$1 |
| **RDS PostgreSQL** | Production database | db.t3.micro (free tier eligible) | ~$0-15 |
| **ElastiCache Redis** | Cache, rate limiting, pub/sub | cache.t3.micro | ~$15 |
| **ALB** | Load balancer (HTTP + WebSocket) | 1 ALB | ~$20 |
| **AWS Bedrock** | Claude AI model access | Pay per token | ~$5-50 (usage) |
| **S3** | Frontend static files + artifacts | Standard | ~$1-5 |
| **CloudFront** | CDN + HTTPS termination | 1 distribution | ~$5-10 |
| **Route 53** | DNS hosting | 1 hosted zone | ~$0.50 |
| **Secrets Manager** | Store credentials | 3-5 secrets | ~$2 |
| **CloudWatch** | Logs + metrics + alarms | Standard | ~$5-10 |
| **ACM** | SSL/TLS certificates | Free with CloudFront/ALB | Free |
| **IAM** | Roles and policies | N/A | Free |

### Estimated Total: **$85-190/month**

### Bedrock Token Pricing (Claude 3 Haiku)

| Metric | Cost |
|--------|------|
| Input tokens | $0.25 / 1M tokens |
| Output tokens | $1.25 / 1M tokens |
| Avg pipeline run (~12 agents) | ~$0.01-0.03 per run |
| 1000 pipeline runs/month | ~$10-30 |

---

## Phase-by-Phase Implementation

### Phase 1: Multi-Environment Config (0.5 day)

**Goal:** Switch between mock/anthropic/bedrock with a single env var.

**Files to modify:**
- `backend/app/core/config.py` — Add new settings
- `backend/app/agents/base.py` — Provider switching logic
- `backend/requirements.txt` — Add `langchain-aws`

**New config.py:**
```python
class Settings(BaseSettings):
    # Environment
    ENV: str = "local"  # local | development | production
    
    # AI Provider: mock | anthropic | bedrock
    AI_PROVIDER: str = "mock"
    
    # Anthropic Direct (when AI_PROVIDER=anthropic)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-20250514"
    
    # AWS Bedrock (when AI_PROVIDER=bedrock)
    AWS_REGION: str = "us-east-1"
    AWS_BEDROCK_MODEL_ID: str = "anthropic.claude-3-haiku-20240307-v1:0"
    
    # Database
    DATABASE_URL: str = "sqlite:///./dev.db"
    
    # Redis (optional for local)
    REDIS_URL: str = ""
    
    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24
```

**New base.py logic:**
```python
class BaseAgent:
    def __init__(self, system_prompt, model=None):
        self.system_prompt = system_prompt
        
        if settings.AI_PROVIDER == "bedrock":
            from langchain_aws import ChatBedrock
            self.llm = ChatBedrock(
                model_id=settings.AWS_BEDROCK_MODEL_ID,
                region_name=settings.AWS_REGION,
                streaming=True,
            )
        elif settings.AI_PROVIDER == "anthropic":
            if not settings.ANTHROPIC_API_KEY:
                raise AgentConfigurationError("ANTHROPIC_API_KEY required")
            from langchain_anthropic import ChatAnthropic
            self.llm = ChatAnthropic(
                model=model or settings.ANTHROPIC_MODEL,
                anthropic_api_key=settings.ANTHROPIC_API_KEY,
                streaming=True,
            )
        else:  # mock
            raise AgentConfigurationError("Mock mode — use mock pipeline")
```

---

### Phase 2: PostgreSQL + Alembic (1 day)

**Goal:** Replace SQLite with PostgreSQL, add schema migrations.

**New dependencies:**
```
alembic==1.14.0
psycopg2-binary==2.9.9
asyncpg==0.30.0
```

**Setup commands:**
```bash
# Initialize Alembic
cd backend
alembic init alembic

# Generate initial migration
alembic revision --autogenerate -m "initial schema"

# Apply migrations
alembic upgrade head
```

**Database URL formats:**
```
# SQLite (local)
sqlite:///./dev.db

# PostgreSQL (Docker local)
postgresql://ideaflow:password@localhost:5432/ideaflow

# PostgreSQL (AWS RDS)
postgresql://ideaflow:password@ideaflow-db.xxxxx.us-east-1.rds.amazonaws.com:5432/ideaflow
```

---

### Phase 3: Docker + docker-compose (1 day)

**Goal:** Containerize for consistent environments.

**Dockerfile.backend:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Dockerfile.frontend:**
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

**docker-compose.yml (full production stack):**
```yaml
version: "3.9"
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - ENV=production
      - AI_PROVIDER=bedrock
      - AWS_REGION=us-east-1
      - DATABASE_URL=postgresql://ideaflow:password@postgres:5432/ideaflow
      - REDIS_URL=redis://redis:6379
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
      - NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ideaflow
      POSTGRES_PASSWORD: password
      POSTGRES_DB: ideaflow
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ideaflow"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

**docker-compose.dev.yml (lightweight — just DB + Redis):**
```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ideaflow
      POSTGRES_PASSWORD: password
      POSTGRES_DB: ideaflow
    ports:
      - "5432:5432"
    volumes:
      - pgdata_dev:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata_dev:
```

---

### Phase 4: Rate Limiting + Input Validation (0.5 day)

**New dependency:** `slowapi==0.1.9`

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Apply to sensitive endpoints
@router.post("/api/auth/login")
@limiter.limit("5/minute")
async def login(...): ...

@router.post("/api/workflows")
@limiter.limit("10/minute")
async def create_workflow(...): ...
```

**Input validation:**
```python
class CreateWorkflowRequest(BaseModel):
    type: str
    input: str = Field(..., max_length=10000)
    title: Optional[str] = Field(None, max_length=100)
```

---

### Phase 5: Structured Logging (1 day)

**New dependency:** `structlog==24.4.0`

```python
import structlog

logger = structlog.get_logger()

# Usage
logger.info("pipeline_started", user_id=user.id, pipeline_type=type)
logger.info("agent_completed", agent_id=agent.id, duration=3.2)
logger.error("pipeline_failed", error=str(e), user_id=user.id)
```

**CloudWatch integration:**
- Logs automatically shipped via ECS task logging driver
- Create metric filters for error rates
- Set alarms for anomalies

---

### Phase 6: CI/CD Pipeline (1 day)

**.github/workflows/ci.yml:**
```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/ -v
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: cd frontend && npm ci
      - run: cd frontend && npm test
      - run: cd frontend && npm run build

  deploy:
    needs: [test-backend, test-frontend]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Build and push to ECR
        run: |
          aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY
          docker build -t ideaflow-backend ./backend
          docker tag ideaflow-backend:latest $ECR_REGISTRY/ideaflow-backend:latest
          docker push $ECR_REGISTRY/ideaflow-backend:latest
      - name: Update ECS service
        run: aws ecs update-service --cluster ideaflow --service backend --force-new-deployment
```

---

### Phase 7: Redis + Background Jobs (2 days)

**Goal:** Move pipeline execution to background workers for scalability.

```
User Request Flow:
                                                    
  Browser --> WebSocket --> FastAPI --> Redis Queue
                                          |
                                          v
                                    Celery Worker
                                          |
                                          v
                                    AWS Bedrock / Anthropic
                                          |
                                          v
                                    Redis Pub/Sub
                                          |
                                          v
                              FastAPI --> WebSocket --> Browser
```

**New dependency:** `celery[redis]==5.4.0`

---

### Phase 8: AWS Infrastructure (2 days)

**Terraform structure:**
```
infra/
├── main.tf
├── variables.tf
├── outputs.tf
├── modules/
│   ├── networking/    # VPC, subnets, security groups
│   ├── ecs/           # Fargate cluster, service, task def
│   ├── rds/           # PostgreSQL instance
│   ├── redis/         # ElastiCache cluster
│   ├── alb/           # Load balancer
│   ├── ecr/           # Container registry
│   ├── bedrock/       # IAM roles for Bedrock access
│   ├── s3/            # Static hosting + artifacts
│   ├── cloudfront/    # CDN distribution
│   └── secrets/       # Secrets Manager
```

---

## AWS Bedrock Setup

### Step 1: Enable Model Access

```bash
# In AWS Console:
# 1. Go to Amazon Bedrock > Model access
# 2. Request access to "Anthropic Claude 3 Haiku"
# 3. Wait for approval (usually instant)
```

### Step 2: Create IAM Role for ECS

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-*"
    }
  ]
}
```

### Step 3: Local Testing with Bedrock

```bash
# Configure AWS SSO on personal laptop
aws configure sso
# Profile name: ideaflow-dev
# SSO start URL: https://your-org.awsapps.com/start
# Region: us-east-1

# Set profile
export AWS_PROFILE=ideaflow-dev

# Test Bedrock access
aws bedrock-runtime invoke-model \
  --model-id anthropic.claude-3-haiku-20240307-v1:0 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":100,"messages":[{"role":"user","content":"Hello"}]}' \
  output.json
```

### Bedrock Model IDs

| Model | Bedrock Model ID |
|-------|-----------------|
| Claude 3 Haiku | `anthropic.claude-3-haiku-20240307-v1:0` |
| Claude 3.5 Sonnet | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Claude 3.5 Haiku | `anthropic.claude-3-5-haiku-20241022-v1:0` |
| Claude 3 Opus | `anthropic.claude-3-opus-20240229-v1:0` |

---

## Database Migration

### From SQLite to PostgreSQL

```bash
# 1. Start PostgreSQL
docker-compose -f docker-compose.dev.yml up -d postgres

# 2. Update .env
DATABASE_URL=postgresql://ideaflow:password@localhost:5432/ideaflow

# 3. Initialize Alembic (first time only)
cd backend
alembic init alembic
# Edit alembic/env.py to use settings.DATABASE_URL

# 4. Generate migration
alembic revision --autogenerate -m "initial schema"

# 5. Apply migration
alembic upgrade head

# 6. Verify
psql -h localhost -U ideaflow -d ideaflow -c "\dt"
```

---

## CI/CD Pipeline

```
+----------+     +---------+     +----------+     +----------+
|  Push to |---->|  Run    |---->|  Build   |---->|  Deploy  |
|  GitHub  |     |  Tests  |     |  Docker  |     |  to AWS  |
+----------+     +---------+     +----------+     +----------+
                      |                                  |
                      v                                  v
               Backend tests              ECR push + ECS update
               Frontend tests             S3/Amplify deploy
               Lint + type check          Run migrations
```

---

## Cost Estimation

### Development (Personal Laptop)

| Item | Cost |
|------|------|
| Docker (local) | Free |
| Anthropic API (testing) | ~$5-10/month |
| AWS Bedrock (testing) | ~$1-5/month |
| **Total** | **~$5-15/month** |

### Production (AWS)

| Item | Low Traffic | Medium Traffic |
|------|------------|----------------|
| ECS Fargate (2 tasks) | $30 | $60 |
| RDS PostgreSQL | $15 | $30 |
| ElastiCache Redis | $15 | $15 |
| ALB | $20 | $20 |
| Bedrock (Claude) | $10 | $50 |
| S3 + CloudFront | $5 | $15 |
| Other (Route53, CW, SM) | $10 | $15 |
| **Total** | **~$105/month** | **~$205/month** |

---

## Quick Reference Card

### Switch Environments

| I want to... | Command |
|--------------|---------|
| Run on office laptop (mock) | `cp env-templates/.env.local backend/.env` then start servers |
| Test with my Anthropic key | `cp env-templates/.env.development backend/.env` + add your key |
| Test with AWS Bedrock | `cp env-templates/.env.production backend/.env` + `aws sso login` |
| Run full Docker stack | `docker-compose up` |
| Run just DB + Redis | `docker-compose -f docker-compose.dev.yml up -d` |
| Deploy to AWS | `git push origin main` (CI/CD handles it) |

### Verify AI Provider

```bash
# Check which provider is active
curl http://localhost:8000/health
# Response includes: {"status": "healthy", "ai_provider": "mock|anthropic|bedrock"}
```

### Common Issues

| Problem | Solution |
|---------|----------|
| "Mock mode" when you want real AI | Set `AI_PROVIDER=anthropic` and add your key |
| Bedrock "Access Denied" | Run `aws sso login` or check IAM permissions |
| Database migration error | Run `alembic upgrade head` |
| CORS error | Check `CORS_ORIGINS` in .env matches your frontend URL |
| WebSocket won't connect | Ensure you're logged in (valid JWT in localStorage) |
