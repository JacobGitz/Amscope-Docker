#!/usr/bin/env sh
###############################################################################
# Thorlabs TDC001 BACKEND one-click launcher  – POSIX / macOS-ready
# • optionally rebuilds the Docker image
# • (re)creates the container
# • opens http://localhost:8000/docs in the default browser
###############################################################################

# ───────── configuration ─────────
compose_relative='../Code/TDC001-project/docker-compose.backend.yml'
service='tdc_backend'    # docker-compose service name
port=8000                # FastAPI external port
# ─────────────────────────────────

set -eu

# colour only when stdout is a TTY
if [ -t 1 ]; then
  cyan="$(printf '\033[36m')" red="$(printf '\033[31m')" reset="$(printf '\033[0m')"
else
  cyan='' red='' reset=''
fi

echo
printf '%s──────── Thorlabs TDC001 BACKEND launcher ────────%s\n\n' "$cyan" "$reset"

# 1) locate compose file (portable realpath)
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"  # shellcheck disable=SC2164
compose_file="$(cd "$(dirname "$compose_relative")" && pwd)/$(basename "$compose_relative")"

if [ ! -f "$compose_file" ]; then
  printf '%s[ERROR]%s Compose file not found: %s\n' "$red" "$reset" "$compose_file" >&2
  exit 1
fi
printf '[INFO] Compose file  %s\n' "$compose_file"

# 2) docker available?
if ! command -v docker >/dev/null 2>&1; then
  printf '%s[ERROR]%s Docker CLI not found\n' "$red" "$reset" >&2; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf '%s[ERROR]%s Docker daemon not running\n' "$red" "$reset" >&2; exit 1
fi

# pick modern plugin if present
if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
else
  compose() { docker-compose "$@"; }
fi

# 3) does an image already exist?
image_id="$(compose -f "$compose_file" images -q "$service" 2>/dev/null | head -n1 || true)"

rebuild=no
if [ -n "$image_id" ]; then
  printf '[INFO] Found existing image for %s (%s)\n' "$service" "$image_id"
  printf 'Rebuild it? [y/N] '
  read ans || true
  ans="$(printf '%s' "$ans" | tr 'A-Z' 'a-z')"
  case "$ans" in y*) rebuild=yes ;; esac
else
  rebuild=yes
fi

# 4) build (if requested)
if [ "$rebuild" = yes ]; then
  printf '[INFO] Building image…\n'
  if ! compose -f "$compose_file" build --pull "$service"; then
    printf '%s[ERROR]%s Build failed\n' "$red" "$reset" >&2; exit 1
  fi
fi

# 5) up / recreate container
printf '[INFO] (re)creating container…\n'
if ! compose -f "$compose_file" up -d --force-recreate "$service"; then
  printf '%s[ERROR]%s docker compose failed\n' "$red" "$reset" >&2; exit 1
fi

# 6) wait for FastAPI
printf '[INFO] Waiting for backend on localhost:%s' "$port"
i=0
while [ $i -lt 30 ]; do
  if curl -fs "http://localhost:$port/ping" >/dev/null 2>&1; then
    printf ' – ready!\n'
    break
  fi
  printf '.'; i=$((i+1)); sleep 0.5
done
[ $i -eq 30 ] && printf '\n[WARN] Timed out waiting for backend (continuing)\n'

# 7) open browser
printf '[INFO] Opening browser…\n'
if command -v open >/dev/null 2>&1; then
  open "http://localhost:$port/docs" >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:$port/docs" >/dev/null 2>&1 &
else
  printf 'Please open your browser at: http://localhost:%s/docs\n' "$port"
fi

echo
printf '%s[OK] Done.%s\n' "$cyan" "$reset"
