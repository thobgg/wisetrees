"""Baumdatei .wise: Kennung, Version, Schema (E12)."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from baum import datei
from baum.schema import APPLICATION_ID, SCHEMA_VERSION


def test_neue_datei_traegt_kennung_und_version(tmp_path):
    p = tmp_path / "falkenrath.wise"
    datei.anlegen(p, "Falkenrath").close()
    assert datei.kopf(p) == (0x57495345, SCHEMA_VERSION)
    assert APPLICATION_ID.to_bytes(4, "big") == b"WISE"
    con = datei.oeffnen(p)
    assert con.exec_driver_sql("PRAGMA application_id").fetchone()[0] == 0x57495345
    assert con.exec_driver_sql("SELECT value FROM meta WHERE key = 'title'").fetchone()[0] == "Falkenrath"
    assert datei.verweise_pruefen(con) == []
    con.close()


def test_nur_endung_wise(tmp_path):
    with pytest.raises(ValueError):
        datei.anlegen(tmp_path / "baum.sqlite")


def test_vorhandene_datei_wird_nicht_ueberschrieben(tmp_path):
    p = tmp_path / "a.wise"
    datei.anlegen(p).close()
    with pytest.raises(FileExistsError):
        datei.anlegen(p)


def test_fehlende_datei_wird_nicht_angelegt(tmp_path):
    p = tmp_path / "fehlt.wise"
    with pytest.raises(datei.KeineBaumdatei):
        datei.oeffnen(p)
    assert not p.exists()


def test_fremde_sqlite_datei_abgelehnt_und_unveraendert(tmp_path):
    p = tmp_path / "fremd.wise"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE x(a)")
    con.commit()
    con.close()
    vorher = p.read_bytes()
    with pytest.raises(datei.KeineBaumdatei, match="application_id"):
        datei.oeffnen(p)
    assert p.read_bytes() == vorher


def test_keine_sqlite_datei(tmp_path):
    p = tmp_path / "text.wise"
    p.write_text("0 HEAD\n" * 30)
    with pytest.raises(datei.KeineBaumdatei, match="keine SQLite"):
        datei.oeffnen(p)


def test_unbekannte_version_abgelehnt(tmp_path):
    p = tmp_path / "neu.wise"
    con = datei.anlegen(p)
    con.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    con.close()
    with pytest.raises(datei.FalscheVersion):
        datei.oeffnen(p)


def test_beteiligter_braucht_genau_einen_traeger(tmp_path):
    con = datei.anlegen(tmp_path / "b.wise")
    con.exec_driver_sql("INSERT INTO event(type) VALUES ('CHR')")
    with pytest.raises(IntegrityError):
        con.exec_driver_sql("INSERT INTO event_role(event_id, role, sort) VALUES (1, 'GODP', 1)")
    con.exec_driver_sql("INSERT INTO event_role(event_id, free_name, role, sort) VALUES (1, 'Martin Hoppe', 'GODP', 1)")
    con.close()


def test_traeger_genau_einer_und_fremdschluessel(tmp_path):
    con = datei.anlegen(tmp_path / "v.wise")
    con.exec_driver_sql("INSERT INTO person(xref) VALUES ('I1')")
    con.exec_driver_sql("INSERT INTO family(xref) VALUES ('F1')")
    con.exec_driver_sql("INSERT INTO note(text) VALUES ('x')")
    with pytest.raises(IntegrityError):  # kein Träger
        con.exec_driver_sql("INSERT INTO note_link(note_id, sort) VALUES (1, 1)")
    with pytest.raises(IntegrityError):  # zwei Träger
        con.exec_driver_sql("INSERT INTO note_link(note_id, person_id, family_id, sort) VALUES (1, 1, 1, 1)")
    with pytest.raises(IntegrityError):  # Träger fehlt
        con.exec_driver_sql("INSERT INTO note_link(note_id, person_id, sort) VALUES (1, 99, 1)")
    con.exec_driver_sql("INSERT INTO note_link(note_id, person_id, sort) VALUES (1, 1, 1)")
    con.exec_driver_sql("INSERT INTO gedcom_rest(on_tree, sort, gedcom) VALUES (1, 1, '0 @U1@ SUBM')")
    assert datei.verweise_pruefen(con) == []
    con.close()


def test_loeschen_nimmt_angehaengtes_mit(tmp_path):
    con = datei.anlegen(tmp_path / "l.wise")
    con.exec_driver_sql("INSERT INTO person(xref) VALUES ('I1')")
    con.exec_driver_sql("INSERT INTO note(text) VALUES ('x')")
    con.exec_driver_sql("INSERT INTO note_link(note_id, person_id, sort) VALUES (1, 1, 1)")
    con.exec_driver_sql("INSERT INTO gedcom_rest(person_id, sort, gedcom) VALUES (1, 1, '1 _X y')")
    con.exec_driver_sql("DELETE FROM person WHERE id = 1")
    assert con.exec_driver_sql("SELECT (SELECT COUNT(*) FROM note_link) + (SELECT COUNT(*) FROM gedcom_rest)").fetchone()[0] == 0
    con.close()


def test_rollencodes(tmp_path):
    con = datei.anlegen(tmp_path / "r.wise")
    con.exec_driver_sql("INSERT INTO event(type) VALUES ('CHR')")
    for rolle in ("PRINCIPAL", "GODP", "WITN", "OTHER", "X_INFORMANT"):
        con.exec_driver_sql("INSERT INTO event_role(event_id, free_name, role, sort) VALUES (1, 'a', ?, 1)", (rolle,))
    for rolle in ("FAMILY", "X_", "x_informant", "Pate"):
        with pytest.raises(IntegrityError):
            con.exec_driver_sql("INSERT INTO event_role(event_id, free_name, role, sort) VALUES (1, 'a', ?, 1)", (rolle,))
    con.close()


def test_umbau_3_auf_4_geschlecht_darf_leer_sein(tmp_path):
    """Schemaversion 3 → 4 (E22): person wird neu aufgebaut; Werte, Namen und Verweise bleiben."""
    from sqlalchemy import func, insert, select

    from baum.schema import tabelle as T

    pfad = tmp_path / "alt.wise"
    con = datei.anlegen(pfad)
    with con.begin():
        con.execute(insert(T("person")).values(xref="I1", sex="F"))
        con.execute(insert(T("name")).values(person_id=1, sort=1, value="Anna /Alt/"))
    # Stand 3 nachbilden: Geschlecht als Pflichtangabe mit Vorgabe U
    con.exec_driver_sql("PRAGMA foreign_keys = OFF")
    con.rollback()
    with con.begin():
        con.exec_driver_sql("BEGIN")
        ddl = con.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name = 'person'").scalar()
        con.exec_driver_sql(ddl.replace("CREATE TABLE person", "CREATE TABLE person_alt", 1)
                            .replace("sex TEXT,", "sex TEXT DEFAULT 'U' NOT NULL,"))
        con.exec_driver_sql("INSERT INTO person_alt SELECT * FROM person")
        con.exec_driver_sql("DROP TABLE person")
        con.exec_driver_sql("ALTER TABLE person_alt RENAME TO person")
        con.exec_driver_sql("PRAGMA user_version = 3")
    con.close()

    con = datei.oeffnen(pfad)
    try:
        assert con.exec_driver_sql("PRAGMA user_version").scalar() == SCHEMA_VERSION
        pe, na = T("person"), T("name")
        assert con.execute(select(pe.c.xref, pe.c.sex)).all() == [("I1", "F")]
        assert con.execute(select(func.count()).select_from(na)).scalar() == 1     # nichts mitgelöscht
        con.rollback()
        with con.begin():
            con.execute(insert(pe).values(xref="I2"))
        assert con.execute(select(pe.c.sex).where(pe.c.xref == "I2")).scalar() is None
        assert datei.verweise_pruefen(con) == []
        assert con.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        indizes = {r[0] for r in con.exec_driver_sql("SELECT name FROM sqlite_master WHERE tbl_name = 'person' "
                                                     "AND type = 'index' AND name NOT LIKE 'sqlite_%'")}
        assert indizes == {i.name for i in pe.indexes}
    finally:
        con.close()
