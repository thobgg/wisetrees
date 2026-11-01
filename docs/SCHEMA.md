# Schema der Datenbanken

*Erzeugt aus dem Code (`backend/baum/schema.py`, `backend/core/konten.py`) mit `python werkzeuge/schema_doku.py`; nicht von Hand bearbeiten.*

*Generated from the code; German only for now. Table and column names are English.*

## Baumdatei (.wise)

Jeder Stammbaum ist eine SQLite-Datei mit `PRAGMA application_id = 0x57495345` („WISE“) und `PRAGMA user_version = 2` (Schemaversion). Die Datei lässt sich mit jedem SQLite-Werkzeug lesen. Das Schema ist portabel für PostgreSQL und MariaDB (KONZEPT.md E16): Kennungen haben höchstens 255 Zeichen, Textspalten mit Index bekommen in MariaDB einen Präfix-Index (191 Zeichen).

Gemeinsame Bausteine:

- **Datum** (`date_text`, `date_kind`, `date_quality`, `date_calendar`, `date_from`, `date_to`): der Text wie in der Quelle, die Art (exact, before, after, between, from, to, from_to, phrase), die Qualität (exact, about, calculated, estimated), der Kalender und der früheste und späteste julianische Tag (KONZEPT 3.8).
- **Sperrvermerk** `resn`: none, privacy, confidential, locked.
- **Träger**: Notizen, Zitate, Medienverweise, Aufgaben und GEDCOM-Reste hängen über je eine Spalte `<typ>_id` an ihrem Träger; genau eine davon ist gefüllt (`on_tree` = am ganzen Baum).
- **Rollen** an Ereignissen: `PRINCIPAL` (Hauptbeteiligte) und die Codes von GEDCOM 7 (CHIL, CLERGY, FATH, FRIEND, GODP, HUSB, MOTH, MULTIPLE, NGHBR, OFFICIATOR, PARENT, SPOU, WIFE, WITN, OTHER), dazu eigene Codes mit `X_`.

### meta

Angaben zur Datei: title, gedcom_head (Kopf der eingelesenen Datei), import_report (Importbericht).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `key` | Text (255) | Schlüssel |  |  |  |
| `value` | Text |  |  |  |  |

### person

Person (3.2); Namen, Ereignisse und Familien hängen über eigene Tabellen an.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) | ja, eindeutig |  |  | GEDCOM-Kennung ohne @ (I12, F3 …) |
| `sex` | Text | ja | 'U' |  |  |
| `uid` | Text |  |  |  |  |
| `changed_at` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`
- `sex IN ('M', 'F', 'X', 'U')`

### name

Name einer Person mit seinen Teilen (NAME mit GIVN, SURN, NICK, _RUFNAME …).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `person_id` | Ganzzahl | ja |  | person.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `type` | Text |  |  |  |  |
| `type_text` | Text |  |  |  |  |
| `value` | Text | ja |  |  |  |
| `given` | Text |  |  |  |  |
| `rufname` | Text |  |  |  |  |
| `nickname` | Text |  |  |  |  |
| `name_prefix` | Text |  |  |  |  |
| `surname_prefix` | Text |  |  |  |  |
| `surname` | Text |  |  |  |  |
| `name_suffix` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`

Indizes: `name_person` (person_id, sort); `name_surname` (surname, given)

### family

Familie als eigenes Objekt (E2); Mitglieder in family_member.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) | ja, eindeutig |  |  | GEDCOM-Kennung ohne @ (I12, F3 …) |
| `uid` | Text |  |  |  |  |
| `changed_at` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`

### family_member

Partner und Kinder einer Familie.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `family_id` | Ganzzahl | ja |  | family.id (beim Löschen: CASCADE) |  |
| `person_id` | Ganzzahl | ja |  | person.id (beim Löschen: CASCADE) |  |
| `role` | Text (20) | ja |  |  |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge in der Familie (Partner 1 = HUSB, 2 = WIFE) |
| `person_sort` | Ganzzahl | ja |  |  | Reihenfolge in der Liste der Person (FAMS/FAMC) |

Regeln:

- eindeutig: family_id, person_id, role
- `role IN ('partner', 'child')`

Indizes: `family_member_person` (person_id)

### parentage

Abstammungsart je Paar aus Kind und Elternteil (leiblich, adoptiert, Pflege …).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `family_id` | Ganzzahl | ja |  | family.id (beim Löschen: CASCADE) |  |
| `child_id` | Ganzzahl | ja |  | person.id (beim Löschen: CASCADE) |  |
| `parent_id` | Ganzzahl | ja |  | person.id (beim Löschen: CASCADE) |  |
| `kind` | Text | ja | 'birth' |  |  |
| `status` | Text |  |  |  | GEDCOM FAMC:STAT (challenged, proven, disproven) |

Regeln:

- eindeutig: family_id, child_id, parent_id
- `kind IN ('birth', 'adopted', 'foster', 'step', 'sealing', 'unknown')`

Indizes: `parentage_child` (child_id); `parentage_parent` (parent_id)

### place

Ort (3.5); Namen, Arten, Zugehörigkeiten und Angaben datiert in eigenen Tabellen.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) | eindeutig |  |  | nur Orte, die als _LOC kamen oder als _LOC gehen |
| `gov_id` | Text |  |  |  |  |
| `lat` | Kommazahl |  |  |  |  |
| `lng` | Kommazahl |  |  |  |  |
| `maidenhead` | Text |  |  |  |  |
| `uid` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`

### place_name

Name eines Ortes, datiert, mit Sprache und Kurzform.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `place_id` | Ganzzahl | ja |  | place.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `name` | Text | ja |  |  |  |
| `lang` | Text |  |  |  |  |
| `abbr` | Text |  |  |  |  |
| `date_text` | Text |  |  |  |  |
| `date_kind` | Text |  |  |  |  |
| `date_quality` | Text |  |  |  |  |
| `date_calendar` | Text |  |  |  |  |
| `date_from` | Ganzzahl |  |  |  |  |
| `date_to` | Ganzzahl |  |  |  |  |

Regeln:

- `date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `date_quality IN ('exact', 'about', 'calculated', 'estimated')`

Indizes: `place_name_name` (name); `place_name_place` (place_id)

### place_type

Art eines Ortes, datiert, mit GOV-Typnummer.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `place_id` | Ganzzahl | ja |  | place.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `type_text` | Text |  |  |  |  |
| `gov_type` | Ganzzahl |  |  |  |  |
| `date_text` | Text |  |  |  |  |
| `date_kind` | Text |  |  |  |  |
| `date_quality` | Text |  |  |  |  |
| `date_calendar` | Text |  |  |  |  |
| `date_from` | Ganzzahl |  |  |  |  |
| `date_to` | Ganzzahl |  |  |  |  |

Regeln:

- `date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `date_quality IN ('exact', 'about', 'calculated', 'estimated')`

### place_link

Ort A liegt in Ort B, datiert, mit Art der Zugehörigkeit (POLI, RELI …).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `place_id` | Ganzzahl | ja |  | place.id (beim Löschen: CASCADE) |  |
| `parent_id` | Ganzzahl | ja |  | place.id (beim Löschen: CASCADE) |  |
| `kind` | Text |  |  |  |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `date_text` | Text |  |  |  |  |
| `date_kind` | Text |  |  |  |  |
| `date_quality` | Text |  |  |  |  |
| `date_calendar` | Text |  |  |  |  |
| `date_from` | Ganzzahl |  |  |  |  |
| `date_to` | Ganzzahl |  |  |  |  |

Regeln:

- `date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `date_quality IN ('exact', 'about', 'calculated', 'estimated')`
- `place_id <> parent_id`

Indizes: `place_link_parent` (parent_id); `place_link_place` (place_id)

### place_attribute

Weitere datierte Angaben am Ort: Postleitzahl, Amtliche Kennung, Einwohner, Land, Religion.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `place_id` | Ganzzahl | ja |  | place.id (beim Löschen: CASCADE) |  |
| `kind` | Text | ja |  |  |  |
| `value` | Text | ja |  |  |  |
| `subtype` | Text |  |  |  |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `date_text` | Text |  |  |  |  |
| `date_kind` | Text |  |  |  |  |
| `date_quality` | Text |  |  |  |  |
| `date_calendar` | Text |  |  |  |  |
| `date_from` | Ganzzahl |  |  |  |  |
| `date_to` | Ganzzahl |  |  |  |  |

Regeln:

- `date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `date_quality IN ('exact', 'about', 'calculated', 'estimated')`

Indizes: `place_attribute_place` (place_id)

### event

Ereignis oder Merkmal (3.3); die Beteiligten stehen in event_role.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `type` | Text | ja |  |  | GEDCOM-Tag: BIRT, CHR, MARR, OCCU, RESI, EVEN, _XYZ … |
| `subtype` | Text |  |  |  | 2 TYPE |
| `value` | Text |  |  |  | Wert (OCCU Bauer, RELI evangelisch, Y) |
| `description` | Text |  |  |  | freie Beschreibung |
| `negated` | Ganzzahl | ja | 0 |  | hat nicht stattgefunden |
| `place_id` | Ganzzahl |  |  | place.id (beim Löschen: SET NULL) |  |
| `place_text` | Text |  |  |  | PLAC wie in der Quelle (E6) |
| `address` | Text |  |  |  |  |
| `cause` | Text |  |  |  |  |
| `agency` | Text |  |  |  |  |
| `date_text` | Text |  |  |  |  |
| `date_kind` | Text |  |  |  |  |
| `date_quality` | Text |  |  |  |  |
| `date_calendar` | Text |  |  |  |  |
| `date_from` | Ganzzahl |  |  |  |  |
| `date_to` | Ganzzahl |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `date_quality IN ('exact', 'about', 'calculated', 'estimated')`
- `negated IN (0, 1)`
- `resn IN ('none', 'privacy', 'confidential', 'locked')`

Indizes: `event_date` (date_from); `event_place` (place_id); `event_type` (type)

### event_role

Beteiligung an einem Ereignis: Hauptbeteiligte (PRINCIPAL), Paten, Zeugen ….

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `event_id` | Ganzzahl | ja |  | event.id (beim Löschen: CASCADE) |  |
| `person_id` | Ganzzahl |  |  | person.id (beim Löschen: CASCADE) |  |
| `family_id` | Ganzzahl |  |  | family.id (beim Löschen: CASCADE) |  |
| `place_id` | Ganzzahl |  |  | place.id (beim Löschen: CASCADE) |  |
| `free_name` | Text |  |  |  | Beteiligter ohne Datensatz (E5): Name … |
| `free_addition` | Text |  |  |  | … Zusatz („Bauer in Hesel“) … |
| `free_text` | Text |  |  |  | … und der Text, wie er kam |
| `role` | Text | ja |  |  |  |
| `rela` | Text |  |  |  | Rollentext, wie er kam (RELA); bei OTHER der Freitext |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge der Beteiligten am Ereignis (PRINCIPAL: 0) |
| `fact_sort` | Ganzzahl |  |  |  | Stelle in der Faktenliste des Trägers (nur Hauptbeteiligte) |
| `preferred` | Ganzzahl | ja | 0 |  |  |
| `age` | Text |  |  |  | Angaben zur Person laut Eintrag (3.3) |
| `occupation` | Text |  |  |  |  |
| `residence` | Text |  |  |  |  |
| `remark` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `(CASE WHEN person_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN family_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN place_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN free_name IS NOT NULL THEN 1 ELSE 0 END) = 1`
- `preferred IN (0, 1)`
- `resn IN ('none', 'privacy', 'confidential', 'locked')`
- `role IN ('PRINCIPAL', 'CHIL', 'CLERGY', 'FATH', 'FRIEND', 'GODP', 'HUSB', 'MOTH', 'MULTIPLE', 'NGHBR', 'OFFICIATOR', 'PARENT', 'SPOU', 'WIFE', 'WITN', 'OTHER') OR (SUBSTR(role, 1, 2) = 'X_' AND LENGTH(role) > 2)`

Indizes: `event_role_event` (event_id); `event_role_family` (family_id); `event_role_person` (person_id); `event_role_place` (place_id)

### event_place_detail

Welche Angaben des Ortes am Ereignis standen (MAP, _GOV, _MAIDENHEAD, _POST); die Werte liegen am Ort (E15).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `event_id` | Ganzzahl | ja |  | event.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `kind` | Text | ja |  |  |  |
| `place_attribute_id` | Ganzzahl |  |  | place_attribute.id (beim Löschen: CASCADE) |  |

Regeln:

- `(kind = 'postal' AND place_attribute_id IS NOT NULL) OR (kind <> 'postal' AND place_attribute_id IS NULL)`
- `kind IN ('map', 'gov', 'maidenhead', 'postal')`

Indizes: `event_place_detail_event` (event_id)

### person_association

Verbindung zweier Personen ohne Ereignis (GEDCOM 5.5.1 1 ASSO).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `person_id` | Ganzzahl | ja |  | person.id (beim Löschen: CASCADE) |  |
| `other_person_id` | Ganzzahl | ja |  | person.id (beim Löschen: CASCADE) |  |
| `relation` | Text |  |  |  |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |

### repository

Archiv.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) | ja, eindeutig |  |  | GEDCOM-Kennung ohne @ (I12, F3 …) |
| `name` | Text |  |  |  |  |
| `address` | Text |  |  |  | ADDR mit CONT, wie es kam |
| `address_name` | Text |  |  |  | GEDCOM-L ADDR:_NAME |
| `adr1` | Text |  |  |  |  |
| `city` | Text |  |  |  |  |
| `postal_code` | Text |  |  |  |  |
| `country` | Text |  |  |  |  |
| `phone` | Text |  |  |  |  |
| `email` | Text |  |  |  |  |
| `www` | Text |  |  |  |  |
| `uid` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`

### source

Quelle (3.6).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) | ja, eindeutig |  |  | GEDCOM-Kennung ohne @ (I12, F3 …) |
| `title` | Text |  |  |  |  |
| `abbr` | Text |  |  |  |  |
| `author` | Text |  |  |  |  |
| `publication` | Text |  |  |  |  |
| `text` | Text |  |  |  |  |
| `agency` | Text |  |  |  |  |
| `uid` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`

### source_coverage

Was eine Quelle abdeckt (SOUR:DATA:EVEN).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `source_id` | Ganzzahl | ja |  | source.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `events` | Text |  |  |  |  |
| `place_text` | Text |  |  |  |  |
| `date_text` | Text |  |  |  |  |
| `date_kind` | Text |  |  |  |  |
| `date_quality` | Text |  |  |  |  |
| `date_calendar` | Text |  |  |  |  |
| `date_from` | Ganzzahl |  |  |  |  |
| `date_to` | Ganzzahl |  |  |  |  |

Regeln:

- `date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `date_quality IN ('exact', 'about', 'calculated', 'estimated')`

### source_repository

Wo eine Quelle liegt: Archiv mit Signatur.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `source_id` | Ganzzahl | ja |  | source.id (beim Löschen: CASCADE) |  |
| `repository_id` | Ganzzahl |  |  | repository.id (beim Löschen: SET NULL) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `call_number` | Text |  |  |  |  |
| `medium` | Text |  |  |  |  |

### note

Notiz, als Datensatz mit Kennung oder eingebettet.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) | eindeutig |  |  | NULL = eingebettete Notiz |
| `text` | Text | ja |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`

### media

Medienobjekt (3.7); Dateien in media_file.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) | eindeutig |  |  | GEDCOM-Kennung ohne @ (I12, F3 …) |
| `title` | Text |  |  |  |  |
| `uid` | Text |  |  |  |  |
| `resn` | Text |  |  |  |  |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'locked')`

### media_file

Datei eines Medienobjekts, Pfad relativ zum Medienordner des Baums.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `media_id` | Ganzzahl | ja |  | media.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `path` | Text | ja |  |  |  |
| `format` | Text |  |  |  |  |
| `media_type` | Text |  |  |  |  |
| `title` | Text |  |  |  |  |

### task

Forschungsaufgabe (_TODO) an Person, Familie oder Ort.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `person_id` | Ganzzahl |  |  | person.id (beim Löschen: CASCADE) |  |
| `family_id` | Ganzzahl |  |  | family.id (beim Löschen: CASCADE) |  |
| `place_id` | Ganzzahl |  |  | place.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `text` | Text |  |  |  |  |
| `description` | Text |  |  |  |  |
| `category` | Text |  |  |  |  |
| `priority` | Text |  |  |  |  |
| `task_type` | Text |  |  |  |  |
| `status` | Text |  |  |  |  |
| `solution` | Text |  |  |  |  |
| `repository_id` | Ganzzahl |  |  | repository.id (beim Löschen: SET NULL) |  |
| `user_name` | Text |  |  |  |  |
| `date_text` | Text |  |  |  |  |
| `date_kind` | Text |  |  |  |  |
| `date_quality` | Text |  |  |  |  |
| `date_calendar` | Text |  |  |  |  |
| `date_from` | Ganzzahl |  |  |  |  |
| `date_to` | Ganzzahl |  |  |  |  |
| `reminder_text` | Text |  |  |  |  |
| `completed_text` | Text |  |  |  |  |

Regeln:

- `(CASE WHEN person_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN family_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN place_id IS NOT NULL THEN 1 ELSE 0 END) = 1`
- `date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `date_quality IN ('exact', 'about', 'calculated', 'estimated')`

Indizes: `task_family` (family_id); `task_person` (person_id); `task_place` (place_id)

### citation

Zitat einer Quelle an seinem Träger, mit Seite, Qualität und Text.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `person_id` | Ganzzahl |  |  | person.id (beim Löschen: CASCADE) |  |
| `name_id` | Ganzzahl |  |  | name.id (beim Löschen: CASCADE) |  |
| `event_id` | Ganzzahl |  |  | event.id (beim Löschen: CASCADE) |  |
| `event_role_id` | Ganzzahl |  |  | event_role.id (beim Löschen: CASCADE) |  |
| `family_id` | Ganzzahl |  |  | family.id (beim Löschen: CASCADE) |  |
| `place_id` | Ganzzahl |  |  | place.id (beim Löschen: CASCADE) |  |
| `media_id` | Ganzzahl |  |  | media.id (beim Löschen: CASCADE) |  |
| `note_id` | Ganzzahl |  |  | note.id (beim Löschen: CASCADE) |  |
| `task_id` | Ganzzahl |  |  | task.id (beim Löschen: CASCADE) |  |
| `person_association_id` | Ganzzahl |  |  | person_association.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `source_id` | Ganzzahl |  |  | source.id (beim Löschen: SET NULL) |  |
| `source_text` | Text |  |  |  | Zitat ohne Quellendatensatz (2 SOUR Text) |
| `page` | Text |  |  |  |  |
| `quality` | Ganzzahl |  |  |  |  |
| `event_type` | Text |  |  |  | SOUR:EVEN |
| `event_role` | Text |  |  |  | SOUR:EVEN:ROLE |
| `data_text` | Text |  |  |  | SOUR:DATA:TEXT |
| `data_date_text` | Text |  |  |  |  |
| `data_date_kind` | Text |  |  |  |  |
| `data_date_quality` | Text |  |  |  |  |
| `data_date_calendar` | Text |  |  |  |  |
| `data_date_from` | Ganzzahl |  |  |  |  |
| `data_date_to` | Ganzzahl |  |  |  |  |
| `entry_id` | Ganzzahl |  |  |  | Eintrag der Belegebene (E10), vorerst immer leer |
| `resn` | Text |  |  |  |  |

Regeln:

- `(CASE WHEN person_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN name_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN event_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN event_role_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN family_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN place_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN media_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN note_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN person_association_id IS NOT NULL THEN 1 ELSE 0 END) = 1`
- `data_date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')`
- `data_date_quality IN ('exact', 'about', 'calculated', 'estimated')`
- `quality BETWEEN 0 AND 3`
- `resn IN ('none', 'privacy', 'confidential', 'locked')`

Indizes: `citation_event` (event_id); `citation_event_role` (event_role_id); `citation_family` (family_id); `citation_media` (media_id); `citation_name` (name_id); `citation_note` (note_id); `citation_person` (person_id); `citation_person_association` (person_association_id); `citation_place` (place_id); `citation_source` (source_id); `citation_task` (task_id)

### note_link

Verweis eines Trägers auf eine Notiz.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `note_id` | Ganzzahl | ja |  | note.id (beim Löschen: CASCADE) |  |
| `person_id` | Ganzzahl |  |  | person.id (beim Löschen: CASCADE) |  |
| `name_id` | Ganzzahl |  |  | name.id (beim Löschen: CASCADE) |  |
| `event_id` | Ganzzahl |  |  | event.id (beim Löschen: CASCADE) |  |
| `event_role_id` | Ganzzahl |  |  | event_role.id (beim Löschen: CASCADE) |  |
| `family_id` | Ganzzahl |  |  | family.id (beim Löschen: CASCADE) |  |
| `place_id` | Ganzzahl |  |  | place.id (beim Löschen: CASCADE) |  |
| `source_id` | Ganzzahl |  |  | source.id (beim Löschen: CASCADE) |  |
| `repository_id` | Ganzzahl |  |  | repository.id (beim Löschen: CASCADE) |  |
| `media_id` | Ganzzahl |  |  | media.id (beim Löschen: CASCADE) |  |
| `citation_id` | Ganzzahl |  |  | citation.id (beim Löschen: CASCADE) |  |
| `task_id` | Ganzzahl |  |  | task.id (beim Löschen: CASCADE) |  |
| `person_association_id` | Ganzzahl |  |  | person_association.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |

Regeln:

- `(CASE WHEN person_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN name_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN event_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN event_role_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN family_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN place_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN source_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN repository_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN media_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN citation_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN person_association_id IS NOT NULL THEN 1 ELSE 0 END) = 1`

Indizes: `note_link_citation` (citation_id); `note_link_event` (event_id); `note_link_event_role` (event_role_id); `note_link_family` (family_id); `note_link_media` (media_id); `note_link_name` (name_id); `note_link_person` (person_id); `note_link_person_association` (person_association_id); `note_link_place` (place_id); `note_link_repository` (repository_id); `note_link_source` (source_id); `note_link_task` (task_id)

### media_link

Verweis eines Trägers auf ein Medienobjekt, mit Ausschnitt.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `media_id` | Ganzzahl | ja |  | media.id (beim Löschen: CASCADE) |  |
| `person_id` | Ganzzahl |  |  | person.id (beim Löschen: CASCADE) |  |
| `event_id` | Ganzzahl |  |  | event.id (beim Löschen: CASCADE) |  |
| `family_id` | Ganzzahl |  |  | family.id (beim Löschen: CASCADE) |  |
| `place_id` | Ganzzahl |  |  | place.id (beim Löschen: CASCADE) |  |
| `source_id` | Ganzzahl |  |  | source.id (beim Löschen: CASCADE) |  |
| `citation_id` | Ganzzahl |  |  | citation.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `is_primary` | Ganzzahl | ja | 0 |  |  |
| `title` | Text |  |  |  |  |
| `crop_top` | Ganzzahl |  |  |  |  |
| `crop_left` | Ganzzahl |  |  |  |  |
| `crop_height` | Ganzzahl |  |  |  |  |
| `crop_width` | Ganzzahl |  |  |  |  |

Regeln:

- `(CASE WHEN person_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN event_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN family_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN place_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN source_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN citation_id IS NOT NULL THEN 1 ELSE 0 END) = 1`
- `is_primary IN (0, 1)`

Indizes: `media_link_citation` (citation_id); `media_link_event` (event_id); `media_link_family` (family_id); `media_link_person` (person_id); `media_link_place` (place_id); `media_link_source` (source_id)

### gedcom_rest

Was das Modell nicht kennt, bleibt als GEDCOM an seiner Struktur (E9).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `on_tree` | Ganzzahl |  |  |  |  |
| `person_id` | Ganzzahl |  |  | person.id (beim Löschen: CASCADE) |  |
| `name_id` | Ganzzahl |  |  | name.id (beim Löschen: CASCADE) |  |
| `event_id` | Ganzzahl |  |  | event.id (beim Löschen: CASCADE) |  |
| `event_role_id` | Ganzzahl |  |  | event_role.id (beim Löschen: CASCADE) |  |
| `family_id` | Ganzzahl |  |  | family.id (beim Löschen: CASCADE) |  |
| `place_id` | Ganzzahl |  |  | place.id (beim Löschen: CASCADE) |  |
| `source_id` | Ganzzahl |  |  | source.id (beim Löschen: CASCADE) |  |
| `repository_id` | Ganzzahl |  |  | repository.id (beim Löschen: CASCADE) |  |
| `media_id` | Ganzzahl |  |  | media.id (beim Löschen: CASCADE) |  |
| `note_id` | Ganzzahl |  |  | note.id (beim Löschen: CASCADE) |  |
| `citation_id` | Ganzzahl |  |  | citation.id (beim Löschen: CASCADE) |  |
| `task_id` | Ganzzahl |  |  | task.id (beim Löschen: CASCADE) |  |
| `person_association_id` | Ganzzahl |  |  | person_association.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `under` | Text |  |  |  | Zeile, unter der der Rest stand, wenn sie selbst in Spalten aufging (PLAC, _STAT …) |
| `gedcom` | Text | ja |  |  | mit den Stufen aus der Datei |

Regeln:

- `(CASE WHEN on_tree IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN person_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN name_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN event_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN event_role_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN family_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN place_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN source_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN repository_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN media_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN note_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN citation_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN person_association_id IS NOT NULL THEN 1 ELSE 0 END) = 1`
- `on_tree = 1`

Indizes: `gedcom_rest_citation` (citation_id); `gedcom_rest_event` (event_id); `gedcom_rest_event_role` (event_role_id); `gedcom_rest_family` (family_id); `gedcom_rest_media` (media_id); `gedcom_rest_name` (name_id); `gedcom_rest_note` (note_id); `gedcom_rest_person` (person_id); `gedcom_rest_person_association` (person_association_id); `gedcom_rest_place` (place_id); `gedcom_rest_repository` (repository_id); `gedcom_rest_source` (source_id); `gedcom_rest_task` (task_id)

### privacy_rule

Datenschutz-Regel ohne Sperrvermerk in den Daten: je Fakt- oder Datensatzart (tag), je Datensatz (xref) oder je Faktart an einem Datensatz (beides).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `xref` | Text (255) |  |  |  | Kennung des Datensatzes; leer = alle Datensätze |
| `tag` | Text (255) |  |  |  | Fakt- oder Datensatzart (SSN, SOUR, _TODO …); leer = der ganze Datensatz |
| `resn` | Text | ja |  |  | none = alle, privacy = ab Mitglied, confidential = nur Verwalter, hidden = niemand |

Regeln:

- `resn IN ('none', 'privacy', 'confidential', 'hidden')`
- `xref IS NOT NULL OR tag IS NOT NULL`

Indizes: `privacy_rule_xref` (xref)

### change_set

Offene Änderungen: ein Satz je Bearbeitung (E4 a).

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `author` | Text | ja |  |  |  |
| `created_at` | Text | ja |  |  |  |
| `status` | Text | ja | 'pending' |  |  |
| `decided_by` | Text |  |  |  |  |
| `decided_at` | Text |  |  |  |  |
| `comment` | Text |  |  |  |  |

Regeln:

- `status IN ('pending', 'accepted', 'rejected')`

### change_step

Einzelschritt eines Änderungssatzes.

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `id` | Ganzzahl | Schlüssel |  |  | interne Kennung, ändert sich nie (E1) |
| `change_set_id` | Ganzzahl | ja |  | change_set.id (beim Löschen: CASCADE) |  |
| `sort` | Ganzzahl | ja |  |  | Reihenfolge |
| `object_type` | Text | ja |  |  |  |
| `object_id` | Ganzzahl |  |  |  | NULL bei Objekten, die der Satz erst anlegt |
| `operation` | Text | ja |  |  |  |
| `old_json` | Text |  |  |  |  |
| `new_json` | Text |  |  |  |  |

Regeln:

- `operation IN ('create', 'update', 'delete')`

Indizes: `change_step_object` (object_type, object_id)

## Kontendatei (konten.sqlite)

Konten, Rollen je Baum und Sitzungen; eine Datei für alle Bäume. Von Sitzungen wird nur der SHA-256 des Tokens gespeichert, Passwörter als Argon2id.

### konto

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `name` | Text (255) | Schlüssel |  |  |  |
| `pw_hash` | Text | ja |  |  |  |
| `real_name` | Text | ja | '' |  |  |
| `email` | Text | ja | '' |  |  |
| `language` | Text | ja | '' |  |  |
| `is_admin` | Ganzzahl | ja | 0 |  |  |
| `created_at` | Kommazahl | ja |  |  |  |

### baumrolle

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `konto` | Text (255) | Schlüssel |  | konto.name (beim Löschen: CASCADE) |  |
| `baum` | Text (255) | Schlüssel |  |  |  |
| `rolle` | Text (20) | ja |  |  |  |

Regeln:

- `rolle IN ('member', 'editor', 'moderator', 'manager')`

### sitzung

| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |
|---|---|---|---|---|---|
| `token_hash` | Text (64) | Schlüssel |  |  |  |
| `konto` | Text (255) |  |  | konto.name (beim Löschen: CASCADE) |  |
| `csrf` | Text | ja |  |  |  |
| `created_at` | Kommazahl | ja |  |  |  |
| `expires_at` | Kommazahl | ja |  |  |  |
| `last_seen` | Kommazahl | ja |  |  |  |
| `ip` | Text |  |  |  |  |
| `user_agent` | Text |  |  |  |  |

Indizes: `sitzung_ablauf` (expires_at); `sitzung_konto` (konto)
