#!/bin/bash
# Backup diário do código fonte → OneDrive:Della/Backups/codigo/
# Mantém os últimos 14 dias, deleta os mais antigos automaticamente.
#
# Faz tar.gz de /var/www/della-sistemas/ excluindo:
# - dependências regeráveis (node_modules, venv, __pycache__)
# - artefatos gerados (staticfiles, cache, build)
# - dados do usuário/uploads (media)
# - logs (rotacionam por conta própria)
# - .git (GitHub já é o backup do repo)
# - dados sensíveis (.env, *.csv com PII, *.xlsx, dumps)

set -e

BACKUP_DIR="/tmp/della_codigo_backups"
ONEDRIVE_PATH="onedrive:Della/Backups/codigo"
FILENAME="codigo_$(date +%Y%m%d_%H%M).tar.gz"
LOG="/var/www/della-sistemas/projetos-claude/site_della/logs/backup_codigo.log"
SOURCE_DIR="/var/www/della-sistemas"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando backup do código..." >> "$LOG"

# Tar com excludes (ordem dos --exclude antes do path)
tar -czf "$BACKUP_DIR/$FILENAME" \
    --exclude='node_modules' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='env' \
    --exclude='ENV' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='cache' \
    --exclude='staticfiles' \
    --exclude='media' \
    --exclude='logs' \
    --exclude='*.log' \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='*.csv' \
    --exclude='*.sql' \
    --exclude='*.dump' \
    --exclude='*.bak' \
    --exclude='*.xlsx' \
    --exclude='clientes*' \
    --exclude='pagseguro_*.json' \
    -C "$(dirname "$SOURCE_DIR")" "$(basename "$SOURCE_DIR")" \
    2>> "$LOG"

SIZE=$(du -h "$BACKUP_DIR/$FILENAME" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Tar gerado: $FILENAME ($SIZE)" >> "$LOG"

# Envia para o OneDrive
/usr/bin/rclone copyto "$BACKUP_DIR/$FILENAME" "$ONEDRIVE_PATH/$FILENAME" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Upload concluído." >> "$LOG"

# Remove arquivo local
rm -f "$BACKUP_DIR/$FILENAME"

# Deleta backups com mais de 14 dias do OneDrive
/usr/bin/rclone delete --min-age 15d "$ONEDRIVE_PATH/" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Limpeza de backups antigos concluída." >> "$LOG"
