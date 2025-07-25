# backend-shutdown.ps1 (Windows)
<# Thorlabs TDC001 BACKEND shutdown (PowerShell)
   • Stops the backend Docker container
   • Offers to remove the container 
#>
$ErrorActionPreference = 'Stop'

# Configuration: docker-compose file path and service name
$composeRelative = "..\Code\TDC001-project\docker-compose.backend.yml"
$service        = "tdc_backend"

Write-Host "`n──── Stopping TDC001 BACKEND ────`n" -ForegroundColor Cyan

# Locate the Docker Compose file
$scriptDir  = Split-Path $MyInvocation.MyCommand.Path -Parent
try {
    $composeFile = Resolve-Path (Join-Path $scriptDir $composeRelative)
} catch {
    Write-Host "[ERROR] Compose file not found: $composeRelative" -ForegroundColor Red
    return
}
Write-Host "[INFO] Using compose file $composeFile"

# Ensure Docker Desktop is running
try {
    docker info | Out-Null
} catch {
    Write-Host "[ERROR] Docker Desktop is not running." -ForegroundColor Red
    return
}

# Stop the backend container
Write-Host "[INFO] Stopping container…"
docker compose -f $composeFile stop $service

# Optionally remove the container
$remove = Read-Host "Remove the container too? [y/N]"
if ($remove -match '^[Yy]') {
    Write-Host "[INFO] Removing container…"
    docker compose -f $composeFile rm -f $service
}

Write-Host "[OK] Done."

