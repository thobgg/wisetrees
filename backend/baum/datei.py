"""Baumdateien (.wise) anlegen und öffnen (E12, E16).

wisetrees öffnet nur SQLite-Dateien mit application_id 0x57495345 („WISE“) und einer Schemaversion, die es
kennt. Die Kennung wird aus dem Dateikopf gelesen, bevor SQLite die Datei anfasst – so legt ein Tippfehler im
Namen keine leere Datenbank an, und eine fremde SQLite-Datei wird nicht verändert.

Zugriff über SQLAlchemy Core: anlegen() und oeffnen() geben eine Connection zurück. Schreiben braucht eine
Transaktion (`with con.begin():`), sonst bleibt nichts gespeichert.
"""

from __future__ import annotations

import struct
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, event, insert
from sqlalchemy.pool import NullPool

from .schema import APPLICATION_ID, SCHEMA_VERSION, meta, metadata

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


def engine(pfad: Path) -> Engine:
    """Engine für eine Baumdatei. Ohne Verbindungspool: Jede Verbindung gehört dem, der sie öffnet, und ist nach
    close() zu – wichtig, weil Dateien gelöscht oder ersetzt werden können."""
    e = create_engine(f"sqlite:///{Path(pfad)}", poolclass=NullPool, connect_args={"check_same_thread": False})
    event.listen(e, "connect", _pragmas)
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
    if version != SCHEMA_VERSION:
        raise FalscheVersion(f"{pfad}: Schemaversion {version}, diese Fassung kennt {SCHEMA_VERSION}")
    return engine(pfad).connect()


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
