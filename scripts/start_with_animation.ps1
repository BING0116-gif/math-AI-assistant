[CmdletBinding()]
param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $ProjectRoot "runtime"
$AnimationRoot = Join-Path $RuntimeRoot "animations"
$PidFile = Join-Path $RuntimeRoot "animation-worker.pid"
$LogFile = Join-Path $RuntimeRoot "animation-worker.log"
$ErrorLogFile = Join-Path $RuntimeRoot "animation-worker.error.log"
$RendererTag = "zhiwei-math-renderer:trixie-poc"

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Find-AvailablePort([int[]]$Candidates) {
    foreach ($candidate in $Candidates) {
        $listener = $null
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $candidate)
            $listener.Start()
            return $candidate
        } catch {
            continue
        } finally {
            if ($listener) { $listener.Stop() }
        }
    }
    throw "No approved local port is available."
}

function Get-ComposeDatabaseConfiguration {
    $json = docker compose --project-directory $ProjectRoot config --format json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) {
        throw "Cannot read Docker Compose config. Check required values in .env."
    }
    return (($json | ConvertFrom-Json).services.db)
}

function Stop-StaleWorker {
    if (-not (Test-Path -LiteralPath $PidFile)) { return }
    $savedPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($savedPid -match '^\d+$') {
        $process = Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "MathAnimator worker is already running (PID $savedPid)."
            return $true
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
    return $false
}

Set-Location $ProjectRoot
Assert-Command "docker"
Assert-Command "python"
Assert-Command "npm"
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Engine is not running." }

New-Item -ItemType Directory -Path $RuntimeRoot, $AnimationRoot -Force | Out-Null

$imageId = docker image inspect $RendererTag --format '{{.Id}}' 2>$null
if ($LASTEXITCODE -ne 0 -or $imageId -notmatch '^sha256:[0-9a-f]{64}$') {
    if ($SkipBuild) { throw "Approved MathAnimator renderer image not found: $RendererTag" }
    Write-Host "Building MathAnimator renderer image (first run can take several minutes)..."
    docker build --target runtime -f ops/math_animator_poc/Dockerfile.renderer-trixie -t $RendererTag ops/math_animator_poc
    if ($LASTEXITCODE -ne 0) { throw "MathAnimator renderer image build failed." }
    $imageId = docker image inspect $RendererTag --format '{{.Id}}'
}
$imageId = $imageId.Trim().ToLowerInvariant()

# These overrides affect only the launched processes; .env is not modified.
$env:MATH_ANIMATION_ENABLED = "true"
$env:ANIMATION_RENDERER_IMAGE = $imageId
$env:ANIMATION_STORAGE_ROOT = "/app/runtime/animations"
$FrontendPort = Find-AvailablePort @(13000, 13001, 18080, 18081)
$BackendPort = Find-AvailablePort @(18000, 18001, 28000, 28001)
$env:FRONTEND_PORT = [string]$FrontendPort
$env:PORT = [string]$BackendPort

$composeArgs = @("compose", "--project-directory", $ProjectRoot, "up", "-d", "--no-build")
if (-not $SkipBuild) {
    Write-Host "Building the frontend with the host Node runtime..."
    Push-Location (Join-Path $ProjectRoot "frontend")
    try {
        npm ci --ignore-scripts
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency install failed." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally {
        Pop-Location
    }
    docker build -f frontend/Dockerfile.runtime -t mathaiassistant-frontend:latest frontend
    if ($LASTEXITCODE -ne 0) { throw "Frontend runtime image build failed." }
    docker compose --project-directory $ProjectRoot build web
    if ($LASTEXITCODE -ne 0) { throw "Web image build failed." }
}
$composeArgs += @("db", "redis", "qdrant", "web", "frontend")
& docker @composeArgs
if ($LASTEXITCODE -ne 0) { throw "Main application startup failed." }

if (Stop-StaleWorker) {
    Write-Host "Application and MathAnimator are ready."
    exit 0
}

$dbConfig = Get-ComposeDatabaseConfiguration
$dbEnv = $dbConfig.environment
$dbUser = [string]$dbEnv.POSTGRES_USER
$dbPassword = [string]$dbEnv.POSTGRES_PASSWORD
$dbName = [string]$dbEnv.POSTGRES_DB
$publishedPort = @($dbConfig.ports | Where-Object { [string]$_.target -eq "5432" } | Select-Object -First 1).published
$dbPort = if ($publishedPort) { [string]$publishedPort } else { "5432" }
if (-not $dbUser -or -not $dbPassword -or -not $dbName) {
    throw "Compose database configuration is incomplete."
}
$escapedUser = [Uri]::EscapeDataString($dbUser)
$escapedPassword = [Uri]::EscapeDataString($dbPassword)
$escapedName = [Uri]::EscapeDataString($dbName)
$env:DATABASE_URL = "postgresql://${escapedUser}:${escapedPassword}@127.0.0.1:${dbPort}/${escapedName}"
$env:ASYNC_DATABASE_URL = "postgresql+asyncpg://${escapedUser}:${escapedPassword}@127.0.0.1:${dbPort}/${escapedName}"
$env:ANIMATION_STORAGE_ROOT = $AnimationRoot

$worker = Start-Process -FilePath "python" `
    -ArgumentList @("-m", "app.tasks.animation_worker") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrorLogFile `
    -PassThru
$worker.Id | Set-Content -LiteralPath $PidFile -Encoding ascii
Start-Sleep -Seconds 2
if (-not (Get-Process -Id $worker.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    throw "MathAnimator worker exited during startup. Check $LogFile and $ErrorLogFile"
}

Write-Host "Application and MathAnimator started."
Write-Host "Open: http://127.0.0.1:$FrontendPort"
Write-Host "API: http://127.0.0.1:$BackendPort"
Write-Host "Worker PID: $($worker.Id)"
Write-Host "Worker logs: $LogFile and $ErrorLogFile"
