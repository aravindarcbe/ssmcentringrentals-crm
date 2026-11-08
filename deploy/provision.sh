#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu EC2 instance (t3.micro/t4g.micro).
# Run as root (or via sudo) on the instance itself, after cloning this repo
# to /opt/ssm-crm. See deploy/DEPLOY.md for the full walkthrough.
#
# Usage: sudo ./deploy/provision.sh

set -euo pipefail

REPO_DIR="/opt/ssm-crm"
APP_DIR="${REPO_DIR}/webapp"
APP_USER="ssmcrm"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root (sudo ./deploy/provision.sh)" >&2
    exit 1
fi

echo "==> Installing system packages"
apt-get update
apt-get install -y python3-venv python3-pip postgresql postgresql-contrib nginx certbot python3-certbot-nginx

echo "==> Creating app user"
id -u "${APP_USER}" &>/dev/null || useradd --system --home "${REPO_DIR}" --shell /usr/sbin/nologin "${APP_USER}"

echo "==> Creating Postgres role + database (skips if they already exist)"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='ssm_crm'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE ROLE ssm_crm WITH LOGIN PASSWORD '${DB_PASSWORD:?Set DB_PASSWORD env var before running}';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='ssm_crm'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE ssm_crm OWNER ssm_crm;"

echo "==> Setting up Python virtualenv"
cd "${APP_DIR}"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f "${APP_DIR}/.env" ]; then
    echo "==> No .env found — copying .env.example. EDIT IT before starting the service:"
    echo "    DJANGO_SECRET_KEY, DJANGO_DEBUG=False, DJANGO_ALLOWED_HOSTS, DB_ENGINE=postgres, DB_PASSWORD, etc."
    cp .env.example .env
fi

echo "==> Running migrations and collecting static files"
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput

echo "==> Fixing ownership"
chown -R "${APP_USER}:www-data" "${REPO_DIR}"

echo "==> Installing systemd service"
cp "${REPO_DIR}/deploy/systemd/ssm-crm.service" /etc/systemd/system/ssm-crm.service
systemctl daemon-reload
systemctl enable --now ssm-crm

echo "==> Installing Nginx site (edit YOUR_DOMAIN in it first if you haven't)"
cp "${REPO_DIR}/deploy/nginx/ssm-crm.conf" /etc/nginx/sites-available/ssm-crm
ln -sf /etc/nginx/sites-available/ssm-crm /etc/nginx/sites-enabled/ssm-crm
nginx -t && systemctl reload nginx

echo "==> Installing nightly backup cron job"
chmod +x "${REPO_DIR}/deploy/backup/pg_backup.sh"
( crontab -l 2>/dev/null | grep -v pg_backup.sh ; echo "0 2 * * * ${REPO_DIR}/deploy/backup/pg_backup.sh >> /var/log/ssm-crm-backup.log 2>&1" ) | crontab -

echo ""
echo "Done. Remaining manual steps:"
echo "  1. Edit ${APP_DIR}/.env with real production values, then: systemctl restart ssm-crm"
echo "  2. Edit /etc/nginx/sites-available/ssm-crm, set server_name to your real domain, then: nginx -t && systemctl reload nginx"
echo "  3. Point your domain's DNS A record at this instance's Elastic IP"
echo "  4. Run: certbot --nginx -d YOUR_DOMAIN   (adds HTTPS, auto-renews via systemd timer)"
echo "  5. Create an admin login: ${APP_DIR}/.venv/bin/python ${APP_DIR}/manage.py createsuperuser"
