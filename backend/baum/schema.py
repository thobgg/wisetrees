"""Schema einer Baumdatei (.wise), Fassung 1. Grundlage: KONZEPT.md Abschnitt 3, E1–E13.

Namen der Tabellen und Spalten sind englisch, damit die Datei auch ohne wisetrees verständlich bleibt (Gedanke
aus E13). Daten: Originaltext plus Bereich in julianischen Tagen (3.8). Rollen an Ereignissen: Codes nach
GEDCOM 7 ROLE (GODP, WITN, CLERGY …) plus PRINCIPAL (Hauptperson), FAMILY (Ereignis der Familie) und SUBJECT
(Ereignis eines Ortes).

Notizen, Zitate, Medienverweise, Aufgaben und GEDCOM-Reste hängen an ihrem Träger über je eine Fremdschlüsselspalte
je möglichem Trägertyp (person_id, event_id …), ON DELETE CASCADE, und eine Regel: genau eine ist gefüllt.
"""

APPLICATION_ID = 0x57495345  # ASCII "WISE", E12
SCHEMA_VERSION = 1

# Mögliche Träger je Tabelle (Tabellenname = Trägertyp, Spalte <typ>_id). „tree“ = am ganzen Baum (Spalte on_tree).
TRAEGER = {
    "citation": ("person", "name", "event", "event_role", "family", "place", "media", "note", "task",
                 "person_association"),
    "note_link": ("person", "name", "event", "event_role", "family", "place", "source", "repository", "media",
                  "citation", "task", "person_association"),
    "media_link": ("person", "event", "family", "place", "source", "citation"),
    "task": ("person", "family", "place"),
    "gedcom_rest": ("tree", "person", "name", "event", "event_role", "family", "place", "source", "repository",
                    "media", "note", "citation", "task", "person_association"),
}


def _traeger(tabelle: str) -> str:
    """Spalten je Trägertyp mit Fremdschlüssel und die Regel „genau einer“."""
    spalten = []
    for typ in TRAEGER[tabelle]:
        if typ == "tree":
            spalten.append("    on_tree INTEGER CHECK (on_tree = 1),")
        else:
            spalten.append(f"    {typ}_id INTEGER REFERENCES {typ}(id) ON DELETE CASCADE,")
    return "\n".join(spalten)


def _traeger_regel(tabelle: str) -> str:
    """Tabellenbedingung „genau ein Träger“ – muss nach allen Spalten stehen."""
    gefuellt = ["(on_tree IS NOT NULL)" if t == "tree" else f"({t}_id IS NOT NULL)" for t in TRAEGER[tabelle]]
    return f"    CHECK ({' + '.join(gefuellt)} = 1)"


def _traeger_index(tabelle: str) -> str:
    return "\n".join(f"CREATE INDEX {tabelle}_{t} ON {tabelle}({t}_id) WHERE {t}_id IS NOT NULL;"
                     for t in TRAEGER[tabelle] if t != "tree")


# Rollen an Ereignissen: GEDCOM 7 ROLE, dazu PRINCIPAL (Hauptbeteiligte: Person, Familie oder Ort) und eigene Codes
# mit Präfix X_ (z. B. X_INFORMANT). OTHER: Freitext steht in rela.
ROLLEN_GEDCOM7 = ("CHIL", "CLERGY", "FATH", "FRIEND", "GODP", "HUSB", "MOTH", "MULTIPLE", "NGHBR", "OFFICIATOR",
                  "PARENT", "SPOU", "WIFE", "WITN", "OTHER")
_ROLLE = "role TEXT NOT NULL CHECK (role IN ({}) OR role GLOB 'X_?*')".format(
    ", ".join(f"'{r}'" for r in ("PRINCIPAL", *ROLLEN_GEDCOM7)))

# Ein Datum: GEDCOM-Text, Art, Qualität, Kalender, frühester und spätester julianischer Tag (KONZEPT 3.8).
_DATUM = """
    {p}date_text     TEXT,
    {p}date_kind     TEXT CHECK ({p}date_kind IN ('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase')),
    {p}date_quality  TEXT CHECK ({p}date_quality IN ('exact', 'about', 'calculated', 'estimated')),
    {p}date_calendar TEXT,
    {p}date_from     INTEGER,
    {p}date_to       INTEGER"""


def _datum(prefix: str = "") -> str:
    return _DATUM.format(p=prefix)


_RESN = "resn TEXT CHECK (resn IN ('none', 'privacy', 'confidential', 'locked'))"

DDL = f"""
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
    {_RESN}
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
    {_RESN}
);
CREATE INDEX name_person ON name(person_id, sort);
CREATE INDEX name_surname ON name(surname, given);

-- Familien und Abstammung (3.4) --------------------------------------------------------------------
CREATE TABLE family (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    xref       TEXT NOT NULL UNIQUE,
    uid        TEXT,
    changed_at TEXT,
    {_RESN}
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
    {_RESN}
);

CREATE TABLE place_name (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    sort     INTEGER NOT NULL,
    name     TEXT NOT NULL,
    lang     TEXT,
    abbr     TEXT,{_datum()}
);
CREATE INDEX place_name_name ON place_name(name);
CREATE INDEX place_name_place ON place_name(place_id);

CREATE TABLE place_type (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id  INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    sort      INTEGER NOT NULL,
    type_text TEXT,
    gov_type  INTEGER,{_datum()}
);

-- Ort A liegt in Ort B, datiert, mit Art der Zugehörigkeit (POLI, RELI …)
CREATE TABLE place_link (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id  INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    parent_id INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    kind      TEXT,
    sort      INTEGER NOT NULL,{_datum()},
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
    sort     INTEGER NOT NULL,{_datum()}
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
    agency      TEXT,{_datum()},
    {_RESN}
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
    {_ROLLE},
    rela          TEXT,                -- Rollentext, wie er kam (RELA); bei OTHER der Freitext
    sort          INTEGER NOT NULL,    -- Reihenfolge der Beteiligten am Ereignis (PRINCIPAL: 0)
    fact_sort     INTEGER,             -- Stelle in der Faktenliste des Trägers (nur Hauptbeteiligte)
    preferred     INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
    age           TEXT,                -- Angaben zur Person laut Eintrag (3.3)
    occupation    TEXT,
    residence     TEXT,
    remark        TEXT,
    {_RESN},
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
    {_RESN}
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
    {_RESN}
);

-- Was eine Quelle abdeckt (SOUR:DATA:EVEN)
CREATE TABLE source_coverage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id  INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    sort       INTEGER NOT NULL,
    events     TEXT,
    place_text TEXT,{_datum()}
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
{_traeger("citation")}
    sort        INTEGER NOT NULL,
    source_id   INTEGER REFERENCES source(id) ON DELETE SET NULL,
    source_text TEXT,                  -- Zitat ohne Quellendatensatz (2 SOUR Text)
    page        TEXT,
    quality     INTEGER CHECK (quality BETWEEN 0 AND 3),
    event_type  TEXT,                  -- SOUR:EVEN
    event_role  TEXT,                  -- SOUR:EVEN:ROLE
    data_text   TEXT,                  -- SOUR:DATA:TEXT{_datum("data_")},
    entry_id    INTEGER,               -- Eintrag der Belegebene (E10), vorerst immer leer
    {_RESN},
{_traeger_regel("citation")}
);
{_traeger_index("citation")}
CREATE INDEX citation_source ON citation(source_id);

-- Notizen, Medien, Aufgaben (3.7) ---------------------------------------------------------------------
CREATE TABLE note (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    xref TEXT UNIQUE,                  -- NULL = eingebettete Notiz
    text TEXT NOT NULL,
    {_RESN}
);

CREATE TABLE note_link (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
{_traeger("note_link")}
    sort    INTEGER NOT NULL,
{_traeger_regel("note_link")}
);
{_traeger_index("note_link")}

CREATE TABLE media (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    xref  TEXT UNIQUE,
    title TEXT,
    uid   TEXT,
    {_RESN}
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
{_traeger("media_link")}
    sort        INTEGER NOT NULL,
    is_primary  INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    title       TEXT,
    crop_top    INTEGER,
    crop_left   INTEGER,
    crop_height INTEGER,
    crop_width  INTEGER,
{_traeger_regel("media_link")}
);
{_traeger_index("media_link")}

CREATE TABLE task (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
{_traeger("task")}
    sort          INTEGER NOT NULL,
    text          TEXT,
    description   TEXT,
    category      TEXT,
    priority      TEXT,
    task_type     TEXT,
    status        TEXT,
    solution      TEXT,
    repository_id INTEGER REFERENCES repository(id) ON DELETE SET NULL,
    user_name     TEXT,{_datum()},
    reminder_text  TEXT,
    completed_text TEXT,
{_traeger_regel("task")}
);
{_traeger_index("task")}

-- Was das Modell nicht kennt, bleibt als GEDCOM an seiner Struktur (E9) ------------------------------
CREATE TABLE gedcom_rest (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
{_traeger("gedcom_rest")}
    sort   INTEGER NOT NULL,
    under  TEXT,                       -- Zeile, unter der der Rest stand, wenn sie selbst in Spalten aufging (PLAC, _STAT …)
    gedcom TEXT NOT NULL,              -- mit den Stufen aus der Datei
{_traeger_regel("gedcom_rest")}
);
{_traeger_index("gedcom_rest")}

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
"""
