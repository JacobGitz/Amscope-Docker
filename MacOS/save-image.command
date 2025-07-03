# save-image.command (macOS)
#!/usr/bin/env sh
# Save a Docker image to a tar archive (macOS)
# Lists local Docker images and saves the selected one into ../Docker-images/.

# Docker availability check
if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] Docker not installed or not in PATH."
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker daemon not running."
    exit 1
fi

# List images for selection
echo "Available Docker images:"
tmpfile=$(mktemp)
docker images --format "{{.Repository}}:{{.Tag}}" | grep -v "<none>" > "$tmpfile"
i=1
while IFS= read -r img; do
    echo "  [$i] $img"
    i=$((i+1))
done < "$tmpfile"
echo "  [$i] Enter an image name manually"
printf "Select an image to save: "
read choice
if [ -z "$choice" ]; then
    echo "Cancelled."
    rm -f "$tmpfile"
    exit 0
fi

# Determine selected image name
selectedImage=""
case "$choice" in
    [0-9]*)
        if [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -lt "$i" ] 2>/dev/null; then
            selectedImage=$(sed -n "${choice}p" "$tmpfile")
        elif [ "$choice" -eq "$i" ] 2>/dev/null; then
            printf "Enter image name (e.g., repo:tag): "
            read manualName
            selectedImage="$manualName"
        else
            selectedImage="$choice"
        fi
        ;;
    *)
        selectedImage="$choice"
        ;;
esac
rm -f "$tmpfile"

if [ -z "$selectedImage" ]; then
    echo "[ERROR] No image selected."
    exit 1
fi

# Determine output filename (default based on image name:tag)
safeName=$(echo "$selectedImage" | sed 's/\//_/g; s/:/_/g')
defaultFile="$safeName.tar"
printf "Enter output file name [default: %s]: " "$defaultFile"
read filename
if [ -z "$filename" ]; then
    filename="$defaultFile"
fi

# Ensure Docker-images directory exists and save the image
outputDir="$(dirname "$0")/../Docker-images"
mkdir -p "$outputDir"
outputPath="$outputDir/$filename"
if [ -f "$outputPath" ]; then
    printf "[WARNING] File '%s' exists. Overwrite? [y/N] " "$filename"
    read overwrite
    case "$overwrite" in
        [Yy]* ) ;;  # proceed to overwrite
        * ) echo "Cancelled."; exit 1 ;;
    esac
fi

echo "[INFO] Saving image '$selectedImage' to $filename..."
if docker save -o "$outputPath" "$selectedImage"; then
    echo "[OK] Image saved to Docker-images/$filename"
else
    echo "[ERROR] Failed to save image."
fi
