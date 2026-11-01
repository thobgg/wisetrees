"""Schema über SQLAlchemy Core (E16 Teil 1): gleich wie in 0.1, portabel, gleich streng."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import insert, select
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from baum import datei
from baum.schema import APPLICATION_ID, SCHEMA_VERSION, XREF_LAENGE, metadata
from baum.schema import tabelle as T

ALT = Path(__file__).parent / "daten" / "schema-0.1.sql"


def _bild(con: sqlite3.Connection) -> dict:
    """Was ein Schema ausmacht, ohne die Schreibweise der Typen: Spalten (Name, Pflicht, Vorgabe, Schlüssel,
    Typ-Affinität), Fremdschlüssel, Indizes mit Spalten und Eindeutigkeit."""
    def affinitaet(typ: str) -> str:
        t = typ.upper()
        return "INTEGER" if "INT" in t else "TEXT" if any(x in t for x in ("CHAR", "TEXT", "CLOB")) else \
            "REAL" if any(x in t for x in ("REAL", "FLOA", "DOUB")) else t

    bild = {}
    for (tab,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"):
        # Pflicht-Vermerk am Primärschlüssel zählt nicht: Neue Dateien tragen dort NOT NULL (Standard-SQL), 0.1-Dateien
        # nicht. Für INTEGER PRIMARY KEY ändert das in SQLite nichts; für meta.key prüft der Test unten eigens.
        spalten = [(r[1], "pk" if r[5] else r[3], r[4], r[5], affinitaet(r[2]))
                   for r in con.execute(f"PRAGMA table_info({tab})")]
        fks = sorted(tuple(r[2:5]) + (r[6],) for r in con.execute(f"PRAGMA foreign_key_list({tab})"))
        indizes = set()
        for r in con.execute(f"PRAGMA index_list({tab})"):
            cols = tuple(c[2] for c in con.execute(f"PRAGMA index_info('{r[1]}')"))
            name = r[1] if not r[1].startswith("sqlite_autoindex") else "(auto)"
            indizes.add((name, cols, r[2]))
        bild[tab] = (spalten, fks, sorted(indizes))
    return bild


def test_gleiches_schema_wie_in_0_1(tmp_path):
    alt = sqlite3.connect(tmp_path / "alt.sqlite")
    alt.executescript(ALT.read_text(encoding="utf-8"))
    neu_pfad = tmp_path / "neu.wise"
    datei.anlegen(neu_pfad).close()
    neu = sqlite3.connect(neu_pfad)
    a, n = _bild(alt), _bild(neu)
    assert sorted(a) == sorted(n)
    for tab in a:
        assert a[tab] == n[tab], tab
    # Gewollte Verschärfung: meta.key ist NOT NULL (SQLite erlaubte dort NULL, PostgreSQL und MariaDB nicht).
    assert [r[3] for r in neu.execute("PRAGMA table_info(meta)")][0] == 1


def _alte_datei(pfad: Path) -> None:
    """Eine Baumdatei, wie wisetrees 0.1 sie angelegt hat."""
    con = sqlite3.connect(pfad)
    con.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.executescript(ALT.read_text(encoding="utf-8"))
    con.execute("INSERT INTO meta(key, value) VALUES ('title', 'Alt')")
    con.execute("INSERT INTO person(xref, sex) VALUES ('I1', 'F')")
    con.execute("INSERT INTO name(person_id, sort, value, given, surname) VALUES (1, 1, 'Anna /Alt/', 'Anna', 'Alt')")
    con.commit()
    con.close()


def test_datei_aus_0_1_lesen_und_schreiben(tmp_path):
    from v1.sicht import Modell

    pfad = tmp_path / "alt.wise"
    _alte_datei(pfad)
    con = datei.oeffnen(pfad)
    m = Modell(con)
    assert m.personen[1].xref == "I1" and m.personen[1].namen[0]["given"] == "Anna"
    con.rollback()  # Lesetransaktion beenden
    with con.begin():
        con.execute(insert(T("person")).values(xref="I2"))
        con.execute(insert(T("event")).values(type="CHR"))
        con.execute(insert(T("event_role")).values(event_id=1, person_id=2, role="X_INFORMANT", sort=0))
    with pytest.raises(IntegrityError), con.begin():  # die alten Prüfregeln gelten weiter
        con.execute(insert(T("event_role")).values(event_id=1, person_id=2, role="x_informant", sort=1))
    assert con.execute(select(T("person").c.xref).order_by(T("person").c.id)).scalars().all() == ["I1", "I2"]
    assert datei.verweise_pruefen(con) == []
    con.close()


@pytest.mark.parametrize("dialekt", [postgresql.dialect(), mysql.dialect(is_mariadb=True)], ids=["postgresql", "mariadb"])
def test_schema_fuer_andere_datenbanken(dialekt):
    """Das Schema lässt sich für PostgreSQL und MariaDB erzeugen: ohne Indizes mit Bedingung, Kennungen mit fester
    Länge, Textspalten mit Index in MariaDB als Präfix-Index."""
    for t in metadata.sorted_tables:
        ddl = str(CreateTable(t).compile(dialect=dialekt))
        assert "GLOB" not in ddl.upper()
        if "xref" in t.c:
            assert f"xref VARCHAR({XREF_LAENGE})" in ddl
        for i in t.indexes:
            idx = str(CreateIndex(i).compile(dialect=dialekt))
            assert " WHERE " not in idx.upper(), idx
    assert "FLOAT" not in str(CreateTable(T("place")).compile(dialect=dialekt)).upper()  # Koordinaten doppelt genau
    namen = str(CreateIndex(next(i for i in T("name").indexes if i.name == "name_surname")).compile(dialect=dialekt))
    if dialekt.name in ("mysql", "mariadb"):
        assert "surname(191)" in namen and "given(191)" in namen


@pytest.fixture
def leer(tmp_path):
    con = datei.anlegen(tmp_path / "e.wise")
    yield con
    con.close()


def _ins(con, tab, **werte):
    with con.begin():
        return con.execute(insert(T(tab)).values(**werte)).inserted_primary_key[0]


def test_kennungen_eindeutig(leer):
    for tab in ("person", "family", "source", "repository"):
        _ins(leer, tab, xref="X1")
        with pytest.raises(IntegrityError):
            _ins(leer, tab, xref="X1")
    for tab in ("note", "media", "place"):  # Kennung freiwillig: mehrere ohne, keine doppelte
        werte = {"text": "t"} if tab == "note" else {}
        _ins(leer, tab, **werte)
        _ins(leer, tab, **werte)
        _ins(leer, tab, xref="X1", **werte)
        with pytest.raises(IntegrityError):
            _ins(leer, tab, xref="X1", **werte)
    with pytest.raises(IntegrityError):
        _ins(leer, "meta", key="title", value="doppelt")


def test_zusammengesetzte_eindeutigkeit(leer):
    p = _ins(leer, "person", xref="I1")
    k = _ins(leer, "person", xref="I2")
    f = _ins(leer, "family", xref="F1")
    _ins(leer, "family_member", family_id=f, person_id=p, role="partner", sort=1, person_sort=1)
    with pytest.raises(IntegrityError):
        _ins(leer, "family_member", family_id=f, person_id=p, role="partner", sort=2, person_sort=2)
    with pytest.raises(IntegrityError):
        _ins(leer, "family_member", family_id=f, person_id=p, role="elternteil", sort=2, person_sort=2)
    _ins(leer, "parentage", family_id=f, child_id=k, parent_id=p)
    with pytest.raises(IntegrityError):
        _ins(leer, "parentage", family_id=f, child_id=k, parent_id=p, kind="adopted")


def test_ortsvermerk_nur_postleitzahl_mit_angabe(leer):
    o = _ins(leer, "place")
    a = _ins(leer, "place_attribute", place_id=o, kind="postal", value="29553", sort=1)
    e = _ins(leer, "event", type="BIRT")
    _ins(leer, "event_place_detail", event_id=e, sort=1, kind="postal", place_attribute_id=a)
    _ins(leer, "event_place_detail", event_id=e, sort=2, kind="map")
    with pytest.raises(IntegrityError):
        _ins(leer, "event_place_detail", event_id=e, sort=3, kind="postal")
    with pytest.raises(IntegrityError):
        _ins(leer, "event_place_detail", event_id=e, sort=4, kind="gov", place_attribute_id=a)


def test_import_lehnt_zu_lange_kennung_ab(tmp_path):
    from gedcom.import551 import importieren

    lang = "I" + "1" * XREF_LAENGE
    ged = (f"0 HEAD\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n0 @{lang}@ INDI\n1 NAME Lang /Kennung/\n"
           "0 @I2@ INDI\n1 NAME Kurz /Kennung/\n0 TRLR\n")
    b = importieren(ged.encode(), tmp_path / "k.wise")
    assert any(f"länger als {XREF_LAENGE}" in v for v in b.verweis_fehlt)
    assert b.zeilen_uebernommen + b.zeilen_rest == b.zeilen_gesamt
    con = datei.oeffnen(tmp_path / "k.wise")
    assert con.execute(select(T("person").c.xref)).scalars().all() == ["I2"]
    con.close()


def test_schema_doku_passt_zum_code():
    """docs/SCHEMA.md ist aus dem Schema erzeugt und auf dem Stand (python werkzeuge/schema_doku.py)."""
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, str(repo / "werkzeuge" / "schema_doku.py"), "--pruefen"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
