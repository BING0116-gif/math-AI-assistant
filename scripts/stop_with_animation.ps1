[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $ProjectRoot "runtime\animation-worker.pid"

if (Test-Path -LiteralPath $PidFile) {
    $savedPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($savedPid -match '^\d+$') {
        Stop-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force
}

Set-Location $ProjectRoot
docker compose --project-directory $ProjectRoot stop frontend web qdrant redis db
if ($LASTEXITCODE -ne 0) { throw "Main application shutdown failed." }
Write-Host "Application and MathAnimator worker stopped. Database volumes and animation artifacts were retained."
