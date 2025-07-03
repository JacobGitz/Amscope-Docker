#!/usr/bin/env bash
#
# Thorlabs TDC001 BACKEND one-click launcher
# • optional rebuild of the image
# • starts (or restarts) the container
# • opens http://localhost:8000/docs
#

################### configuration ########################################
compose_relative="../Code/TDC001-project/docker-compose.backend.yml"
service="tdc_backend" # docker-compose service name
port=8000             # FastAPI external port
##########################################################################

echo -e "\n\e[36m──────── Thorlabs TDC001 BACKEND launcher ────────\e[0m\n"

# 1) locate compose file -------------------------------------------------
script_dir="$(cd -- "$(dirname "$0")" && pwd)"
compose_file="$(realpath "$script_dir/$compose_relative")"

[[ -f $compose_file ]] || {
  echo -e "\e[31m[ERROR]\e[0m Compose file not found: $compose_file"
  exit 1
}
echo "[INFO] Compose file  $compose_file"

# 2) docker available? ---------------------------------------------------
command -v docker &>/dev/null || {
  echo -e "\e[31m[ERROR]\e[0m Docker CLI not found"
  exit 1
}
docker info &>/dev/null || {
  echo -e "\e[31m[ERROR]\e[0m Docker daemon not running"
  exit 1
}

# 3) does an image already exist? ---------------------------------------
image_id=$(docker compose -f "$compose_file" images -q "$service" 2>/dev/null | head -n 1)

rebuild=false
if [[ -n $image_id ]]; then
  echo "[INFO] Found existing image for $service ($image_id)"
  read -p "Rebuild it? [y/N] " ans
  [[ ${ans,,} == y* ]] && rebuild=true
else
  rebuild=true # first time → must build
fi

# 4) build (if requested) -----------------------------------------------
if $rebuild; then
  echo "[INFO] Building image…"
  docker compose -f "$compose_file" build --pull "$service" || {
    echo -e "\e[31m[ERROR]\e[0m Build failed"
    exit 1
  }
fi

# 5) up / recreate container --------------------------------------------
echo "[INFO] (re)creating container…"
docker compose -f "$compose_file" up -d --force-recreate "$service" || {
  echo -e "\e[31m[ERROR]\e[0m docker compose failed"
  exit 1
}

# 6) wait for FastAPI ----------------------------------------------------
printf "[INFO] Waiting for backend on localhost:%d" "$port"
for _ in {1..30}; do
  if curl -s "http://localhost:$port/ping" &>/dev/null; then
    echo " – ready!"
    break
  fi
  printf "."
  sleep 0.5
done

# 7) open browser --------------------------------------------------------
echo "[INFO] Opening browser…"
xdg-open "http://localhost:$port/docs" &>/dev/null &

echo -e "\n[OK] Done."
sleep 1
