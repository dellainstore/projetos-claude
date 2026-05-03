#!/bin/bash
# Backup diário do banco della_site → OneDrive:Della/Backups/site_della/
# Mantém os últimos 30 dias, deleta os mais antigos automaticamente.

set -e

BACKUP_DIR="/tmp/della_backups"
ONEDRIVE_PATH="onedrive:Della/Backups/site_della"
FILENAME="della_site_$(date +%Y%m%d_%H%M).sql.gz"
LOG="/var/www/della-sistemas/projetos-claude/site_della/logs/backup_db.log"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando backup..." >> "$LOG"

# Exporta senha do banco a partir do .env
export PGPASSWORD=$(grep '^DB_PASSWORD=' /var/www/della-sistemas/projetos-claude/site_della/.env | cut -d'=' -f2)

# Gera o dump comprimido
pg_dump -U della_user -h localhost della_site | gzip > "$BACKUP_DIR/$FILENAME"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Dump gerado: $FILENAME" >> "$LOG"

# Envia para o OneDrive
/usr/bin/rclone copyto "$BACKUP_DIR/$FILENAME" "$ONEDRIVE_PATH/$FILENAME" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Upload concluído." >> "$LOG"

# Remove arquivo local
rm -f "$BACKUP_DIR/$FILENAME"

# Deleta backups com mais de 30 dias do OneDrive
/usr/bin/rclone delete --min-age 31d "$ONEDRIVE_PATH/" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Limpeza de backups antigos concluída." >> "$LOG"
