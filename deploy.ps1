tar.exe -czf deploy.tar.gz --exclude='.venv' --exclude='.git' --exclude='__pycache__' --exclude='*.pem' --exclude='.vscode' .
scp -o StrictHostKeyChecking=no -i findata-key.pem deploy.tar.gz ubuntu@3.107.112.100:~
ssh -o StrictHostKeyChecking=no -i findata-key.pem ubuntu@3.107.112.100 "
  mkdir -p findata-api
  tar -xzf deploy.tar.gz -C findata-api
  cd findata-api
  sudo apt-get update
  sudo apt-get install -y python3-pip python3-venv libpq-dev
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -e '.[all]'
  
  sudo bash -c 'cat > /etc/systemd/system/findata-api.service << EOF
[Unit]
Description=FinData API Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/findata-api
ExecStart=/home/ubuntu/findata-api/.venv/bin/uvicorn findata.server.app:app --host 0.0.0.0 --port 80
Restart=always
AmbientCapabilities=CAP_NET_BIND_SERVICE
EnvironmentFile=/home/ubuntu/findata-api/.env

[Install]
WantedBy=multi-user.target
EOF'

  sudo systemctl daemon-reload
  sudo systemctl enable findata-api
  sudo systemctl restart findata-api
"
