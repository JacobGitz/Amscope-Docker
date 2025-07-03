# load-image.ps1 (Windows)
<# Load a Docker image from a tar archive (Windows PowerShell)
   Lists tar files in Docker-images\ and loads the selected image.
#>
$ErrorActionPreference = 'Stop'

# Verify Docker Desktop is running
try {
    docker info | Out-Null
} catch {
    Write-Host "[ERROR] Docker Desktop is not running." -ForegroundColor Red
    return
}

# Find image archive files in Docker-images directory
$imagesDir = Join-Path (Split-Path $PSScriptRoot -Parent) "Docker-images"
if (-not (Test-Path $imagesDir)) {
    Write-Host "[ERROR] Docker-images directory not found." -ForegroundColor Red
    return
}
$files = Get-ChildItem -Path $imagesDir -Filter *.tar
if ($files.Count -eq 0) {
    Write-Host "(No image archives found in Docker-images\.)"
    return
}

# List available archives
Write-Host "Available image archives:"
[int]$i = 1
foreach ($file in $files) {
    Write-Host "  [$i] $($file.Name)"
    $i++
}
Write-Host "  [$i] Enter a file path manually"
# Prompt user selection
$choice = Read-Host "Select an archive to load (number or path)"
if ([string]::IsNullOrWhiteSpace($choice)) {
    Write-Host "Cancelled."
    return
}

# Determine selected file path
if ($choice -match '^\d+$') {
    $choiceNum = [int]$choice
    if ($choiceNum -ge 1 -and $choiceNum -lt $i) {
        $selectedPath = $files[$choiceNum - 1].FullName
    } elseif ($choiceNum -eq $i) {
        $selectedPath = Read-Host "Enter the path to the image tar file"
    } else {
        $selectedPath = $choice
    }
} else {
    # If the user entered a file name in Docker-images or a full path
    $candidate = Join-Path $imagesDir $choice
    if (Test-Path $candidate) {
        $selectedPath = $candidate
    } else {
        $selectedPath = $choice
    }
}

if (-not (Test-Path $selectedPath)) {
    Write-Host "[ERROR] File not found: $selectedPath" -ForegroundColor Red
    return
}

# Optionally ask for a new tag
$newTag = Read-Host "Enter a new image tag to apply (e.g., name:tag), or press Enter to keep original tags"

Write-Host "[INFO] Loading image from $selectedPath..."
try {
    $output = docker load -i $selectedPath
} catch {
    Write-Host "[ERROR] Image load failed." -ForegroundColor Red
    return
}
Write-Host $output
if (-not [string]::IsNullOrWhiteSpace($newTag)) {
    if ($output -match "Loaded image:\s+(.+)$") {
        $origImage = $Matches[1]
        try {
            docker tag $origImage $newTag
            Write-Host "[INFO] Image also tagged as $newTag"
        } catch {
            Write-Host "[WARNING] Failed to tag image as $newTag" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[WARNING] Could not determine loaded image name for tagging." -ForegroundColor Yellow
    }
}

Write-Host "[OK] Image load complete."
