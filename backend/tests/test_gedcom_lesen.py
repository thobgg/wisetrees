"""GEDCOM lesen: Zeichensätze, Zeilenenden, CONC/CONT, Zeiger, Rückschreiben."""

from __future__ import annotations

import pytest

from gedcom.lesen import NichtLesbar, lesen

KOPF = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n1 CHAR {char}\n"
PERSON = "0 @I1@ INDI\n1 NAME Jürgen /Möller/\n1 NOTE Erste Zeile\n2 CONT zweite Zeile\n2 CONC  fortgesetzt\n0 TRLR\n"


def _datei(char="UTF-8", person=PERSON):
    return KOPF.format(char=char) + person


def test_utf8_mit_und_ohne_bom():
    for daten in (_datei().encode(), b"\xef\xbb\xbf" + _datei().encode()):
        d = lesen(daten)
        assert d.version == "5.5.1" and d.zeichensatz == "utf-8"
        assert d.datensaetze[0].wert_von("NAME") == "Jürgen /Möller/"


def test_utf16_mit_bom_und_ohne():
    assert lesen(_datei("UNICODE").encode("utf-16")).datensaetze[0].wert_von("NAME") == "Jürgen /Möller/"
    assert lesen(_datei("UNICODE").encode("utf-16-le")).datensaetze[0].wert_von("NAME") == "Jürgen /Möller/"


def test_ansi_ist_windows_1252():
    d = lesen(_datei("ANSI").encode("cp1252"))
    assert (d.zeichensatz, d.datensaetze[0].wert_von("NAME")) == ("cp1252", "Jürgen /Möller/")


def test_ansel_wird_klar_abgelehnt():
    with pytest.raises(NichtLesbar, match="ANSEL"):
        lesen(_datei("ANSEL").encode("ascii", "replace"))


def test_falscher_zeichensatz_meldet_sich():
    with pytest.raises(NichtLesbar, match="Zeichensatz"):
        lesen(_datei("UTF-8").encode("cp1252"))


def test_zeilenenden_crlf_und_cr():
    for ende in ("\r\n", "\r"):
        d = lesen(_datei().replace("\n", ende).encode())
        assert d.datensaetze[0].wert_von("NAME") == "Jürgen /Möller/"


def test_conc_und_cont_werden_zusammengefuegt_und_gezaehlt():
    d = lesen(_datei().encode())
    notiz = d.datensaetze[0].erstes("NOTE")
    assert notiz.wert == "Erste Zeile\nzweite Zeile fortgesetzt"
    assert notiz.zeilen == 3
    assert d.zeilen == sum(k.zeilen_gesamt() for k in d.datensaetze) + d.kopf.zeilen_gesamt()


def test_zeiger_und_kennung():
    d = lesen(_datei(person="0 @F1@ FAM\n1 HUSB @I1@\n1 NOTE @@ ist kein Zeiger\n0 TRLR\n").encode())
    f = d.datensaetze[0]
    assert (f.xref, f.erstes("HUSB").zeiger, f.erstes("NOTE").zeiger) == ("F1", "I1", None)
    assert f.erstes("NOTE").wert == "@ ist kein Zeiger"


def test_unlesbare_zeile_bleibt_erhalten():
    d = lesen(_datei(person="0 @I1@ INDI\n1 NAME A /B/\nkaputt ohne Stufe\n0 TRLR\n").encode())
    assert d.fehler == ["Zeile 7: 'kaputt ohne Stufe'"]
    assert d.datensaetze[0].kinder[-1].gedcom() == "kaputt ohne Stufe"


def test_ohne_kopf():
    with pytest.raises(NichtLesbar, match="HEAD"):
        lesen(b"0 @I1@ INDI\n0 TRLR\n")


def test_rueckschreiben_eines_teilbaums():
    d = lesen(_datei().encode())
    assert d.datensaetze[0].erstes("NOTE").gedcom(2) == "2 NOTE Erste Zeile\n3 CONT zweite Zeile fortgesetzt"
    assert d.datensaetze[0].gedcom().startswith("0 @I1@ INDI\n1 NAME Jürgen /Möller/\n1 NOTE")
