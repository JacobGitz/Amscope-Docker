#!/usr/bin/env bash
#
# Thorlabs TDC001 backend stopper
# • stops (or, on request, removes) the backend container
#

################### configuration ########################################
compose_relative="../Code/TDC001-project/docker-compose.backend.yml"
service="tdc_backend"           # docker-compose service name
##########################################################################

echo -e "\n\e[36m──── stopping TDC001 BACKEND ────\e[0m\n"

# locate compose file ----------------------------------------------------
script_dir="$(cd -- "$(dirname "$0")" && pwd)"
compose_file="$(realpath "$script_dir/$compose_relative")"

[[ -f $compose_file ]] || { echo "[ERROR] Compose file not found: $compose_file"; exit 1; }

# docker available? ------------------------------------------------------
command -v docker &>/dev/null || { echo "[ERROR] docker not found"; exit 1; }
docker info &>/dev/null || { echo "[ERROR] Docker daemon not running"; exit 1; }

# stop service -----------------------------------------------------------
echo "[INFO] Stopping container…"
docker compose -f "$compose_file" stop "$service"

# optional remove --------------------------------------------------------
read -p "Remove the container too? [y/N] " ans
if [[ ${ans,,} == y* ]]; then
  echo "[INFO] Removing container…"
  docker compose -f "$compose_file" rm -f "$service"
fi

echo -e "\n[OK] Done."
