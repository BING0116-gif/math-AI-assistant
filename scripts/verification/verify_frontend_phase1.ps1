param(
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'frontend'

Write-Host 'Phase 1 frontend baseline verification'
Write-Host "Repository: $repoRoot"

$requiredFiles = @(
    'frontend/package.json',
    'frontend/src/router/index.js',
    'frontend/src/api/chat.js',
    'frontend/src/api/knowledge.js',
    'frontend/src/api/errorBook.js',
    'docs/UI_UX_MASTER_PLAN.md',
    'plans/frontend-refactor/phase-1-baseline-and-design-freeze.md'
)

foreach ($relativePath in $requiredFiles) {
    $path = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required baseline file: $relativePath"
    }
    Write-Host "OK  $relativePath"
}

if (-not $SkipBuild) {
    Push-Location $frontendRoot
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host 'Baseline checks completed.'
