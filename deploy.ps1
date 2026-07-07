# ─────────────────────────────────────────────────────────────────────
# FinData API deploy script (Docker-based, SQLite single-container model)
#
# What this does:
#   1. Package the local source into deploy.tar.gz (excluding junk).
#   2. Upload it to the EC2 instance via scp.
#   3. On the EC2: extract, then run deploy_remote.sh which installs Docker
#      (if missing), ensures swap, builds the image, and runs the API
#      container with a persistent `findata-data` volume for the SQLite DBs.
#
# DB: SQLite (no Postgres). DATABASE_URL is left unset in .env, so the app
#     uses per-file SQLite under FINDATA_DATA_DIR (=/data/findata, on the
#     mounted `findata-data` volume). Nothing else to provision.
#
# Before first use: set $EC2_HOST below to the new instance's IP, and make
# sure $KEY_FILE is the matching .pem.
# ─────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

$EC2_HOST = "ubuntu@13.54.120.122"
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
# Single-line remote command (no fragile inline heredoc): extract, then run the
# LF-terminated deploy_remote.sh that ships inside the tarball.
ssh -o StrictHostKeyChecking=no -i $KEY_FILE $EC2_HOST "set -e; mkdir -p ~/findata-api; tar -xzf ~/deploy.tar.gz -C ~/findata-api; bash ~/findata-api/deploy_remote.sh"

Write-Host "==> Done." -ForegroundColor Green
Write-Host "Test with: curl http://<new-ip>/health" -ForegroundColor Yellow
