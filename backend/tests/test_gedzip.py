"""GEDZIP (E23): Baum als 7.0 mit seinen Mediendateien, zurück ohne Verlust."""

from __future__ import annotations

import datetime
import io
import zipfile

import pytest

from baum import datei
from baum.auszug import auszug
from gedcom import gedzip
from gedcom.import551 import importieren
from gedcom.lesen import NichtLesbar

HEUTE = datetime.datetime(2026, 11, 2, 12, 0, 0)

BAUM = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Anna /Weber/
1 OBJE @M1@
1 OBJE @M2@
1 OBJE @M3@
0 @M1@ OBJE
1 FILE bilder/Taufe Anna.jpg
2 FORM jpg
2 TITL Taufe
0 @M2@ OBJE
1 FILE fehlt.jpg
2 FORM jpg
0 @M3@ OBJE
1 FILE https://example.org/bild.jpg
2 FORM jpg
0 TRLR
"""


@pytest.fixture
def baum(tmp_path):
    medien = tmp_path / "medien"
    (medien / "bilder").mkdir(parents=True)
    (medien / "bilder" / "Taufe Anna.jpg").write_bytes(b"\xff\xd8 Bild")
    importieren(BAUM.encode(), tmp_path / "a.wise")
    con = datei.oeffnen(tmp_path / "a.wise")
    yield con, medien
    con.close()


def test_schreiben(baum):
    con, medien = baum
    daten, bericht = gedzip.schreiben(con, medien, HEUTE)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        assert z.namelist() == ["gedcom.ged", "bilder/Taufe Anna.jpg"]
        text = z.read("gedcom.ged").decode()
        assert z.read("bilder/Taufe Anna.jpg") == b"\xff\xd8 Bild"
    assert "1 FILE bilder/Taufe%20Anna.jpg\n2 FORM image/jpeg" in text and "2 VERS 7.0" in text
    assert bericht.medien_im_archiv == 1 and bericht.medien_fehlen == ["fehlt.jpg"]


def test_schreiben_bitgenau(baum):
    con, medien = baum
    assert gedzip.schreiben(con, medien, HEUTE)[0] == gedzip.schreiben(con, medien, HEUTE)[0]


def test_zurueck_ohne_verlust(baum, tmp_path):
    con, medien = baum
    daten, _ = gedzip.schreiben(con, medien, HEUTE)
    neu = tmp_path / "neu"
    gedcom = gedzip.entpacken(daten, neu)
    assert (neu / "bilder" / "Taufe Anna.jpg").read_bytes() == b"\xff\xd8 Bild"
    importieren(gedcom, tmp_path / "b.wise")
    b = datei.oeffnen(tmp_path / "b.wise")
    try:
        vorher, nachher = auszug(con), auszug(b)
    finally:
        b.close()
    # gleich bis auf die Werte, die 7.0 anders schreibt (E27): Format jpg → image/jpeg
    for m in vorher["media"].values():
        for f in m["files"]:
            f["format"] = "image/jpeg"
    assert nachher == vorher


def test_entpacken_bleibt_im_ordner(tmp_path):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("gedcom.ged", "0 HEAD\n1 GEDC\n2 VERS 7.0\n0 TRLR\n")
        z.writestr("../boese.txt", "x")
        z.writestr("/absolut.txt", "x")
        z.writestr("gut/datei.txt", "x")
    ziel = tmp_path / "medien"
    gedzip.entpacken(puffer.getvalue(), ziel)
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file()) == [
        "medien/gut/datei.txt"]


def test_kein_gedzip():
    with pytest.raises(NichtLesbar):
        gedzip.lesen(b"0 HEAD\n")
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("baum.ged", "0 HEAD\n")
    with pytest.raises(NichtLesbar, match="gedcom.ged"):
        gedzip.lesen(puffer.getvalue())
