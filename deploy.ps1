# ─────────────────────────────────────────────────────────────────────
# FinData API deploy script (Docker-based)
#
# What this does:
#   1. Package the local source into deploy.tar.gz (excluding junk).
#   2. Upload it to the EC2 instance via scp.
#   3. On the EC2: extract, free disk space, rebuild the Docker image,
#      then recreate the API container on the existing findata-net
#      network so it can talk to the findata-db Postgres container.
#
# Prerequisites on the EC2 (one-time setup, already done):
#   - Docker installed
#   - findata-net network exists
#   - findata-db (postgres:16) container running on findata-net
#   - findata-pgdata volume exists (persists DB data)
#   - ~/findata-api/.env exists with DATABASE_URL pointing to findata-db
# ─────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

$EC2_HOST = "ubuntu@3.107.112.100"
$KEY_FILE = "findata-key.pem"

Write-Host "==> Packaging local source..." -ForegroundColor Cyan
tar.exe -czf deploy.tar.gz `
    --exclude='.venv' `
    --exclude='.git' `
    --exclude='__pycache__' `
    --exclude='*.pem' `
    --exclude='.vscode' `
    --exclude='data' `
    --exclude='companies_json' `
    --exclude='test.ipynb' `
    --exclude='deploy.tar.gz' `
    --exclude='*.egg-info' `
    --exclude='build' `
    .

Write-Host "==> Uploading to EC2..." -ForegroundColor Cyan
scp -o StrictHostKeyChecking=no -i $KEY_FILE deploy.tar.gz "${EC2_HOST}:~/deploy.tar.gz"

Write-Host "==> Deploying on EC2 (this may take a few minutes)..." -ForegroundColor Cyan
ssh -o StrictHostKeyChecking=no -i $KEY_FILE $EC2_HOST @'
set -e

echo "--- Extracting source ---"
mkdir -p ~/findata-api
tar -xzf ~/deploy.tar.gz -C ~/findata-api

echo "--- Freeing disk space (removing unused Docker layers) ---"
sudo docker image prune -af
sudo docker builder prune -af
df -h /

echo "--- Ensuring Docker network and Postgres container exist ---"
sudo docker network create findata-net 2>/dev/null || echo "network exists"
if [ -z "$(sudo docker ps -q -f name=findata-db)" ]; then
  echo "Postgres container missing — creating it"
  sudo docker volume create findata-pgdata
  sudo docker run -d \
    --name findata-db \
    --network findata-net \
    --restart unless-stopped \
    -e POSTGRES_PASSWORD=Yena0907 \
    -e POSTGRES_DB=postgres \
    -v findata-pgdata:/var/lib/postgresql/data \
    postgres:16
  sleep 5
else
  echo "Postgres container already running"
fi

echo "--- Building new API image ---"
cd ~/findata-api
sudo docker build -t findata-api .

echo "--- Recreating API container ---"
sudo docker rm -f findata-api-container 2>/dev/null || true
sudo docker run -d \
  --name findata-api-container \
  --network findata-net \
  --restart unless-stopped \
  -p 80:8000 \
  --env-file /home/ubuntu/findata-api/.env \
  findata-api

echo "--- Waiting for API to boot ---"
sleep 5

echo "--- Health check ---"
curl -sf http://localhost/health && echo " OK" || echo "HEALTH CHECK FAILED"

echo "--- Container status ---"
sudo docker ps

echo "--- Deploy complete ---"
'@

Write-Host "==> Done." -ForegroundColor Green
Write-Host "Test with: curl http://3.107.112.100/health" -ForegroundColor Yellow
