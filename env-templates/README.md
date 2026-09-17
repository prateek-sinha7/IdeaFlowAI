# Deprecated: Environment Templates

This directory contains legacy environment configuration templates. **Do not use these files.**

## Current Environment Configuration

For local development, use:
- **Backend (native):** Copy `backend/.env.example` to `backend/.env`
- **Backend (Docker):** Copy `app.env.example` to `app.env`
- **Frontend:** Copy `frontend/.env.example` to `frontend/.env.local`

For production reference, see the Terraform modules under `infra/terraform/` and the SSM secrets loader documentation in `docs/`.

## Migration Notes

The old templates in this directory pre-date the Cognito-only auth migration and the unified Docker Compose setup. They are kept for historical reference only:

- `.env.development` — superseded by `backend/.env.example`
- `.env.frontend` — superseded by `frontend/.env.example`
- `.env.production.example` — production configuration is managed via Terraform/SSM, not env files
