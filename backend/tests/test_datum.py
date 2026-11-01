"""GEDCOM-Datumsangaben. Julianische Tage für einfache Daten geprüft gegen die v1-Aufzeichnungen
(vertrag/aufzeichnungen: 26 APR 1897 → 2414041, 1 MAY 1897 → 2414046, 14 JAN 1969 → 2440236)."""

from __future__ import annotations

import pytest

from gedcom.datum import jd_gregorianisch, lesen


@pytest.mark.parametrize("text,jd", [("26 APR 1897", 2414041), ("1 MAY 1897", 2414046), ("14 JAN 1969", 2440236)])
def test_wie_aufgezeichnet(text, jd):
    d = lesen(text)
    assert (d.von, d.bis, d.kind, d.quality, d.gueltig) == (jd, jd, "exact", "exact", True)


def test_monat_und_jahr_sind_bereiche():
    assert (lesen("APR 1897").von, lesen("APR 1897").bis) == (jd_gregorianisch(1897, 4, 1), jd_gregorianisch(1897, 4, 30))
    assert lesen("1897").bis - lesen("1897").von == 364
    assert lesen("FEB 1900").bis == jd_gregorianisch(1900, 2, 28)  # kein Schaltjahr
    assert lesen("FEB 2000").bis == jd_gregorianisch(2000, 2, 29)


def test_qualitaet():
    for vorsatz, q in (("ABT", "about"), ("CAL", "calculated"), ("EST", "estimated")):
        d = lesen(f"{vorsatz} 1770")
        assert (d.quality, d.kind, d.von, d.bis) == (q, "exact", lesen("1770").von, lesen("1770").bis)


def test_vor_nach_zwischen_zeitraum():
    j1884_ende = jd_gregorianisch(1884, 12, 31)
    assert (lesen("BEF 1885").von, lesen("BEF 1885").bis, lesen("BEF 1885").kind) == (None, j1884_ende, "before")
    assert (lesen("AFT 1884").von, lesen("AFT 1884").bis) == (j1884_ende + 1, None)
    d = lesen("BET 1800 AND 1810")
    assert (d.kind, d.von, d.bis) == ("between", jd_gregorianisch(1800, 1, 1), jd_gregorianisch(1810, 12, 31))
    d = lesen("FROM 1861 TO 1919")
    assert (d.kind, d.von, d.bis) == ("from_to", jd_gregorianisch(1861, 1, 1), jd_gregorianisch(1919, 12, 31))
    d = lesen("FROM 1 JUL 1993")
    assert (d.kind, d.von, d.bis) == ("from", jd_gregorianisch(1993, 7, 1), None)
    d = lesen("TO 1919")
    assert (d.kind, d.von, d.bis) == ("to", None, jd_gregorianisch(1919, 12, 31))


def test_julianischer_kalender_551_und_7():
    for text in ("@#DJULIAN@ 1 JAN 1700", "JULIAN 1 JAN 1700"):
        d = lesen(text)
        assert (d.calendar, d.von) == ("julian", jd_gregorianisch(1700, 1, 11))  # bis 29.02.1700 jul. 10 Tage Abstand
    assert lesen("@#DJULIAN@ FEB 1700").bis == jd_gregorianisch(1700, 3, 11)  # julianisch 29.02.1700


def test_doppeldatierung_und_vor_christus():
    assert lesen("1 FEB 1700/01").von == jd_gregorianisch(1701, 2, 1)
    assert lesen("44 B.C.").von == jd_gregorianisch(-43, 1, 1)


def test_wortlaut_und_ausgelegtes_datum():
    d = lesen("(unleserlich)")
    assert (d.kind, d.von, d.gueltig, d.text) == ("phrase", None, True, "(unleserlich)")
    d = lesen("INT 1900 (Jahrhundertwende)")
    assert (d.von, d.text) == (jd_gregorianisch(1900, 1, 1), "INT 1900 (Jahrhundertwende)")


def test_nicht_verstanden_bleibt_text():
    for text in ("Frühjahr 1850", "31 FEB 1900", "13 1900", "ABT irgendwann"):
        d = lesen(text)
        assert (d.kind, d.von, d.bis, d.gueltig, d.text) == ("phrase", None, None, False, text)


def test_andere_kalender_erkannt_aber_nicht_umgerechnet():
    d = lesen("@#DHEBREW@ 1 TSH 5600")
    assert (d.calendar, d.von, d.gueltig) == ("hebrew", None, True)
    assert lesen("@#DFRENCH R@ 1 VEND 2").calendar == "french_r"


def test_leer():
    assert lesen("") is None and lesen(None) is None and lesen("  ") is None


def test_kleinschreibung_und_leerraum():
    assert lesen("abt  1770").quality == "about"
