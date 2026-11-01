# Funktionsinventur: was wtAnd und wtWin von api4wisetrees brauchen

Stand: 01.11.2026. Grundlage:

- die Schnittstellenbeschreibung `vertrag/api-v1.json` (Stufe 42) und
  [API-V1.md](API-V1.md);
- der Quellcode der Apps, Stand wtAnd 1.57: die Stelle, an der die Apps
  die Schnittstelle aufrufen, und alle Bildschirme, die sie nutzen.

wtWin steht hier auch für die Linux-Fassung; beide sind dasselbe Programm.

## 1. Vorbemerkungen

### 1.1 Wo die Apps aufrufen

Der Code der Apps liegt in drei Teilen. Die Spalte „wo“ nennt die Datei
ohne Pfad und ordnet sie so zu:

| Ort im Code | gehört zu |
|---|---|
| `shared/src/commonMain/.../ui/` | gemeinsamer Kern; die Bildschirme dort sind die von wtAnd, die `…Actions.kt` nutzt auch wtWin |
| `shared/src/desktopMain/.../desk/`, `.../lokal/` | nur wtWin |
| `shared/src/androidMain/.../ui/` | nur wtAnd (z. B. `AnniversaryWorker`, Hintergrunddienst) |

Abkürzungen in den Tabellen: **A** = wtAnd, **W** = wtWin, **A+W** = beide.

### 1.2 Fähigkeiten statt Stufen (E17)

Bisher fragen die Apps nicht ab, ob eine Route existiert. Sie lesen
`Info.api` und schalten jede Funktion ab einer festen Stufe frei:

| Konstante | Stufe | schaltet frei |
|---|---:|---|
| `MIN_API` | 1 | Verbindung überhaupt |
| `API_PHOTOS` | 2 | Fotos, Foto hochladen |
| `API_ANNIVERSARIES` | 4 | Jahrestage |
| `API_PLACES` | 8 | Ortsvorschläge beim Bearbeiten |
| `API_BOOKMARKS` | 11 | Merkliste |
| `API_EXPORT` | 17 | ganzen Baum laden (wtWin: lokaler Speicher, Bücher, Prüfung) |
| `API_SOURCES` | 18 | Quellen nachschlagen und bearbeiten |
| `API_ASSOCIATES` / `_WRITE` | 19 / 20 | Paten und Zeugen lesen / schreiben |
| `API_PLACE_LIST` / `_WRITE` / `_RENAME` | 21 / 22 / 23 | Ortsliste, Ortsdatensatz, Orte bereinigen |
| `API_START_PERSON` | 24 | Startperson setzen |
| `API_LOC_HIERARCHY` | 27 | Höfe und Häuser als Orte |
| `API_MERGE` | 29 | Personen zusammenführen |
| `API_TASKS` | 30 | Aufgaben |
| `API_LOC_LINKS` / `API_ADDRESS` | 32 / 33 | Ortsverweise, Adressen zu Häusern |
| `API_GEDCOML` / `_WRITE` | 34 / 35 | GEDCOM-L-Felder lesen / schreiben |
| `API_ACCESS` | 36 | Sichtbarkeit je Fakt (Bücher für Besucher) |
| `API_MESSAGES` | 42 | Nachrichten |

Mit der Stufe allein müsste wisetrees jede Stufe vollständig bauen,
bevor es die nächste melden darf, auch Funktionen, die keine App
aufruft. Darum (E17): **`Info` meldet zusätzlich `features`**, eine
Liste der Fähigkeiten, die wisetrees vollständig anbietet. Die Apps
prüfen zuerst `features`; fehlt das Feld, gilt wie bisher die Stufe.
Die Fähigkeiten sind in [KONZEPT.md](KONZEPT.md) E17 festgelegt. Die
Änderung in den Apps kommt erst nach Freigabe.

### 1.3 Einstufung

- **Meilenstein 2**, nach Nutzen in dieser Reihenfolge:
  1. **Schreiben mit Moderation** – Fakten, Personen, Verknüpfungen;
     offene Änderungen, Annehmen, Verwerfen.
  2. **Fotos** – Medienliste, Hochladen, Verknüpfen, Hauptbild,
     verkleinerte Vorschaubilder (Pillow).
  3. **Export** – der ganze Baum seitenweise; Grundlage fast aller
     wtWin-Funktionen.
  4. **Koppeln** – Einmal-Code statt Passwort in der App.
  5. **Merkliste**.
  6. **Jahrestage**.
- **später**: alles andere, nach Nutzen; Haltepunkte sind Quellen,
  Orte, Aufgaben und Zusammenführen.
- **nie**: Wege, die wisetrees nicht anbieten will (Abschnitt 4).

### 1.4 Die Fähigkeiten in `features`

Jede Fähigkeit umfasst alles, was sie braucht: Routen, Felder und die
Bausteine darunter. wisetrees meldet sie erst, wenn alles davon steht
und durch Tests belegt ist.

| Fähigkeit | Routen und Felder | Bausteine | wann |
|---|---|---|---|
| `read` | `Info`, `Individuals`, `Individual`, `Family`, `Pedigree`, `Descendants`, `Tags`, Bildauslieferung; `relativeTo` mit naher Verwandtschaft (direkte Linie, Geschwister, Partner) auf Deutsch | Leseschicht mit Sichtbarkeit je Rolle | **vorhanden** (Meilenstein 1) |
| `write` | `Fact`, `DeleteFact`, `AddIndividual`, `Link`, `Unlink`, `DeleteRecord`; `Info.trees[].canEdit`, `autoAccept` | **Schreibschicht mit Moderation und Protokoll** (2.0); **Rechte je Baum** aus `baumrolle`; neue Kennungen (E1), stabile `factId` (E7); Ortstext einem Ort zuordnen (wie beim Import) | **Meilenstein 2 (1)** |
| `moderation` | `Pending`, `Accept`, `Reject`; `pending` an Fakten; `Info.trees[].pending`, `canModerate` | Überlagerung offener Änderungen in der Leseschicht (E4); Konflikterkennung beim Annehmen; Test, dass Besucher und Mitglieder nie Offenes sehen | **Meilenstein 2 (1)**, zusammen mit `write` |
| `photos` | `MediaList`, `Media` (hochladen, Vorhandenes verknüpfen), `UnlinkMedia`, `PrimaryMedia`; verkleinerte Bilder in `thumb`; `Info.maxUpload`, `Info.trees[].canUpload` | **Dateiablage** unter `<daten>/medien/{Baum}/` (Namen ohne Kollision, Prüfung des Dateityps); **Vorschaubilder** mit Pillow; **Zeitstempel am Medium** (für „neueste zuerst“) | **Meilenstein 2 (2)** |
| `export` | `Export` (250 Datensätze je Seite), `lastChange` je Baum | Leseschicht über alle Personen und Familien | **Meilenstein 2 (3)** |
| `pair` | `Pair`; Seite „App verbinden“ mit Code und QR-Code | **Einmal-Codes** in der Kontendatei (nur Hash, 10 Minuten gültig, einmal einlösbar) | **Meilenstein 2 (4)** |
| `bookmarks` | `Bookmarks` lesen und ändern | **Merkliste** je Konto und Baum in der Kontendatei | **Meilenstein 2 (5)** |
| `anniversaries` | `Anniversaries` | Suche nach Monat und Tag über die Datumsbereiche; Schutz lebender Personen | **Meilenstein 2 (6)** |
| `languages` | Parameter `lang`: Beschriftungen und Datumsanzeige in den Sprachen der Apps (de, en, nl, fr, es) | Texttabellen je Sprache | später |
| `relationship` | `Relationship`; `relativeTo` mit allen Verwandtschaftsgraden („Cousine 2. Grades“) | Wegesuche über Familien, Bezeichnungen je Sprache | später |

Nicht als Fähigkeit vorgesehen: **GEDCOM-Teilbaum als Eingabe bei
`Fact`**. Keine App sendet ihn (die Anfrage der Apps hat nur einzelne
Felder: Art, Wert, Datum, Ort, Notiz, Typ, Adresse). Er kommt erst, wenn
ein Client ihn braucht.

### 1.5 Was wisetrees schon hat (Meilenstein 1)

Routen: `Info`, `/login`, `/logout`, `Individuals`, `Individual`,
`Family`, `Pedigree`, `Descendants`, `Tags`, Bildauslieferung
`/wisetrees/medien/{Baum}/{Datei}`, Startseite und Seite „App
verbinden“. Gemeldet wird Stufe 1 („lesend vollständig“).

Tabellen im Baum (`.wise`): `person`, `name`, `event`, `event_role`,
`event_place_detail`, `family`, `family_member`, `parentage`,
`person_association`, `place`, `place_name`, `place_type`,
`place_attribute`, `place_link`, `source`, `source_coverage`,
`source_repository`, `repository`, `citation`, `note`, `note_link`,
`media`, `media_file`, `media_link` (mit `is_primary` und
`crop_top/left/height/width`), `task`, `gedcom_rest`, `change_set`,
`change_step`, `meta`. In der Kontendatei: `konto`, `baumrolle`,
`sitzung`.

## 2. Routen von api4wisetrees

Alle Routen haben die Form
`index.php?route={pfad}/module/{Modul}/{Aktion}[/{Baum}]` (Einzelheiten
in [API-V1.md](API-V1.md)). Schreibende Routen sind `POST` mit
JSON und `X-CSRF-TOKEN`. Jede schreibende Route braucht die
**Schreibschicht** (siehe 2.0), die hier nicht bei jeder Zeile
wiederholt wird.

### 2.0 Querschnitt für alles Schreibende

Bevor die erste Schreibroute geht, braucht wisetrees:

- **Schreibschicht mit Moderation**: Änderungen von Bearbeitern ohne
  Freigaberecht als `change_set` / `change_step`, Annahme und Ablehnung,
  Antwort mit `pending: true` (KONZEPT 5.3, E4). Die Leseschicht muss
  offene Schritte für Bearbeiter überlagern.
- **Änderungsprotokoll**: wer, wann, welcher Datensatz. Angenommene
  `change_set` sind das Protokoll; Verwalter-Änderungen ohne Moderation
  brauchen ebenfalls einen Satz (Status sofort `accepted`).
- **Rechte je Baum** aus `baumrolle`: `canEdit`, `canUpload`,
  `canModerate`, `autoAccept` in `Info.trees[]`.
- **Neue Kennungen** im Stil `I…`, `F…`, `S…`, `R…`, `M…`, `L…` (E1)
  und stabile `factId` (E7).
- **GEDCOM-Text als Eingabe** bei `Fact`: nicht nötig, keine App sendet
  ihn (1.4).

### 2.1 Grundlagen, Anmeldung, Konten

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Einstieg, Sitzung, CSRF, Bäume mit Rechten | `GET Info` | 1 | `info()`: `SessionActions` (A+W), `BaumSpeicher`, `LokalerServer`, `Verbindungslinks` (W) | vorhanden; je Stufe neue Felder (`startXref` 24, `loginForm` 26, `availableModules` 31, `user.language` 41, `user.messages` 42) | vorhanden, wächst mit |
| Anmelden mit Passwort | `POST /login` (Formular) | – | `login()`: `SessionActions` (A+W), `LokalBetrieb`, `LokalStart` (W) | vorhanden (`konto`, `sitzung`, Sperre nach Fehlversuchen) | vorhanden |
| Abmelden | `POST /logout` | – | `logout()`: `MainScreen`, `SessionActions` (A+W) | vorhanden | vorhanden |
| Gerät koppeln mit Einmal-Code | `POST Pair` | 6 | `pair()`: `SessionActions` (A+W); Verbindungslink und QR-Code | Tabelle für Einmal-Codes in der Kontendatei (nur Hash, 10 Minuten gültig, einmal), Seite „App verbinden“ erzeugt den Code (QR aus `qr_min`), nur über https | **Meilenstein 2 (4. Koppeln)** – ersetzt das Passwort in der App |
| Eigenen Anzeigenamen ändern | `POST MyAccount` | 25 | nicht aufgerufen | `konto.real_name` schreiben | später – keine App nutzt es, nötig erst für Stufe 25 |
| Einstellungen der Anmeldeseite | Felder `Info.loginForm` (`welcomeMessage`, `isSelfRegistrationAllowed`, `registrationTerms`) | 26 | nicht ausgewertet | Einstellung je Server; vorerst feste Werte (`false`, `null`) | später – nur Felder, Stufe 26 |
| Sprache des Kontos | Feld `Info.user.language` | 41 | nicht ausgewertet | `konto.language` (vorhanden) | später – Stufe 41 |
| Registrierung | keine Route | – | nicht aufgerufen; die Apps bieten sie nicht an | Formular im Browser, Freischaltung durch Verwalter, E-Mail-Bestätigung | **nie** – Konten legt der Verwalter an (KONZEPT 7: eigene Familie, kein offener Dienst); `isSelfRegistrationAllowed` bleibt `false` |
| Passwort vergessen / ändern | keine Route | – | nicht aufgerufen; die Apps bieten es nicht an | Browser-Seite; „vergessen“ zusätzlich E-Mail-Versand mit Einmal-Link | später, nur im Browser – nicht Teil der Schnittstelle; Ändern zuerst, „vergessen“ erst mit E-Mail |
| Konten und Rollen verwalten | keine Route | – | nicht aufgerufen | Browser-Seite oder `werkzeuge/konten.py` (vorhanden) | später, nur im Browser |

### 2.2 Stammbaum lesen

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Personenliste, Suche | `GET Individuals` | 1 | `individuals()`: `TreeActions`, `ArchiveActions`, `GesichterBearbeiten` (A+W); `DeskRoot`, `Listen`, `AnfuegenDialog`, `PatenDialog`, `StartpersonDialog`, `TafelFenster`, `ZusammenfuehrenFenster`, `GesichterFenster` (W) | vorhanden | vorhanden |
| Eine Person | `GET Individual` | 1 | `individual()`: `TreeActions`, `EditActions` (A+W); `DeskRoot`, `Buch`, `Familienansicht`, `Listen`, `MetaSuche`, `TafelDaten`, `AnfuegenDialog` (W) | vorhanden; Felder späterer Stufen prüfen (2: `relationship` mit `relativeTo`; 9: `media[].path`; 10: Heiraten der Kinder; 12: `stepFamilies`, `hasParents` …) | vorhanden, Felder bis Stufe 42 durch die Vertragstests belegt |
| Eine Familie | `GET Family` | 1 | nicht aufgerufen | vorhanden | vorhanden |
| Vorfahren | `GET Pedigree` | 1 (15: `siblings`, 16: 12 Generationen) | `pedigree()`: `TreeActions` (A+W); `DeskRoot`, `Familienansicht`, `TafelDaten` (W) | vorhanden; `siblings` und Tiefe prüfen | vorhanden |
| Nachkommen | `GET Descendants` | 1 (12: 10 Generationen) | `descendants()`: wie `Pedigree` | vorhanden | vorhanden |
| Angebotene Fakten mit Beschriftung | `GET Tags` | 1 | `tags()`: `SessionActions` (A+W) | vorhanden | vorhanden |
| Sprache der Antworten | Parameter `lang` | 3 | jede Anfrage (`apiLanguage()`) | Beschriftungen und Datumsanzeige je Sprache (de, en, nl, fr …, wie die Apps) | später – vorerst Deutsch |
| Verwandtschaft zweier Personen | `GET Relationship` | 13 | nicht aufgerufen (die Apps nutzen `Individual?relativeTo`) | Wegesuche über `family_member`/`parentage`, Bezeichnungen je Sprache | später – keine App ruft es auf; mit E17 nicht mehr für eine Stufenfolge nötig |
| Ganzer Baum seitenweise | `GET Export` | 17 | `export()` in `api/Export.kt`; `BaumSpeicher` (W) lädt damit den lokalen Speicher | Leseschicht über alle Personen und Familien, 250 je Seite, `lastChange` je Baum | **Meilenstein 2 (3. Export)** – Grundlage fast aller wtWin-Funktionen |
| Bäume ausblenden | Fehler `tree-disabled` | 7 | Fehlerbehandlung | Schalter je Baum, ob er für die Apps freigegeben ist | später – klein |

### 2.3 Stammbaum schreiben

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Fakt anlegen oder ändern | `POST Fact` | 1 (20: `type`, 32: `_LOC`-Verweis, 35: GEDCOM-L) | `saveFact()`: `EditActions`, `GedcomLActions`, `ProfilePanel` (A+W); `PersonSheet`, `OrteFenster`, `PruefFenster` (W) | Schreibschicht (2.0); `event`, `event_role`, `name`, `note`, Ort zuordnen | **Meilenstein 2 (1. Schreiben)** |
| Fakt löschen | `POST DeleteFact` | 1 | `deleteFact()`: `EditActions`, `GedcomLActions`, `ProfilePanel`, `Aufgaben` (A+W); `AufgabenFenster` (W) | Schreibschicht; geteilte Ereignisse: nur den Verweis lösen, wenn andere beteiligt sind | **Meilenstein 2 (1. Schreiben)** |
| Person anlegen und verknüpfen | `POST AddIndividual` | 1 | `addIndividual()`: `EditActions` (A+W) | neue Person, ggf. neue Familie, `family_member`, `parentage` | **Meilenstein 2 (1. Schreiben)** |
| Person aus Familie lösen | `POST Unlink` | 4 | `unlink()`: `EditActions`, `ProfilePanel` (A+W) | `family_member` löschen, leere Familie entfernen | **Meilenstein 2 (1. Schreiben)** |
| Datensatz löschen | `POST DeleteRecord` | 4 | `deleteRecord()`: `EditActions` (A+W); `QuelleDialog`, `QuellenFenster` (W) | Löschen mit allen Verweisen (CASCADE ist vorbereitet), leere Familien mit | **Meilenstein 2 (1. Schreiben)** |
| Zwei Personen verknüpfen | `POST Link` | 8 | `link()`: `EditActions` (A+W) | wie `AddIndividual` ohne neue Person | **Meilenstein 2 (1. Schreiben)** |
| Paten, Zeugen, Beteiligte | `POST Association` | 20 | `association()`: `EditActions` (A+W, Ziel aus `PatenDialog` W) | `event_role` mit Rolle, auch ohne Datensatz (`free_name` …, E5) | später – Stufe 20; das Modell kann es schon |
| Reihenfolge von Kindern, Partnerschaften, Namen, Medien | `POST Reorder` | 30 | `reorder()`: `BookmarkActions` (A+W); `PersonSheet` (W) | Spalten `sort` (vorhanden) | später – Stufe 30 |

### 2.4 Moderation und Änderungsverlauf

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Offene Änderungen anzeigen | `GET Pending` | 5 | `pending()`: `EditActions` (A+W); `AnniversaryWorker` (A, Benachrichtigung im Hintergrund) | `change_set`/`change_step` lesen; `Info.trees[].pending` zählen | **Meilenstein 2 (1. Schreiben)** – ohne Moderation kein Schreiben für Bearbeiter |
| Annehmen | `POST Accept` | 5 | `moderate()`: `EditActions`, `HomeSection` (A+W) | Schritte anwenden, Konflikt mit geändertem Stand erkennen (Anhang A) | **Meilenstein 2 (1. Schreiben)** |
| Verwerfen | `POST Reject` | 5 | `moderate()`: wie `Accept` | Satz auf `rejected` | **Meilenstein 2 (1. Schreiben)** |
| Offene Fakten kennzeichnen | Feld `pending` an Fakten | 28 | Anzeige | Überlagerung in der Leseschicht (E4) | **Meilenstein 2 (1. Schreiben)** – das Feld gibt es schon (immer `false`), die Überlagerung kommt mit der Schreibschicht |
| Änderungsverlauf | `GET Changes` | 30 | `changes()`: `AenderungenFenster` (W) | Protokoll aus `change_set` (angenommen, offen, verworfen) mit Verfasser und Zeit, je Baum und je Datensatz | später – Stufe 30 |

### 2.5 Medien, Hauptbild, Ausschnitte

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Bilder ausliefern | Adressen in `thumb`, `file`, `image` | – | `AsyncImage` überall | vorhanden (`/wisetrees/medien/…`); verkleinerte Vorschaubilder fehlen noch | vorhanden; Vorschaubilder **Meilenstein 2 (2. Fotos)** (Datenmenge auf dem Handy) |
| Medienliste | `GET MediaList` | 2 | `mediaList()`: `PhotoActions` (A+W); `MedienWahl` (W) | `media`, `media_file`, `media_link`, 60 je Seite, neueste zuerst (Zeitstempel am Medium fehlt noch) | **Meilenstein 2 (2. Fotos)** |
| Datei hochladen, Medium anlegen und verknüpfen | `POST Media` (Multipart) | 1 (18: `type`, `link=false`) | `uploadMedia()`: `PhotoActions` (A+W); `OrteFenster`, `QuelleDialog`, `ZitatDialog` (W) | **Dateiablage** `<daten>/medien/{Baum}/`, `Info.maxUpload`, Dateinamen ohne Kollision, Prüfung des Dateityps | **Meilenstein 2 (2. Fotos)** |
| Vorhandenes Medium verknüpfen | `POST Media` mit `{media}` | 8 | `linkMedia()`: `PhotoActions` (A+W); `PersonSheet`, `GesichterFenster` (W) | `media_link` anlegen | **Meilenstein 2 (2. Fotos)** |
| Verknüpfung lösen | `POST UnlinkMedia` | 8 | `unlinkMedia()`: `PhotoActions` (A+W); `PersonSheet` (W) | `media_link` löschen; Datei bleibt | **Meilenstein 2 (2. Fotos)** |
| Hauptbild | `POST PrimaryMedia` | 8 (35: `_PRIM`) | `primaryMedia()`: `GedcomLActions` (A+W); `PersonSheet` (W) | `media_link.sort` und `is_primary` (vorhanden) | **Meilenstein 2 (2. Fotos)** |
| Pfad im Medienordner | Feld `media[].path` | 9 | Archiv-Funktionen (Abschnitt 3) | `media_file.path` (vorhanden) | vorhanden |
| Medium aus vorhandener Datei | `POST MediaFromFile` | 18 | `mediaFromFile()`: `MedienWahl`, `GesichterFenster` (W) | Datei im Medienordner suchen, `media` anlegen | später – Stufe 18 |
| Titel und Art ändern | `POST MediaObject` | 23 | `mediaObject()`: `PhotoActions` (A+W); `OrteFenster` (W) | `media.title`, `media_file.media_type` | später – Stufe 23 |
| Ausschnitt setzen | `POST MediaCrop`; Feld `crop` an Medien | 38 | nicht aufgerufen | `media_link.crop_*` (vorhanden) | später – Stufe 38 |
| Porträt aus Ausschnitt | `GET Portrait` (Bild, kein JSON) | 39 | nicht aufgerufen | Bild zuschneiden und verkleinern; dafür eine Bildbibliothek mit verträglicher Lizenz (DEPENDENCIES.md) | später – Stufe 39 |
| Ein Medium mit allen Verknüpften | `GET MediaObject` | 40 | nicht aufgerufen | `media_link` mit `crop` je Person | später – Stufe 40 |

### 2.6 Quellen und Archive

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Quellenliste | `GET Sources` | 18 | `sources()`: `Nachschlagen`, `ProfilePanel` (A+W); `QuellenFenster`, `ZitatDialog` (W) | `source`, `source_repository`, Zählung über `citation` | später – Stufe 18 |
| Eine Quelle mit Zitierenden | `GET Source` | 18 | `source()`: `Nachschlagen` (A+W); `QuellenFenster` (W) | `citation` rückwärts nach Person, Familie, Ereignis | später |
| Quelle anlegen, ändern | `POST Source` | 18 | `saveSource()`: `QuelleDialog`, `QuellenFenster`, `ZitatDialog` (W) | Schreibschicht für `source` | später |
| Archive | `GET Repositories`, `POST Repository` | 18 | `repositories()`, `saveRepository()`: `QuelleDialog`, `AufgabenFenster` (W) | `repository` | später |
| Zitat an Fakt oder Datensatz | `POST Citation` | 18 | `citation()`: `EditActions` (A+W) | `citation` schreiben, verschieben, löschen | später |

### 2.7 Orte und Ortsdatensätze

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Ortsvorschläge beim Tippen | `GET Places?q=` | 8 | `places()`: `EditActions` (A+W) | Suche über `place_name` je Ebene („Wien, Ö“) | später – Orte lassen sich beim Bearbeiten auch ohne Vorschlag eintippen |
| Alle Orte mit Zählung | `GET Places?list=1` | 21 | `placeList()`: `Nachschlagen` (A+W); `Buch`, `BuchFamilien`, `Listen`, `OrteFenster` (W) | `place` mit Zählung über `event`, Koordinaten | später – Stufe 21 |
| Ein Ort | `GET Place` | 21 (27: Typ, Oberort; 32: `unlinked`) | `place()`: `Nachschlagen` (A+W); `OrteFenster`, `AdressenZuHaeusern`, `BuchFamilien`, `Listen` (W) | `place`, `place_type`, `place_link`, `place_attribute`, Unterorte, Personen und Familien am Ort | später |
| Ortsdatensatz speichern | `POST Place` | 22 (27, 32) | `savePlace()`: `OrtDialog`, `OrteFenster`, `AdressenZuHaeusern` (W) | Ort mit GOV-Kennung, Koordinaten, PLZ, Typ, Oberort schreiben; Ereignisse zuordnen (`linkEvents`) | später – Stufe 22 |
| Ort umbenennen, zusammenführen | `POST PlaceRename` | 23 | `renamePlace()`: `OrteFenster` (W) | Ereignisse umhängen, Ortstext am Ereignis (E6) mitziehen, Vorschau | später – Stufe 23 |
| Adresse am Ereignis | Feld `address` | 33 | Anzeige, `AdressenZuHaeusern` (W) | `event.address` | später – Stufe 33 |

### 2.8 Merkliste, Startperson, Jahrestage

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Jahrestage | `GET Anniversaries` | 4 | `anniversaries()`: `AnniversaryActions` (A+W); `AnniversaryWorker` (A, tägliche Erinnerung) | Suche nach Monat und Tag über die Datumsbereiche der Ereignisse; Schutz lebender Personen | **Meilenstein 2 (6. Jahrestage)** |
| Merkliste lesen | `GET Bookmarks` | 11 (30: Favoriten des Baums) | `bookmarks()`: `BookmarkActions` (A+W) | Tabelle Merkliste je Konto und Baum (Kontendatei); ab Stufe 30 dazu Merkliste des Baums mit Notiz | **Meilenstein 2 (5. Merkliste)**; Baum-Favoriten später |
| Merkliste ändern | `POST Bookmarks` | 11 (30: `note`, `forTree`) | `setBookmark()`: `BookmarkActions` (A+W) | wie oben | **Meilenstein 2 (5. Merkliste)** |
| Startperson setzen | `POST StartPerson`; Felder `startXref`, `treeDefaultXref` | 24 | `setStartPerson()`: `BookmarkActions`, `StartpersonDialog` (A+W) | Startperson je Konto und Baum (Kontendatei), Vorgabe je Baum (`meta`) | später – Stufe 24 |

### 2.9 Aufgaben

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Alle Forschungsaufgaben | `GET Tasks` | 30 | `tasks()`: `Aufgaben` (A); `AufgabenFenster` (W) | `task` (vorhanden) mit Träger Person oder Familie, Filter „offen“ | später – Stufe 30 |
| Aufgabe anlegen, ändern | `POST Task` | 30 (35: GEDCOM-L-Felder) | `saveTask()`: `Aufgaben` (A); `AufgabenFenster` (W); erledigt = `DeleteFact` | `task` schreiben; Archiv-Verweis `repository_id` | später |

### 2.10 Zusammenführen

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Vorschau | `POST Merge` mit `preview` | 29 | `mergePreview()`: `ZusammenfuehrenDialog` (W) | Fakten beider Personen vergleichen (gleich, enthalten, verschieden) | später – Stufe 29, nur Verwalter |
| Zusammenführen | `POST Merge` | 29 | `merge()`: `ZusammenfuehrenDialog` (W) | alle Verweise umhängen (`family_member`, `event_role`, `citation`, `media_link`, `note_link`, `person_association`), Fakten nach Auswahl | später |
| Rückgängig | `POST MergeUndo` | 29 | `mergeUndo()`: `ZusammenfuehrenDialog`, `ZusammenfuehrenFenster` (W) | Protokoll mit vollständigem Vorher-Stand; Fehler `changed-since`, wenn seither geändert | später |
| Protokoll | `GET Merges` | 29 | `merges()`: `ZusammenfuehrenFenster` (W) | Tabelle der Zusammenführungen (wer, wann, wen, `undone`) | später |

### 2.11 Nachrichten

| Funktion | Route(n) | Stufe | wo (App) | wisetrees braucht | Einstufung |
|---|---|---:|---|---|---|
| Posteingang, Empfängerliste | `GET Messages`; Feld `Info.user.messages` | 42 | `messages()`: `NachrichtenActions`, `HomeSection` (A); `AnniversaryWorker` (A, Hinweis auf neue Nachrichten) | Tabelle Nachricht (Absender, Empfänger, Betreff, Text, Adresse, Zeit) in der Kontendatei; Liste der möglichen Empfänger | später – Stufe 42, nur wtAnd |
| Senden | `POST Messages` | 42 | `sendMessage()`: `Nachrichten`, `NachrichtenActions` (A); Teilen einer Person als Nachricht | intern speichern und/oder **E-Mail** je Wunsch des Empfängers: SMTP-Einstellungen, E-Mail-Adresse und Zustellwunsch am Konto | später |
| Löschen | `POST MessageDelete` | 42 | `deleteMessages()`: `NachrichtenActions` (A) | nur eigene Nachrichten | später |

### 2.12 Stufen ohne eigene Route

Diese Stufen fügen bestehenden Antworten Felder hinzu. Die Vertragstests
vergleichen mit Antworten der Stufe 42; was dort steht, liefert
wisetrees schon.

| Stufe | Inhalt | Stand |
|---:|---|---|
| 9 | `media[].path` | vorhanden |
| 10 | Heiraten der Kinder in `Individual` | vorhanden |
| 12 | `stepFamilies`, `hasParents`, `partnersCount`, `childrenCount`; `Descendants` bis 10 Generationen | vorhanden |
| 14 | `call`, `chr`, `buri`, `occupation` an jeder Person | vorhanden |
| 15, 16 | `Pedigree` mit Geschwistern, bis 12 Generationen | vorhanden |
| 19 | Paten und Zeugen lesen (`associates`, `associatedIn`) | vorhanden |
| 26 | `Info.loginForm` | vorhanden (feste Werte) |
| 27 | ganzer Ortsdatensatz: Typ, Oberort, GOV-Typ | später (gehört zu `Place`) |
| 28 | `pending` an Fakten | Feld vorhanden; Inhalt mit Meilenstein 2 |
| 31 | `Info.trees[].availableModules` | vorhanden ([API-V1.md](API-V1.md) 6) |
| 32 | Ortsverweise beim Schreiben, `unlinked` | später |
| 34–36 | GEDCOM-L lesen (`extras`, `uids`), `access` je Fakt; GEDCOM-L schreiben | lesen vorhanden; schreiben später |
| 37 | `details` an jedem Fakt | vorhanden |
| 41 | `Info.user.language` | vorhanden |

## 3. Archiv: Sammlungen und Gesichter

Diese Routen gehören **nicht** zu api4wisetrees. Sie haben eine eigene
Stufe (1–6, Feld `api` der Übersicht). Die Apps prüfen beim Start mit
`GET …/sammlungen`, ob es sie gibt; eine 404 ohne JSON heißt „nicht
vorhanden“, und das Archiv bleibt aus. Alle Adressen:
`index.php?route={pfad}/tree/{Baum}/archiv/api/{Aktion}`.

| Funktion | Route(n) | Archiv-Stufe | wo (App) | wisetrees braucht |
|---|---|---:|---|---|
| Übersicht der Sammlungen | `GET sammlungen` (`alle=1` für Verwalter) | 1 (6) | `archive()`, `archiveAdmin()`: `ArchiveActions` (A+W); `ArchivFenster` (W) | Tabellen Sammlung (Name, Symbol, Farbe, Ansicht, Ordner, aktiv, Reihenfolge) und Zuordnung Datei–Sammlung |
| Eine Seite einer Sammlung | `GET sammlung` (`kategorie`, `typ`, `seite`, `pro_seite`) | 1 | `collection()`: `ArchiveActions` (A+W); `ArchivFenster`, `MedienWahl` (W) | Dateien im Medienordner auflisten, auch nicht eingebundene; Vorschaubilder; Zwischenspeicher |
| Bilder, auf denen eine Person ist | `GET sammlung?person=` | 5 | `archivePerson()`: `Gruppenbilder` (A+W), `ProfilePanel`, `PersonSheet` | Gesichter-Index Person → Datei |
| Foto ins Archiv hochladen | `POST hochladen` (Multipart) | 2 | `uploadArchive()`: `ArchiveActions` (A+W); `ArchivFenster` (W) | Dateiablage, Beschriftung in die Bilddatei (EXIF/XMP) schreiben |
| Eintrag zu einer Datei | `GET eintrag?pfad=` | 3 | `archiveEntry()`: `ArchiveActions` (A+W) | Metadaten aus der Datei lesen |
| Beschriftung schreiben | `POST exif` | 2 | `writeExif()`: `ArchiveActions` (A+W); `ArchivFenster` (W) | **Metadaten in Bilddateien schreiben** (Beschreibung, Datum, Personen, Stichwörter) |
| **Gesichter** schreiben | `POST exif` mit `bereiche` | 5 | `writeRegions()`: `GesichterBearbeiten` (A+W); `GesichterFenster` (W) | XMP-Regionen lesen und schreiben; Gesicht → Person oder Text ohne Datensatz (KONZEPT 3.7, E5) |
| Postkarte beschriften | `POST exif` (Motiv, Transkription, Vorder- und Rückseite) | 6 | `writePostcard()`: `ArchivFenster` (W) | wie oben, zwei Dateien |
| Datei umbenennen | `POST umbenennen` | 6 | `archiveRename()`: `ArchivVerwaltung` (W) | Datei und `media_file.path` gemeinsam ändern |
| Bild einer Sammlung zuordnen | `POST zuordnen` | 6 | `archiveAssign()`: `ArchivFenster`, `ArchivVerwaltung` (W) | Zuordnungstabelle |
| Sammlung sichtbar, anlegen, ändern, löschen | `POST sichtbar`, `sammlung-speichern`, `sammlung-loeschen` | 6 | `ArchivFenster`, `ArchivVerwaltung` (W) | Sammlungstabelle |
| Einstellungen, Zwischenspeicher | `GET`/`POST einstellungen`, `POST cache-leeren` | 6 | `archiveSettings()`, `archiveSaveSettings()`, `archiveClearCache()`: `ArchivVerwaltung` (W) | Einstellungen je Baum |

**Einstufung: später.** Begründung: Die Apps laufen ohne Archiv
vollständig und erkennen sein Fehlen selbst. Das Archiv braucht drei
größere Bausteine, die sonst nirgends vorkommen: Metadaten in
Bilddateien schreiben, einen Index über den ganzen Medienordner und
eine eigene Rechteprüfung für Dateien ohne Medienobjekt. Die Gesichter
sind im Modell schon vorgesehen (3.7); sie sollten zuerst als Daten im
Baum stehen und erst danach in die Dateien geschrieben werden.

## 4. Wege außerhalb der Stufen

| Funktion | Weg | wo (App) | Einstufung |
|---|---|---|---|
| GEDCOM oder GEDZIP speichern | `POST /tree/{Baum}/export-client` (Formular, Verwalter) | `exportGedcom()`: `GedcomSpeichernDialog` in `ArchivFenster` (W), nur für den Stammbaum auf diesem PC | **nie** in dieser Form – wisetrees exportiert GEDCOM über die eigene Browser-Seite; für den Desktop-Modus (E14) wird der Weg dort neu festgelegt |
| Seiten im Browser öffnen | Felder `url` in den Antworten | Personentafel: Knopf „im Browser öffnen“, **immer sichtbar**, öffnet `url` in der eingebauten Browseransicht; Teilen einer Person nur mit nicht leerer `url` (sie steht im geteilten Text); Bildbetrachter: Knopf nur mit Adresse; PDF-Ansicht: `url` als Herkunft | siehe Vorschlag unten |

| Geteilte Links erkennen | Adressen `/tree/{Baum}/individual/{xref}` u. ä. | `GeteilteLinks.kt` (A+W) | später – nur nötig, wenn Nachrichten (Stufe 42) Links auf Datensätze enthalten |

**Entschieden zu `url`:** (1) `url` zeigt auf die Startseite von
wisetrees, nicht auf eine Adresse, unter der nichts liegt – umgesetzt.
(2) Mit der App-Änderung zu E17 zeigen die Apps den Knopf nur, wenn
`url` nicht leer ist; danach liefert wisetrees `""`. Teilen einer Person
bleibt damit aus. (3) Eine eigene, nur lesende Personenseite (Fähigkeit
`web`) vorerst nicht.

## 5. Zusammenfassung

| Bereich | Meilenstein 2 | später | nie |
|---|---|---|---|
| Schreiben | `Fact`, `DeleteFact`, `AddIndividual`, `Unlink`, `DeleteRecord`, `Link` | `Association`, `Reorder` | – |
| Moderation | `Pending`, `Accept`, `Reject`, `pending` an Fakten | `Changes` | – |
| Fotos | `MediaList`, `Media` (hochladen, verknüpfen), `UnlinkMedia`, `PrimaryMedia`, Vorschaubilder | `MediaFromFile`, `MediaObject`, `MediaCrop`, `Portrait`, `GET MediaObject` | – |
| Lesen | `Export` | `lang`, `Relationship`, Bäume ausblenden | – |
| Anmeldung, Konten | Koppeln (`Pair`) | `MyAccount`, Passwort im Browser | Registrierung |
| Merkliste, Jahrestage | `Bookmarks`, `Anniversaries` | Baum-Favoriten, `StartPerson` | – |
| Quellen | – | alle (Stufe 18) | – |
| Orte | – | Vorschläge, Liste, Ort, Ortsdatensatz, Umbenennen, Adressen | – |
| Aufgaben, Zusammenführen | – | alle (Stufen 29, 30) | – |
| Nachrichten | – | alle (Stufe 42, mit E-Mail) | – |
| Archiv, Gesichter | – | alle | – |
| Sonstiges | – | geteilte Links | GEDCOM über `export-client`, Browser-Seiten über `url` |

Neue Bausteine, die Meilenstein 2 braucht:

1. Schreibschicht mit Moderation und Protokoll (2.0).
2. Dateiablage für hochgeladene Medien und verkleinerte Vorschaubilder
   mit Pillow (Lizenz MIT-CMU; vor dem Einbau in DEPENDENCIES.md prüfen).
3. `Export`: Leseschicht über alle Personen und Familien, seitenweise.
4. In der Kontendatei: Einmal-Codes zum Koppeln, Merkliste.
5. Jahrestage: Suche nach Monat und Tag über die Datumsbereiche.
6. `Info.features` (E17) mit jeder fertigen Fähigkeit erweitern.
