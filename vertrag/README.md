# Vertragstests api4wisetrees v1

Prüfen einen Server darauf, ob er die Routen von v1 so beantwortet wie festgelegt. Hintergrund:
[KONZEPT.md](../docs/KONZEPT.md) 4.3 und E11, [API-V1.md](../docs/API-V1.md).

## Was geprüft wird

- **Vergleich mit Aufzeichnungen** (`aufzeichnungen/`): 32 Fälle (`faelle.py`) für 5 Rollen (Besucher, Mitglied,
  Bearbeiter, Moderator, Verwalter) am Falkenrath-Baum 1.7.1 (CC0). Die Antwort wird normalisiert
  (`normalisieren.py`: Sitzung, Token, frei vergebene Kennungen und Adressen) und muss der Aufzeichnung gleichen.
- **Form** jeder Antwort gegen die Schemadatei `api-v1.json`.
- **Fehlerantworten**: HTTP 200 mit `{ok: false, error, status}`, nie 401/407.
- **Abläufe**: Anmelden, Abmelden, falsches Passwort, falsches CSRF-Token beim Anmelden und beim Schreiben
  (302 ohne JSON), unbekannte Route (404 ohne JSON), Porträt lädt mit der Sitzung.

`aufzeichnungen/stand.json` nennt Stufe, Baum, Prüfsumme der Datei und das Datum der Aufzeichnung. Lebend/verstorben
und Altersangaben hängen vom Datum ab; wisetrees läuft in den Tests deshalb mit diesem Datum als „heute“.

## Ausführen

Einmal einrichten (Python 3.11):

    uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt

Gegen einen frischen wisetrees (Falkenrath importiert, Testkonten angelegt, danach wieder abgebaut):

    .venv/bin/python -m vertrag.wisetrees

Gegen einen beliebigen laufenden Server:

    WT_VERTRAG_URL=http://host:port .venv/bin/python -m pytest vertrag

Der Server braucht dann den Baum `falkenrath` (Falkenrath 1.7.1) und die Konten `mitglied`, `bearbeiter`,
`moderator`, `verwalter` mit dem Passwort aus `faelle.py` (oder `WT_VERTRAG_PASSWORT`). Ohne `WT_VERTRAG_URL` werden
die Tests übersprungen.

Unterschiede eines einzelnen Falls zur Aufzeichnung, Pfad für Pfad:

    .venv/bin/python -m vertrag.vergleich verwalter "Individual__xref=I21"
