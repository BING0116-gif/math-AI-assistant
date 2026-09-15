[CmdletBinding()]
param()

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $ProjectRoot "runtime\animation-worker.pid"
$workerState = "stopped"
if (Test-Path -LiteralPath $PidFile) {
    $savedPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($savedPid -match '^\d+$' -and (Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue)) {
        $workerState = "running (PID $savedPid)"
    }
}
Write-Host "MathAnimator worker: $workerState"
Set-Location $ProjectRoot
docker compose --project-directory $ProjectRoot ps web frontend db redis qdrant