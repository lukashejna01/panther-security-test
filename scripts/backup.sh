#!/usr/bin/env bash
# Noční záloha databáze a nahraných souborů (smlouvy, faktury, doklady).
# Na PythonAnywhere: záložka Tasks → Scheduled task, denně, příkaz:
#     ~/panther-security/scripts/backup.sh
#
# Záloha je zašifrovaná (AES-256) heslem BACKUP_PASSPHRASE z .env – bez něj
# ji nikdo nepřečte, ani kdyby unikla. Heslo si uložte i mimo server, jinak
# zálohu neobnovíte. Starší zálohy než BACKUP_KEEP_DAYS (výchozí 14) se mažou.
#
# Obnova:
#     openssl enc -d -aes-256-cbc -pbkdf2 -in ZALOHA.tar.gz.enc -pass env:BACKUP_PASSPHRASE | tar xz
set -euo pipefail
umask 077

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/zalohy}"

# Hodnoty z .env (bez spouštění jeho obsahu jako kódu)
env_value() {
    # Chybějící hodnota = prázdný řetězec (grep bez shody nesmí ukončit skript)
    { grep -E "^$1=" "$PROJECT_DIR/.env" || true; } | tail -n 1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
}
DB_PASSWORD="$(env_value DB_PASSWORD)"
BACKUP_PASSPHRASE="$(env_value BACKUP_PASSPHRASE)"
BACKUP_KEEP_DAYS="$(env_value BACKUP_KEEP_DAYS)"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
export BACKUP_PASSPHRASE

if [ ${#BACKUP_PASSPHRASE} -lt 20 ]; then
    echo "Chybí BACKUP_PASSPHRASE v .env (aspoň 20 znaků) – záloha se nevytvořila." >&2
    exit 1
fi

DB_USER=panthersec
DB_HOST=panthersec.mysql.pythonanywhere-services.com
DB_NAME='panthersec$panther'

STAMP="$(date +%Y-%m-%d_%H%M)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Heslo do databáze přes dočasný soubor – na příkazové řádce by bylo vidět v seznamu procesů.
# V uvozovkách, aby znak # v hesle nezačal komentář.
DB_PASSWORD_ESCAPED="${DB_PASSWORD//\\/\\\\}"
DB_PASSWORD_ESCAPED="${DB_PASSWORD_ESCAPED//\"/\\\"}"
cat > "$WORK/my.cnf" <<CNF
[client]
user=$DB_USER
password="$DB_PASSWORD_ESCAPED"
host=$DB_HOST
CNF

echo "==> Databáze"
mysqldump --defaults-extra-file="$WORK/my.cnf" --no-tablespaces --single-transaction \
    --routines --default-character-set=utf8mb4 "$DB_NAME" > "$WORK/databaze.sql"

echo "==> Soubory (media)"
mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/panther_$STAMP.tar.gz.enc"
tar czf - -C "$WORK" databaze.sql -C "$PROJECT_DIR" media \
    | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT"

echo "==> Mažu zálohy starší než $BACKUP_KEEP_DAYS dní"
find "$BACKUP_DIR" -name 'panther_*.tar.gz.enc' -mtime "+$BACKUP_KEEP_DAYS" -delete

echo "✅ Záloha $OUT ($(du -h "$OUT" | cut -f1))"
