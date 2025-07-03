# backend-shutdown.command (macOS)
#!/usr/bin/env sh
# Thorlabs TDC001 BACKEND shutdown script – macOS
# Stops (and optionally removes) the backend Docker container

# Docker availability checks
if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] Docker not installed or not in PATH."
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker daemon not running."
    exit 1
fi

# Compose file and service configuration
compose_relative='../Code/TDC001-project/docker-compose.backend.yml'
service='tdc_backend'

echo
printf "%s──── stopping TDC001 BACKEND ────%s\n\n" "$(printf '\033[36m')" "$(printf '\033[0m')"

# Locate the docker-compose file
script_dir="$(cd "$(dirname "$0")" && pwd)"
compose_file="$(cd "$(dirname "$compose_relative")" && pwd)/$(basename "$compose_relative")"
if [ ! -f "$compose_file" ]; then
    printf "\033[31m[ERROR]\033[0m Compose file not found: %s\n" "$compose_file" >&2
    exit 1
fi
printf "[INFO] Using compose file %s\n" "$compose_file"

# Stop the backend container
if docker compose version >/dev/null 2>&1; then
    compose() { docker compose "$@"; }
else
    compose() { docker-compose "$@"; }
fi
echo "[INFO] Stopping container…"
compose -f "$compose_file" stop "$service"

# Prompt to optionally remove the container
printf "Remove the container too? [y/N] "
read ans || true
case "$ans" in
    [Yy]* )
        echo "[INFO] Removing container…"
        compose -f "$compose_file" rm -f "$service"
        ;;
esac

echo "[OK] Done."

