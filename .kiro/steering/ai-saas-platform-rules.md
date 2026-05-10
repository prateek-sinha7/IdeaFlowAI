---
inclusion: auto
---

# AI SaaS Platform — Task Execution Rules

## File Creation Rules

- Do NOT create any markdown (.md) files during task execution
- The only markdown files that should exist are the spec files already created in `.kiro/specs/ai-saas-platform/`
- If a task mentions creating a README.md or any other .md file, skip that specific sub-step or convert it to a different format (e.g., plain text README.txt or inline code comments)

## Command Execution Rules

- Run all commands without waiting for user confirmation
- Do not ask the user "should I run this?" — just run it
- Trust all install, build, and test commands
- If a command fails, attempt to fix the issue and re-run automatically
- Use `--yes` or equivalent flags where available to avoid interactive prompts (e.g., `npm init -y`, `pip install` without prompts)

## Project Environment Reference

- **OS**: Windows (also targeting macOS compatibility)
- **Python**: 3.12.2
- **Node.js**: v20.9.0
- **Package managers**: pip, npm
- **Version control**: git
- **Shell**: bash

### Backend (Python/FastAPI)

- **Location**: `backend/`
- **Runtime**: Python 3.12.2
- **Framework**: FastAPI + Uvicorn
- **Database**: SQLite (dev) via SQLAlchemy
- **Auth**: python-jose (JWT) + passlib with bcrypt
- **AI**: LangChain + langchain-aws (AWS Bedrock — Claude Haiku 4.5 via the EU cross-region inference profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0`). Bedrock-only — no direct Anthropic SDK / API path.
- **Env var**: `AWS_REGION` (default `eu-central-1`), `BEDROCK_MODEL_ID` (default `anthropic.claude-haiku-4-5-20251001-v1:0`), `BEDROCK_INFERENCE_PROFILE_ID` (default `eu.anthropic.claude-haiku-4-5-20251001-v1:0`), `SECRET_KEY` (required), `DATABASE_URL=sqlite:///./dev.db`. AWS auth via the boto3 default credential chain — no API key.
- **Testing**: pytest + Hypothesis
- **Key packages**: fastapi, uvicorn, sqlalchemy, pydantic[email], python-jose[cryptography], passlib[bcrypt], langchain, langchain-aws, boto3, websockets, python-dotenv, pytest, hypothesis

### Frontend (React/Next.js)

- **Location**: `frontend/`
- **Runtime**: Node.js v20.9.0
- **Framework**: Next.js with TypeScript + App Router
- **Styling**: Tailwind CSS
- **Theme**: Enterprise-dark (Navy Blue #001f3f, White #FFFFFF, Grey #AAAAAA, Black #000000)
- **Testing**: Vitest + React Testing Library + fast-check (property-based)
- **Key packages**: next, react, react-dom, tailwindcss, fast-check (dev), vitest (dev), @testing-library/react (dev), @testing-library/jest-dom (dev), jsdom (dev)
