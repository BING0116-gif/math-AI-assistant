param(
  [ValidateSet('backup','verify','restore')] [string]$Action,
  [Parameter(Mandatory=$true)] [string]$BackupPath,
  [string]$RestoreDatabase = 'math_ai_restore_verify'
)
$ErrorActionPreference = 'Stop'
$resolved = [System.IO.Path]::GetFullPath($BackupPath)
$dbUser = if ($env:DB_USER) { $env:DB_USER } else { 'mathai' }
$dbName = if ($env:DB_NAME) { $env:DB_NAME } else { 'math_ai' }
if ($Action -eq 'backup') {
  docker compose exec -T db pg_dump -U $dbUser -d $dbName -Fc | Set-Content -LiteralPath $resolved -AsByteStream
  Get-FileHash -LiteralPath $resolved -Algorithm SHA256
  exit
}
if (-not (Test-Path -LiteralPath $resolved)) { throw "Backup not found: $resolved" }
if ($RestoreDatabase -eq $dbName) { throw 'RestoreDatabase must be an isolated database, not the production database.' }
docker compose exec -T db createdb -U $dbUser $RestoreDatabase 2>$null
Get-Content -LiteralPath $resolved -AsByteStream -Raw | docker compose exec -T db pg_restore -U $dbUser -d $RestoreDatabase --clean --if-exists
docker compose exec -T db psql -U $dbUser -d $RestoreDatabase -c 'select count(*) as questions from questions;'
if ($Action -eq 'verify') { docker compose exec -T db dropdb -U $dbUser $RestoreDatabase }
