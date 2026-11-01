"""GEDCOM-5.5.1-Export (KONZEPT.md 6, E24–E26): Rundlauf ohne Verlust und fester Punkt."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from baum import datei
from baum.auszug import auszug
from gedcom.export551 import exportieren
from gedcom.import551 import importieren

DATEN = Path(__file__).with_name("daten")
HEUTE = datetime.datetime(2026, 11, 2, 12, 0, 0)


def _import(pfad: Path, gedcom: bytes):
    importieren(gedcom, pfad)
    return datei.oeffnen(pfad)


def rundlauf(tmp: Path, gedcom: bytes):
    """Import → Export → Import → Export; liefert beide Auszüge, beide Exporte und den ersten Bericht."""
    a = _import(tmp / "a.wise", gedcom)
    b = None
    try:
        g1, bericht = exportieren(a, HEUTE)
        b = _import(tmp / "b.wise", g1)
        g2, _ = exportieren(b, HEUTE)
        return auszug(a), auszug(b), g1, g2, bericht
    finally:
        a.close()
        if b is not None:
            b.close()


@pytest.fixture(scope="module")
def falkenrath(tmp_path_factory):
    return rundlauf(tmp_path_factory.mktemp("falk"), (DATEN / "falkenrath-1.7.1.ged").read_bytes())


def test_falkenrath_rundlauf_ohne_verlust(falkenrath):
    vorher, nachher, *_ = falkenrath
    assert nachher == vorher


def test_falkenrath_fester_punkt_bitgenau(falkenrath):
    *_, g1, g2, _ = falkenrath
    assert g1 == g2


def test_falkenrath_bericht_ohne_verlust(falkenrath):
    bericht = falkenrath[4]
    assert bericht.nicht_verlustfrei == [] and bericht.geteilte_ereignisse == []
    assert bericht.datensaetze == {"person": 492, "family": 154, "place": 5, "source": 204, "repository": 40,
                                   "media": 142, "note": 0}


def test_kopf(falkenrath):
    text = falkenrath[2].decode()
    kopf = text.split("\n0 ", 1)[0].split("\n")
    assert kopf[:3] == ["0 HEAD", "1 CHAR UTF-8", "1 SOUR WISE"]
    assert "2 CORP Thomas Bugge" in kopf and "2 VERS 5.5.1" in kopf
    assert "3 _ADDENDUM GEDCOM-L Addendum" in kopf
    # aus dem Kopf der eingelesenen Datei: Einsender, Rechte, Sprache, Notiz
    assert {"1 SUBM @U1@", "1 COPR CC0 1.0", "1 LANG German"} <= set(kopf)
    assert "\n0 @U1@ SUBM\n" in text and text.endswith("\n0 TRLR\n")


def test_loc_verweise_am_ort_bleiben(falkenrath):
    text = falkenrath[2].decode()
    original = (DATEN / "falkenrath-1.7.1.ged").read_text()
    assert text.count("\n3 _LOC @") == original.count("\n3 _LOC @") == 17


KLEIN = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Karl /Vater/
2 _RUFNAME Karl
1 SEX M
1 FAMS @F1@
1 _UID 1234
0 @I2@ INDI
1 NAME Erna /Mutter/
1 SEX F
1 FAMS @F1@
1 CHAN
2 DATE 1 NOV 2026
3 TIME 10:11:12
0 @I3@ INDI
1 NAME Paul /Kind/
1 BIRT
2 DATE ABT 1850
2 PLAC Hof 3, Neustadt
3 _UNBEKANNT x
2 _ASSO @I1@
3 RELA Pate
2 _GODP Hans Meier, Bauer in Hesel
2 _WITN Fritz
1 ADOP
2 FAMC @F1@
3 ADOP HUSB
1 FAMC @F1@
1 NOTE Erste Zeile
2 CONT zweite Zeile
1 NOTE @@ am Anfang
1 _MILT Infanterie
2 DATE 1870
0 @I4@ INDI
1 NAME Grete /Pflege/
1 FAMC @F1@
2 PEDI foster
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 _STAT NOT MARRIED
2 NOTE Nie geheiratet.
1 MARR
2 SOUR @S1@
3 PAGE S. 4
3 QUAY 2
3 TEXT Wortlaut
0 @S1@ SOUR
1 TITL Kirchenbuch
1 REPO @R1@
2 CALN 1
2 CALN 2
3 MEDI book
0 @R1@ REPO
1 NAME Archiv
0 @N1@ NOTE Notiz
0 @L1@ _LOC
1 NAME Neustadt
1 TYPE Stadt
2 _GOVTYPE 39
0 TRLR
"""


@pytest.fixture
def klein(tmp_path):
    return rundlauf(tmp_path, KLEIN.encode())


def test_klein_rundlauf_und_fester_punkt(klein):
    vorher, nachher, g1, g2, bericht = klein
    assert nachher == vorher
    assert g1 == g2
    assert bericht.nicht_verlustfrei == []


def test_klein_gedcom_wie_erwartet(klein):
    text = klein[2].decode()
    for teil in ("1 ADOP\n2 FAMC @F1@\n3 ADOP HUSB",      # Adoption aus der Abstammung je Elternteil
                 "1 CHIL @I3@\n2 _FREL adopted\n2 _MREL natural",
                 "1 FAMC @F1@\n2 PEDI foster",
                 "1 _STAT NOT MARRIED\n2 NOTE Nie geheiratet.",
                 "2 PLAC Hof 3, Neustadt\n3 _UNBEKANNT x",   # Rest an seiner Stelle
                 "2 _ASSO @I1@\n3 RELA Pate",
                 "2 _GODP Hans Meier, Bauer in Hesel",
                 "1 NOTE Erste Zeile\n2 CONT zweite Zeile",
                 "1 NOTE @@ am Anfang",
                 "1 CHAN\n2 DATE 1 NOV 2026\n3 TIME 10:11:12",
                 "3 DATA\n4 TEXT Wortlaut",                 # TEXT am Zitat gehört unter DATA
                 "1 REPO @R1@\n2 CALN 1\n2 CALN 2\n3 MEDI book",
                 "1 _MILT Infanterie\n2 DATE 1870"):
        assert teil in text, teil


def test_lange_werte_mit_conc(tmp_path):
    lang = "Wort " * 120 + "Ende"
    vorher, nachher, g1, g2, _ = rundlauf(tmp_path, KLEIN.replace("0 @N1@ NOTE Notiz", f"0 @N1@ NOTE {lang}").encode())
    assert nachher == vorher and g1 == g2
    zeilen = g1.decode().split("\n")
    assert max(len(z) for z in zeilen) <= 255
    conc = [z for z in zeilen if z.startswith("1 CONC")]
    assert conc and not any(z.startswith("1 CONC  ") for z in conc)


def test_doppelte_kennung_bleibt_rest(tmp_path):
    text = KLEIN.replace("0 @N1@ NOTE Notiz", "0 @N1@ NOTE Notiz\n0 @I1@ INDI\n1 NAME Zweiter /Datensatz/")
    vorher, nachher, g1, g2, _ = rundlauf(tmp_path, text.encode())
    assert nachher == vorher and g1 == g2
    assert g1.decode().count("0 @I1@ INDI") == 2


def test_geteiltes_ereignis_bei_jedem_hauptbeteiligten(tmp_path):
    """E26: Ein Ereignis mit zwei Hauptbeteiligten steht bei beiden und im Bericht."""
    con = _import(tmp_path / "g.wise", KLEIN.encode())
    try:
        with con.begin():
            eid, = con.exec_driver_sql("SELECT e.id FROM event e JOIN event_role r ON r.event_id = e.id "
                                       "JOIN person p ON p.id = r.person_id WHERE p.xref = 'I3' AND e.type = 'BIRT'"
                                       ).one()
            pid, = con.exec_driver_sql("SELECT id FROM person WHERE xref = 'I4'").one()
            con.exec_driver_sql("INSERT INTO event_role (event_id, person_id, role, sort, fact_sort) "
                                "VALUES (?, ?, 'PRINCIPAL', 0, 99)", (eid, pid))
        g, bericht = exportieren(con, HEUTE)
    finally:
        con.close()
    text = g.decode()
    i4 = text.split("0 @I4@ INDI", 1)[1].split("\n0 ", 1)[0]
    assert "1 BIRT\n2 DATE ABT 1850" in i4 and "2 _GODP Hans Meier" in i4
    assert len(bericht.geteilte_ereignisse) == 1
