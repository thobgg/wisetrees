"""Baumdateien (.wise) anlegen und öffnen (E12, E16).

wisetrees öffnet nur SQLite-Dateien mit application_id 0x57495345 („WISE“) und einer Schemaversion, die es
kennt. Die Kennung wird aus dem Dateikopf gelesen, bevor SQLite die Datei anfasst – so legt ein Tippfehler im
Namen keine leere Datenbank an, und eine fremde SQLite-Datei wird nicht verändert.

Zugriff über SQLAlchemy Core: anlegen() und oeffnen() geben eine Connection zurück. Schreiben braucht eine
Transaktion (`with con.begin():`), sonst bleibt nichts gespeichert.
"""

from __future__ import annotations

import struct
import threading
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, event, insert
from sqlalchemy.pool import NullPool

from .schema import APPLICATION_ID, SCHEMA_VERSION, meta, metadata, privacy_rule

# Schemaversionen, die oeffnen() umbaut: alte Version → Funktion(con), danach steht user_version eins höher.
UMBAU: dict = {}
_UMBAU_SPERRE = threading.Lock()  # zwei Anfragen bauen dieselbe Datei nicht gleichzeitig um

ENDUNG = ".wise"
_SQLITE_KOPF = b"SQLite format 3\x00"


class KeineBaumdatei(Exception):
    """Die Datei ist keine wisetrees-Baumdatei (fehlt, kein SQLite oder fremde application_id)."""


class FalscheVersion(Exception):
    """Die Baumdatei hat eine Schemaversion, die diese wisetrees-Fassung nicht kennt."""


def _pragmas(dbapi_con, _eintrag) -> None:
    c = dbapi_con.cursor()
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    c.close()


_ENGINES: dict[str, Engine] = {}
_ENGINES_SPERRE = threading.Lock()


def engine(pfad: Path) -> Engine:
    """Engine für eine Baumdatei, je Datei einmal angelegt (der Aufbau kostet mehr als eine Abfrage). Ohne
    Verbindungspool: Jede Verbindung gehört dem, der sie öffnet, und ist nach close() zu – wichtig, weil Dateien
    gelöscht oder ersetzt werden können."""
    schluessel = str(Path(pfad).resolve())
    with _ENGINES_SPERRE:
        e = _ENGINES.get(schluessel)
        if e is None:
            e = create_engine(f"sqlite:///{schluessel}", poolclass=NullPool, connect_args={"check_same_thread": False})
            event.listen(e, "connect", _pragmas)
            _ENGINES[schluessel] = e
        return e


def anlegen(pfad: Path, titel: str = "") -> Connection:
    """Neue, leere Baumdatei. Gibt es die Datei schon, bricht es ab."""
    pfad = Path(pfad)
    if pfad.suffix != ENDUNG:
        raise ValueError(f"Baumdateien enden auf {ENDUNG}: {pfad.name}")
    if pfad.exists():
        raise FileExistsError(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = engine(pfad).connect()
    with con.begin():
        con.exec_driver_sql(f"PRAGMA application_id = {APPLICATION_ID}")
        con.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
        metadata.create_all(con)
        con.execute(insert(meta).values(key="title", value=titel))
        from .datenschutz import vorgaben_anlegen

        vorgaben_anlegen(con)
    return con


def kopf(pfad: Path) -> tuple[int, int]:
    """(application_id, user_version) aus dem Dateikopf, ohne SQLite. Wirft KeineBaumdatei."""
    try:
        with open(pfad, "rb") as f:
            k = f.read(100)
    except OSError as e:
        raise KeineBaumdatei(f"{pfad}: {e.strerror}") from e
    if len(k) < 100 or not k.startswith(_SQLITE_KOPF):
        raise KeineBaumdatei(f"{pfad}: keine SQLite-Datei")
    user_version, = struct.unpack(">I", k[60:64])
    application_id, = struct.unpack(">I", k[68:72])
    return application_id, user_version


def oeffnen(pfad: Path) -> Connection:
    pfad = Path(pfad)
    application_id, version = kopf(pfad)
    if application_id != APPLICATION_ID:
        raise KeineBaumdatei(f"{pfad}: application_id {application_id:#010x} statt {APPLICATION_ID:#010x}")
    if version > SCHEMA_VERSION or (version < SCHEMA_VERSION and version not in UMBAU):
        raise FalscheVersion(f"{pfad}: Schemaversion {version}, diese Fassung kennt {SCHEMA_VERSION}")
    con = engine(pfad).connect()
    # Maßgeblich ist die Version, die SQLite selbst meldet: Im WAL-Modus kann der Dateikopf noch die alte zeigen.
    def _version() -> int:
        v = con.exec_driver_sql("PRAGMA user_version").scalar()
        con.rollback()
        return v

    if _version() < SCHEMA_VERSION:
        with _UMBAU_SPERRE:
            umgebaut = False
            while (version := _version()) < SCHEMA_VERSION:
                if version not in UMBAU:
                    con.close()
                    raise FalscheVersion(f"{pfad}: Schemaversion {version}, diese Fassung kennt {SCHEMA_VERSION}")
                umbau = UMBAU[version]
                neu_aufbauen = getattr(umbau, "tabellen_neu", False)
                if neu_aufbauen:
                    # Tabellen neu aufbauen: Fremdschlüssel aus, sonst löscht DROP TABLE abhängige Zeilen mit
                    con.exec_driver_sql("PRAGMA foreign_keys = OFF")
                    con.rollback()
                try:
                    with con.begin():
                        con.exec_driver_sql("BEGIN")   # ausdrücklich: auch Tabellenänderungen in einer Transaktion
                        umbau(con)
                        if neu_aufbauen and (fehler := verweise_pruefen(con)):
                            raise RuntimeError(f"{pfad}: Umbau {version} → {version + 1}: {fehler[:3]}")
                        con.exec_driver_sql(f"PRAGMA user_version = {version + 1}")
                finally:
                    if neu_aufbauen:
                        con.exec_driver_sql("PRAGMA foreign_keys = ON")
                        con.rollback()
                umgebaut = True
            if umgebaut:
                con.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")  # neue Version gleich in den Dateikopf
            con.rollback()
    return con


def _von_1(con: Connection) -> None:
    """1 → 2: Datenschutz-Regeln (E19) mit den Vorgaben eines neuen Baums."""
    from .datenschutz import vorgaben_anlegen

    privacy_rule.create(con, checkfirst=True)
    vorgaben_anlegen(con)


UMBAU[1] = _von_1


def _von_2(con: Connection) -> None:
    """2 → 3: Datensatz am Änderungssatz (E21). Die Spalte kommt ans Ende, wie bei einer neuen Datei."""
    from sqlalchemy.schema import CreateIndex

    from .schema import change_set

    con.exec_driver_sql("ALTER TABLE change_set ADD COLUMN record_xref VARCHAR(255)")
    con.execute(CreateIndex(next(i for i in change_set.indexes if i.name == "change_set_offen")))


UMBAU[2] = _von_2


def _von_3(con: Connection) -> None:
    """3 → 4: Geschlecht darf leer sein (E22). SQLite ändert NOT NULL nicht an Ort und Stelle: die Tabelle wird nach
    der Definition im Schema neu angelegt und umgefüllt. Vorhandene Werte bleiben."""
    from sqlalchemy.schema import CreateIndex, CreateTable

    from .schema import person

    ddl = str(CreateTable(person).compile(dialect=con.dialect)).strip()
    con.exec_driver_sql(ddl.replace("CREATE TABLE person ", "CREATE TABLE person_neu ", 1))
    spalten = ", ".join(c.name for c in person.columns)
    con.exec_driver_sql(f"INSERT INTO person_neu ({spalten}) SELECT {spalten} FROM person")
    con.exec_driver_sql("DROP TABLE person")
    con.exec_driver_sql("ALTER TABLE person_neu RENAME TO person")
    for i in person.indexes:
        con.execute(CreateIndex(i))


_von_3.tabellen_neu = True
UMBAU[3] = _von_3


def verweise_pruefen(con: Connection) -> list[str]:
    """Alle Fremdschlüssel prüfen (auch die Trägerspalten). Leere Liste = alles in Ordnung."""
    return [f"Fremdschlüssel: {tuple(r)}" for r in con.exec_driver_sql("PRAGMA foreign_key_check")]


class Zeile:
    """Ergebniszeile, lesbar über Stelle (z[0], z[1:]) und Spaltenname (z["xref"])."""

    __slots__ = ("_r",)

    def __init__(self, r):
        self._r = r

    def __getitem__(self, k):
        return self._r._mapping[k] if isinstance(k, str) else self._r[k]

    def __iter__(self):
        return iter(self._r)

    def __len__(self):
        return len(self._r)

    def keys(self):
        return list(self._r._mapping.keys())

    def __repr__(self):
        return f"Zeile({dict(self._r._mapping)!r})"


def zeilen(con: Connection, abfrage) -> list[Zeile]:
    return [Zeile(r) for r in con.execute(abfrage)]


def zeile(con: Connection, abfrage) -> Zeile | None:
    r = con.execute(abfrage).first()
    return Zeile(r) if r is not None else None


def wert(con: Connection, abfrage):
    """Erste Spalte der ersten Zeile, None ohne Treffer."""
    return con.execute(abfrage).scalar()
