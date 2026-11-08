#!/usr/bin/env bash
# Nightly Postgres backup for the SSM CRM database. Run via cron as the
# postgres-capable deploy user, e.g. in root's crontab:
#   0 2 * * * /opt/ssm-crm/deploy/backup/pg_backup.sh >> /var/log/ssm-crm-backup.log 2>&1
#
# Keeps the last 14 days locally. Set AWS_S3_BACKUP_BUCKET to also push each
# dump to S3 (requires the aws CLI configured with write access to that bucket).

set -euo pipefail

DB_NAME="${DB_NAME:-ssm_crm}"
BACKUP_DIR="/opt/ssm-crm/backups"
RETENTION_DAYS=14
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/${DB_NAME}-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

pg_dump -U "${DB_USER:-ssm_crm}" -h "${DB_HOST:-localhost}" "${DB_NAME}" | gzip > "${DUMP_FILE}"
echo "Backed up ${DB_NAME} to ${DUMP_FILE}"

find "${BACKUP_DIR}" -name "${DB_NAME}-*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

if [ -n "${AWS_S3_BACKUP_BUCKET:-}" ]; then
    aws s3 cp "${DUMP_FILE}" "s3://${AWS_S3_BACKUP_BUCKET}/$(basename "${DUMP_FILE}")"
    echo "Pushed backup to s3://${AWS_S3_BACKUP_BUCKET}/"
fi
