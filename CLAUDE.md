# Regeln für die Arbeit an wisetrees

Diese Regeln gelten für jede Sitzung in diesem Repository.

## Entscheidungen und Doku

- Entscheidungen stehen in [docs/KONZEPT.md](docs/KONZEPT.md), Abschnitt 9 (E1, E2 …). Neue Entscheidungen dort
  eintragen, bevor Code sie umsetzt.
- Was die Apps von der Schnittstelle brauchen und wann es kommt: [docs/FUNKTIONEN.md](docs/FUNKTIONEN.md).
- Die Schnittstelle api4wisetrees v1: [docs/API-V1.md](docs/API-V1.md) und `vertrag/api-v1.json`. v1 ist fest; die
  Routen bleiben im Code unverändert und unkommentiert.
- Abhängigkeiten mit Lizenz: [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).
- Das Schema der Datenbanken steht in [docs/SCHEMA.md](docs/SCHEMA.md); die Datei wird mit
  `python werkzeuge/schema_doku.py` aus dem Code erzeugt, nie von Hand bearbeitet.

## Arbeitsweise

- Nach jedem Schritt anhalten und das Ergebnis zeigen; erst nach Freigabe weiter.
- Entscheidungen, die das Datenmodell oder die Schnittstelle festlegen: Optionen kurz nennen und fragen, nicht selbst
  entscheiden.
- Nur als fertig melden, was durch Tests belegt ist. Unit-Tests und Vertragstests müssen grün sein:

      .venv/bin/ruff check .
      .venv/bin/python -m pytest backend/tests
      .venv/bin/python -m vertrag.wisetrees

- Kleine Commits mit einem Thema, jeder mit Tests.
- Pushen, Tags und Veröffentlichungen nur auf ausdrücklichen Auftrag.

## Sprache

- Doku und Oberfläche zuerst Deutsch, dann Englisch. Code: deutsche Namen und Kommentare; Tabellen- und
  Spaltennamen der Baumdatei englisch.
- Sachlich, ohne Werbesprache. Generisches Maskulinum (Bearbeiter, Mitglied), keine Paarformen oder Sternchen.
- Deutsche Texte ohne persönliche Anrede, wo es geht.

## Lizenz und Abhängigkeiten

- wisetrees steht unter **AGPL-3.0-only**. Kein Code aus fremden Projekten.
- Erlaubte Lizenzen für Abhängigkeiten: MIT (auch MIT-0), BSD, Apache-2.0, PSF-2.0. Für reine Testabhängigkeiten
  zusätzlich MPL-2.0. Jede neue Abhängigkeit, auch mitgezogene, mit Lizenz in `docs/DEPENDENCIES.md` eintragen.

## Öffentliche Texte

Gilt für Dateien, Kommentare und Commit-Nachrichten:

- Keine Herkunftsangaben zu anderen Projekten und keine Vergleiche mit anderen Programmen; Begründungen stehen für
  sich.
- Keine Geheimnisse und Zugangsdaten, keine lokalen Pfade oder Adressen, keine persönlichen Daten.
- Keine Namen echter Personen außer dem Urheber; Testdaten sind erfunden (Falkenrath-Demobaum, CC0).
- Keine internen Notizen oder Bemerkungen über andere Projekte oder Personen.
- Werkzeuge, die nur der eigenen Entwicklung dienen, liegen in `intern/` (nicht im Repository).
