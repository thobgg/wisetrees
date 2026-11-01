"""GEDCOM-7.0-Import (KONZEPT.md 6, E23). Prüfstein: Falkenrath 1.7.1 in der 7.0-Fassung (CC0)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from baum import datei
from gedcom.import551 import importieren

DATEN = Path(__file__).with_name("daten")


def alle(con, sql, *args):
    return [tuple(r) for r in con.exec_driver_sql(sql, args)]


@pytest.fixture(scope="module")
def falkenrath7(tmp_path_factory):
    ziel = tmp_path_factory.mktemp("f7") / "f7.wise"
    b = importieren((DATEN / "falkenrath-1.7.1-gedcom7.ged").read_bytes(), ziel)
    con = datei.oeffnen(ziel)
    yield con, b
    con.close()


def test_jede_zeile_uebernommen_oder_rest(falkenrath7):
    _, b = falkenrath7
    assert b.gedcom_version == "7.0"
    assert b.zeilen_uebernommen + b.zeilen_rest == b.zeilen_gesamt
    assert b.verweis_fehlt == [] and b.lesefehler == []


def test_rest_ist_genau_das_erwartete(falkenrath7):
    """Rest: der Einsender und die Wortlaute (PHRASE) an MEDI und an der Rolle im Zitat – dafür hat das Modell
    noch keine Spalte."""
    _, b = falkenrath7
    stellen = Counter()
    for pfad, n in b.rest_pfade.items():
        stellen[re.sub(r"FILE [^:]+", "FILE …", pfad)] += n
    assert stellen == {"citation:EVEN:ROLE:PHRASE": 3, "media:FILE …:FORM:MEDI:PHRASE": 11, "tree:SUBM": 1}


def test_anzahl_wie_in_5_5_1(falkenrath7, tmp_path):
    """Gleiche Zahlen wie aus der 5.5.1-Fassung, bis auf das, was die 7.0-Fassung anders ausdrückt: eine Textquelle
    als eigener Datensatz, zwei Ereignistexte als Notiz (7.0 erlaubt hinter EMIG/IMMI nur Y), die Wortlaute als Rest."""
    _, b = falkenrath7
    b551 = importieren((DATEN / "falkenrath-1.7.1.ged").read_bytes(), tmp_path / "f.wise")
    anders = {k: (b551.anzahl[k], n) for k, n in b.anzahl.items() if b551.anzahl[k] != n}
    assert anders == {"source": (204, 205), "note": (110, 112), "gedcom_rest": (1, 15)}


def test_paten_ohne_datensatz_aus_void(falkenrath7):
    con, _ = falkenrath7
    r = alle(con, "SELECT role, free_name, free_addition FROM event_role WHERE free_text = ?",
             "Martin Hoppe, Bauingenieur, Hannover")
    assert r == [("GODP", "Martin Hoppe", "Bauingenieur, Hannover")]


def test_gov_kennung_aus_exid(falkenrath7):
    con, _ = falkenrath7
    assert alle(con, "SELECT COUNT(*) FROM event_place_detail WHERE kind = 'gov'") == [(94,)]
    assert alle(con, "SELECT COUNT(*) FROM gedcom_rest WHERE gedcom LIKE '%EXID%'") == [(0,)]


KLEIN7 = """0 HEAD
1 GEDC
2 VERS 7.0
0 @I1@ INDI
1 NAME Anna /Weber/
1 SEX F
1 NO MARR
2 DATE FROM 1900 TO 1920
1 BAPM
2 DATE JULIAN 1 JAN 1700
2 ASSO @I2@
3 ROLE OTHER
4 PHRASE Taufzeugin
2 ASSO @VOID@
3 PHRASE Unbekannter Pate
3 ROLE GODP
1 SNOTE @N1@
1 ASSO @I2@
2 ROLE FRIEND
0 @I2@ INDI
1 NAME Berta /Weber/
0 @N1@ SNOTE Geteilte Notiz
0 TRLR
"""


def test_klein7(tmp_path):
    b = importieren(KLEIN7.encode(), tmp_path / "k7.wise")
    con = datei.oeffnen(tmp_path / "k7.wise")
    try:
        assert b.zeilen_rest == 0 and b.verweis_fehlt == []
        assert alle(con, "SELECT type, negated, date_text FROM event WHERE negated = 1") == [
            ("MARR", 1, "FROM 1900 TO 1920")]
        assert alle(con, "SELECT date_calendar FROM event WHERE type = 'BAPM'") == [("julian",)]
        assert alle(con, "SELECT role, rela, free_name FROM event_role WHERE role <> 'PRINCIPAL' ORDER BY sort") == [
            ("OTHER", "Taufzeugin", None), ("GODP", None, "Unbekannter Pate")]
        assert alle(con, "SELECT n.xref, n.text FROM note n JOIN note_link l ON l.note_id = n.id") == [
            ("N1", "Geteilte Notiz")]
        assert alle(con, "SELECT relation FROM person_association") == [("FRIEND",)]
    finally:
        con.close()
