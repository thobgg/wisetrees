# wisetrees

**Deutsch** · [English](README.md)

Ein selbst gehosteter Genealogie-Server mit eigener JSON-Schnittstelle. Er hält Personen, Ereignisse, Orte und Quellen
als eigenes Datenmodell; GEDCOM ist das Austauschformat. Ein Ereignis wie eine Taufe ist ein Objekt, an dem
Täufling, Eltern und Paten mit ihrer Rolle hängen; Orte haben datierte Namen und eine datierte Zugehörigkeit.

![wtTux zeigt den Falkenrath-Demobaum aus wisetrees](docs/img/wttux-falkenrath.jpg)

## Stand

**Was geht**

- GEDCOM 5.5.1 mit GEDCOM-L einlesen. Jede Zeile wird übernommen oder bleibt als Rest an ihrer Stelle; der
  Importbericht zählt beides und nennt unsichere Ortszuordnungen.
- Die Schnittstelle [api4wisetrees v1](docs/API-V1.md) zum Lesen: Personenliste und Suche, Person, Familie,
  Vorfahren, Nachkommen, Faktenarten, Bilder. Sichtbarkeit je Rolle (Besucher, Mitglied, Bearbeiter, Moderator,
  Verwalter) einschließlich Schutz lebender Personen.
- Schreiben über v1 mit Moderation: Fakten anlegen, ändern und löschen; Personen anlegen, verknüpfen und lösen,
  Personen und Familien löschen. Änderungen von Bearbeitern bleiben offen, bis ein Moderator oder Verwalter sie
  annimmt oder verwirft; offene Änderungen sehen Bearbeiter und höher, Besucher und Mitglieder nie. Mit Vertragstests
  gegen die Referenz geprüft; in den Apps noch nicht ausprobiert.
- wtTux zeigt den Falkenrath-Demobaum aus wisetrees: Baum, Navigator, Personentafel mit Paten, Quellen und Fotos.
  wtAnd nutzt denselben Kern; der Test am Gerät steht aus.
- Konten, Rollen je Baum, Sitzungen; Betrieb als Docker-Container (nicht als root).
- Verwaltung im Browser für Administratoren: Ersteinrichtung mit Einmal-Code, Konten anlegen, Passwörter und Rollen
  setzen, GEDCOM hochladen und einlesen mit Importbericht, Bäume löschen. Jedes Konto kann dort sein Passwort ändern.
- Datenschutz einstellbar je Baum: Schutz an/aus, Baum nur für Mitglieder, Verstorbene und Namen privater Personen
  ab Rolle, private Beziehungen, Höchstalter, Schutz nach Geburt oder Tod, Regeln je Art, Datensatz und Faktart. Je
  Konto: „Das bin ich“ und Verwandtschaftsschutz (Lebende nur bis zu einer Zahl von Verwandtschaftsschritten).
- Datenbankzugriff über SQLAlchemy Core mit portablem Schema ([docs/SCHEMA.md](docs/SCHEMA.md)).

**Was fehlt**

- Medien hochladen und die übrigen Teile von Meilenstein 2: der ganze Baum seitenweise für die Apps, Gerät koppeln,
  Merkliste, Jahrestage.
- GEDCOM-Export und der Rundlauf-Test Import → Export → Import.
- GEDCOM 7.0, Zeichensatz ANSEL.
- PostgreSQL und MariaDB als Alternative zu SQLite.
- Verwandtschaftsbezeichnungen über nahe Verwandte hinaus („Partners Urgroßvater“).

**Als Nächstes**

Die übrigen Teile von Meilenstein 2 in der Reihenfolge von [docs/FUNKTIONEN.md](docs/FUNKTIONEN.md) 1.3: Fotos
(hochladen, verknüpfen, Hauptbild, Vorschaubilder), der ganze Baum seitenweise, Gerät koppeln, Merkliste, Jahrestage.
Das Konzept mit allen Entscheidungen steht in [docs/KONZEPT.md](docs/KONZEPT.md).

## Ausprobieren

Fertige Installation mit Docker oder dem Synology Container Manager: [install/LIESMICH.md](install/LIESMICH.md), als
Paket an jedem Release. Aus dem Quelltext:

```sh
mkdir -p data
docker compose up -d --build
docker compose logs wisetrees     # zeigt beim ersten Start den Einrichtungscode
```

Danach `http://<host>:8099/index.php` öffnen und auf „Verwaltung“ gehen: Beim ersten Mal legt man dort mit dem
Einrichtungscode das erste Administratorkonto an. Danach lassen sich weitere Konten anlegen und GEDCOM-Dateien
einlesen; die Seite „App verbinden“ nennt die Adresse für die Apps. Bäume liegen als `data/baeume/<name>.wise` (SQLite), Bilder unter `data/medien/<name>/`.

Tests (Python 3.11):

```sh
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest backend/tests      # Unit-Tests
.venv/bin/python -m vertrag.wisetrees         # Vertragstests der Schnittstelle
```

## Mitmachen

Ideen und Fehlerberichte sind willkommen, siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## Lizenz

[AGPL-3.0-only](LICENSE). Abhängigkeiten und ihre Lizenzen: [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

Entwickelt mit Claude Code.
