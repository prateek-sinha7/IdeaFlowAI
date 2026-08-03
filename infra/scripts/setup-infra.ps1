#Requires -Version 5.1
<#
.SYNOPSIS
    One-time-variable setup script for the VelocityAI Terraform layers.

.DESCRIPTION
    Edit the CONFIGURATION block below once, then run this script from
    anywhere (it locates the repo root relative to its own path). It runs,
    in order:

        1. bootstrap   (state backend + GitHub OIDC roles)     - once per account
        2. shared      (ECR repositories)                      - once per account
        3. foundation  (VPC/KMS/SSM/backups) for each environment
        4. app         (EC2 host/DNS/monitoring)  for each environment

    Each layer runs: init -> validate -> plan -> (pause for confirmation) -> apply,
    matching the fmt/validate/plan/scan/approve/apply order required for this
    workspace's Terraform changes. Nothing is applied without either an
    explicit "yes" at the prompt, or -AutoApprove.

.PARAMETER AutoApprove
    Skip the interactive "apply now?" prompt for every layer. Use only in a
    controlled, reviewed pipeline context - never as a default habit for
    production.

.PARAMETER PlanOnly
    Run init + validate + plan for every layer and stop. Never applies
    anything. Useful for a dry run before the first real apply.

.PARAMETER Environments
    Subset of dev/stage/prod to provision the foundation+app layers for.
    Defaults to all three, applied in that order (dev validated first).

.PARAMETER SkipBootstrap
    Skip the bootstrap layer (use on repeat runs once the account is bootstrapped).

.PARAMETER SkipShared
    Skip the shared (ECR) layer (use on repeat runs once ECR exists).

.PARAMETER RunSecurityScans
    If tflint/checkov/trivy/gitleaks are installed locally, run them against
    infra/terraform before any apply, per the workspace Terraform security
    guardrails. Missing tools are skipped with a warning, not a hard failure.

.EXAMPLE
    ./infra/scripts/setup-infra.ps1 -PlanOnly
    Dry run: shows what would change in every layer, applies nothing.

.EXAMPLE
    ./infra/scripts/setup-infra.ps1 -Environments dev
    Bootstrap + shared + only the dev foundation/app layers, with a plan
    review + confirmation prompt before each apply.

.NOTES
    - This provisions real AWS resources (S3, DynamoDB, IAM, KMS, VPC, EC2,
      backups, CloudWatch, SNS...) and will incur AWS cost. Review every
      `plan` before typing "yes".
    - No secrets are hardcoded here. app_secret_key / db_password /
      langsmith_api_key are left unset so the Terraform modules auto-generate
      them; override only via TF_VAR_* environment variables set OUTSIDE this
      file, never by editing this script.
    - bootstrap.tfvars is (re)generated from the CONFIGURATION block below so
      there is exactly one place to edit. It is already git-ignored
      (infra/terraform/**/*.tfvars) - do not remove that ignore rule.
    - foundation/app *.tfvars (dev.tfvars, stage.tfvars, prod.tfvars) are the
      committed, non-secret, per-environment files already in the repo. This
      script reads them via -var-file and does not modify them.
#>

[CmdletBinding()]
param(
    [switch]$AutoApprove,
    [switch]$PlanOnly,
    [ValidateSet('dev', 'stage', 'prod')]
    [string[]]$Environments = @('dev', 'stage', 'prod'),
    [switch]$SkipBootstrap,
    [switch]$SkipShared,
    [switch]$RunSecurityScans
)

$ErrorActionPreference = 'Stop'

# =============================================================================
# CONFIGURATION - edit these once, then just run the script.
# =============================================================================

# --- Account / region --------------------------------------------------------
# Leave $ExpectedAccountId empty to auto-adopt whatever account your AWS CLI
# session is currently authenticated to. Set it to a 12-digit account id to
# make every layer's account_guard hard-fail on any mismatch (recommended for
# shared/multi-account setups).
$ExpectedAccountId = ""
$AwsRegion         = "eu-central-1"

# --- Terraform remote state backend (created by the bootstrap layer) --------
$StateBucketName = "velocityai-tfstate"
$LockTableName   = "velocityai-tfstate-locks"

# --- Tags (Cost Explorer / Billing) ------------------------------------------
$Owner      = "velocityai-platform-team@hexaware.com"
$CostCenter = "velocityai"

# --- GitHub Actions OIDC (bootstrap/github_oidc.tf) -------------------------
$CreateGithubOidc  = $true
$GithubOrgRepo     = "Hexaware-HnI/velocityai"   # EXACT "<owner>/<repo>", no wildcards
# Optional IAM permissions boundary applied to every GitHub-assumable role.
# Recommended in a shared AWS account; leave empty if you don't have one yet.
$DeployBoundaryArn = ""

# --- Per-environment app-layer required input --------------------------------
# alert_email has NO module default (validated as a real email) - fill these
# in before running, or the app layer will fail plan/apply for that env.
$AlertEmails = @{
    dev   = "REPLACE_ME_dev@example.com"
    stage = "REPLACE_ME_stage@example.com"
    prod  = "REPLACE_ME_prod@example.com"
}

# =============================================================================
# Paths - resolved relative to this script, not hardcoded.
# =============================================================================
$RepoRoot      = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$TerraformRoot = Join-Path $RepoRoot "infra\terraform"
$BootstrapDir  = Join-Path $TerraformRoot "bootstrap"
$SharedDir     = Join-Path $TerraformRoot "shared"
$FoundationDir = Join-Path $TerraformRoot "foundation"
$AppDir        = Join-Path $TerraformRoot "app"

# =============================================================================
# Helpers
# =============================================================================

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Confirm-Apply {
    param([string]$Layer)
    if ($AutoApprove) { return $true }
    $resp = Read-Host "Apply '$Layer' now? Review the plan above. Type 'yes' to apply, anything else to skip"
    return $resp -eq 'yes'
}

function Invoke-Terraform {
    param(
        [Parameter(Mandatory)][string]$WorkDir,
        [Parameter(Mandatory)][string[]]$Arguments
    )
    Write-Host "  > terraform $($Arguments -join ' ')" -ForegroundColor DarkGray
    & terraform "-chdir=$WorkDir" @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "terraform $($Arguments[0]) failed in '$WorkDir' (exit $LASTEXITCODE)."
    }
}

function Test-Prerequisites {
    Write-Section "Checking prerequisites"

    foreach ($cmd in 'terraform', 'aws') {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
            throw "'$cmd' is not installed or not on PATH."
        }
    }
    & terraform version | Out-Host
    & aws --version | Out-Host

    $identityJson = aws sts get-caller-identity --output json 2>$null
    if (-not $identityJson) {
        throw "aws sts get-caller-identity failed - check your AWS credentials/session (SSO login, env vars, or profile)."
    }
    return ($identityJson | ConvertFrom-Json)
}

function Invoke-OptionalScan {
    param([string]$Tool, [string[]]$Arguments, [string]$WorkDir)
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) {
        Write-Host "  [skip] $Tool not found on PATH." -ForegroundColor Yellow
        return
    }
    Write-Host "  > $Tool $($Arguments -join ' ')" -ForegroundColor DarkGray
    Push-Location $WorkDir
    try {
        & $Tool @Arguments
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [warn] $Tool reported findings (exit $LASTEXITCODE). Review before applying." -ForegroundColor Yellow
        }
    } finally {
        Pop-Location
    }
}

function Invoke-SecurityScans {
    if (-not $RunSecurityScans) { return }
    Write-Section "Security scans (best-effort, non-blocking)"
    Invoke-OptionalScan -Tool 'tflint' -Arguments @('--recursive') -WorkDir $TerraformRoot
    Invoke-OptionalScan -Tool 'checkov' -Arguments @('-d', '.') -WorkDir $TerraformRoot
    Invoke-OptionalScan -Tool 'trivy' -Arguments @('config', '.') -WorkDir $TerraformRoot
    Invoke-OptionalScan -Tool 'gitleaks' -Arguments @('detect', '--source', '.', '--no-git') -WorkDir $TerraformRoot
}

function New-BootstrapTfvars {
    $path = Join-Path $BootstrapDir "bootstrap.tfvars"
    if (Test-Path $path) {
        $backup = "$path.bak"
        Copy-Item $path $backup -Force
        Write-Host "  Existing bootstrap.tfvars backed up to $backup" -ForegroundColor DarkGray
    }

    $lines = @(
        "# Generated by infra/scripts/setup-infra.ps1 - edit the CONFIGURATION block",
        "# in that script, not this file directly; it is regenerated on every run.",
        "",
        "aws_region        = `"$AwsRegion`"",
        "state_bucket_name = `"$StateBucketName`"",
        "lock_table_name   = `"$LockTableName`"",
        "",
        "owner       = `"$Owner`"",
        "cost_center = `"$CostCenter`"",
        "",
        "create_github_oidc = $($CreateGithubOidc.ToString().ToLower())",
        "github_org_repo    = `"$GithubOrgRepo`""
    )
    if ($DeployBoundaryArn) {
        $lines += "deploy_permissions_boundary_arn = `"$DeployBoundaryArn`""
    }

    Set-Content -Path $path -Value $lines -Encoding UTF8
    Write-Host "  Wrote $path" -ForegroundColor DarkGray
}

function Invoke-Layer {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$WorkDir,
        [Parameter(Mandatory)][string]$BackendKey,
        [string[]]$PlanVars = @(),
        [string]$VarFile
    )

    Write-Section "Layer: $Name"

    Invoke-Terraform -WorkDir $WorkDir -Arguments @(
        'init', '-reconfigure',
        "-backend-config=bucket=$StateBucketName",
        "-backend-config=key=$BackendKey",
        "-backend-config=region=$AwsRegion",
        "-backend-config=dynamodb_table=$LockTableName",
        "-backend-config=encrypt=true"
    )

    Invoke-Terraform -WorkDir $WorkDir -Arguments @('validate')

    $planFile = "setup-infra.auto.tfplan"
    $planArgs = @('plan', "-out=$planFile")
    if ($VarFile) { $planArgs += "-var-file=$VarFile" }
    $planArgs += $PlanVars
    Invoke-Terraform -WorkDir $WorkDir -Arguments $planArgs

    $planFullPath = Join-Path $WorkDir $planFile

    if ($PlanOnly) {
        Write-Host "  -PlanOnly set: skipping apply for '$Name'. Plan kept at $planFullPath." -ForegroundColor Yellow
        return
    }

    if (-not (Confirm-Apply -Layer $Name)) {
        Write-Host "  Skipped apply for '$Name'." -ForegroundColor Yellow
        Remove-Item $planFullPath -ErrorAction SilentlyContinue
        return
    }

    Invoke-Terraform -WorkDir $WorkDir -Arguments @('apply', $planFile)
    Remove-Item $planFullPath -ErrorAction SilentlyContinue
}

function Invoke-BootstrapLayer {
    if ($SkipBootstrap) {
        Write-Host "-SkipBootstrap set: skipping bootstrap layer." -ForegroundColor Yellow
        return
    }

    Write-Section "Layer: bootstrap"
    New-BootstrapTfvars

    # Bootstrap creates the remote backend itself, so it has no backend-config
    # of its own - it uses local state (see infra/terraform/RUNBOOK.md).
    Invoke-Terraform -WorkDir $BootstrapDir -Arguments @('init')
    Invoke-Terraform -WorkDir $BootstrapDir -Arguments @('validate')

    $planFile = "setup-infra.auto.tfplan"
    $planArgs = @(
        'plan', "-out=$planFile",
        '-var-file=bootstrap.tfvars',
        "-var=expected_account_id=$script:AccountId",
        "-var=aws_region=$AwsRegion"
    )
    Invoke-Terraform -WorkDir $BootstrapDir -Arguments $planArgs

    $planFullPath = Join-Path $BootstrapDir $planFile

    if ($PlanOnly) {
        Write-Host "  -PlanOnly set: skipping apply for 'bootstrap'. Plan kept at $planFullPath." -ForegroundColor Yellow
        return
    }

    if (-not (Confirm-Apply -Layer 'bootstrap')) {
        Write-Host "  Skipped apply for 'bootstrap'." -ForegroundColor Yellow
        Remove-Item $planFullPath -ErrorAction SilentlyContinue
        return
    }

    Invoke-Terraform -WorkDir $BootstrapDir -Arguments @('apply', $planFile)
    Remove-Item $planFullPath -ErrorAction SilentlyContinue

    # Bootstrap's own state is local (see comment above) - remind the operator
    # to protect it rather than silently leaving plaintext state on disk.
    Write-Host "  NOTE: bootstrap layer state is LOCAL (infra/terraform/bootstrap/terraform.tfstate)." -ForegroundColor Yellow
    Write-Host "        It may contain sensitive values. Keep it out of git (already ignored) and back it up securely." -ForegroundColor Yellow
}

# =============================================================================
# Main
# =============================================================================

$script:AccountId = $null

try {
    $identity = Test-Prerequisites
    $script:AccountId = if ($ExpectedAccountId) { $ExpectedAccountId } else { $identity.Account }

    Write-Section "Target"
    Write-Host "  AWS Account : $script:AccountId"
    Write-Host "  AWS Region  : $AwsRegion"
    Write-Host "  Environments: $($Environments -join ', ')"
    Write-Host "  Mode        : $(if ($PlanOnly) { 'PLAN ONLY (no apply)' } elseif ($AutoApprove) { 'AUTO-APPROVE (no prompts)' } else { 'INTERACTIVE (confirm each apply)' })"

    if (-not $AutoApprove -and -not $PlanOnly) {
        $go = Read-Host "Continue against this account/region? Type 'yes' to proceed"
        if ($go -ne 'yes') {
            Write-Host "Aborted by user." -ForegroundColor Yellow
            exit 0
        }
    }

    Invoke-SecurityScans

    Invoke-BootstrapLayer

    if ($SkipShared) {
        Write-Host "-SkipShared set: skipping shared (ECR) layer." -ForegroundColor Yellow
    } else {
        Invoke-Layer -Name "shared" -WorkDir $SharedDir `
            -BackendKey "velocityai/shared.tfstate" `
            -PlanVars @(
                "-var=expected_account_id=$script:AccountId",
                "-var=aws_region=$AwsRegion"
            )
    }

    foreach ($envName in $Environments) {
        Invoke-Layer -Name "foundation ($envName)" -WorkDir $FoundationDir `
            -BackendKey "velocityai/$envName/foundation.tfstate" `
            -VarFile "$envName.tfvars" `
            -PlanVars @(
                "-var=expected_account_id=$script:AccountId",
                "-var=aws_region=$AwsRegion"
            )

        $alertEmail = $AlertEmails[$envName]
        if ($alertEmail -like "REPLACE_ME*") {
            Write-Host "  Skipping app layer for '$envName': set a real alert_email in `$AlertEmails before running." -ForegroundColor Yellow
            continue
        }

        Invoke-Layer -Name "app ($envName)" -WorkDir $AppDir `
            -BackendKey "velocityai/$envName/app.tfstate" `
            -VarFile "$envName.tfvars" `
            -PlanVars @(
                "-var=expected_account_id=$script:AccountId",
                "-var=aws_region=$AwsRegion",
                "-var=state_bucket=$StateBucketName",
                "-var=alert_email=$alertEmail"
            )
    }

    if (-not $PlanOnly) {
        Write-Section "Outputs"
        try {
            if (-not $SkipBootstrap) {
                Write-Host "-- bootstrap --" -ForegroundColor DarkGray
                Invoke-Terraform -WorkDir $BootstrapDir -Arguments @('output')
            }
            if (-not $SkipShared) {
                Write-Host "-- shared --" -ForegroundColor DarkGray
                Invoke-Terraform -WorkDir $SharedDir -Arguments @('output')
            }
            foreach ($envName in $Environments) {
                Write-Host "-- app ($envName) --" -ForegroundColor DarkGray
                Invoke-Terraform -WorkDir $AppDir -Arguments @('output')
            }
        } catch {
            Write-Host "  Could not print every output (a layer may have been skipped or not applied). Run 'terraform -chdir=<dir> output' manually to inspect." -ForegroundColor Yellow
        }

        Write-Host ""
        Write-Host "Next: use github_build_role_arn / github_deploy_role_arns (bootstrap output) and" -ForegroundColor Cyan
        Write-Host "ecr_registry_url (shared output) to configure the GitHub Environment variables/secrets" -ForegroundColor Cyan
        Write-Host "(AWS_BUILD_ROLE_ARN, AWS_DEPLOY_ROLE_ARN, ECR_REGISTRY, EC2_INSTANCE_ID, ...) - see docs/GITHUB_CICD_SETUP.md." -ForegroundColor Cyan
    }

    Write-Section "Done"
}
catch {
    Write-Host ""
    Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
