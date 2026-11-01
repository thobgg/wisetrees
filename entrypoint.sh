#!/bin/sh
# Startet wisetrees im Container.
DATEN="${WISETREES_DATEN:-/data}"
echo "wisetrees $(cat /app/backend/version.txt) – Python $(python3 --version 2>&1 | cut -d' ' -f2) – Benutzer $(id -u):$(id -g) – Port ${WISETREES_PORT:-8099}"
if [ ! -w "$DATEN" ]; then
    echo "FEHLER: $DATEN ist für Benutzer $(id -u):$(id -g) nicht beschreibbar (Eigentümer des Datenordners prüfen)." >&2
    exit 1
fi
# Konten, Sitzungen und Bäume nur für den Eigentümer: neue Dateien ohne Rechte für andere, und der Datenordner selbst
# zu – auf einer NAS erben Dateien sonst die offenen Zugriffslisten des Ordners darüber.
umask 077
if [ "$(stat -c %u "$DATEN")" = "$(id -u)" ]; then
    chmod 700 "$DATEN" || echo "Hinweis: Rechte von $DATEN ließen sich nicht auf 700 setzen." >&2
fi
# Weiterleitungsköpfe (X-Forwarded-Proto, X-Forwarded-For) nur von diesen Adressen glauben: Reverse Proxy auf demselben
# Rechner kommt über ein internes Docker-Netz.
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "${WISETREES_PORT:-8099}" --proxy-headers \
    --forwarded-allow-ips "${WISETREES_PROXY:-127.0.0.1,172.16.0.0/12}" --log-level info
