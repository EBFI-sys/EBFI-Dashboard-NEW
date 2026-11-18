#!/bin/bash
# First start of EBFI Ops on the server. Run from the repository folder: bash deploy/install.sh
set -e
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  IP=$(curl -s https://api.ipify.org || hostname -I | awk '{print $1}')
  cat > .env <<ENV
# Generated $(date -I). Keep this file secret and backed up: without ENCRYPTION_KEY the bank details cannot be read.
SITE_ADDRESS=${IP//./-}.sslip.io
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
ENV
  chmod 600 .env
  echo "Создан .env, адрес: https://$(grep SITE_ADDRESS .env | cut -d= -f2)"
fi
docker compose up -d --build
echo "Жду запуска…"
sleep 10
docker compose ps
echo
echo "Готово. Откройте https://$(grep SITE_ADDRESS .env | cut -d= -f2)"
