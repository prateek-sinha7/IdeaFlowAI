# `ci/` — CI/CD scanner configuration

Configuration for the security/quality scanners the pipeline runs. These files
were moved here from the repo root to stop the root from accumulating one
dotfile per tool.

| File | Tool | Consumed by | Passed as |
|---|---|---|---|
| `gitleaks.toml` | gitleaks | `ci.yml` (`fast-checks`, `security-scan-secrets`) | `--config ci/gitleaks.toml` |
| `gitleaksignore` | gitleaks | same | `-i ci/gitleaksignore` |
| `checkov.yaml` | checkov | `ci.yml` (`security-scan-iac`) | `--config-file ci/checkov.yaml` |
| `trivyignore` | trivy `config` | `ci.yml` (`security-scan-iac`) | `--ignorefile ci/trivyignore` |
| `trivyignore.images` | *(retired, unconsumed)* | — | Image CVE suppression was removed (Task 3.18, bugfix 2.8): every resolved HIGH/CRITICAL image finding now blocks regardless of fix availability. See the file's own header. |

## Every file here is referenced by an explicit flag

None of these are auto-discovered any more. Both gitleaks files in particular
are only found at the `--source` root by default (`.gitleaks.toml` /
`.gitleaksignore`), so moving them into `ci/` makes `--config` and `-i`
**mandatory**. If you drop either flag, gitleaks silently falls back to its
built-in defaults: the scan still runs and still exits 0 on a clean tree, so
the breakage looks like "CI is green" rather than an error. Keep the flags.

## What deliberately did NOT move

These stay where they are because the tool that reads them hardcodes the
location — moving them silently disables the tool rather than erroring:

| Path | Why it can't move |
|---|---|
| `.github/workflows/*.yml` | GitHub Actions only executes workflows from this exact directory. |
| `.github/actions/*` | Referenced as `uses: ./.github/actions/<name>`; local actions resolve from the repo root. |
| `.github/CODEOWNERS`, `.github/dependabot.yml` | GitHub only reads these from `.github/` (or the root / `docs/`). |
| `.pre-commit-config.yaml` | `pre-commit` requires it at the repo root. |
| `.gitignore`, `.gitattributes` | git only reads these per-directory from the root. |
| `infra/terraform/.tflint.hcl` | Colocated with the Terraform it lints; passed via `TFLINT_CONFIG_FILE`. |
| `backend/pyproject.toml` | ruff/pytest/coverage config; must sit at the Python project root. |
| `frontend/package.json`, `eslint.config.*` | npm/eslint resolve from the package root. |

## Regenerating gitleaks fingerprints

`ci/gitleaksignore` suppresses individually-triaged historical findings by
exact fingerprint. Fingerprints are position-sensitive
(`commit:file:rule-id:start-line`) — never hand-write one. Run the same
command CI runs and copy the `Fingerprint:` line verbatim:

```bash
gitleaks detect --redact --no-banner -v \
  --config ci/gitleaks.toml -i ci/gitleaksignore --source .
```

Triage before suppressing: confirm a finding is a false positive, or that a
real credential has been rotated/expired, and record which in the comment
above its entry. Do not add an entry to make CI green.
