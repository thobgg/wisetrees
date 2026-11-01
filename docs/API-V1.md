# api4wisetrees v1

Die JSON-Schnittstelle von wisetrees für die Apps wtAnd (Android), wtTux (Linux) und wtWin (Windows). Die Form jeder
Antwort steht maschinenlesbar in [`vertrag/api-v1.json`](../vertrag/api-v1.json) (OpenAPI 3.1); dieses Dokument
beschreibt, was darüber hinaus gilt: Adressen, Anmeldung, Fehler, Sicherheit. Jeder Punkt ist durch die
Vertragstests ([`vertrag/`](../vertrag/README.md)) belegt.

Stand: Stufe 1, **lesend vollständig** (siehe 6).

## 1. Adressen

- Jede Anfrage geht an `{basis}/index.php?route={pfad}{route}&lang={sprache}[&…]`.
  - `{basis}`: die Adresse, die in der App eingetragen ist, z. B. `https://nas.example/wisetrees`.
  - `{pfad}`: der Pfadteil von `{basis}` (`/wisetrees`, leer im Wurzelverzeichnis). Er steht mit im Parameter
    `route`; wisetrees nimmt ihn dort an und schneidet ihn ab. So funktioniert wisetrees auch hinter einem
    Reverse Proxy unter einem Unterpfad.
  - `{route}` für die Schnittstelle: `/module/_api4webtrees_/{Aktion}[/{Baum}]`.
  - Weitere Parameter (`xref`, `page`, `q` …) stehen in der Abfrage.
- Unbekannte Routen: 404 ohne JSON. Daran erkennen die Apps, dass es eine Route nicht gibt.
- `lang` bestimmt Bezeichnungen und Datumsanzeige (vorerst Deutsch).
- `http://` nehmen die Apps nur im Heimnetz an (private Adressen, Loopback); sonst ist `https://` nötig.
- `index.php` ohne Route zeigt eine schlichte Startseite, `route={pfad}/wisetrees/app` die Seite „App verbinden“ mit
  der Adresse für die Apps.

## 2. Antworten und Fehler

- Eine Antwort zählt nur mit `Content-Type: application/json`. Alles andere hält die App für eine Anmelde- oder
  Fehlerseite.
- **Fachliche Fehler kommen mit HTTP 200** und `{"ok": false, "error": "…", "status": 403}`. Grund: Webserver wie
  der einer Synology ersetzen 4xx/5xx-Antworten durch eigene Seiten, die App sähe dann nur HTML.
- **wisetrees sendet nie 401 oder 407.** Die Apps deuten diese Codes als vorgeschaltete Anmeldung (SSO,
  Verzeichnisschutz) und zeigen eine Anmeldewand. Fehlende Rechte sind `ok: false` mit `status: 403`.
- Umleitungen nur auf denselben Host. Eine Umleitung auf einen anderen Host ohne JSON gilt als SSO-Anmeldeseite.
- `Info` enthält immer `api` (> 0) und `module` (nicht leer).

## 3. Anmeldung und Sitzung

- **Sitzung über ein Cookie**, auch für Besucher: `Info` liefert schon vor der Anmeldung ein CSRF-Token (`csrf`).
  Das Cookie gilt für `{pfad}`.
- **Anmelden**: `POST index.php?route={pfad}/login`, Formular (`application/x-www-form-urlencoded`) mit `_csrf`,
  `username`, `password`. Die Antwort ist eine Umleitung auf die Startseite; ob die Anmeldung geklappt hat, steht
  danach in `Info.user`. Nach fünf Fehlversuchen in fünf Minuten ist die Anmeldung von dieser Adresse aus eine
  Minute gesperrt.
- **Abmelden**: `POST index.php?route={pfad}/logout` mit leerem Formular, ohne Token.
- Lesezugriffe, `/login` und `/logout` dürfen die Apps bei Verbindungsfehlern still wiederholen; schreibende `POST`
  nicht.

## 4. Schreiben und CSRF

- Schreibende Aufrufe sind `POST` mit JSON-Rumpf und Kopfzeile `X-CSRF-TOKEN: {Info.csrf}`.
- **Ungültiges Token → Umleitung (302) ohne JSON, nichts wird ausgeführt.** Die App holt `Info` neu und wiederholt
  genau einmal.
- Jeder ausgeführte Schreibzugriff antwortet mit JSON, auch im Fehlerfall. Eine Antwort ohne JSON und ohne
  Umleitung bedeutet für die App „Ausgang unklar“; sie wiederholt dann nicht.
- Antwort auf Schreibzugriffe: `ok`, oft `xref`, und `pending: true`, wenn die Änderung auf Freigabe wartet.

## 5. Inhalte

- **Bild-Adressen** (`thumb`, Medien) sind für die Apps undurchsichtig; sie laden sie mit dem Sitzungs-Cookie.
  wisetrees liefert sie unter `index.php?route={pfad}/wisetrees/medien/{Baum}/{Medium}` aus `<daten>/medien/{Baum}/`,
  nur sichtbare Medien.
- **`factId`** ist eine stabile Kennung je Fakt, für die Apps nur eine Zeichenkette. Sie beginnt nie mit `assoc-`
  (dieses Präfix nutzen die Apps selbst). Nach einer Änderung bleibt sie gleich.
- **Offene Änderungen** sehen nur Bearbeiter, Moderatoren und Verwalter; Fakten tragen dann `pending: true`.
- **Sichtbarkeit**: Lebende sehen erst Mitglieder, Verstorbene alle; Namen Lebender ab Mitglied. Quellen und
  Archive sehen erst Mitglieder (ein verborgenes Archiv erscheint mit Kennung, ohne Namen). Ein Medium ist
  verborgen, wenn ein Datensatz, der es verwendet, verborgen ist. Familien sind sichtbar, wenn alle Mitglieder es
  sind. Sperrvermerke (`RESN`) gehen vor. Die Lebend-Regel steht in [KONZEPT.md](KONZEPT.md) 5.2.

## 6. Stufen und `Info`

- `Info.api` meldet Stufe 1. Stufe 1 heißt vorerst **„lesend vollständig“**: Info, Individuals, Individual, Family,
  Pedigree, Descendants, Tags. Die Schreibrouten der Stufe 1 (Fact, DeleteFact, AddIndividual, Media) fehlen noch.
  **Bis es sie gibt, Konten für Tester nur als Mitglied anlegen, nicht als Bearbeiter** – die Apps böten sonst
  Bearbeiten an, das scheitert.
- Die Apps schalten mit Stufe 1 Fotos, Jahrestage, Orte usw. ab; nicht vorhandene Routen fangen sie ab.
- `availableModules`, `maxUpload` und `rewriteUrls` beschreiben den Server selbst (Module: nur die Schnittstelle).
  Die Vertragstests prüfen sie nur auf ihre Form.

## 7. Nicht Teil von v1

Die Apps kennen noch weitere Wege (Export einer GEDCOM-Datei über eine Webseite, Archiv-Routen, Seiten im Browser
über die `url`-Felder). wisetrees bietet sie nicht an; die Apps fangen ihr Fehlen ab.
