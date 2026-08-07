# Sources and Adaptation Notes

## Upstream inspiration

This workspace skill is an original, Flowin-specific synthesis informed by the MIT-licensed [QA Skills for AI Agents](https://github.com/petrkindlmann/qa-skills) collection by Petr Kindlmann.

Representative upstream references consulted:

- [Collection overview and skill catalogue](https://github.com/petrkindlmann/qa-skills/blob/main/README.md)
- [QA routing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/qa-do/SKILL.md)
- [Test strategy](https://github.com/petrkindlmann/qa-skills/blob/main/skills/test-strategy/SKILL.md)
- [Test planning](https://github.com/petrkindlmann/qa-skills/blob/main/skills/test-planning/SKILL.md)
- [Risk-based testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/risk-based-testing/SKILL.md)
- [Unit testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/unit-testing/SKILL.md)
- [API testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/api-testing/SKILL.md)
- [Playwright automation](https://github.com/petrkindlmann/qa-skills/blob/main/skills/playwright-automation/SKILL.md)
- [Accessibility testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/accessibility-testing/SKILL.md)
- [Security testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/security-testing/SKILL.md)
- [Performance testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/performance-testing/SKILL.md)
- [Test reliability](https://github.com/petrkindlmann/qa-skills/blob/main/skills/test-reliability/SKILL.md)
- [Exploratory testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/exploratory-testing/SKILL.md)
- [AI-system testing](https://github.com/petrkindlmann/qa-skills/blob/main/skills/ai-system-testing/SKILL.md)
- [Release readiness](https://github.com/petrkindlmann/qa-skills/blob/main/skills/release-readiness/SKILL.md)
- [Upstream MIT license](https://github.com/petrkindlmann/qa-skills/blob/main/LICENSE)

Content was rephrased for compliance with licensing restrictions. No upstream scripts or long verbatim passages were copied. The workflow was consolidated and materially adapted to this repository's stack, safety rules, evidence conventions, and historical `/velocity-ai-test` register contract.

## Local sources of truth

The generated skill defers to these workspace files when they change:

- `.kiro/steering/localsetup.md` — PowerShell, working-directory, package-manager, PostgreSQL, and no-watch/no-server rules.
- `.kiro/steering/backend-coding-guardrails.md` — backend architecture, pytest/async/API/property/AI test practices, and validation gates.
- `.kiro/steering/frontend-coding-guardrails.md` — React/Next.js behavior testing, accessibility, Vitest/RTL, Playwright, lint/build, and security expectations.
- `.kiro/steering/terraform.md` — Terraform security, state, validation, scanning, and secrets requirements.
- `.github/workflows/ci.yml` — current blocking CI jobs and warn-only audit status.
- `.planning/FIX-TEST-REGISTER.md` — TEST-NNN traceability and detailed evidence format.
- `.planning/FIX-REGISTER.md` — FIX-NNN root-cause and changed-file authority.
- `.planning/CUSTOM-WORKFLOW-QA-TEST-SHEET.md` and campaign reports — existing PASS/FAIL/BY DESIGN/NOT VERIFIABLE and live-evidence patterns.

When an upstream recommendation conflicts with these local authorities, the local workspace rule wins.
