"""Umsetzung zwischen GEDCOM 5.5.1 und 7.0 (E24, E27): Datumsangaben und Werte, in beide Richtungen."""

from __future__ import annotations

import pytest

from gedcom.struktur import E, aus_text, zeilen
from gedcom.umsetzen import Umsetzer, datei_nach7, datum_nach7, datum_nach551

DATEN = [   # 5.5.1, 7.0 (Datum, PHRASE); zurück ergibt wieder 5.5.1
    ("1 JAN 1850", ("1 JAN 1850", None)),
    ("ABT 1850", ("ABT 1850", None)),
    ("BET 1850 AND 1860", ("BET 1850 AND 1860", None)),
    ("FROM 1850 TO 1860", ("FROM 1850 TO 1860", None)),
    ("@#DJULIAN@ 1 JAN 1700", ("JULIAN 1 JAN 1700", None)),
    ("@#DFRENCH R@ 1 VEND 10", ("FRENCH_R 1 VEND 10", None)),
    ("100 B.C.", ("100 BCE", None)),
    ("INT 1850 (um Ostern)", ("1850", "um Ostern")),
    ("(Frühjahr 1850)", ("", "Frühjahr 1850")),
    ("10 FEB 1700/01", ("10 FEB 1701", "10 FEB 1700/01")),
    ("31 DEC 1699/00", ("31 DEC 1700", "31 DEC 1699/00")),
]


@pytest.mark.parametrize(("alt", "neu"), DATEN)
def test_datum_hin_und_zurueck(alt, neu):
    assert datum_nach7(alt) == neu
    assert datum_nach551(*neu) == (alt, None)


def test_unverstandenes_datum_wird_phrase():
    assert datum_nach7("Frühjahr 1850") == ("", "Frühjahr 1850")
    assert datum_nach551("", "Frühjahr 1850") == ("(Frühjahr 1850)", None)


def test_wortlaut_in_klammern_bleibt_unberuehrt():
    assert datum_nach551("(JULIAN, unsicher)", None) == ("(JULIAN, unsicher)", None)


def test_kleinschreibung_wird_gross():
    assert datum_nach7("abt 1850") == ("ABT 1850", None)


def test_datei_als_url():
    assert datei_nach7("bilder/Taufe Müller 100%.jpg") == "bilder/Taufe%20M%C3%BCller%20100%25.jpg"
    assert datei_nach7("https://example.org/a b.jpg") == "https://example.org/a b.jpg"


def _umgesetzt(text: str, fassung: str) -> tuple[str, Umsetzer]:
    saetze = aus_text(text)
    u = Umsetzer(fassung)
    u.saetze(saetze)
    return "\n".join(z for s in saetze for z in zeilen(s, 0, v551=not fassung.startswith("7"))), u


def test_werte_nach_7_und_zurueck():
    alt = ("0 @M1@ OBJE\n1 FILE a.jpg\n2 FORM jpg\n3 TYPE photo\n"
           "0 @S1@ SOUR\n1 REPO @R1@\n2 CALN 7\n3 MEDI microfilm\n"
           "0 HEAD\n1 LANG German")
    neu, u = _umgesetzt(alt, "7.0")
    assert neu == ("0 @M1@ OBJE\n1 FILE a.jpg\n2 FORM image/jpeg\n3 MEDI PHOTO\n"
                   "0 @S1@ SOUR\n1 REPO @R1@\n2 CALN 7\n3 MEDI OTHER\n4 PHRASE microfilm\n"
                   "0 HEAD\n1 LANG de")
    zurueck, _ = _umgesetzt(neu, "5.5.1")
    assert zurueck == alt
    assert u.ungueltig == {}


def test_was_ungueltig_bleibt_steht_im_zaehler():
    _, u = _umgesetzt("0 @M1@ OBJE\n1 FILE a.xyz\n2 FORM xyz\n0 HEAD\n1 LANG Plattdeutsch", "7.0")
    assert u.ungueltig == {"FORM xyz": 1, "LANG Plattdeutsch": 1}


def test_eigene_tags_bleiben():
    neu, u = _umgesetzt("0 @I1@ INDI\n1 _RUFNAME Karl\n1 _TODO Kirchenbuch prüfen", "7.0")
    assert neu == "0 @I1@ INDI\n1 _RUFNAME Karl\n1 _TODO Kirchenbuch prüfen" and u.umgesetzt == {}


def test_struktur_aus_text_und_zurueck():
    text = "0 @N1@ NOTE Zeile 1\n1 CONT Zeile 2\n1 _X y\n2 _Z\nZeile ohne Stufe"
    saetze = aus_text(text)
    assert [s.tag for s in saetze] == ["NOTE"] and saetze[0].wert == "Zeile 1\nZeile 2"
    assert "\n".join(zeilen(saetze[0], 0, v551=True)) == text
    assert isinstance(saetze[0].kinder[-1], E) and saetze[0].kinder[-1].roh == "Zeile ohne Stufe"
