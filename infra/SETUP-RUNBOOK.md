# VelocityAI — Full Setup Runbook

> **This file is superseded.** The authoritative setup and operational
> documentation now lives in two locations:
>
> - **Infrastructure (Terraform):** [`infra/terraform/RUNBOOK.md`](terraform/RUNBOOK.md)
>   — complete Quickstart, layer-by-layer apply, day-2 ops, backups, DR, CI/CD
>   triggers. Start here if you are setting up the AWS side.
>
> - **GitHub Actions CI/CD:** [`docs/GITHUB_CICD_SETUP.md`](../docs/GITHUB_CICD_SETUP.md)
>   — OIDC setup, per-env AWS config, GitHub Environments/variables/secrets,
>   deploy workflow architecture, troubleshooting, rollback.
>
> The split model described in this file's previous version (restricted IAM role
> + manager handoff) still applies conceptually, but the step-by-step commands,
> variable names, and CI/CD technology (GitLab/CodeBuild → GitHub Actions OIDC)
> are all outdated and should not be followed. Refer to the two documents above.

---

## Quick links

| Task | Document |
|---|---|
| First-time AWS + Terraform setup | [`infra/terraform/RUNBOOK.md` Quickstart](terraform/RUNBOOK.md) |
| GitHub Actions OIDC + deploy role | [`infra/terraform/RUNBOOK.md` §1a](terraform/RUNBOOK.md) |
| Per-env GitHub configuration | [`docs/GITHUB_CICD_SETUP.md` §2–§3](../docs/GITHUB_CICD_SETUP.md) |
| Trigger a deploy | [`docs/GITHUB_CICD_SETUP.md` §5](../docs/GITHUB_CICD_SETUP.md) |
| Troubleshooting deploys | [`docs/GITHUB_CICD_SETUP.md` §7](../docs/GITHUB_CICD_SETUP.md) |
| Backups & DR drill | [`infra/terraform/RUNBOOK.md` §6](terraform/RUNBOOK.md) |
| Running bootstrap-ec2.sh | [`infra/terraform/RUNBOOK.md` §5.1](terraform/RUNBOOK.md) |
