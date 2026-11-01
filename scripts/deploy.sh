#!/usr/bin/env bash
# Nasazení nové verze na PythonAnywhere – spustit v Bash konzoli:
#     ~/panther-security/scripts/deploy.sh
# Stáhne kód, doinstaluje knihovny, provede migrace a statické soubory,
# zkontroluje nastavení a restartuje web. Při jakékoli chybě se zastaví
# dřív, než web restartuje, takže běžící verze zůstane beze změny.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VENV:-$HOME/.virtualenvs/panther313}"
WSGI_FILE="${WSGI_FILE:-/var/www/www_panther-security_cz_wsgi.py}"
PYTHON="$VENV/bin/python"

cd "$PROJECT_DIR"
echo "==> Stahuji kód (git pull)"
git pull --ff-only

echo "==> Instaluji knihovny"
"$VENV/bin/pip" install --quiet -r requirements.txt

echo "==> Automatické testy"
"$PYTHON" manage.py test --settings=config.settings_test --verbosity 1

echo "==> Kontrola nastavení"
"$PYTHON" manage.py check --deploy --fail-level ERROR

echo "==> Migrace databáze"
"$PYTHON" manage.py migrate --noinput

echo "==> Statické soubory"
"$PYTHON" manage.py collectstatic --noinput --verbosity 0

echo "==> Restart webu"
# Změna času WSGI souboru = Reload na záložce Web
touch "$WSGI_FILE"

echo "✅ Hotovo – nasazena verze $(git log -1 --format='%h %s')"
