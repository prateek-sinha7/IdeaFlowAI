# Integration Guide: Workflow Gate Contract Check

This guide explains how to integrate the workflow gate contract check into your CI/CD pipeline and development workflow.

## Quick Start

The check is available in two implementations:

1. **Python** (Recommended for CI): `.github/scripts/check-workflow-gate-contract.py`
   - No dependencies beyond PyYAML (included in most environments)
   - Works on Windows, macOS, and Linux
   - More robust YAML parsing with error messages

2. **Bash** (Optional): `.github/scripts/check-workflow-gate-contract.sh`
   - Requires `yq` for YAML parsing
   - Better for shell-based workflows
   - Linux/macOS focused

## Integration Options

### Option 1: GitHub Actions CI Job (RECOMMENDED)

Add this step to `.github/workflows/ci.yml`:

```yaml
- name: Validate workflow gate contract
  run: |
    python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml --verbose
```

**Benefits:**
- Runs on every CI/CD pipeline
- Prevents merging PRs that break the contract
- Clear error messages on failure
- No setup required beyond Python (default in most CI runners)

**Example CI job integration:**

```yaml
jobs:
  validate-workflow-structure:
    name: Validate Workflow Structure
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Validate deploy workflow gate contract
        run: |
          python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml --verbose
```

### Option 2: Pre-commit Hook (LOCAL DEVELOPER)

Set up a pre-commit hook to catch violations before pushing:

**1. Create or update `.git/hooks/pre-commit`:**

```bash
#!/bin/bash
# Pre-commit hook: validate workflow gate contract

set -e

if git diff --cached .github/workflows/deploy.yml > /dev/null 2>&1; then
    echo "Checking workflow gate contract..."
    if ! python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml; then
        echo ""
        echo "ERROR: Workflow gate contract violation detected."
        echo "Commit aborted. Fix the contract violation and try again."
        exit 1
    fi
    echo "Workflow gate contract validated."
fi
```

**2. Make it executable:**

```bash
chmod +x .git/hooks/pre-commit
```

**3. Test it:**

```bash
# This should pass
git add .github/workflows/deploy.yml
git commit -m "test: validate hook"
```

**Benefits:**
- Catches violations before PR creation
- No CI resources wasted on invalid PRs
- Fast local feedback loop

### Option 3: Manual Validation (DEVELOPER WORKFLOW)

Add a make target for developers to validate on demand:

**In `Makefile` (or equivalent build script):**

```makefile
.PHONY: validate-workflow
validate-workflow: ## Validate the deployment workflow gate contract
	@echo "Validating workflow gate contract..."
	@python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml --verbose

.PHONY: validate-all
validate-all: validate-workflow ## Run all validation checks
	@echo "All validation checks passed."
```

**Usage:**

```bash
make validate-workflow
```

### Option 4: Pre-push Hook

For a more aggressive check before pushing (in addition to pre-commit):

**`.git/hooks/pre-push`:**

```bash
#!/bin/bash
# Pre-push hook: final validation before pushing

set -e

echo "Running final workflow validation before push..."
python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml

echo "Workflow validation passed. Proceeding with push."
```

**Make executable:**

```bash
chmod +x .git/hooks/pre-push
```

## Testing the Integration

### Test 1: Verify the Hook is Installed

```bash
# Check pre-commit hook exists
test -x .git/hooks/pre-commit && echo "pre-commit hook installed" || echo "not installed"
```

### Test 2: Test on a Correct Workflow

```bash
# Should pass
python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml
echo $?  # Should print 0
```

### Test 3: Test on a Broken Workflow

Create a test scenario (the Python script includes examples):

```bash
# Run the test with verbose output
python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml --verbose
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'yaml'"

**Problem**: PyYAML is not installed in the Python environment

**Solution (for CI)**: PyYAML should be in the system environment by default. If not, add to CI steps:

```yaml
- name: Install dependencies
  run: pip install PyYAML
```

**Solution (local)**: Install via pip:

```bash
pip install PyYAML
# or
pip3 install PyYAML
```

### "workflow file not found"

**Problem**: Script is run from wrong directory or path is incorrect

**Solution**: Always run from the repository root:

```bash
cd /path/to/velocityai
python3 .github/scripts/check-workflow-gate-contract.py
```

### Hook doesn't run on commit

**Problem**: Hook file doesn't have execute permissions

**Solution**:

```bash
chmod +x .git/hooks/pre-commit
```

**Verify:**

```bash
ls -la .git/hooks/pre-commit
# Should show: -rwxr-xr-x (or similar with x permission)
```

## CI Integration Checklist

- [ ] Added validation step to `.github/workflows/ci.yml`
- [ ] Step runs on all PR merges
- [ ] Python 3.x available in runner (default on ubuntu-latest)
- [ ] Script uses absolute path or relative from repo root
- [ ] Verbose flag used for clear error messages
- [ ] Tested on a sample PR merge to confirm hook fires
- [ ] Pre-commit hook installed locally: `chmod +x .git/hooks/pre-commit`
- [ ] Documented in team onboarding/contributing guide

## Maintenance

### When to Update the Check

- **After significant workflow changes**: Re-run with `--verbose` to verify output
- **After architecture decisions**: Update the requirements if contracts change
- **When new jobs are added**: Verify they comply with the contract

### Keeping Documentation Current

After any workflow structure change, run:

```bash
python3 .github/scripts/check-workflow-gate-contract.py .github/workflows/deploy.yml --verbose
```

And update this file if the output changes.

## Requirements Coverage

This integration satisfies:
- **GAP-001**: Deploy quality-gate dependency bypass prevention
- **FIND-001**: Workflow structure enforcement
- **Task 1.2**: Workflow-contract assertion

## Reference

- Script documentation: [WORKFLOW-GATE-CHECK.md](./WORKFLOW-GATE-CHECK.md)
- Deployment workflow: `.github/workflows/deploy.yml`
- CI workflow: `.github/workflows/ci.yml`
