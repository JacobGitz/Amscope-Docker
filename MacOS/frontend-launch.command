#!/usr/bin/env sh
###############################################################################
# Thorlabs TDC001 GUI one-click launcher – macOS-ready & future-proof (POSIX)
# * optionally rebuilds the Docker image
# * (re)creates the container
# * opens http://localhost:6080 in the default browser
###############################################################################

# ───────── configuration ─────────
compose_relative='../Code/TDC001-project/docker-compose.frontend.yml'
service='tdc_frontend'   # docker-compose service name
port=6080                # external noVNC port
# ─────────────────────────────────

set -eu

# ---- colours only when stdout is a terminal ----
if [ -t 1 ]; then
  cyan="$(printf '\033[36m')"
  red="$(printf '\033[31m')"
  reset="$(printf '\033[0m')"
else
  cyan='' red='' reset=''
fi

echo
printf '%s──────── Thorlabs TDC001 GUI launcher ────────%s\n\n' "$cyan" "$reset"

# ---- locate compose file (portable realpath) ----
script_dir="$(cd "$(dirname "$0")" && pwd)"
# resolve the relative path without realpath/readlink -f
cd "$script_dir"  # shellcheck disable=SC2164
# shellcheck disable=SC2039
compose_file="$(cd "$(dirname "$compose_relative")" && pwd)/$(basename "$compose_relative")"

if [ ! -f "$compose_file" ]; then
  printf '%s[ERROR]%s Compose file not found: %s\n' "$red" "$reset" "$compose_file" >&2
  exit 1
fi
printf '[INFO] Compose file  %s\n' "$compose_file"

# ---- Docker availability check ----
if ! command -v docker >/dev/null 2>&1; then
  printf '%s[ERROR]%s Docker CLI not found\n' "$red" "$reset" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf '%s[ERROR]%s Docker daemon not running\n' "$red" "$reset" >&2
  exit 1
fi

# detect modern plugin or legacy binary
if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
else
  compose() { docker-compose "$@"; }
fi

# ---- does an image already exist? ----
image_id="$(compose -f "$compose_file" images -q "$service" 2>/dev/null | head -n1 || true)"

rebuild=no
if [ -n "$image_id" ]; then
  printf '[INFO] Found existing image for %s (%s)\n' "$service" "$image_id"
  printf 'Rebuild it? [y/N] '
  # read uses default stdin
  read ans
  # to lower-case safely without Bash ${var,,}
  ans="$(printf '%s' "$ans" | tr 'A-Z' 'a-z')"
  case "$ans" in
    y* ) rebuild=yes ;;
  esac
else
  rebuild=yes  # no image yet → must build
fi

# ---- build (if requested) ----
if [ "$rebuild" = yes ]; then
  printf '[INFO] Building image…\n'
  if ! compose -f "$compose_file" build --pull "$service"; then
    printf '%s[ERROR]%s Build failed\n' "$red" "$reset" >&2
    exit 1
  fi
fi

# ---- up / recreate container ----
printf '[INFO] (re)creating container…\n'
if ! compose -f "$compose_file" up -d --force-recreate "$service"; then
  printf '%s[ERROR]%s docker compose failed\n' "$red" "$reset" >&2
  exit 1
fi

# ---- wait for noVNC ----
printf '[INFO] Waiting for noVNC on localhost:%s' "$port"
i=0
while [ $i -lt 30 ]; do
  if curl -fs "http://localhost:$port" >/dev/null 2>&1; then
    printf ' – ready!\n'
    break
  fi
  printf '.'
  i=$((i + 1))
  sleep 0.5
done
[ $i -eq 30 ] && printf '\n[WARN] Timed out waiting for noVNC (continuing anyway)\n'

# ---- open browser ----
printf '[INFO] Opening browser…\n'
if command -v open >/dev/null 2>&1; then
  open "http://localhost:$port" >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:$port" >/dev/null 2>&1 &
else
  printf 'Please open your browser at: http://localhost:%s\n' "$port"
fi

echo
printf '%s[OK] Done.%s\n' "$cyan" "$reset"
