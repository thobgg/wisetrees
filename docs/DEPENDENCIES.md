# Abhängigkeiten

Erlaubt sind Lizenzen, die mit AGPL-3.0-only verträglich sind: MIT (auch MIT-0), BSD, Apache-2.0, PSF-2.0. Für reine
Testabhängigkeiten, die nicht in den ausgelieferten Server kommen, ist zusätzlich MPL-2.0 erlaubt. Jede neue
Abhängigkeit kommt hier mit Lizenz hinein, auch mitgezogene.

## Server (`requirements.txt`)

| Paket | Fassung | Lizenz | Wofür |
|---|---|---|---|
| fastapi | 0.162.0 | MIT | Web-Rahmen |
| uvicorn | 0.54.0 | BSD-3-Clause | HTTP-Server |
| argon2-cffi | 25.1.0 | MIT | Passwort-Hashes (Argon2id) |
| python-multipart | 0.0.33 | Apache-2.0 | Formulare (Anmeldung in v1) |
| sqlalchemy | 2.1.6 | MIT | Datenbankzugriff über SQLAlchemy Core (E16); zieht nur typing_extensions mit |
| jinja2 | 3.1.6 | BSD-3-Clause | Seiten der Verwaltung im Browser (E18) |
| *mitgezogen:* starlette | 1.10.0 | BSD-3-Clause | fastapi |
| *mitgezogen:* pydantic, pydantic_core | 2.14.2, 2.50.2 | MIT | fastapi |
| *mitgezogen:* annotated-types, annotated-doc, typing-inspection | 0.8.0, 0.0.5, 0.4.4 | MIT | pydantic, fastapi |
| *mitgezogen:* typing_extensions | 4.16.0 | PSF-2.0 | pydantic, referencing, sqlalchemy |
| *mitgezogen:* opentelemetry-api | 1.45.2 | Apache-2.0 | fastapi |
| *mitgezogen:* anyio | 4.15.1 | MIT | starlette |
| *mitgezogen:* idna | 3.20 | BSD-3-Clause | anyio |
| *mitgezogen:* click | 8.5.0 | BSD-3-Clause | uvicorn |
| *mitgezogen:* h11 | 0.16.0 | MIT | uvicorn |
| *mitgezogen:* argon2-cffi-bindings | 26.1.0 | MIT | argon2-cffi |
| *mitgezogen:* cffi | 2.1.1 | MIT-0 (MIT ohne Pflicht zur Namensnennung) | argon2-cffi-bindings |
| *mitgezogen:* pycparser | 3.12 | BSD-3-Clause | cffi |
| *mitgezogen:* markupsafe | 3.0.4 | BSD-3-Clause | jinja2 |

Nicht nötig: `httpx` für FastAPIs TestClient (zöge `certifi`, MPL-2.0, mit). Die Tests sprechen einen echten uvicorn
über den Client aus `vertrag/client.py` an (nur Standardbibliothek).

## Entwicklung und Tests (`requirements-dev.txt`, nicht im ausgelieferten Server)

| Paket | Fassung | Lizenz | Wofür |
|---|---|---|---|
| pytest | 8.3.5 | MIT | Tests |
| jsonschema | 4.23.0 | MIT | Schemaprüfung der Vertragstests |
| ruff | 0.11.8 | MIT | Stilprüfung |
| *mitgezogen:* iniconfig | 2.3.1 | MIT | pytest |
| *mitgezogen:* pluggy | 1.7.0 | MIT | pytest |
| *mitgezogen:* packaging | 26.3 | Apache-2.0 oder BSD-2-Clause | pytest |
| *mitgezogen:* attrs | 26.1.0 | MIT | jsonschema |
| *mitgezogen:* jsonschema-specifications | 2025.9.1 | MIT | jsonschema |
| *mitgezogen:* referencing | 0.37.0 | MIT | jsonschema |
| *mitgezogen:* rpds-py | 2026.9.1 | MIT | jsonschema |

## Daten im Repository

| Datei | Inhalt | Lizenz |
|---|---|---|
| `backend/tests/daten/falkenrath-1.7.1.ged`, `backend/tests/daten/medien/` | Falkenrath-Demobaum 1.7.1 und ein Porträt, unverändert | CC0 |
| `vertrag/aufzeichnungen/` | festgelegte v1-Antworten am Falkenrath-Baum | CC0 (Falkenrath) |
| `vertrag/api-v1.json` | Schemata von api4wisetrees v1 | AGPL-3.0-only wie das Projekt |
