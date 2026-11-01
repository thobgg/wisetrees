"""Bildauslieferung: nur sichtbare Medien, nur Dateien im Medienordner des Baums."""

from __future__ import annotations

from gedcom.import551 import importieren
from vertrag.client import Sitzung

GED = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Alt /Tot/
1 DEAT Y
1 OBJE @M1@
1 OBJE @M2@
0 @I2@ INDI
1 NAME Jung /Lebt/
1 BIRT
2 DATE 1 JAN 2000
1 OBJE @M3@
0 @M1@ OBJE
1 FILE bild.jpg
2 FORM jpg
0 @M2@ OBJE
1 FILE ../../geheim.txt
2 FORM jpg
0 @M3@ OBJE
1 FILE lebend.jpg
2 FORM jpg
0 TRLR
"""


def test_bilder_nur_sichtbar_und_im_ordner(einstellungen, server):
    importieren(GED.encode(), einstellungen.baeume / "probe.wise")
    ordner = einstellungen.medien / "probe"
    ordner.mkdir(parents=True)
    (ordner / "bild.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 200)
    (ordner / "lebend.jpg").write_bytes(b"\xff\xd8\xff" + b"y" * 200)
    (einstellungen.daten / "geheim.txt").write_text("geheim")
    s = Sitzung(server)
    url = lambda x: s.url(f"/wisetrees/medien/probe/{x}")  # noqa: E731
    ok = s.holen(url("M1"))
    assert ok.status == 200 and ok.content_type == "image/jpeg"
    assert s.holen(url("M2")).status == 404          # Pfad aus dem Medienordner hinaus
    assert s.holen(url("M3")).status == 404          # Bild einer lebenden Person, Besucher
    assert s.holen(url("M9")).status == 404
    assert s.holen(s.url("/wisetrees/medien/gibtsnicht/M1")).status == 404
