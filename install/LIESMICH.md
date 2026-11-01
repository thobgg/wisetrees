# wisetrees installieren

[English](README.md)

wisetrees läuft als Container. Gebraucht wird ein Rechner mit Docker: ein Linux-Server, ein Raspberry Pi oder eine
NAS mit Container-Unterstützung (Synology Container Manager, QNAP Container Station, Unraid …). Das Image gibt es für
amd64 und arm64. Eine Datenbank muss nicht eingerichtet werden: Jeder Stammbaum ist eine Datei.

Dieses Paket enthält:

- `docker-compose.yml` – lädt das fertige Image, nichts zu bauen
- `env.beispiel` – Einstellungen; als `.env` neben die `docker-compose.yml` legen

## Mit Docker Compose

```sh
mkdir wisetrees && cd wisetrees
# docker-compose.yml und env.beispiel hierher kopieren
cp env.beispiel .env          # Benutzer (id -u, id -g), Port und Datenordner anpassen
mkdir data
docker compose up -d
docker compose logs wisetrees # zeigt beim ersten Start den Einrichtungscode
```

Dann im Browser `http://<rechner>:8099/index.php` öffnen und auf **Verwaltung** gehen. Beim ersten Mal legt man dort
mit dem Einrichtungscode das erste Administratorkonto an. Danach: GEDCOM-Datei einlesen, Konten anlegen, Rollen
vergeben. Die Seite **App verbinden** nennt die Adresse für wtAnd, wtTux und wtWin.

Bilder gehören nach `data/medien/<Name des Baums>/`, mit den Pfaden aus den FILE-Zeilen der GEDCOM-Datei.

## Auf einer Synology mit dem Container Manager

1. In der File Station einen Ordner anlegen, zum Beispiel `docker/wisetrees`, darin den Unterordner `data`.
2. `docker-compose.yml` und `env.beispiel` in `docker/wisetrees` hochladen, `env.beispiel` in `.env` umbenennen.
3. In `.env` den Benutzer eintragen, unter dem wisetrees laufen soll (`WISETREES_UID`, `WISETREES_GID`). Dieser
   Benutzer braucht Schreibrecht auf `data`.
4. Im Container Manager: **Projekt** › **Erstellen**, Pfad `docker/wisetrees` wählen, die vorhandene
   `docker-compose.yml` verwenden und das Projekt starten.
5. Den Einrichtungscode findet man im Container Manager beim Container `wisetrees` unter **Protokoll**.
6. Weiter wie oben im Browser.

## Aktualisieren und sichern

- Neue Fassung: `docker compose pull && docker compose up -d` (Container Manager: Projekt › Aktion › Neu erstellen).
- Gesichert werden muss nur der Ordner `data`: `konten.sqlite` (Konten, Rollen, Sitzungen), `baeume/*.wise` (je
  Baum eine SQLite-Datei) und `medien/`.

## Erreichbarkeit

wisetrees spricht selbst kein HTTPS. Im Heimnetz reicht die Adresse oben. Für den Zugriff von außen gehört ein
Reverse Proxy mit Zertifikat davor (auf der Synology: Systemsteuerung › Anmeldeportal › Erweitert › Reverse Proxy).
Die Apps nehmen Adressen ohne HTTPS nur im Heimnetz an.
