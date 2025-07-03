# save-image.sh (Linux)
#!/usr/bin/env bash
# Save a Docker image to a tar archive (Linux)
# Lists available images and saves the chosen one into the Docker-images/ directory.

# Ensure Docker is available and running
if ! command -v docker &>/dev/null; then
    echo "[ERROR] Docker is not installed or not in PATH."
    exit 1
fi
if ! docker info &>/dev/null; then
    echo "[ERROR] Docker daemon is not running."
    exit 1
fi

# List images for user selection
echo "Available Docker images:"
mapfile -t images < <(docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep -v "<none>")
if [ ${#images[@]} -eq 0 ]; then
    echo "(No images available to save.)"
    exit 1
fi
i=1
for entry in "${images[@]}"; do
    echo "  [$i] $entry"
    ((i++))
done
echo "  [$i] Enter image name manually"
printf "Select an image to save: "
read choice
if [ -z "$choice" ]; then
    echo "Cancelled."
    exit 0
fi

# Determine selected image
selectedImage=""
if [[ "$choice" =~ ^[0-9]+$ && $choice -ge 1 && $choice -le $i ]]; then
    if [ "$choice" -eq "$i" ]; then
        # Manual entry chosen
        printf "Enter image name (e.g., repository:tag or image ID): "
        read manualName
        selectedImage="$manualName"
    else
        # Use the image name:tag from the selected list entry
        selectedImage="$(cut -d ' ' -f1 <<< "${images[$((choice-1))]}")"
    fi
else
    # User entered an image name/tag directly
    selectedImage="$choice"
fi

if [ -z "$selectedImage" ]; then
    echo "[ERROR] No image specified."
    exit 1
fi

# Prompt for output filename, suggest a default based on image name:tag
safeName="${selectedImage//\//_}"
safeName="${safeName//:/_}"
defaultFileName="${safeName}.tar"
printf "Enter output file name (default: %s): " "$defaultFileName"
read filename
if [ -z "$filename" ]; then
    filename="$defaultFileName"
fi

# Ensure Docker-images directory exists
outputDir="$(dirname "$0")/../Docker-images"
mkdir -p "$outputDir"
outputPath="$outputDir/$filename"
if [ -f "$outputPath" ]; then
    printf "[WARNING] '%s' already exists. Overwrite? [y/N] " "$filename"
    read overwrite
    if [[ ${overwrite,,} != y* ]]; then
        echo "Cancelled (file not saved)."
        exit 1
    fi
fi

echo "[INFO] Saving image '$selectedImage' to $filename..."
if docker save -o "$outputPath" "$selectedImage"; then
    echo "[OK] Image saved as Docker-images/$filename"
else
    echo "[ERROR] Docker image save failed."
fi
