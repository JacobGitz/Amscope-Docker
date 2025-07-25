# save-image.ps1 (Windows)
<# Save a Docker image to a tar archive (Windows PowerShell)
   Lists local Docker images and saves the selected one to Docker-images\ 
#>
$ErrorActionPreference = 'Stop'

# Verify Docker Desktop is running
try {
    docker info | Out-Null
} catch {
    Write-Host "[ERROR] Docker Desktop is not running." -ForegroundColor Red
    return
}

# Gather Docker images
Write-Host "Available Docker images:"
$images = @(docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | Where-Object {$_ -notmatch "<none>"} )
if ($images.Count -eq 0) {
    Write-Host "(No images available to save.)"
    return
}
# Display images with indices
[int]$i = 1
foreach ($entry in $images) {
    Write-Host "  [$i] $entry"
    $i++
}
Write-Host "  [$i] Enter image name manually"
# Prompt for choice
$choice = Read-Host "Select an image to save (number or name)"
if ([string]::IsNullOrWhiteSpace($choice)) {
    Write-Host "Cancelled."
    return
}

# Determine selected image
if ($choice -match '^\d+$') {
    $choiceNum = [int]$choice
    if ($choiceNum -ge 1 -and $choiceNum -lt $i) {
        # Selected from list
        $selectedImage = $images[$choiceNum - 1] -split ' ' | Select-Object -First 1
    } elseif ($choiceNum -eq $i) {
        $selectedImage = Read-Host "Enter image name (e.g., repository:tag or image ID)"
    } else {
        $selectedImage = $choice  # out of range, treat as name
    }
} else {
    $selectedImage = $choice
}

if ([string]::IsNullOrWhiteSpace($selectedImage)) {
    Write-Host "[ERROR] No image specified." -ForegroundColor Red
    return
}

# Suggest a default file name based on image name:tag
$safeName = $selectedImage -replace '[\/:]', '_'
$defaultFile = "$safeName.tar"
$filename = Read-Host "Enter output file name (Default: $defaultFile)"
if ([string]::IsNullOrWhiteSpace($filename)) { $filename = $defaultFile }

# Ensure Docker-images directory exists
$outputDir = Join-Path (Split-Path $PSScriptRoot -Parent) "Docker-images"
New-Item -Path $outputDir -ItemType Directory -Force | Out-Null
$outputPath = Join-Path $outputDir $filename
if (Test-Path $outputPath) {
    $overwrite = Read-Host "[WARNING] '$filename' already exists. Overwrite? [y/N]"
    if ($overwrite -notmatch '^[Yy]') {
        Write-Host "Cancelled (file not saved)."
        return
    }
}

Write-Host "[INFO] Saving image '$selectedImage' to $filename..."
try {
    docker save -o $outputPath $selectedImage
    Write-Host "[OK] Image saved as Docker-images\$filename"
} catch {
    Write-Host "[ERROR] Docker image save failed." -ForegroundColor Red
}
