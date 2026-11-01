"""Baumdateien (.wise) anlegen und öffnen (E12).

wisetrees öffnet nur SQLite-Dateien mit application_id 0x57495345 („WISE“) und einer Schemaversion, die es
kennt. Die Kennung wird aus dem Dateikopf gelesen, bevor SQLite die Datei anfasst – so legt ein Tippfehler im
Namen keine leere Datenbank an, und eine fremde SQLite-Datei wird nicht verändert.
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

from .schema import APPLICATION_ID, DDL, SCHEMA_VERSION

ENDUNG = ".wise"
_SQLITE_KOPF = b"SQLite format 3\x00"


class KeineBaumdatei(Exception):
    """Die Datei ist keine wisetrees-Baumdatei (fehlt, kein SQLite oder fremde application_id)."""


class FalscheVersion(Exception):
    """Die Baumdatei hat eine Schemaversion, die diese wisetrees-Fassung nicht kennt."""


def _verbinden(pfad: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(pfad), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def anlegen(pfad: Path, titel: str = "") -> sqlite3.Connection:
    """Neue, leere Baumdatei. Gibt es die Datei schon, bricht es ab."""
    pfad = Path(pfad)
    if pfad.suffix != ENDUNG:
        raise ValueError(f"Baumdateien enden auf {ENDUNG}: {pfad.name}")
    if pfad.exists():
        raise FileExistsError(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = _verbinden(pfad)
    with con:
        con.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.executescript(DDL)
        con.execute("INSERT INTO meta(key, value) VALUES ('title', ?)", (titel,))
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


def oeffnen(pfad: Path) -> sqlite3.Connection:
    pfad = Path(pfad)
    application_id, version = kopf(pfad)
    if application_id != APPLICATION_ID:
        raise KeineBaumdatei(f"{pfad}: application_id {application_id:#010x} statt {APPLICATION_ID:#010x}")
    if version != SCHEMA_VERSION:
        raise FalscheVersion(f"{pfad}: Schemaversion {version}, diese Fassung kennt {SCHEMA_VERSION}")
    return _verbinden(pfad)


def verweise_pruefen(con: sqlite3.Connection) -> list[str]:
    """Alle Fremdschlüssel prüfen (auch die Trägerspalten). Leere Liste = alles in Ordnung."""
    return [f"Fremdschlüssel: {tuple(r)}" for r in con.execute("PRAGMA foreign_key_check")]
