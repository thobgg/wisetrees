# wisetrees – Konzept

Stand: 01.11.2026, Entwurf 5. Die Entscheidungen stehen in Abschnitt 9.

## 1. Worum es geht

wisetrees ist ein selbst gehosteter Genealogie-Server. Er speichert einen
oder mehrere Stammbäume in SQLite, liefert sie über eine JSON-API an Apps
aus und tauscht sie über GEDCOM mit anderen Programmen aus.

Drei Grundsätze bestimmen ihn:

1. **Das Datenmodell ist nicht GEDCOM.** wisetrees hält Personen,
   Ereignisse, Orte und Quellen als eigene Tabellen mit Verweisen, nicht als
   GEDCOM-Text, der bei jedem Zugriff neu gelesen wird. GEDCOM entsteht nur
   beim Import und Export.
2. **Es denkt von der Quelle her.** Eine Person im Stammbaum ist eine
   Schlussfolgerung aus Einträgen in Quellen. Das Modell sieht dafür eine
   eigene Ebene vor (Abschnitt 3.6), auch wenn sie anfangs noch nicht
   gebaut wird.
3. **Kein Lock-in.** Die Daten gehören dem Betreiber. Er kann wisetrees
   jederzeit verlassen, ohne Angaben zu verlieren und ohne wisetrees zum
   Auslesen zu brauchen.

Prüfliste zu Grundsatz 3. Ein Punkt gilt erst als erfüllt, wenn ein Test
oder eine veröffentlichte Spezifikation ihn belegt.

| Punkt | Belegt durch | Stand |
| ----- | ------------ | ----- |
| GEDCOM 5.5.1 ohne Verlust | Rundlauf-Test Import → Export → Import (Abschnitt 6) | Import da, Export und Rundlauf offen |
| GEDCOM 7.0 ohne Verlust | Rundlauf-Test wie oben | offen |
| `.wise` ist offenes SQLite | Datei mit jedem SQLite-Werkzeug lesbar; Schema dokumentiert (`docs/SCHEMA.md`, aus dem Code erzeugt, Test prüft den Stand) | erfüllt |
| WTX mit offener Spezifikation | Spezifikation im Repository, Rundlauf-Test (E13) | vorgesehen |
| Dokumentierte API | `docs/API-V1.md` und Schema `vertrag/api-v1.json`, Vertragstests | erfüllt für v1 lesend |
| Offene Datenbanken | SQLite; PostgreSQL als Option (E16) | SQLite da, PostgreSQL offen |
| Freie Lizenz | AGPL-3.0-only, Abhängigkeiten nur mit verträglichen Lizenzen (`docs/DEPENDENCIES.md`) | erfüllt |
| Nächtliche GEDCOM-Sicherung | Export je Baum in den Datenordner, einstellbar, mit Test | offen, folgt auf den Export |

## 2. Ausgangslage

| Was | Rolle für wisetrees |
|---|---|
| Apps wtAnd (Android), wtTux (Linux), wtWin (Windows) | Clients von api4wisetrees v1; sie sollen unverändert laufen |
| api4wisetrees v1 | die Schnittstelle zu den Apps, beschrieben in [API-V1.md](API-V1.md) und `vertrag/api-v1.json` |
| Falkenrath-Demobaum 1.7.1 (CC0) | Testdaten: 492 Personen, 154 Familien, 204 Quellen, 40 Archive, 142 Medien, 5 `_LOC`; GEDCOM 5.5.1 mit GEDCOM-L und als 7.0 |

Technik: Python 3.11, FastAPI, SQLite, pytest, ruff, kein Frontend-Build;
Betrieb in Docker. Konten mit Argon2id und Dummy-Hash gegen das
Ausprobieren von Benutzernamen, Sitzungen mit gespeichertem Token-Hash,
Sperre nach Fehlversuchen, Rechteprüfung an genau einer Stelle.

## 3. Datenmodell

Grundsatz: **Jede Angabe hat einen Ort im Modell, nichts geht beim Import
verloren.** Was das Modell (noch) nicht kennt, bleibt als GEDCOM-Rest am
Objekt hängen und kommt beim Export wieder heraus (E9).

### 3.1 Übersicht

```
                 Belegebene (später)
   Quelle ── Eintrag ── Persona ──Zuordnung (Begründung)──┐
     │                                                     │
     │ Zitat                     Ebene der Schlussfolgerung ▼
     ├────────────► Ereignis ◄──Ereignisverweis (Rolle)── Person
     │                 │                                    │
     │                 ▼                                    ▼
     │                Ort ──datierte Hierarchie──► Ort    Name(n)
     │                                                      │
     └────────────► Familie ◄──Mitglied (Rolle)─────────────┘
```

### 3.2 Personen und Namen

- **Person**: Kennung, Geschlecht (`M`, `F`, `X`, `U` – X kennen
  GEDCOM-L und 7.0), Schutzvermerk (RESN), Zeitstempel. Lebensdaten
  stehen nicht an der Person, sie ergeben sich aus den Ereignissen.
- **Name**: beliebig viele je Person, mit Art (Geburtsname, Ehename,
  angenommener Name …), Teilen (Vornamen, Rufname `_RUFNAME`, Spitzname,
  Präfix, Familienname, Suffix) und Reihenfolge. Der erste Name ist der
  Hauptname.

### 3.3 Ereignisse und Rollen

- **Ereignis**: Art (Geburt, Taufe, Heirat, Beruf, Wohnort …), Datum,
  Ort, Adresse, Notizen, Zitate. Ein Ereignis gehört niemandem allein.
  - **Wert** und **Beschreibung** sind getrennt: Bei „Beruf“ ist „Bauer“
    der Wert (GEDCOM `1 OCCU Bauer`), dazu kommen eine Präzisierung der
    Art (`2 TYPE`) und eine freie Beschreibung.
  - **Nicht-Ereignis**: Ein Kennzeichen „hat nicht stattgefunden“ mit
    Zeitraum und Zitaten. Das deckt `NO MARR` (GEDCOM 7), `_STAT NOT
    MARRIED` (GEDCOM-L) und „keine Kinder“ (`NCHI 0`, GEDCOM 7 `NO CHR`
    usw.) ab.
- **Ereignisverweis**: verbindet Person oder Familie mit einem Ereignis,
  mit **Rolle** (Hauptperson, Täufling, Vater, Mutter, Pate, Zeuge,
  Pfarrer, Standesbeamter, Informant …) und Reihenfolge. Am Verweis, nicht
  am Ereignis, stehen außerdem:
  - **Angaben zur Person laut Eintrag**: Alter (GEDCOM `AGE`), Beruf,
    Wohnort, Bemerkung – „Pate, 25 J., Bauer in Hesel“. Bei einer
    geteilten Taufe hat jeder Beteiligte seine eigenen Angaben.
  - **Zitate**: Eine Quelle kann belegen, dass jemand Pate war, ohne die
    Taufe selbst zu belegen, und umgekehrt.

Damit wird eine Taufe ein einziges Objekt, an dem Täufling, Eltern und
Paten hängen. In GEDCOM ist das verstreut: `BAPM` beim Kind, `_GODP`,
`_ASSO`+`RELA`, `_WITN` und Notizen. Der Importer führt das zusammen, der
Exporter verteilt es wieder.

**Widersprüchliche Angaben**: Eine Person kann mehrere Ereignisse
gleicher Art haben (zwei Taufdaten aus zwei Quellen). Genau eines je Art
und Rolle trägt den Merker **bevorzugt**; das bevorzugte gilt für
Lebensdaten, Sortierung und Anzeige. Beim Import ist das erste in der
Datei bevorzugt (GEDCOM 7 ordnet gleichartige Angaben nach Vorrang),
keines geht verloren.

Beteiligte ohne eigenen Datensatz (`_GODP Name`, „unbekannt“) stehen als
strukturierter Text am Verweis (E5, Abschnitt 3.8).

### 3.4 Familien

- **Familie**: Partner und Kinder als Mitglieder mit Rolle (Partner,
  Kind). Familienereignisse (Heirat, Scheidung) hängen über
  Ereignisverweise an der Familie.
- **Abstammung je Elternteil**: Die Abstammungsart (leiblich, adoptiert,
  Pflegekind, Stiefkind, unbekannt) gehört an das Paar aus Kind und
  Elternteil, nicht an das Kind. Ein Kind kann leiblich von der Mutter
  und adoptiert vom Partner sein. GEDCOM 5.5.1 drückt das mit
  `ADOP` + `2 FAMC` + `3 ADOP HUSB|WIFE|BOTH` aus, `FAMC`+`PEDI` gilt für
  beide Elternteile; der Importer verteilt beides auf die Paare.
- Die Familie bleibt ein eigenes Objekt mit Kennung (`F12`), wie v1 es
  braucht (E2).

### 3.5 Orte

- **Ort**: Kennung, GOV-Kennung, Koordinaten, Postleitzahl, Maidenhead,
  Notizen, Medien, Zitate.
- **Ortsart**: datiert, eine Liste wie die Namen – erst Gemeinde, ab 1900
  Ortsteil. Jede Art mit Text, GOV-Typnummer (`_GOVTYPE`) und Zeitraum
  (GEDCOM-L: mehrere `1 TYPE` mit `2 DATE`).
- **Ortsname**: datiert, mehrere je Ort (Umbenennungen, Sprachen).
- **Ortsbeziehung**: Ort A liegt in Ort B, **von–bis**, mit Art der
  Zugehörigkeit (politisch, kirchlich, Gericht …). Das deckt GEDCOM-L
  `_LOC` mit `1 _LOC @…@`, `2 DATE`, `2 TYPE` ab.
- **Ortsereignis**: Besitzerwechsel, Brand, Umbenennung (GEDCOM-L
  `_LOC:EVEN`).

Ein Ereignis zeigt auf einen Ort. Der Ortstext aus GEDCOM (`PLAC Hof Nr.
3, Bienenbüttel, Uelzen`) wird beim Import einem Ort zugeordnet: zuerst
über `_LOC`-Verweise, sonst über die Namenskette. Der Originaltext bleibt
am Ereignis erhalten (E6).

**Ortsangaben am Ereignis** (E15): Nennt ein Ereignis Angaben des Ortes
(GEDCOM: `PLAC` mit `MAP`, `_GOV`, `_MAIDENHEAD`, `_POST`), liegen die Werte
am Ort; am Ereignis steht nur, *welche* es nannte (`event_place_detail`,
bei der Postleitzahl mit Verweis auf die datierte Angabe). Werte am
Ereignis, die der Ort nicht kennt (z. B. eine abweichende `_GOV`), bleiben
als Rest am Ereignis (E9). So geben v1 und der Export genau wieder, was in
der Quelle stand.

### 3.6 Quellen und Belege

- **Archiv** (Repository), **Quelle**, **Zitat** (Quelle, Seite, Qualität,
  Datum, Text) wie in GEDCOM. Zitate hängen an Ereignissen, Namen,
  Personen, Familien, Orten.
- **Belegebene, nur vorgesehen, noch nicht gebaut:**
  - **Eintrag**: eine Stelle in einer Quelle (z. B. Taufeintrag Nr. 17,
    1803), mit Transkription und Bild.
  - **Persona**: eine Person, wie sie in genau diesem Eintrag steht
    (Name, Rolle, Alter, Beruf, Wohnort – wörtlich).
  - **Zuordnung**: Persona → Person, mit Begründung, Verfasser und Datum.
    Nicht zerstörend: Lösen löscht die Zuordnung, nicht die Persona.
  - In der ersten Fassung sind Zitate die einfache Form davon. Jedes Zitat
    hat schon jetzt eine optionale, leere Verweisspalte auf einen Eintrag.
    Wie Zitate später in Einträge übergehen, wird mit der Belegebene
    entschieden (E10).

### 3.7 Medien, Notizen, Aufgaben

- **Medium**: Datei(en), Titel, Art; Verweise auf Person, Ereignis, Ort,
  Quelle, Zitat, je mit Ausschnitt (GEDCOM 7 `CROP`) und Hauptbild-Merker
  (`_PRIM`).
- **Gesichter auf Gruppenfotos** (XMP-Regionen, wie in wtWin): Ein
  Gesicht zeigt auf eine Person, auf jemanden ohne Datensatz oder auf
  „unbekannt“; ohne Person wie in E5 als strukturierter Text.
- **Notiz**: eigenes Objekt oder eingebettet (beides gibt es in GEDCOM).
- **Forschungsaufgabe** (`_TODO` mit GEDCOM-L-Feldern).

### 3.8 Querschnitt

- **Bäume**: mehrere je Server, jeder Baum in einer eigenen SQLite-Datei
  mit der Endung **`.wise`** (z. B. `falkenrath.wise`); Konten, Rollen und
  Sitzungen in einer eigenen Datei, die keine `.wise` ist (E8, E12).
- **Dateikennung** (E12): `PRAGMA application_id = 0x57495345` (ASCII
  „WISE“, dezimal 1464423237) und die Schemaversion in
  `PRAGMA user_version`. wisetrees öffnet nur Dateien mit dieser Kennung
  und prüft die Version, bevor es liest oder schreibt.
- **Kennungen** (E1): Jedes Objekt hat eine interne Kennung, die sich nie
  ändert. Die GEDCOM-Kennung (`I123`, `F12`, `S5` …) ist ein eigenes Feld:
  beim Import übernommen, für v1 und den Export genutzt. Neue Datensätze
  bekommen Kennungen im gleichen Stil (`I…`, `F…`, `S…`, `R…`, `M…`,
  `L…` für Orte), fortlaufend nach der höchsten vorhandenen.
- **Lebensdaten** (E3): werden aus den Ereignissen berechnet, nicht an
  der Person gespeichert. Der Lesezugriff läuft über eine Stelle, damit
  später eine Zwischenspeicher-Tabelle dahinter treten kann, ohne dass
  sich Aufrufer ändern.
- **Datum**: Originaltext und ein sortierbarer Bereich (früheste und
  späteste julianische Tageszahl) mit Kalender und Qualität
  (genau/ungefähr/berechnet/geschätzt). Der Bereich dient zum Suchen und
  Sortieren, nicht zur Anzeige.
- **Eindeutige Kennungen** (`_UID`, GEDCOM 7 `UID`) bleiben erhalten.
- **Beteiligte ohne Datensatz** (E5): Paten ohne eigenen Datensatz
  (`_GODP Name`), Gesichter auf Gruppenfotos ohne Person und „unbekannt“
  stehen als **strukturierter Text** am Verweis: Name, Rolle, Zusatz
  (etwa „Bauer in Hesel“), Zitat. Damit lässt sich jeder Eintrag später
  mechanisch in eine Persona der Belegebene umwandeln. Der Schutz
  lebender Personen gilt auch für diesen Text (Abschnitt 5.2).
- **GEDCOM-Rest** (E9): Angaben, die das Modell nicht kennt, hängen als
  GEDCOM-Teilbaum an der Struktur, unter der sie standen (Person,
  Ereignis, Name, Zitat …). Sie werden mit ihr exportiert und mit ihr
  gelöscht.
- **Träger**: Notizen, Zitate, Medienverweise, Aufgaben und GEDCOM-Reste
  hängen an ihrem Träger über je eine Fremdschlüsselspalte je möglichem
  Trägertyp (`person_id`, `event_id` …, `ON DELETE CASCADE`) mit der Regel
  „genau eine gefüllt“ (entschieden 01.11.2026). Rest am ganzen Baum:
  `on_tree`.
- **Rollencodes an Ereignissen**: GEDCOM-7-ROLE-Codes (`GODP`, `WITN`,
  `CLERGY` …), `PRINCIPAL` für die Hauptbeteiligung (Person, Familie oder
  Ort), eigene Codes mit Präfix `X_` (z. B. `X_INFORMANT`), `OTHER` mit
  Freitext. Tabellen- und Spaltennamen der Datei sind englisch.
- **Änderungen**: Jede Änderung wird protokolliert (wer, wann, was).
  Moderation siehe 5.3.

## 4. API-Strategie

### 4.1 v1: api4wisetrees

v1 ist die Schnittstelle, die die Apps heute sprechen. Sie ist **fest**
(Stufe 42 als Obergrenze des Funktionsumfangs, Schemata in
`vertrag/api-v1.json`); v1 wird nicht mehr erweitert, Neues kommt in v2.
Was über die Schemata hinaus gilt (Adressform, Anmeldeformular, Cookie,
CSRF mit 302, Fehler als HTTP 200, Bildadressen, Sichtbarkeit), steht in
[API-V1.md](API-V1.md).

**Fähigkeiten (E17):** `Info.features` nennt, was wisetrees
vollständig anbietet; die Apps richten sich zuerst danach und erst ohne
dieses Feld nach der Stufe. So muss wisetrees nicht jede Stufe
vollständig bauen, um eine einzelne Funktion freizugeben.

**Routen von Meilenstein 1 (lesend):** `Info`, `/login`, `/logout`,
`Individuals`, `Individual`, `Family`, `Pedigree`, `Descendants`, `Tags`
und die Bildauslieferung für `thumb`. Danach `Pair`, `Anniversaries`,
`MediaList`, `Bookmarks` und die Schreibrouten.

**Grenzen von v1:** v1 kennt Fakten je Person und Familie. Rollen an
Ereignissen, Ortshierarchie und Belege lassen sich über v1 nur so weit
zeigen, wie die Felder es vorsehen (Paten, Ortsdatensätze). Mehrere
Ereignisse gleicher Art erscheinen als mehrere Fakten, das bevorzugte
zuerst.

**`factId`** (E7): wisetrees vergibt je Fakt eine eigene, stabile
Kennung. Die Apps behandeln `factId` als Zeichenkette; nach dem Speichern
suchen sie eine neue Kennung und nehmen, wenn es keine gibt, die alte.
Stabile Kennungen funktionieren damit. Einschränkung: Die Kennung beginnt
nie mit `assoc-` (dieses Präfix nutzen die Apps selbst).

### 4.2 v2: später

Eine eigene API unter `/api/v2/…`, die das Modell aus Abschnitt 3 direkt
zeigt: Ereignisse mit allen Beteiligten, Orte mit Hierarchie, später
Einträge und Personae. v2 kann die zum Datum eines Ereignisses gültigen
Ortsangaben (Name, Zugehörigkeit, Postleitzahl …) aus dem Ort ableiten,
statt nur die am Ereignis genannten zu zeigen (E15). Sie wird erst entworfen, wenn v1 läuft. v1 bleibt
danach bestehen.

### 4.3 Vertragstests

Eine Testsuite, die gegen einen beliebigen Server läuft (Adresse, Baum und
Konten konfigurierbar). Sie prüft zweierlei (E11):

1. **Form**: jede Antwort gegen das Schema der Route in
   `vertrag/api-v1.json`.
2. **Inhalt**: gegen **Aufzeichnungen** – die festgelegten Antworten jeder
   Route mit festen Parametern je Rolle am Falkenrath-Baum (CC0), im
   Repository. `stand.json` nennt Stufe, Baum, Prüfsumme und Datum.

Wechselnde Werte werden vor dem Vergleich normalisiert: Sitzung,
CSRF-Token, Zeitstempel, `factId` (E7), Bild-URLs, die Basisadresse.
Altersangaben und „lebend“ hängen vom Tagesdatum ab; die Aufzeichnung
nennt ihr Datum. Darum kennt wisetrees ein **festes Bezugsdatum für
„heute“** (Einstellung, nur für Tests). Die Vertragstests lassen
wisetrees immer mit dem Datum der Aufzeichnung laufen.

## 5. Rechte, Schutz, Moderation

### 5.1 Rollen je Baum

| Rolle | darf |
|---|---|
| Besucher | ohne Anmeldung lesen, was öffentlich ist (falls der Baum das zulässt) |
| Mitglied | angemeldet lesen, eigene Merkliste |
| Bearbeiter | Änderungen vorschlagen oder schreiben |
| Moderator | Änderungen anderer annehmen oder verwerfen |
| Verwalter | Baum einrichten, Konten und Rollen, Import/Export |

Dazu eine Serverrolle **Administrator** für alle Bäume und Konten.

### 5.2 Schutz lebender Personen

Regel mit der einstellbaren Grenze *G* (Vorgabe 120 Jahre). Sie ist
bewährt und schätzt aus den Daten der Person und ihrer Angehörigen:

1. Gibt es ein Todesereignis (Tod, Begräbnis, Einäscherung …) mit Datum,
   Ort oder `Y`, ist die Person tot.
2. Liegt irgendein Datum der Person mehr als *G* Jahre zurück, ist sie
   tot. Hat sie ein Geburtsdatum und sind alle Daten jünger, lebt sie.
3. Sonst entscheiden die Angehörigen. Die Person gilt als tot, wenn
   - ein Datum eines Elternteils mehr als *G* + 45 Jahre zurückliegt,
   - ein Datum einer ihrer Familien (z. B. Heirat) mehr als *G* − 10,
   - ein Datum eines Partners mehr als *G* + 40,
   - ein Datum eines Kindes mehr als *G* − 15,
   - ein Datum eines Enkels mehr als *G* − 30 Jahre zurückliegt.
4. Sonst gilt sie als lebend. Wer also keine eigenen Daten hat, aber ein
   Kind, das vor weniger als *G* − 15 Jahren geboren ist, gilt als lebend.

Weiter:

- Schutzvermerke (`RESN none/privacy/confidential/locked`) an Personen,
  Ereignissen und Namen.
- Der Schutz gilt auch für Beteiligte ohne Datensatz (E5), soweit ihr
  Text eine lebende Person nennen kann.
- Die Prüfung sitzt in einer Schicht zwischen Datenbank und API: Keine
  Route liest an ihr vorbei.
- Die Aufzeichnungen der Vertragstests (4.3) prüfen die Regel.

### 5.3 Moderation

Änderungen von Bearbeitern ohne Freigaberecht werden als **offene
Änderung** gespeichert und erst nach Annahme wirksam. Offene Änderungen
sehen nur Bearbeiter, Moderatoren und Verwalter; v1 kennzeichnet sie mit
`pending: true`.

Umsetzung nach E4 (Variante a, Anhang A): Die Modelltabellen enthalten nur
den angenommenen Stand, offene Änderungen liegen als Änderungssätze in
eigenen Tabellen. **Eine einzige Leseschicht** legt für Bearbeiter die
offenen Schritte über die Antwort und wendet danach den Schutz lebender
Personen an (5.2). Keine Route liest an ihr vorbei. Tests belegen, dass
Besucher und Mitglieder offene Änderungen nie sehen – weder in einer
Einzelantwort noch in Liste oder Suche.

## 6. GEDCOM-Ein- und Ausgabe

- **GEDCOM 7.0 und GEDZIP**: lesen und schreiben mit `gedcom7`
  (python-gedcom7, MIT, keine weiteren Abhängigkeiten).
- **GEDCOM 5.5.1 mit GEDCOM-L**: eigener Importer. Zeichensätze UTF-8
  (mit und ohne BOM), UTF-16, ANSEL, ANSI; `CONT`/`CONC`.
- Prüfstein ist der Falkenrath-Baum 1.7.1. Er enthält jede Angabe des
  GEDCOM-L-Addendums: `_UID`, `_GODP`, `_ASSO`, `_WITN`, `_RUFNAME`,
  `_PRIM`, `_TODO` mit Unterfeldern, `_STAT`, `_LOC` mit `_GOVTYPE`, an
  `PLAC` `_GOV`, `_POST`, `_MAIDENHEAD`.
- **Importbericht**: Zahlen je Objektart, übernommene GEDCOM-Reste (E9),
  Fehler je Datensatz – und **ausdrücklich jede unsichere
  Ortszuordnung**: Ortstexte, die keinem `_LOC` zugeordnet waren und
  über die Namenskette mehrdeutig oder gar nicht passten, mit Ereignis
  und gewähltem Ort.
- **Export-Kopf**: `1 SOUR WISE` mit `2 NAME wisetrees` und
  `2 CORP Thomas Bugge`. Im 5.5.1-Export steht `1 CHAR` direkt nach
  `0 HEAD`, damit Leser den Zeichensatz sofort finden. `RIN` trägt die
  interne Kennung mit dem Präfix `WISE:` (z. B. `1 RIN WISE:4711`).
- **Rundlauf-Test**: Import → Export → Import ergibt dasselbe Modell. Ein
  zeilengleicher Export ist kein Ziel.
- **WTX – „wisetrees exchange“** (E13, nur vorgesehen): ein offenes,
  dokumentiertes Austauschformat. ZIP mit JSON nach eigener Spezifikation
  und den Medien, ähnlich GEDZIP, aber mit dem vollen Modell (Rollen,
  Ortshierarchie, später Belegebene). Die Daten bleiben lesbar, auch wenn
  es wisetrees nicht mehr gibt. Entwurf erst
  nach Meilenstein 1.

## 7. Abgrenzung

wisetrees ist **nicht**:

- ein Ableger eines anderen Programms. Es ist eigenständig geschrieben und
  enthält keinen fremden Code.
- eine Webseite für die Familie. Am Anfang gibt es im Browser nur das
  Nötigste: Anmelden, Konten, Baum importieren und exportieren, App
  koppeln. Anzeige und Bearbeitung laufen über die Apps.
- ein Ersatz für Diagramme, Berichte und Bücher – die erzeugen wtWin und
  wtAnd.
- ein Mehrbenutzer-Dienst für fremde Nutzer im Internet. Zielgruppe ist
  die eigene NAS und die eigene Familie oder Forschungsgruppe.

Außerdem gilt:

- **Desktop-Modus (E14) offenhalten:** Die Bäume kommen über eine Stelle
  (`app.state.baeume`, Schnittstelle `alle()`/`baum(name)`), nicht über
  feste Pfade im Code; Konten und Sitzungen hängen an `app.state.konten`
  und lassen sich durch eine Prüfung per Zufalls-Token ersetzen. Neuer Code
  liest Bäume und Anmeldung nur über diese beiden Stellen.

- Abhängigkeiten nur unter einer AGPL-verträglichen Lizenz (MIT, BSD,
  Apache-2.0, PSF-2.0). Jede neue Abhängigkeit kommt mit Lizenz in
  `docs/DEPENDENCIES.md`.

## 8. Vorgehen

1. Repository, README, dieses Konzept – erledigt.
2. Vertragstests für v1 (4.3) – erledigt, siehe `vertrag/README.md`.
3. Grundgerüst, SQLite-Schema, GEDCOM-Import für Falkenrath – erledigt.
4. Meilenstein 1: Routen lesend, Vertragstests grün (329/329), Falkenrath-
   Baum in wtTux angezeigt – erledigt 01.11.2026.

## 9. Entscheidungen

Entschieden am 01.11.2026.

| | Frage | Entscheidung |
|---|---|---|
| E1 | Kennungen | **b** – interne Kennung, GEDCOM-Kennung als Feld; neue Datensätze im gleichen Stil (`I…`, `F…`, `S…`) |
| E2 | Familie | **a** – eigenes Objekt |
| E3 | Lebensdaten | **a** – aus Ereignissen berechnen; so bauen, dass später eine Zwischenspeicher-Tabelle ergänzt werden kann |
| E4 | Offene Änderungen | **a** – Änderungssätze in eigener Tabelle; Überlagerung und Schutz lebender Personen in einer Leseschicht; Tests, dass Besucher nie Offenes sehen (5.3, Anhang A) |
| E5 | Beteiligte ohne Datensatz | **c jetzt, b später** – strukturierter Text am Verweis (Name, Rolle, Zusatz, Zitat), Schutz lebender Personen gilt; Gesichter ohne Datensatz gleich |
| E6 | Ortstext | **b** – Originaltext bleibt am Ereignis |
| E7 | `factId` in v1 | **a** – eigene stabile Kennung; im Client geprüft (4.1) |
| E8 | Bäume | **b** – eine SQLite-Datei je Baum |
| E9 | Unbekannte GEDCOM-Angaben | **a** – bleiben an ihrer Struktur, werden mit ihr gelöscht |
| E10 | Zitat → Eintrag | **später**; jetzt schon eine optionale, leere Verweisspalte vom Zitat auf einen Eintrag |
| E11 | Prüfung der Vertragstests | **b und c** – Aufzeichnungen im Repository, normalisiert, mit API-Stand; zusätzlich Schemata (`vertrag/api-v1.json`). Die Schemata sind aus einem kleinen Testbaum und Falkenrath abgeleitet, damit Felder, die nur in großen Bäumen gefüllt sind, nicht zu eng beschrieben werden |
| E12 | Dateiformat | Baum = SQLite-Datei `.wise`; `application_id` 0x57495345 („WISE“), Schemaversion in `user_version`; Konten und Sitzungen getrennt, nicht als `.wise`. Prüfung am 01.11.2026, siehe unten |
| E13 | Austauschformat | WTX (ZIP + JSON + Medien, eigene offene Spezifikation), nur vorgesehen, Entwurf nach Meilenstein 1 |
| E14 | Desktop-Modus | **vorgesehen, nach Meilenstein 1**: dasselbe Backend öffnet statt eines Verzeichnisses eine einzelne `.wise`-Datei, gestartet von wtWin, ohne Konten, nur auf 127.0.0.1 und mit Zufalls-Token erreichbar. Die Architektur darf das nicht verbauen (siehe 7) |
| E15 | Ortsangaben am Ereignis | **a** – am Ereignis vermerken, welche Angaben des Ortes es nannte; Werte, die der Ort nicht kennt, bleiben Rest am Ereignis (3.5); v2 kann die zum Datum gültigen Angaben ableiten (4.2) |
| E16 | Datenbank | **SQLite Standard**; **PostgreSQL als Option** mit dem Treiber `pg8000`; **MariaDB vorbereitet** mit `PyMySQL`, gebaut nur auf Nachfrage. Das Schema ist schon in Teil 1 MariaDB-tauglich: feste Längen, keine Indizes mit Bedingung, exakte Vergleiche. Die Eindeutigkeitsregeln bleiben dabei gleich streng, mit Tests belegt. Wie Bäume in MariaDB abgelegt werden (Datenbank je Baum oder Tabellenpräfix), wird erst entschieden, wenn MariaDB drankommt. Festgelegt am 01.11.2026 für Teil 1: GEDCOM-Kennungen höchstens 255 Zeichen (längere lehnt der Import mit Meldung ab); Schemaversion bleibt 1, Dateien aus 0.1 bleiben nutzbar; die Kontendatei ist mit umgestellt; Kommazahlen doppelt genau |
| E17 | Fähigkeiten statt Stufen | `Info` meldet zusätzlich `features`: die Fähigkeiten, die wisetrees **vollständig** anbietet (`read`, `write`, `moderation`, `photos`, `export`, `pair`, `bookmarks`, `anniversaries`, `languages`, `relationship`; Umfang je Fähigkeit in [FUNKTIONEN.md](FUNKTIONEN.md) 1.4). Die Apps prüfen zuerst `features`, fehlt das Feld, gilt die Stufe. Änderung in den Apps erst nach Freigabe. Meilenstein 2 nach Nutzen: Schreiben mit Moderation, Fotos mit Hochladen und Vorschaubildern, Export, Koppeln, Merkliste, Jahrestage |
| E18 | Verwaltung im Browser | **Stufe 1, vor E16 Teil 2** (entschieden 01.11.2026): nur für Administratoren unter `index.php?route={pfad}/wisetrees/verwaltung`; Anmelden, Konten (anlegen, Passwort setzen, Rollen je Baum, löschen), Bäume (GEDCOM hochladen und einlesen mit Importbericht, löschen mit Rückfrage). Eigenes Passwort ändern für jedes Konto. Seiten aus Vorlagen mit Jinja2 (BSD-3), kein Frontend-Build. Export und Koppeln kommen mit ihren Fähigkeiten (E17) |

**Prüfung zu E12 (01.11.2026):**

- `application_id` 0x57495345 ist **frei**: nicht im Register der
  SQLite-Entwickler (`magic.txt` im SQLite-Quellbaum, 11 Einträge, seit
  Jahren kaum gepflegt), nicht in libmagic 5.46 (`file`), keine Treffer in
  der GitHub-Codesuche. Ein eigenes Register gibt es nicht; eintragen
  lassen könnte man die Kennung über `magic.txt` bzw. die Magic-Dateien
  von `file`.
- Die Endung `.wise` ist **schon in Gebrauch**, aber in einer Nische (eine
  Fachanwendung für Flussmodelle). fileinfo.com und filext.com kennen
  `.wise` nicht. Folge: Nur auf Rechnern mit dieser Anwendung könnte die
  Doppelklick-Zuordnung kollidieren. Erkannt wird eine
  wisetrees-Datei ohnehin an der `application_id`, nicht an der Endung.

## Anhang A: Skizze zu E4 – Lesen bei offenen Änderungen (entschieden: a)

### Was v1 verlangt

- Offene Änderungen sieht nur, wer Bearbeiter oder mehr ist. Für alle
  anderen gibt es sie nicht.
- **Individual**: Bearbeiter bekommen den Stand mit offenen Änderungen;
  geänderte oder neue Fakten tragen `pending: true`. Besucher und
  Mitglieder bekommen den angenommenen Stand. Eine neu angelegte, noch
  nicht angenommene Person gibt es für sie nicht (Fehler 404).
- **Individuals und Suche**: Gesucht und sortiert wird in den Tabellen
  des angenommenen Stands, für alle Rollen. Eine neue Person ohne Annahme
  findet auch ein Bearbeiter nicht; eine offene Namensänderung findet er
  nur unter dem alten Namen, angezeigt wird ihm der neue.
  (Feinheiten wie offene Löschungen klären die Aufzeichnungen.)

wisetrees muss für v1 mindestens das liefern; ob die Suche für
Bearbeiter auch offene Namen finden soll, ist eine eigene kleine Frage.

### Variante a – Änderungssätze in eigener Tabelle

Die Modelltabellen enthalten nur den angenommenen Stand. Eine offene
Änderung ist ein Satz in `aenderung` (Verfasser, Zeit, Status) mit
Einzelschritten in `aenderung_schritt`: Objektart, interne Kennung,
Operation (anlegen/ändern/löschen), alte und neue Werte als JSON. Ein
Index „welche Objekte berührt welcher offene Satz“ gehört dazu.

| Lesen | Besucher, Mitglied | Bearbeiter (`pending: true`) |
|---|---|---|
| Individual | direkt aus den Tabellen | aus den Tabellen lesen, dann die offenen Schritte für alle Objekte der Antwort (Person, Namen, Ereignisse, Verweise, Familien) im Speicher anwenden; berührte Fakten bekommen `pending: true`. Neue Person: nur aus dem Satz zusammengesetzt |
| Individuals | direkt aus den Tabellen | Treffer aus den Tabellen, für die höchstens 50 Personen der Seite die offenen Namen darüberlegen |
| Suche | direkt aus den Tabellen | wie Individuals; wer auch offene Namen finden will, durchsucht zusätzlich die (wenigen) offenen Namensschritte |

- Für Besucher kann nichts durchsickern: Offenes liegt in einer anderen
  Tabelle, keine Abfrage muss etwas ausfiltern.
- Annahme = Schritte auf die Tabellen anwenden, Satz wird zum Protokoll.
  Ablehnen = Satz verwerfen.
- Aufwand und Risiko liegen beim Bearbeiter-Lesen: Die Überlagerung ist
  eigener Code, der für jede Objektart stimmen muss. Geteilte Ereignisse
  machen das breiter: Eine offene Änderung an einer Taufe betrifft die
  Antwort für Täufling, Eltern und Paten.
- Ändert jemand den angenommenen Stand, während eine Änderung offen ist,
  muss die Annahme den Konflikt erkennen (alte Werte vergleichen).

### Variante b – Zeilen mit Version und Status

Jede Modelltabelle hat neben der Kennung eine Version und einen Status
(`angenommen`, `offen`, `offen_geloescht`, `abgelöst`). Eine offene
Änderung legt neue Zeilen mit Status `offen` an; die angenommene Zeile
bleibt bis zur Annahme gültig. Verweise zeigen auf die Kennung, nicht
auf die Zeile.

| Lesen | Besucher, Mitglied | Bearbeiter (`pending: true`) |
|---|---|---|
| Individual | jede Abfrage nur über Zeilen mit `angenommen` | je Kennung die `offen`-Zeile, sonst die `angenommen`-Zeile; `pending: true` steht direkt im Status |
| Individuals | wie links | Sortieren über den angenommenen Namen (wie v1 verlangt) oder über den offenen (Abweichung, aber einfach zu haben) |
| Suche | wie links | dieselbe Wahl: angenommen wie v1 oder offen mit einbeziehen |

- Die Überlagerung macht SQL: zwei Sichten je Tabelle (`…_angenommen`,
  `…_mit_offenen`), der Code wählt nur die Sicht nach Rolle.
- Für Besucher hängt die Sicherheit daran, dass **jede** Abfrage über die
  richtige Sicht läuft. Eine vergessene Bedingung zeigt Offenes.
- Annahme = Status umstellen, alte Zeile `abgelöst`; Ablehnen = offene
  Zeilen löschen. Die Geschichte jedes Objekts gibt es nebenbei.
- Das Schema wird schwerer: Primärschlüssel aus Kennung und Version,
  Fremdschlüssel nicht mehr direkt durch SQLite prüfbar, eindeutige
  Indizes (z. B. GEDCOM-Kennung) nur über die gültigen Zeilen. Alle
  Tabellen sind davon betroffen, auch solche, die nie moderiert werden.

### Abwägung

| | a | b |
|---|---|---|
| Besucher-Lesen | einfach, nichts zu filtern | jede Abfrage über die richtige Sicht |
| Bearbeiter-Lesen | eigener Überlagerungscode | SQL-Sichten |
| v1 wie verlangt | natürlich (Suche läuft auf dem angenommenen Stand) | möglich, muss gewählt werden |
| Schema | unverändert, Fremdschlüssel durch SQLite geprüft | Version und Status in jeder Tabelle |
| Geschichte | Protokoll der Sätze | Zeilen selbst |
| Konflikte | beim Annehmen prüfen | beim Annehmen prüfen |
