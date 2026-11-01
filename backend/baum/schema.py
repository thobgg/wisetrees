"""Schema einer Baumdatei (.wise), Fassung 1. Grundlage: KONZEPT.md Abschnitt 3, E1–E16.

Namen der Tabellen und Spalten sind englisch, damit die Datei auch ohne wisetrees verständlich bleibt (Gedanke
aus E13). Daten: Originaltext plus Bereich in julianischen Tagen (3.8). Rollen an Ereignissen: Codes nach
GEDCOM 7 ROLE (GODP, WITN, CLERGY …) plus PRINCIPAL (Hauptperson) und eigene Codes mit Präfix X_.

Notizen, Zitate, Medienverweise, Aufgaben und GEDCOM-Reste hängen an ihrem Träger über je eine Fremdschlüsselspalte
je möglichem Trägertyp (person_id, event_id …), ON DELETE CASCADE, und eine Regel: genau eine ist gefüllt.

Das Schema ist mit SQLAlchemy Core beschrieben und portabel (E16): feste Längen nur, wo ein eindeutiger Index sie
verlangt (xref, meta.key), Indizes ohne Bedingung, Prüfregeln in Standard-SQL. Textspalten mit Index bekommen in
MariaDB einen Präfix-Index; ihre Werte bleiben ohne Längengrenze.
"""

from __future__ import annotations

from sqlalchemy import (CheckConstraint, Column, Double, ForeignKey, Index, Integer, MetaData, String, Table, Text,
                        UniqueConstraint, text)

APPLICATION_ID = 0x57495345  # ASCII "WISE", E12
SCHEMA_VERSION = 1

XREF_LAENGE = 255     # GEDCOM-Kennung ohne @ (E16); längere lehnt der Import ab
PRAEFIX = 191         # Länge des Präfix-Index für Textspalten in MariaDB (utf8mb4)

metadata = MetaData()

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

# Rollen an Ereignissen: GEDCOM 7 ROLE, dazu PRINCIPAL (Hauptbeteiligte: Person, Familie oder Ort) und eigene Codes
# mit Präfix X_ (z. B. X_INFORMANT). OTHER: Freitext steht in rela.
ROLLEN_GEDCOM7 = ("CHIL", "CLERGY", "FATH", "FRIEND", "GODP", "HUSB", "MOTH", "MULTIPLE", "NGHBR", "OFFICIATOR",
                  "PARENT", "SPOU", "WIFE", "WITN", "OTHER")


def _liste(werte) -> str:
    return ", ".join(f"'{w}'" for w in werte)


def _genau_eine(spalten) -> str:
    """Standard-SQL für „genau eine der Spalten ist gefüllt“."""
    return " + ".join(f"(CASE WHEN {s} IS NOT NULL THEN 1 ELSE 0 END)" for s in spalten) + " = 1"


def _tabelle(name: str, *teile) -> Table:
    return Table(name, metadata, Column("id", Integer, primary_key=True), *teile, sqlite_autoincrement=True)


def _ref(tabelle: str, *, pflicht: bool = False, beim_loeschen: str = "CASCADE", spalte: str | None = None) -> Column:
    return Column(spalte or f"{tabelle}_id", Integer, ForeignKey(f"{tabelle}.id", ondelete=beim_loeschen),
                  nullable=not pflicht)


def _sort(name: str = "sort") -> Column:
    return Column(name, Integer, nullable=False)


def _flag(name: str) -> list:
    return [Column(name, Integer, nullable=False, server_default=text("0")), CheckConstraint(f"{name} IN (0, 1)")]


def _datum(p: str = "") -> list:
    """Ein Datum: GEDCOM-Text, Art, Qualität, Kalender, frühester und spätester julianischer Tag (KONZEPT 3.8)."""
    return [
        Column(f"{p}date_text", Text),
        Column(f"{p}date_kind", Text),
        Column(f"{p}date_quality", Text),
        Column(f"{p}date_calendar", Text),
        Column(f"{p}date_from", Integer),
        Column(f"{p}date_to", Integer),
        CheckConstraint(f"{p}date_kind IN ({_liste(('exact', 'before', 'after', 'between', 'from', 'to', 'from_to', 'phrase'))})"),
        CheckConstraint(f"{p}date_quality IN ({_liste(('exact', 'about', 'calculated', 'estimated'))})"),
    ]


def _resn() -> list:
    return [Column("resn", Text), CheckConstraint(f"resn IN ({_liste(('none', 'privacy', 'confidential', 'locked'))})")]


def _xref(pflicht: bool = True) -> Column:
    return Column("xref", String(XREF_LAENGE), nullable=not pflicht, unique=True)


def _traeger(tabelle: str) -> list:
    """Spalten je Trägertyp mit Fremdschlüssel und die Regel „genau einer“."""
    teile, spalten = [], []
    for typ in TRAEGER[tabelle]:
        if typ == "tree":
            teile += [Column("on_tree", Integer), CheckConstraint("on_tree = 1")]
            spalten.append("on_tree")
        else:
            teile.append(_ref(typ))
            spalten.append(f"{typ}_id")
    return teile


def _traeger_regel(tabelle: str) -> CheckConstraint:
    return CheckConstraint(_genau_eine("on_tree" if t == "tree" else f"{t}_id" for t in TRAEGER[tabelle]))


def _traeger_index(tabelle: str) -> list:
    return [Index(f"{tabelle}_{t}", f"{t}_id") for t in TRAEGER[tabelle] if t != "tree"]


def _text_index(name: str, *spalten: str, texte: tuple[str, ...] | None = None) -> Index:
    """Index über Textspalten; in MariaDB als Präfix-Index (nur die Textspalten, Zahlen ganz)."""
    return Index(name, *spalten, mysql_length={s: PRAEFIX for s in (texte or spalten)})


meta = Table(
    "meta", metadata,
    Column("key", String(XREF_LAENGE), primary_key=True),
    Column("value", Text),
)

# Personen und Namen (3.2) --------------------------------------------------------------------------------------
person = _tabelle(
    "person",
    _xref(),
    Column("sex", Text, nullable=False, server_default=text("'U'")),
    Column("uid", Text),
    Column("changed_at", Text),
    *_resn(),
    CheckConstraint("sex IN ('M', 'F', 'X', 'U')"),
)

name = _tabelle(
    "name",
    _ref("person", pflicht=True),
    _sort(),
    Column("type", Text),
    Column("type_text", Text),
    Column("value", Text, nullable=False),
    Column("given", Text),
    Column("rufname", Text),
    Column("nickname", Text),
    Column("name_prefix", Text),
    Column("surname_prefix", Text),
    Column("surname", Text),
    Column("name_suffix", Text),
    *_resn(),
    Index("name_person", "person_id", "sort"),
    _text_index("name_surname", "surname", "given"),
)

# Familien und Abstammung (3.4) ---------------------------------------------------------------------------------
family = _tabelle(
    "family",
    _xref(),
    Column("uid", Text),
    Column("changed_at", Text),
    *_resn(),
)

family_member = _tabelle(
    "family_member",
    _ref("family", pflicht=True),
    _ref("person", pflicht=True),
    Column("role", String(20), nullable=False),
    _sort(),                 # Reihenfolge in der Familie (Partner 1 = HUSB, 2 = WIFE)
    _sort("person_sort"),    # Reihenfolge in der Liste der Person (FAMS/FAMC)
    CheckConstraint("role IN ('partner', 'child')"),
    UniqueConstraint("family_id", "person_id", "role"),
    Index("family_member_person", "person_id"),
)

# Abstammungsart je Paar aus Kind und Elternteil (3.4)
parentage = _tabelle(
    "parentage",
    _ref("family", pflicht=True),
    _ref("person", pflicht=True, spalte="child_id"),
    _ref("person", pflicht=True, spalte="parent_id"),
    Column("kind", Text, nullable=False, server_default=text("'birth'")),
    Column("status", Text),  # GEDCOM FAMC:STAT (challenged, proven, disproven)
    CheckConstraint(f"kind IN ({_liste(('birth', 'adopted', 'foster', 'step', 'sealing', 'unknown'))})"),
    UniqueConstraint("family_id", "child_id", "parent_id"),
    Index("parentage_child", "child_id"),
    Index("parentage_parent", "parent_id"),
)

# Orte (3.5) ----------------------------------------------------------------------------------------------------
place = _tabelle(
    "place",
    _xref(pflicht=False),    # nur Orte, die als _LOC kamen oder als _LOC gehen
    Column("gov_id", Text),
    Column("lat", Double),   # Double: in MariaDB ist FLOAT nur einfach genau
    Column("lng", Double),
    Column("maidenhead", Text),
    Column("uid", Text),
    *_resn(),
)

place_name = _tabelle(
    "place_name",
    _ref("place", pflicht=True),
    _sort(),
    Column("name", Text, nullable=False),
    Column("lang", Text),
    Column("abbr", Text),
    *_datum(),
    _text_index("place_name_name", "name"),
    Index("place_name_place", "place_id"),
)

place_type = _tabelle(
    "place_type",
    _ref("place", pflicht=True),
    _sort(),
    Column("type_text", Text),
    Column("gov_type", Integer),
    *_datum(),
)

# Ort A liegt in Ort B, datiert, mit Art der Zugehörigkeit (POLI, RELI …)
place_link = _tabelle(
    "place_link",
    _ref("place", pflicht=True),
    _ref("place", pflicht=True, spalte="parent_id"),
    Column("kind", Text),
    _sort(),
    *_datum(),
    CheckConstraint("place_id <> parent_id"),
    Index("place_link_place", "place_id"),
    Index("place_link_parent", "parent_id"),
)

# Weitere datierte Angaben am Ort: postal, aidn, demographics, state, country, religion
place_attribute = _tabelle(
    "place_attribute",
    _ref("place", pflicht=True),
    Column("kind", Text, nullable=False),
    Column("value", Text, nullable=False),
    Column("subtype", Text),
    _sort(),
    *_datum(),
    Index("place_attribute_place", "place_id"),
)

# Ereignisse und Beteiligte (3.3) -------------------------------------------------------------------------------
event = _tabelle(
    "event",
    Column("type", Text, nullable=False),     # GEDCOM-Tag: BIRT, CHR, MARR, OCCU, RESI, EVEN, _XYZ …
    Column("subtype", Text),                  # 2 TYPE
    Column("value", Text),                    # Wert (OCCU Bauer, RELI evangelisch, Y)
    Column("description", Text),              # freie Beschreibung
    *_flag("negated"),                        # hat nicht stattgefunden
    _ref("place", beim_loeschen="SET NULL"),
    Column("place_text", Text),               # PLAC wie in der Quelle (E6)
    Column("address", Text),
    Column("cause", Text),
    Column("agency", Text),
    *_datum(),
    *_resn(),
    _text_index("event_type", "type"),
    Index("event_place", "place_id"),
    Index("event_date", "date_from"),
)

event_role = _tabelle(
    "event_role",
    _ref("event", pflicht=True),
    _ref("person"),
    _ref("family"),
    _ref("place"),
    Column("free_name", Text),       # Beteiligter ohne Datensatz (E5): Name …
    Column("free_addition", Text),   # … Zusatz („Bauer in Hesel“) …
    Column("free_text", Text),       # … und der Text, wie er kam
    Column("role", Text, nullable=False),
    Column("rela", Text),            # Rollentext, wie er kam (RELA); bei OTHER der Freitext
    _sort(),                         # Reihenfolge der Beteiligten am Ereignis (PRINCIPAL: 0)
    Column("fact_sort", Integer),    # Stelle in der Faktenliste des Trägers (nur Hauptbeteiligte)
    *_flag("preferred"),
    Column("age", Text),             # Angaben zur Person laut Eintrag (3.3)
    Column("occupation", Text),
    Column("residence", Text),
    Column("remark", Text),
    *_resn(),
    CheckConstraint(f"role IN ({_liste(('PRINCIPAL', *ROLLEN_GEDCOM7))}) "
                    "OR (SUBSTR(role, 1, 2) = 'X_' AND LENGTH(role) > 2)"),
    CheckConstraint(_genau_eine(("person_id", "family_id", "place_id", "free_name"))),
    Index("event_role_event", "event_id"),
    Index("event_role_person", "person_id"),
    Index("event_role_family", "family_id"),
    Index("event_role_place", "place_id"),
)

# Welche Angaben des Ortes am Ereignis standen (GEDCOM: PLAC mit MAP, _GOV, _MAIDENHEAD, _POST). Die Werte liegen
# am Ort; hier steht nur, dass das Ereignis sie nannte. Abweichende Werte bleiben Rest am Ereignis (E9, E15).
event_place_detail = _tabelle(
    "event_place_detail",
    _ref("event", pflicht=True),
    _sort(),
    Column("kind", Text, nullable=False),
    _ref("place_attribute"),
    CheckConstraint("kind IN ('map', 'gov', 'maidenhead', 'postal')"),
    CheckConstraint("(kind = 'postal' AND place_attribute_id IS NOT NULL) "
                    "OR (kind <> 'postal' AND place_attribute_id IS NULL)"),
    Index("event_place_detail_event", "event_id"),
)

# Verbindung zweier Personen ohne Ereignis (GEDCOM 5.5.1 1 ASSO)
person_association = _tabelle(
    "person_association",
    _ref("person", pflicht=True),
    _ref("person", pflicht=True, spalte="other_person_id"),
    Column("relation", Text),
    _sort(),
)

# Quellen (3.6) -------------------------------------------------------------------------------------------------
repository = _tabelle(
    "repository",
    _xref(),
    Column("name", Text),
    Column("address", Text),         # ADDR mit CONT, wie es kam
    Column("address_name", Text),    # GEDCOM-L ADDR:_NAME
    Column("adr1", Text),
    Column("city", Text),
    Column("postal_code", Text),
    Column("country", Text),
    Column("phone", Text),
    Column("email", Text),
    Column("www", Text),
    Column("uid", Text),
    *_resn(),
)

source = _tabelle(
    "source",
    _xref(),
    Column("title", Text),
    Column("abbr", Text),
    Column("author", Text),
    Column("publication", Text),
    Column("text", Text),
    Column("agency", Text),
    Column("uid", Text),
    *_resn(),
)

# Was eine Quelle abdeckt (SOUR:DATA:EVEN)
source_coverage = _tabelle(
    "source_coverage",
    _ref("source", pflicht=True),
    _sort(),
    Column("events", Text),
    Column("place_text", Text),
    *_datum(),
)

source_repository = _tabelle(
    "source_repository",
    _ref("source", pflicht=True),
    _ref("repository", beim_loeschen="SET NULL"),
    _sort(),
    Column("call_number", Text),
    Column("medium", Text),
)

# Notizen, Medien, Aufgaben (3.7) – vor den Tabellen mit Trägerspalten, die auf sie zeigen ------------------------
note = _tabelle(
    "note",
    _xref(pflicht=False),            # NULL = eingebettete Notiz
    Column("text", Text, nullable=False),
    *_resn(),
)

media = _tabelle(
    "media",
    _xref(pflicht=False),
    Column("title", Text),
    Column("uid", Text),
    *_resn(),
)

media_file = _tabelle(
    "media_file",
    _ref("media", pflicht=True),
    _sort(),
    Column("path", Text, nullable=False),
    Column("format", Text),
    Column("media_type", Text),
    Column("title", Text),
)

task = _tabelle(
    "task",
    *_traeger("task"),
    _sort(),
    Column("text", Text),
    Column("description", Text),
    Column("category", Text),
    Column("priority", Text),
    Column("task_type", Text),
    Column("status", Text),
    Column("solution", Text),
    _ref("repository", beim_loeschen="SET NULL"),
    Column("user_name", Text),
    *_datum(),
    Column("reminder_text", Text),
    Column("completed_text", Text),
    _traeger_regel("task"),
    *_traeger_index("task"),
)

citation = _tabelle(
    "citation",
    *_traeger("citation"),
    _sort(),
    _ref("source", beim_loeschen="SET NULL"),
    Column("source_text", Text),     # Zitat ohne Quellendatensatz (2 SOUR Text)
    Column("page", Text),
    Column("quality", Integer),
    Column("event_type", Text),      # SOUR:EVEN
    Column("event_role", Text),      # SOUR:EVEN:ROLE
    Column("data_text", Text),       # SOUR:DATA:TEXT
    *_datum("data_"),
    Column("entry_id", Integer),     # Eintrag der Belegebene (E10), vorerst immer leer
    *_resn(),
    CheckConstraint("quality BETWEEN 0 AND 3"),
    _traeger_regel("citation"),
    *_traeger_index("citation"),
    Index("citation_source", "source_id"),
)

note_link = _tabelle(
    "note_link",
    _ref("note", pflicht=True),
    *_traeger("note_link"),
    _sort(),
    _traeger_regel("note_link"),
    *_traeger_index("note_link"),
)

media_link = _tabelle(
    "media_link",
    _ref("media", pflicht=True),
    *_traeger("media_link"),
    _sort(),
    *_flag("is_primary"),
    Column("title", Text),
    Column("crop_top", Integer),
    Column("crop_left", Integer),
    Column("crop_height", Integer),
    Column("crop_width", Integer),
    _traeger_regel("media_link"),
    *_traeger_index("media_link"),
)

# Was das Modell nicht kennt, bleibt als GEDCOM an seiner Struktur (E9) -----------------------------------------
gedcom_rest = _tabelle(
    "gedcom_rest",
    *_traeger("gedcom_rest"),
    _sort(),
    Column("under", Text),           # Zeile, unter der der Rest stand, wenn sie selbst in Spalten aufging (PLAC, _STAT …)
    Column("gedcom", Text, nullable=False),  # mit den Stufen aus der Datei
    _traeger_regel("gedcom_rest"),
    *_traeger_index("gedcom_rest"),
)

# Offene Änderungen (E4 a) --------------------------------------------------------------------------------------
change_set = _tabelle(
    "change_set",
    Column("author", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'pending'")),
    Column("decided_by", Text),
    Column("decided_at", Text),
    Column("comment", Text),
    CheckConstraint("status IN ('pending', 'accepted', 'rejected')"),
)

change_step = _tabelle(
    "change_step",
    _ref("change_set", pflicht=True),
    _sort(),
    Column("object_type", Text, nullable=False),
    Column("object_id", Integer),    # NULL bei Objekten, die der Satz erst anlegt
    Column("operation", Text, nullable=False),
    Column("old_json", Text),
    Column("new_json", Text),
    CheckConstraint("operation IN ('create', 'update', 'delete')"),
    _text_index("change_step_object", "object_type", "object_id", texte=("object_type",)),
)


def tabelle(name_: str) -> Table:
    return metadata.tables[name_]
