#!/bin/sh
# Startet wisetrees im Container.
echo "wisetrees $(cat /app/backend/version.txt) – Python $(python3 --version 2>&1 | cut -d' ' -f2) – Benutzer $(id -u):$(id -g) – Port ${WISETREES_PORT:-8099}"
if [ ! -w "${WISETREES_DATEN:-/data}" ]; then
    echo "FEHLER: ${WISETREES_DATEN:-/data} ist für Benutzer $(id -u):$(id -g) nicht beschreibbar (Eigentümer des Datenordners prüfen)." >&2
    exit 1
fi
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "${WISETREES_PORT:-8099}" --proxy-headers --log-level info
