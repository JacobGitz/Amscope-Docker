<#  Thorlabs TDC001 GUI one-click launcher  (PowerShell)
    • asks to rebuild only when an image already exists
    • starts (or recreates) the container
    • opens http://localhost:6080
#>

$ErrorActionPreference = 'Stop'

# ───────── configuration ─────────
$composeRelative = "..\Code\TDC001-project\docker-compose.frontend.yml"
$service         = "tdc_frontend"
$port            = 6080
# ─────────────────────────────────

Write-Host "`n──────── Thorlabs TDC001 GUI launcher ────────`n" -Foreground Cyan

# 1) locate compose file -------------------------------------------------
$scriptDir  = Split-Path $MyInvocation.MyCommand.Path -Parent
try   { $composeFile = Resolve-Path (Join-Path $scriptDir $composeRelative) }
catch { Write-Host "[ERROR] Compose file not found." -Foreground Red; return }

Write-Host "[INFO] Compose file  $composeFile"

# 2) docker available? ---------------------------------------------------
try { docker info | Out-Null }
catch { Write-Host "[ERROR] Docker Desktop is not running." -Foreground Red; return }

# 3) image check / rebuild prompt ---------------------------------------
$imageId = docker compose -f $composeFile images -q $service 2>$null | Select-Object -First 1
$rebuild = $true
if ($imageId) {
    Write-Host "[INFO] Found existing image for $service ($imageId)"
    $rebuild = (Read-Host "Rebuild it? [y/N]") -match '^[Yy]'
}

if ($rebuild) {
    Write-Host "[INFO] Building image…"
    docker compose -f $composeFile build --pull $service
    if ($LASTEXITCODE) { Write-Host "[ERROR] Build failed." -Foreground Red; return }
}

# 4) start / recreate container -----------------------------------------
Write-Host "[INFO] (re)creating container…"
docker compose -f $composeFile up -d --force-recreate $service
if ($LASTEXITCODE) { Write-Host "[ERROR] docker compose failed." -Foreground Red; return }

# 5) wait for noVNC ------------------------------------------------------
Write-Host "[INFO] Waiting for noVNC on localhost:$port"
for ($i=0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$port" -TimeoutSec 1 | Out-Null
        break
    } catch { Start-Sleep -Milliseconds 500 }
}

# 6) open browser --------------------------------------------------------
Write-Host "[INFO] Opening browser…"
Start-Process "http://localhost:$port"

Write-Host "`n[OK] Done."
