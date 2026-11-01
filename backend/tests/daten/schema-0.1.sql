-- Schema der Baumdateien aus wisetrees 0.1 (Schemaversion 1), eingefroren als Vergleich für Tests.
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Personen und Namen (3.2) ------------------------------------------------------------------------
CREATE TABLE person (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    xref       TEXT NOT NULL UNIQUE,
    sex        TEXT NOT NULL DEFAULT 'U' CHECK (sex IN ('M', 'F', 'X', 'U')),
    uid        TEXT,
    changed_at TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);

CREATE TABLE name (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id      INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    sort           INTEGER NOT NULL,
    type           TEXT,
    type_text      TEXT,
    value          TEXT NOT NULL,
    given          TEXT,
    rufname        TEXT,
    nickname       TEXT,
    name_prefix    TEXT,
    surname_prefix TEXT,
    surname        TEXT,
    name_suffix    TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);
CREATE INDEX name_person ON name(person_id, sort);
CREATE INDEX name_surname ON name(surname, given);

-- Familien und Abstammung (3.4) --------------------------------------------------------------------
CREATE TABLE family (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    xref       TEXT NOT NULL UNIQUE,
    uid        TEXT,
    changed_at TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);

CREATE TABLE family_member (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id   INTEGER NOT NULL REFERENCES family(id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('partner', 'child')),
    sort        INTEGER NOT NULL,      -- Reihenfolge in der Familie (Partner 1 = HUSB, 2 = WIFE)
    person_sort INTEGER NOT NULL,      -- Reihenfolge in der Liste der Person (FAMS/FAMC)
    UNIQUE (family_id, person_id, role)
);
CREATE INDEX family_member_person ON family_member(person_id);

-- Abstammungsart je Paar aus Kind und Elternteil (3.4)
CREATE TABLE parentage (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER NOT NULL REFERENCES family(id) ON DELETE CASCADE,
    child_id  INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    parent_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL DEFAULT 'birth' CHECK (kind IN ('birth', 'adopted', 'foster', 'step', 'sealing', 'unknown')),
    status    TEXT,                    -- GEDCOM FAMC:STAT (challenged, proven, disproven)
    UNIQUE (family_id, child_id, parent_id)
);
CREATE INDEX parentage_child ON parentage(child_id);
CREATE INDEX parentage_parent ON parentage(parent_id);

-- Orte (3.5) -----------------------------------------------------------------------------------------
CREATE TABLE place (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    xref       TEXT UNIQUE,            -- nur Orte, die als _LOC kamen oder als _LOC gehen
    gov_id     TEXT,
    lat        REAL,
    lng        REAL,
    maidenhead TEXT,
    uid        TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);

CREATE TABLE place_name (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    sort     INTEGER NOT NULL,
    name     TEXT NOT NULL,
    lang     TEXT,
    abbr     TEXT,
    date_text     TEXT,
    date_kind     TEXT CHECK (date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    date_quality  TEXT CHECK (date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    date_calendar TEXT,
    date_from     INTEGER,
    date_to       INTEGER
);
CREATE INDEX place_name_name ON place_name(name);
CREATE INDEX place_name_place ON place_name(place_id);

CREATE TABLE place_type (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id  INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    sort      INTEGER NOT NULL,
    type_text TEXT,
    gov_type  INTEGER,
    date_text     TEXT,
    date_kind     TEXT CHECK (date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    date_quality  TEXT CHECK (date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    date_calendar TEXT,
    date_from     INTEGER,
    date_to       INTEGER
);

-- Ort A liegt in Ort B, datiert, mit Art der Zugehörigkeit (POLI, RELI …)
CREATE TABLE place_link (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id  INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    parent_id INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    kind      TEXT,
    sort      INTEGER NOT NULL,
    date_text     TEXT,
    date_kind     TEXT CHECK (date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    date_quality  TEXT CHECK (date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    date_calendar TEXT,
    date_from     INTEGER,
    date_to       INTEGER,
    CHECK (place_id <> parent_id)
);
CREATE INDEX place_link_place ON place_link(place_id);
CREATE INDEX place_link_parent ON place_link(parent_id);

-- Weitere datierte Angaben am Ort: postal, aidn, demographics, state, country, religion
CREATE TABLE place_attribute (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    kind     TEXT NOT NULL,
    value    TEXT NOT NULL,
    subtype  TEXT,
    sort     INTEGER NOT NULL,
    date_text     TEXT,
    date_kind     TEXT CHECK (date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    date_quality  TEXT CHECK (date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    date_calendar TEXT,
    date_from     INTEGER,
    date_to       INTEGER
);
CREATE INDEX place_attribute_place ON place_attribute(place_id);

-- Ereignisse und Beteiligte (3.3) -----------------------------------------------------------------
CREATE TABLE event (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,         -- GEDCOM-Tag: BIRT, CHR, MARR, OCCU, RESI, EVEN, _XYZ …
    subtype     TEXT,                  -- 2 TYPE
    value       TEXT,                  -- Wert (OCCU Bauer, RELI evangelisch, Y)
    description TEXT,                  -- freie Beschreibung
    negated     INTEGER NOT NULL DEFAULT 0 CHECK (negated IN (0, 1)),  -- hat nicht stattgefunden
    place_id    INTEGER REFERENCES place(id) ON DELETE SET NULL,
    place_text  TEXT,                  -- PLAC wie in der Quelle (E6)
    address     TEXT,
    cause       TEXT,
    agency      TEXT,
    date_text     TEXT,
    date_kind     TEXT CHECK (date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    date_quality  TEXT CHECK (date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    date_calendar TEXT,
    date_from     INTEGER,
    date_to       INTEGER,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);
CREATE INDEX event_type ON event(type);
CREATE INDEX event_place ON event(place_id);
CREATE INDEX event_date ON event(date_from);

CREATE TABLE event_role (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      INTEGER NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    person_id     INTEGER REFERENCES person(id) ON DELETE CASCADE,
    family_id     INTEGER REFERENCES family(id) ON DELETE CASCADE,
    place_id      INTEGER REFERENCES place(id) ON DELETE CASCADE,
    free_name     TEXT,                -- Beteiligter ohne Datensatz (E5): Name …
    free_addition TEXT,                -- … Zusatz („Bauer in Hesel“) …
    free_text     TEXT,                -- … und der Text, wie er kam
    role TEXT NOT NULL CHECK (role IN ('PRINCIPAL', 'CHIL', 'CLERGY', 'FATH', 'FRIEND', 'GODP', 'HUSB', 'MOTH', 'MULTIPLE', 'NGHBR', 'OFFICIATOR', 'PARENT', 'SPOU', 'WIFE', 'WITN', 'OTHER') OR role GLOB 'X_?*'),
    rela          TEXT,                -- Rollentext, wie er kam (RELA); bei OTHER der Freitext
    sort          INTEGER NOT NULL,    -- Reihenfolge der Beteiligten am Ereignis (PRINCIPAL: 0)
    fact_sort     INTEGER,             -- Stelle in der Faktenliste des Trägers (nur Hauptbeteiligte)
    preferred     INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
    age           TEXT,                -- Angaben zur Person laut Eintrag (3.3)
    occupation    TEXT,
    residence     TEXT,
    remark        TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked')),
    CHECK ((person_id IS NOT NULL) + (family_id IS NOT NULL) + (place_id IS NOT NULL) + (free_name IS NOT NULL) = 1)
);
CREATE INDEX event_role_event ON event_role(event_id);
CREATE INDEX event_role_person ON event_role(person_id);
CREATE INDEX event_role_family ON event_role(family_id);
CREATE INDEX event_role_place ON event_role(place_id);

-- Welche Angaben des Ortes am Ereignis standen (GEDCOM: PLAC mit MAP, _GOV, _MAIDENHEAD, _POST). Die Werte liegen
-- am Ort; hier steht nur, dass das Ereignis sie nannte. Abweichende Werte bleiben Rest am Ereignis (E9). Entschieden
-- 01.11.2026 (KONZEPT 3.5).
CREATE TABLE event_place_detail (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id           INTEGER NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    sort               INTEGER NOT NULL,
    kind               TEXT NOT NULL CHECK (kind IN ('map', 'gov', 'maidenhead', 'postal')),
    place_attribute_id INTEGER REFERENCES place_attribute(id) ON DELETE CASCADE,
    CHECK ((kind = 'postal') = (place_attribute_id IS NOT NULL))
);
CREATE INDEX event_place_detail_event ON event_place_detail(event_id);

-- Verbindung zweier Personen ohne Ereignis (GEDCOM 5.5.1 1 ASSO)
CREATE TABLE person_association (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id       INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    other_person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    relation        TEXT,
    sort            INTEGER NOT NULL
);

-- Quellen (3.6) --------------------------------------------------------------------------------------
CREATE TABLE repository (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    xref         TEXT NOT NULL UNIQUE,
    name         TEXT,
    address      TEXT,                 -- ADDR mit CONT, wie es kam
    address_name TEXT,                 -- GEDCOM-L ADDR:_NAME
    adr1         TEXT,
    city         TEXT,
    postal_code  TEXT,
    country      TEXT,
    phone        TEXT,
    email        TEXT,
    www          TEXT,
    uid          TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);

CREATE TABLE source (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    xref        TEXT NOT NULL UNIQUE,
    title       TEXT,
    abbr        TEXT,
    author      TEXT,
    publication TEXT,
    text        TEXT,
    agency      TEXT,
    uid         TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);

-- Was eine Quelle abdeckt (SOUR:DATA:EVEN)
CREATE TABLE source_coverage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id  INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    sort       INTEGER NOT NULL,
    events     TEXT,
    place_text TEXT,
    date_text     TEXT,
    date_kind     TEXT CHECK (date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    date_quality  TEXT CHECK (date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    date_calendar TEXT,
    date_from     INTEGER,
    date_to       INTEGER
);

CREATE TABLE source_repository (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    repository_id INTEGER REFERENCES repository(id) ON DELETE SET NULL,
    sort          INTEGER NOT NULL,
    call_number   TEXT,
    medium        TEXT
);

CREATE TABLE citation (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
    name_id INTEGER REFERENCES name(id) ON DELETE CASCADE,
    event_id INTEGER REFERENCES event(id) ON DELETE CASCADE,
    event_role_id INTEGER REFERENCES event_role(id) ON DELETE CASCADE,
    family_id INTEGER REFERENCES family(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES place(id) ON DELETE CASCADE,
    media_id INTEGER REFERENCES media(id) ON DELETE CASCADE,
    note_id INTEGER REFERENCES note(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES task(id) ON DELETE CASCADE,
    person_association_id INTEGER REFERENCES person_association(id) ON DELETE CASCADE,
    sort        INTEGER NOT NULL,
    source_id   INTEGER REFERENCES source(id) ON DELETE SET NULL,
    source_text TEXT,                  -- Zitat ohne Quellendatensatz (2 SOUR Text)
    page        TEXT,
    quality     INTEGER CHECK (quality BETWEEN 0 AND 3),
    event_type  TEXT,                  -- SOUR:EVEN
    event_role  TEXT,                  -- SOUR:EVEN:ROLE
    data_text   TEXT,                  -- SOUR:DATA:TEXT
    data_date_text     TEXT,
    data_date_kind     TEXT CHECK (data_date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    data_date_quality  TEXT CHECK (data_date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    data_date_calendar TEXT,
    data_date_from     INTEGER,
    data_date_to       INTEGER,
    entry_id    INTEGER,               -- Eintrag der Belegebene (E10), vorerst immer leer
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked')),
    CHECK ((person_id IS NOT NULL) + (name_id IS NOT NULL) + (event_id IS NOT NULL) + (event_role_id IS NOT NULL) + (family_id IS NOT NULL) + (place_id IS NOT NULL) + (media_id IS NOT NULL) + (note_id IS NOT NULL) + (task_id IS NOT NULL) + (person_association_id IS NOT NULL) = 1)
);
CREATE INDEX citation_person ON citation(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX citation_name ON citation(name_id) WHERE name_id IS NOT NULL;
CREATE INDEX citation_event ON citation(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX citation_event_role ON citation(event_role_id) WHERE event_role_id IS NOT NULL;
CREATE INDEX citation_family ON citation(family_id) WHERE family_id IS NOT NULL;
CREATE INDEX citation_place ON citation(place_id) WHERE place_id IS NOT NULL;
CREATE INDEX citation_media ON citation(media_id) WHERE media_id IS NOT NULL;
CREATE INDEX citation_note ON citation(note_id) WHERE note_id IS NOT NULL;
CREATE INDEX citation_task ON citation(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX citation_person_association ON citation(person_association_id) WHERE person_association_id IS NOT NULL;
CREATE INDEX citation_source ON citation(source_id);

-- Notizen, Medien, Aufgaben (3.7) ---------------------------------------------------------------------
CREATE TABLE note (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    xref TEXT UNIQUE,                  -- NULL = eingebettete Notiz
    text TEXT NOT NULL,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);

CREATE TABLE note_link (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
    name_id INTEGER REFERENCES name(id) ON DELETE CASCADE,
    event_id INTEGER REFERENCES event(id) ON DELETE CASCADE,
    event_role_id INTEGER REFERENCES event_role(id) ON DELETE CASCADE,
    family_id INTEGER REFERENCES family(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES place(id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES source(id) ON DELETE CASCADE,
    repository_id INTEGER REFERENCES repository(id) ON DELETE CASCADE,
    media_id INTEGER REFERENCES media(id) ON DELETE CASCADE,
    citation_id INTEGER REFERENCES citation(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES task(id) ON DELETE CASCADE,
    person_association_id INTEGER REFERENCES person_association(id) ON DELETE CASCADE,
    sort    INTEGER NOT NULL,
    CHECK ((person_id IS NOT NULL) + (name_id IS NOT NULL) + (event_id IS NOT NULL) + (event_role_id IS NOT NULL) + (family_id IS NOT NULL) + (place_id IS NOT NULL) + (source_id IS NOT NULL) + (repository_id IS NOT NULL) + (media_id IS NOT NULL) + (citation_id IS NOT NULL) + (task_id IS NOT NULL) + (person_association_id IS NOT NULL) = 1)
);
CREATE INDEX note_link_person ON note_link(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX note_link_name ON note_link(name_id) WHERE name_id IS NOT NULL;
CREATE INDEX note_link_event ON note_link(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX note_link_event_role ON note_link(event_role_id) WHERE event_role_id IS NOT NULL;
CREATE INDEX note_link_family ON note_link(family_id) WHERE family_id IS NOT NULL;
CREATE INDEX note_link_place ON note_link(place_id) WHERE place_id IS NOT NULL;
CREATE INDEX note_link_source ON note_link(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX note_link_repository ON note_link(repository_id) WHERE repository_id IS NOT NULL;
CREATE INDEX note_link_media ON note_link(media_id) WHERE media_id IS NOT NULL;
CREATE INDEX note_link_citation ON note_link(citation_id) WHERE citation_id IS NOT NULL;
CREATE INDEX note_link_task ON note_link(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX note_link_person_association ON note_link(person_association_id) WHERE person_association_id IS NOT NULL;

CREATE TABLE media (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    xref  TEXT UNIQUE,
    title TEXT,
    uid   TEXT,
    resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))
);

CREATE TABLE media_file (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id   INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    sort       INTEGER NOT NULL,
    path       TEXT NOT NULL,
    format     TEXT,
    media_type TEXT,
    title      TEXT
);

CREATE TABLE media_link (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id    INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
    event_id INTEGER REFERENCES event(id) ON DELETE CASCADE,
    family_id INTEGER REFERENCES family(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES place(id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES source(id) ON DELETE CASCADE,
    citation_id INTEGER REFERENCES citation(id) ON DELETE CASCADE,
    sort        INTEGER NOT NULL,
    is_primary  INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    title       TEXT,
    crop_top    INTEGER,
    crop_left   INTEGER,
    crop_height INTEGER,
    crop_width  INTEGER,
    CHECK ((person_id IS NOT NULL) + (event_id IS NOT NULL) + (family_id IS NOT NULL) + (place_id IS NOT NULL) + (source_id IS NOT NULL) + (citation_id IS NOT NULL) = 1)
);
CREATE INDEX media_link_person ON media_link(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX media_link_event ON media_link(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX media_link_family ON media_link(family_id) WHERE family_id IS NOT NULL;
CREATE INDEX media_link_place ON media_link(place_id) WHERE place_id IS NOT NULL;
CREATE INDEX media_link_source ON media_link(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX media_link_citation ON media_link(citation_id) WHERE citation_id IS NOT NULL;

CREATE TABLE task (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
    family_id INTEGER REFERENCES family(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES place(id) ON DELETE CASCADE,
    sort          INTEGER NOT NULL,
    text          TEXT,
    description   TEXT,
    category      TEXT,
    priority      TEXT,
    task_type     TEXT,
    status        TEXT,
    solution      TEXT,
    repository_id INTEGER REFERENCES repository(id) ON DELETE SET NULL,
    user_name     TEXT,
    date_text     TEXT,
    date_kind     TEXT CHECK (date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    date_quality  TEXT CHECK (date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    date_calendar TEXT,
    date_from     INTEGER,
    date_to       INTEGER,
    reminder_text  TEXT,
    completed_text TEXT,
    CHECK ((person_id IS NOT NULL) + (family_id IS NOT NULL) + (place_id IS NOT NULL) = 1)
);
CREATE INDEX task_person ON task(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX task_family ON task(family_id) WHERE family_id IS NOT NULL;
CREATE INDEX task_place ON task(place_id) WHERE place_id IS NOT NULL;

-- Was das Modell nicht kennt, bleibt als GEDCOM an seiner Struktur (E9) ------------------------------
CREATE TABLE gedcom_rest (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    on_tree INTEGER CHECK (on_tree = 1),
    person_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
    name_id INTEGER REFERENCES name(id) ON DELETE CASCADE,
    event_id INTEGER REFERENCES event(id) ON DELETE CASCADE,
    event_role_id INTEGER REFERENCES event_role(id) ON DELETE CASCADE,
    family_id INTEGER REFERENCES family(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES place(id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES source(id) ON DELETE CASCADE,
    repository_id INTEGER REFERENCES repository(id) ON DELETE CASCADE,
    media_id INTEGER REFERENCES media(id) ON DELETE CASCADE,
    note_id INTEGER REFERENCES note(id) ON DELETE CASCADE,
    citation_id INTEGER REFERENCES citation(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES task(id) ON DELETE CASCADE,
    person_association_id INTEGER REFERENCES person_association(id) ON DELETE CASCADE,
    sort   INTEGER NOT NULL,
    under  TEXT,                       -- Zeile, unter der der Rest stand, wenn sie selbst in Spalten aufging (PLAC, _STAT …)
    gedcom TEXT NOT NULL,              -- mit den Stufen aus der Datei
    CHECK ((on_tree IS NOT NULL) + (person_id IS NOT NULL) + (name_id IS NOT NULL) + (event_id IS NOT NULL) + (event_role_id IS NOT NULL) + (family_id IS NOT NULL) + (place_id IS NOT NULL) + (source_id IS NOT NULL) + (repository_id IS NOT NULL) + (media_id IS NOT NULL) + (note_id IS NOT NULL) + (citation_id IS NOT NULL) + (task_id IS NOT NULL) + (person_association_id IS NOT NULL) = 1)
);
CREATE INDEX gedcom_rest_person ON gedcom_rest(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX gedcom_rest_name ON gedcom_rest(name_id) WHERE name_id IS NOT NULL;
CREATE INDEX gedcom_rest_event ON gedcom_rest(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX gedcom_rest_event_role ON gedcom_rest(event_role_id) WHERE event_role_id IS NOT NULL;
CREATE INDEX gedcom_rest_family ON gedcom_rest(family_id) WHERE family_id IS NOT NULL;
CREATE INDEX gedcom_rest_place ON gedcom_rest(place_id) WHERE place_id IS NOT NULL;
CREATE INDEX gedcom_rest_source ON gedcom_rest(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX gedcom_rest_repository ON gedcom_rest(repository_id) WHERE repository_id IS NOT NULL;
CREATE INDEX gedcom_rest_media ON gedcom_rest(media_id) WHERE media_id IS NOT NULL;
CREATE INDEX gedcom_rest_note ON gedcom_rest(note_id) WHERE note_id IS NOT NULL;
CREATE INDEX gedcom_rest_citation ON gedcom_rest(citation_id) WHERE citation_id IS NOT NULL;
CREATE INDEX gedcom_rest_task ON gedcom_rest(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX gedcom_rest_person_association ON gedcom_rest(person_association_id) WHERE person_association_id IS NOT NULL;

-- Offene Änderungen (E4 a) ------------------------------------------------------------------------------
CREATE TABLE change_set (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    author      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    decided_by  TEXT,
    decided_at  TEXT,
    comment     TEXT
);

CREATE TABLE change_step (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    change_set_id INTEGER NOT NULL REFERENCES change_set(id) ON DELETE CASCADE,
    sort          INTEGER NOT NULL,
    object_type   TEXT NOT NULL,
    object_id     INTEGER,             -- NULL bei Objekten, die der Satz erst anlegt
    operation     TEXT NOT NULL CHECK (operation IN ('create', 'update', 'delete')),
    old_json      TEXT,
    new_json      TEXT
);
CREATE INDEX change_step_object ON change_step(object_type, object_id);
