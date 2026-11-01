# wisetrees als Container. Läuft nicht als root.
FROM python:3.11-slim

# Benutzer im Container; beim Bauen einstellbar (--build-arg), beim Start auch (docker run --user / compose user:).
ARG WISETREES_UID=1000
ARG WISETREES_GID=1000

# tzdata: ohne Zonendaten bleibt die Uhr des Containers still auf UTC, auch wenn TZ gesetzt ist.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "$WISETREES_GID" wisetrees \
    && useradd --uid "$WISETREES_UID" --gid "$WISETREES_GID" --no-create-home --home-dir /data --shell /usr/sbin/nologin wisetrees \
    && mkdir -p /data && chown "$WISETREES_UID:$WISETREES_GID" /data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY werkzeuge/ ./werkzeuge/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh

# Konten, Sitzungen und die Bäume (*.wise) liegen im Datenordner; er muss dem Benutzer gehören.
ENV WISETREES_DATEN=/data PYTHONDONTWRITEBYTECODE=1
VOLUME /data
EXPOSE 8099

USER wisetrees
WORKDIR /app/backend
ENTRYPOINT ["/app/entrypoint.sh"]
