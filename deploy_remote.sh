#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Remote deploy steps, run ON the EC2 box by deploy.ps1.
# Single-container SQLite model: no Postgres container, no network, no RDS.
# The SQLite DB files live in the `findata-data` volume mounted at /data
# (FINDATA_DATA_DIR=/data/findata in .env), so they survive redeploys.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="$HOME/findata-api"

echo "--- Ensuring Docker is installed ---"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found; installing docker.io ..."
  sudo apt-get update -y
  sudo apt-get install -y docker.io
  sudo systemctl enable --now docker
fi

echo "--- Ensuring 1G swap (protects the pip build on a 1GB t2.micro) ---"
if ! sudo swapon --show | grep -q '/swapfile'; then
  sudo fallocate -l 1G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "--- Freeing old Docker layers (small disk) ---"
sudo docker image prune -af || true
sudo docker builder prune -af || true

echo "--- Building API image ---"
cd "$APP_DIR"
sudo docker build -t findata-api .

echo "--- (Re)creating API container ---"
sudo docker volume create findata-data >/dev/null
sudo docker rm -f findata-api-container 2>/dev/null || true
sudo docker run -d \
  --name findata-api-container \
  --restart unless-stopped \
  -p 80:8000 \
  --env-file "$APP_DIR/.env" \
  -v findata-data:/data \
  findata-api

echo "--- Waiting for API to boot ---"
sleep 5

echo "--- Health check ---"
curl -sf http://localhost/health && echo " OK" || echo "HEALTH CHECK FAILED"

echo "--- Container status ---"
sudo docker ps
echo "--- Deploy complete ---"
