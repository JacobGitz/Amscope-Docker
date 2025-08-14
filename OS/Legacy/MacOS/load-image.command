# load-image.command (macOS)
#!/usr/bin/env sh
# Load a Docker image from a tar archive (macOS)
# Lists tar files in ../Docker-images/ and loads the selected image into Docker.

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] Docker CLI not found."
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker daemon not running."
    exit 1
fi

imagesDir="$(dirname "$0")/../Docker-images"
if [ ! -d "$imagesDir" ]; then
    echo "[ERROR] Docker-images directory not found."
    exit 1
fi

# List available tar archives
tmpfile=$(mktemp)
cd "$imagesDir" || { echo "[ERROR] Cannot access $imagesDir"; exit 1; }
ls -1 *.tar > "$tmpfile" 2>/dev/null
if [ ! -s "$tmpfile" ]; then
    echo "(No image archive files found in Docker-images/)"
    rm -f "$tmpfile"
    exit 0
fi
echo "Available image archives:"
i=1
while IFS= read -r tarname; do
    echo "  [$i] $tarname"
    i=$((i+1))
done < "$tmpfile"
echo "  [$i] Enter a file path manually"
printf "Select an archive to load: "
read choice
selectedFile=""
case "$choice" in
    "" )
        echo "Cancelled."
        rm -f "$tmpfile"
        exit 0
        ;;
    [0-9]* )
        if [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -lt "$i" ] 2>/dev/null; then
            selectedFile="$imagesDir/$(sed -n "${choice}p" "$tmpfile")"
        elif [ "$choice" -eq "$i" ] 2>/dev/null; then
            printf "Enter path to image tar file: "
            read manualPath
            selectedFile="$manualPath"
        else
            selectedFile="$choice"
        fi
        ;;
    * )
        selectedFile="$choice"
        ;;
esac
rm -f "$tmpfile"

if [ ! -f "$selectedFile" ]; then
    echo "[ERROR] File not found: $selectedFile"
    exit 1
fi

printf "Enter new image tag to apply (e.g., name:tag), or press Enter to keep original: "
read newTag

echo "[INFO] Loading image from $selectedFile..."
loadOutput=$(docker load -i "$selectedFile")
if [ $? -ne 0 ]; then
    echo "[ERROR] Image load failed."
    exit 1
fi
echo "$loadOutput"
if [ -n "$newTag" ]; then
    loadedRepoTag=$(echo "$loadOutput" | grep -o "Loaded image: .*" | sed 's/Loaded image: //')
    if [ -n "$loadedRepoTag" ]; then
        docker tag "$loadedRepoTag" "$newTag"
        echo "[INFO] Image also tagged as $newTag"
    else
        echo "[WARNING] Could not detect image name for tagging."
    fi
fi

echo "[OK] Image load complete."
