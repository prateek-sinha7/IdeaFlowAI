<#
.SYNOPSIS
  Collects a read-only diff between two branches for PR/MR review.

.DESCRIPTION
  Fetches the given source and target branches from origin, then produces a
  three-dot diff (origin/target...origin/source) representing only the
  changes introduced by the source branch since it diverged from target.
  This mirrors what a GitLab merge request diff shows.

  This script is READ-ONLY: it does not check out, merge, rebase, or push
  anything. It only runs `git fetch` (read) and `git diff`/`git log` (read).

.PARAMETER Source
  The source branch (the branch being merged in, e.g. a feature branch).

.PARAMETER Target
  The target branch (the branch being merged into, e.g. dev). Defaults to
  "dev" if not specified.

.PARAMETER RepoPath
  Path to the git repository. Defaults to the current directory.

.OUTPUTS
  Writes a diff file to $env:TEMP and prints its path plus a stat summary
  to stdout as JSON so the calling agent can parse it reliably.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $false)]
    [string]$Target = "dev",

    [Parameter(Mandatory = $false)]
    [string]$RepoPath = "."
)

# Note: kept at "Continue" deliberately. Git writes normal progress/status
# output to stderr (e.g. "From gitlab.com:..." on fetch). If this were set to
# "Stop", PowerShell would wrap that stderr text as a terminating error even
# though the command succeeded. We rely on $LASTEXITCODE for success/failure
# instead of stderr content.
$ErrorActionPreference = "Continue"

function Fail($message) {
    $result = @{
        success = $false
        error   = $message
    }
    $result | ConvertTo-Json -Compress
    exit 1
}

Push-Location $RepoPath
try {
    # Confirm we're inside a git repository
    git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail "Not a git repository: $RepoPath"
    }

    # Fetch latest refs for both branches (read-only, no local branch changes)
    git fetch origin $Target $Source *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail "git fetch failed for origin/$Target or origin/$Source. Check branch names and remote access."
    }

    $targetRef = "origin/$Target"
    $sourceRef = "origin/$Source"

    # Verify both refs actually resolve after fetch
    git rev-parse --verify $targetRef *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail "Target branch '$Target' not found on origin."
    }
    git rev-parse --verify $sourceRef *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail "Source branch '$Source' not found on origin."
    }

    $range = "$targetRef...$sourceRef"
    $logRange = "$targetRef..$sourceRef"

    $diffText = git diff $range 2>&1
    $statText = git diff --stat $range 2>&1
    $logText = git log $logRange --oneline 2>&1
    $filesChanged = git diff --name-only $range 2>&1

    $commitCount = ($logText | Measure-Object -Line).Lines
    $fileCount = ($filesChanged | Where-Object { $_.Trim() -ne "" } | Measure-Object).Count

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $safeSource = $Source -replace '[\\/:]', '_'
    $safeTarget = $Target -replace '[\\/:]', '_'
    $outFile = Join-Path $env:TEMP "flowin-pr-review-$safeSource-to-$safeTarget-$timestamp.diff"

    $output = @()
    $output += "# PR Review Diff"
    $output += "# Source: $Source ($sourceRef)"
    $output += "# Target: $Target ($targetRef)"
    $output += "# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    $output += ""
    $output += "## Commit log ($logRange)"
    $output += $logText
    $output += ""
    $output += "## Diff stat"
    $output += $statText
    $output += ""
    $output += "## Full diff"
    $output += $diffText

    $output -join "`n" | Out-File -FilePath $outFile -Encoding utf8

    $result = @{
        success      = $true
        diffFile     = $outFile
        source       = $Source
        target       = $Target
        commitCount  = $commitCount
        filesChanged = $fileCount
        fileList     = @($filesChanged | Where-Object { $_.Trim() -ne "" })
    }
    $result | ConvertTo-Json -Compress -Depth 5
}
finally {
    Pop-Location
}
