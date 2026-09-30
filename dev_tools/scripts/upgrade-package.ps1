<#
.SYNOPSIS
    Upgrades a Python package across all uv-managed projects in Integration-Hub-Beta.

.DESCRIPTION
    Runs in two phases across every directory containing a uv.lock file:

      Phase 1 - raise the minimum version floor in pyproject.toml (for direct
                dependencies) in ALL directories first, with no locking yet.
      Phase 2 - regenerate every lock file via `uv lock --upgrade-package`.

    Local path dependencies (e.g. shared_libs/*) cache a snapshot of their own
    pyproject.toml `requires-dist` metadata inside every dependent's uv.lock.
    Bumping manifests and locking directory-by-directory in a single pass would
    let a dependent lock against a shared lib's pre-bump manifest if that lib
    hadn't been processed yet (alphabetical ordering), leaving stale floors
    embedded in the dependent's lock file and failing CI's `uv lock --locked`
    check. Running phase 1 to completion before any phase-2 locking begins
    avoids that ordering issue entirely - no need to run this script twice.

    Use this script whenever a vulnerability is identified in a shared dependency.

.PARAMETER Package
    The package name to upgrade (e.g. pyjwt, cryptography, requests).

.PARAMETER MinVersion
    Optional. If supplied, any direct dependency in pyproject.toml with a floor
    lower than this value (e.g. >=2.12.0) will be raised to >=<MinVersion>.
    Transitive-only dependencies are lock-upgraded without touching the manifest.

.EXAMPLE
    .\dev_tools\scripts\upgrade-package.ps1 -Package pyjwt -MinVersion 2.13.0

.EXAMPLE
    .\dev_tools\scripts\upgrade-package.ps1 -Package cryptography -MinVersion 44.0.1
#>

param(
    [Parameter(Mandatory)]
    [string] $Package,

    [string] $MinVersion = ""
)

# Resolve repo root (two levels above the dev_tools/scripts/ folder)
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$lockFiles = Get-ChildItem -Path $repoRoot -Recurse -Filter "uv.lock" |
             Where-Object { $_.FullName -notmatch '\\.venv\\' }

$upgraded  = @()
$failed    = @()

# --- Phase 1: raise the pyproject.toml floor for direct dependencies EVERYWHERE first ---
# This must fully complete before any `uv lock` runs (phase 2), otherwise a dependent
# project could lock against a path-dependency's (e.g. shared_libs/*) pre-bump manifest.
if ($MinVersion) {
    Write-Host "`n--- Phase 1: bumping pyproject.toml floors ---" -ForegroundColor Yellow
    foreach ($lock in $lockFiles) {
        $dir        = $lock.DirectoryName
        $pyproject  = Join-Path $dir "pyproject.toml"
        $relDir     = $dir.Substring($repoRoot.Length).TrimStart('\')

        if (-not (Test-Path $pyproject)) { continue }

        $content = Get-Content $pyproject -Raw

        # Matches lines like:  "pyjwt>=2.12.0",  or  "pyjwt>=2.12.1"
        $pattern = '(?i)("' + [regex]::Escape($Package) + '>=)(\d+\.\d+[\.\d]*)(")'

        if ($content -match $pattern) {
            $currentFloor = $Matches[2]
            if ([version]$currentFloor -lt [version]$MinVersion) {
                Write-Host "  [$relDir] Bumping $Package floor: $currentFloor -> $MinVersion"
                $updated = [regex]::Replace($content, $pattern, "`${1}$MinVersion`${3}")
                [System.IO.File]::WriteAllText($pyproject, $updated)
            } else {
                Write-Host "  [$relDir] floor ($currentFloor) already >= $MinVersion — no manifest change needed"
            }
        } else {
            Write-Host "  [$relDir] $Package is a transitive dependency only — no manifest change needed"
        }
    }
}

# --- Phase 2: regenerate every lock file now that all manifests are settled ---
Write-Host "`n--- Phase 2: regenerating lock files ---" -ForegroundColor Yellow
foreach ($lock in $lockFiles) {
    $dir    = $lock.DirectoryName
    $relDir = $dir.Substring($repoRoot.Length).TrimStart('\')

    Write-Host "`n=== $relDir ===" -ForegroundColor Cyan
    Write-Host "  Running: uv lock --upgrade-package $Package"
    Push-Location $dir
    try {
        uv lock --upgrade-package $Package 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "  uv lock FAILED in $relDir"
            $failed += $relDir
        } else {
            Write-Host "  Lock updated successfully" -ForegroundColor Green
            $upgraded += $relDir
        }
    } catch {
        Write-Warning "  Exception in $relDir : $_"
        $failed += $relDir
    } finally {
        Pop-Location
    }
}

# --- Summary ---
Write-Host "`n=============================" -ForegroundColor White
Write-Host " Upgrade summary for: $Package" -ForegroundColor White
Write-Host "=============================" -ForegroundColor White
Write-Host "  Upgraded : $($upgraded.Count)" -ForegroundColor Green
if ($failed.Count -gt 0) {
    Write-Host "  Failed   : $($failed.Count)" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
Write-Host ""
