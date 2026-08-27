# GitHub Rulesets & Environments — Setup Guide

This document walks you through setting up GitHub branch protection rulesets
and deployment environments for the velocityai repository. These are created
as code (JSON files in `.github/rulesets/` and `.github/environments/`) and
applied via the GitHub CLI.

## Prerequisites

- **GitHub Admin access** to the repository
- **GitHub CLI (`gh`)** installed and authenticated:
  ```bash
  gh auth login
  gh auth status
  ```
- **`jq`** installed (for JSON parsing in the setup script)
- The repository's CI pipeline must have already created the `ci-required`
  aggregator status check (Phase 1 prerequisite)

## Quick Start

```bash
# Navigate to the repository root
cd velocityai

# Dry run: see what will be applied without making changes
./.github/scripts/setup-rulesets.sh --repo Hexaware-HnI/velocityai --dry-run

# Apply the rulesets and environments
./.github/scripts/setup-rulesets.sh --repo Hexaware-HnI/velocityai
```

If successful, you'll see:
```
Step 1: Validating JSON syntax...
  ✓ main.json
  ✓ dev-staging.json
  ✓ tags.json
  ✓ prod.json
  ✓ staging.json
  ✓ dev.json

Step 2: Verifying gh CLI and repository access...
  ✓ Repository access verified

Step 3: Applying branch protection rulesets...
  Applying ruleset: main
  ✓ Ruleset created: main
  Applying ruleset: dev-staging
  ✓ Ruleset created: dev-staging
  Applying ruleset: tags
  ✓ Ruleset created: tags

Step 4: Applying environment configurations...
  Configuring environment: prod
  ✓ Environment configured: prod
  Configuring environment: staging
  ✓ Environment configured: staging
  Configuring environment: dev
  ✓ Environment configured: dev

Step 5: Configuring repository merge settings...
  ✓ Merge settings configured (squash-only, delete-on-merge, required signatures)

Phase 2 Bootstrap Complete
```

## What Gets Applied

### Branch Protection Rulesets

**`main` ruleset** (`main.json`)
- Target: `refs/heads/main`
- Protections:
  - Deletion blocked
  - Force push blocked (non-fast-forward)
  - Pull requests required with:
    - **2 approvals** (strict for production)
    - Code owner review required
    - Self-approval blocked (require_last_push_approval)
    - All threads must be resolved
    - Stale reviews dismissed on push
  - Required status checks (strict mode):
    - `ci-required` (Phase 1 aggregator)
    - `CodeQL`
    - `SonarCloud Code Analysis`
  - Commit signatures required (GPG)
  - **No bypass actors** (not even admins)

**`dev-staging` ruleset** (`dev-staging.json`)
- Target: `refs/heads/dev`, `refs/heads/staging`
- Protections:
  - Deletion blocked
  - Force push blocked
  - Pull requests required with:
    - **1 approval** (lighter than main)
    - Code owner review optional
    - All threads must be resolved
  - Required status checks (strict):
    - `ci-required` only
  - No bypass actors

**`tags` ruleset** (`tags.json`)
- Target: `refs/tags/v*` (release tags)
- Protections:
  - Deletion blocked
  - Non-fast-forward blocked
  - Prevents accidental/malicious retagging of releases

### Deployment Environments

**`prod` environment** (`prod.json`)
- Deployment branch policy: protected tags only
- Reviewers: `release-managers` team (2 approvals)
- **Admins cannot bypass** (`can_admins_bypass: false`)
- No wait timer
- Used by: `deploy.yml` production releases

**`staging` environment** (`staging.json`)
- Deployment branch policy: `refs/heads/staging` branch only
- Reviewers: `engineering` team (1 approval)
- Admins can bypass (emergency expedite)

**`dev` environment** (`dev.json`)
- Deployment branch policy: `refs/heads/dev` branch only
- Reviewers: none (CI gates the branch; no approval needed)
- Admins can bypass

### Repository Settings

- `delete_branch_on_merge: true` — auto-clean PR branches after merge
- `allow_squash_merge: true` — squash strategy enabled
- `allow_merge_commit: false` — prohibit traditional merge commits
- `allow_rebase_merge: false` — prohibit rebase merges
- `allow_auto_merge: true` — allow auto-merge on approval
- `web_commit_signoff_required: true` — require committer sign-off

## Verification

### 1. Check Rulesets in GitHub UI

1. Go to **Settings > Rules** (or **Settings > Branches** for legacy view)
2. Verify three rulesets exist:
   - `main-production-protection`
   - `dev-staging-protection`
   - `release-tag-protection`
3. Click each to verify conditions and enforcement status

### 2. Check Environments

1. Go to **Settings > Environments**
2. Verify three environments exist:
   - `prod` — with release-managers reviewers, `can_admins_bypass: false`
   - `staging` — with engineering reviewers
   - `dev` — with no reviewers

### 3. Test Main Branch Protection

```bash
# Create a test PR to main
git checkout -b test/ruleset-verification
echo "test" > TEST.md
git add TEST.md
git commit -m "test: verify main ruleset"
git push origin test/ruleset-verification

# Open a PR in the GitHub UI to main
# Verify you cannot merge without:
#   - 2 approvals
#   - All checks passing (ci-required, CodeQL, SonarCloud)
#   - All threads resolved
#   - Your own approval does not count as one of the two
```

### 4. Test Dev/Staging Protection

```bash
# Test that dev and staging branches have their own rules
git checkout staging
git pull origin staging

# Verify CI must pass before you can push to staging/dev
# (attempt to push without CI passing should fail at ruleset check)
```

### 5. Test Tag Protection

```bash
# Only members of release-managers team can create tags matching v*
# Attempt from a non-release-manager account should fail:
git tag v0.0.0-test
git push origin v0.0.0-test
# Expected: "refused by GitHub: tag creation rejected by rules"
```

## Troubleshooting

### "Cannot access repository"

```bash
gh auth status
# If not authenticated, run:
gh auth login
# Select GitHub.com, paste your personal access token or use device login
```

### "Invalid JSON" error

Check that all JSON files are valid:
```bash
jq '.' .github/rulesets/*.json
jq '.' .github/environments/*.json
```

### "Ruleset creation failed"

Some possible causes:
- The `ci-required` status check doesn't exist yet (Phase 1 not complete)
- Account lacks admin permissions
- The ruleset name conflicts with an existing ruleset

Check with:
```bash
gh api repos/Hexaware-HnI/velocityai/rulesets
```

### Rulesets not appearing in UI

GitHub may cache settings. Try:
1. Refresh the page (Cmd+Shift+R or Ctrl+Shift+R)
2. Wait 5–10 seconds and refresh again
3. Verify via CLI:
   ```bash
   gh api repos/Hexaware-HnI/velocityai/rulesets
   ```

## Manual Application (Without Script)

If you prefer to apply rulesets manually:

```bash
# Apply main ruleset
gh api -X POST repos/Hexaware-HnI/velocityai/rulesets \
  --input .github/rulesets/main.json

# Apply dev/staging ruleset
gh api -X POST repos/Hexaware-HnI/velocityai/rulesets \
  --input .github/rulesets/dev-staging.json

# Apply tag ruleset
gh api -X POST repos/Hexaware-HnI/velocityai/rulesets \
  --input .github/rulesets/tags.json

# Configure prod environment
gh api -X PUT repos/Hexaware-HnI/velocityai/environments/prod \
  -F can_admins_bypass=false \
  -F 'deployment_branch_policy[protected_tags]=true'

# Configure staging environment
gh api -X PUT repos/Hexaware-HnI/velocityai/environments/staging \
  -f 'deployment_branch_policy[protected_branches]=true'

# Configure dev environment
gh api -X PUT repos/Hexaware-HnI/velocityai/environments/dev \
  -f 'deployment_branch_policy[protected_branches]=true'

# Set merge settings
gh api -X PATCH repos/Hexaware-HnI/velocityai \
  -F delete_branch_on_merge=true \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F allow_auto_merge=true \
  -F web_commit_signoff_required=true
```

## Updating Rulesets

To update a ruleset after creation, you have two options:

### Option 1: Via Script (Recommended)

The setup script checks for existing rulesets. Edit the JSON file and re-run:

```bash
# Edit .github/rulesets/main.json
nano .github/rulesets/main.json

# Re-apply (you may need to delete the old ruleset first if the API doesn't
# allow in-place updates; check the error message)
./.github/scripts/setup-rulesets.sh --repo Hexaware-HnI/velocityai
```

### Option 2: Via GitHub CLI

```bash
# Find the ruleset ID
gh api repos/Hexaware-HnI/velocityai/rulesets -q '.[] | "\(.id) \(.name)"'

# Update by ID (example: ruleset ID = 12345)
gh api -X PUT repos/Hexaware-HnI/velocityai/rulesets/12345 \
  --input .github/rulesets/main.json
```

### Option 3: Via GitHub UI

1. Settings > Rules
2. Click the ruleset to edit
3. Update conditions, rules, or bypass actors
4. Save

After any update via UI or CLI, commit the corresponding JSON file to keep
the code in sync.

## Maintenance Checklist

- [ ] Rulesets applied and verified in GitHub UI
- [ ] All three environments created and reviewers assigned
- [ ] Merge settings configured (squash-only, delete-on-merge)
- [ ] Test PR to `main` verifies 2-approval gate
- [ ] Test push to `staging` verifies CI gate
- [ ] Tag protection verified (v* tags can't be created by non-release-managers)
- [ ] Team members notified of new approval requirements
- [ ] Documentation updated with team-specific reviewer groups

## Next Steps

- **Phase 3**: Automated branch protection + rule updates via GitHub API in CI
- **Phase 4**: Enforcement of commit signatures across all branches
- **Phase 5+**: Advanced security gates (SBOM, cosign verification, supply chain)

