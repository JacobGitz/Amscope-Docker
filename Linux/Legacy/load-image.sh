# load-image.sh (Linux)
#!/usr/bin/env bash
# Load a Docker image from a tar archive (Linux)
# Lets you pick a tar file from Docker-images/ and loads it into Docker.

# Ensure Docker is available and running
if ! command -v docker &>/dev/null; then
    echo "[ERROR] Docker CLI not found."
    exit 1
fi
if ! docker info &>/dev/null; then
    echo "[ERROR] Docker daemon is not running."
    exit 1
fi

# Find tar files in Docker-images directory
inputDir="$(dirname "$0")/../Docker-images"
if [ ! -d "$inputDir" ]; then
    echo "[ERROR] Docker-images directory not found."
    exit 1
fi
mapfile -t tarfiles < <(find "$inputDir" -maxdepth 1 -type f -name "*.tar")
if [ ${#tarfiles[@]} -eq 0 ]; then
    echo "No saved Docker image archives found in Docker-images/."
    exit 0
fi

echo "Available image archives:"
i=1
for filepath in "${tarfiles[@]}"; do
    file="$(basename "$filepath")"
    echo "  [$i] $file"
    ((i++))
done
echo "  [$i] Enter other file path"
printf "Select an image archive to load: "
read choice
if [ -z "$choice" ]; then
    echo "Cancelled."
    exit 0
fi

# Determine selected file
selectedFile=""
if [[ "$choice" =~ ^[0-9]+$ && $choice -ge 1 && $choice -le $i ]]; then
    if [ "$choice" -eq "$i" ]; then
        printf "Enter path to image tar file: "
        read manualPath
        selectedFile="$manualPath"
    else
        selectedFile="${tarfiles[$((choice-1))]}"
    fi
else
    # treat input as file name or path
    if [ -f "$inputDir/$choice" ]; then
        selectedFile="$inputDir/$choice"
    else
        selectedFile="$choice"
    fi
fi

if [ ! -f "$selectedFile" ]; then
    echo "[ERROR] File not found: $selectedFile"
    exit 1
fi

# Optional retagging
printf "Enter a new image tag to apply (e.g., name:tag), or press Enter to keep original tags: "
read newTag

echo "[INFO] Loading image from $selectedFile..."
loadOutput=$(docker load -i "$selectedFile")
if [ $? -ne 0 ]; then
    echo "[ERROR] Docker image load failed."
    exit 1
fi
echo "$loadOutput"
if [ -n "$newTag" ]; then
    loadedRepoTag=$(echo "$loadOutput" | grep -oE "Loaded image: (.+)$" | sed -e "s/Loaded image: //")
    if [ -n "$loadedRepoTag" ]; then
        docker tag "$loadedRepoTag" "$newTag"
        echo "[INFO] Image also tagged as $newTag"
    else
        echo "[WARNING] Could not determine loaded image name for tagging."
    fi
fi

echo "[OK] Image load complete."
