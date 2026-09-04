<#
.SYNOPSIS
    Upgrades a Python package across all uv-managed projects in Integration-Hub-Beta.

.DESCRIPTION
    Walks every directory containing a uv.lock file, optionally raises the minimum
    version floor in pyproject.toml for direct dependencies, then regenerates the
    lock file via `uv lock --upgrade-package`.

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

foreach ($lock in $lockFiles) {
    $dir        = $lock.DirectoryName
    $pyproject  = Join-Path $dir "pyproject.toml"
    $relDir     = $dir.Substring($repoRoot.Length).TrimStart('\')

    Write-Host "`n=== $relDir ===" -ForegroundColor Cyan

    # --- Optionally raise the pyproject.toml floor for direct dependencies ---
    if ($MinVersion -and (Test-Path $pyproject)) {
        $content = Get-Content $pyproject -Raw

        # Matches lines like:  "pyjwt>=2.12.0",  or  "pyjwt>=2.12.1"
        $pattern = '(?i)("' + [regex]::Escape($Package) + '>=)(\d+\.\d+[\.\d]*)(")'

        if ($content -match $pattern) {
            $currentFloor = $Matches[2]
            if ([version]$currentFloor -lt [version]$MinVersion) {
                Write-Host "  Bumping $Package floor in pyproject.toml: $currentFloor -> $MinVersion"
                $updated = [regex]::Replace($content, $pattern, "`${1}$MinVersion`${3}")
                [System.IO.File]::WriteAllText($pyproject, $updated)
            } else {
                Write-Host "  pyproject.toml floor ($currentFloor) already >= $MinVersion — no manifest change needed"
            }
        } else {
            Write-Host "  $Package is a transitive dependency only — no manifest change needed"
        }
    }

    # --- Upgrade the lock file ---
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
