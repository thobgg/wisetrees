"""Modellauszug (KONZEPT.md 6): Grundlage des Rundlauf-Tests Import → Export → Import."""

from __future__ import annotations

from pathlib import Path

import pytest

from baum import datei
from baum.auszug import Auszug, auszug
from gedcom.import551 import importieren

DATEN = Path(__file__).with_name("daten")


def _import(tmp_path: Path, gedcom: bytes, name: str = "t.wise"):
    ziel = tmp_path / name
    importieren(gedcom, ziel)
    return datei.oeffnen(ziel)


@pytest.fixture(scope="module")
def falkenrath(tmp_path_factory):
    con = _import(tmp_path_factory.mktemp("falk"), (DATEN / "falkenrath-1.7.1.ged").read_bytes())
    a = Auszug(con)
    ganz = a.ganz()
    yield con, a, ganz
    con.close()


def test_jede_zeile_des_modells_steht_im_auszug(falkenrath):
    _, a, _ = falkenrath
    assert a.nicht_erfasst() == {}


def test_alle_datensaetze_unter_ihrer_kennung(falkenrath):
    _, _, g = falkenrath
    assert (len(g["person"]), len(g["family"]), len(g["source"]), len(g["repository"])) == (492, 154, 204, 40)
    assert all(k.startswith("@") for k in g["person"])
    assert "id" not in g["person"]["@I1@"]


def test_orte_ohne_kennung_heissen_nach_der_namenskette(falkenrath):
    _, _, g = falkenrath
    ohne = [k for k in g["place"] if not k.startswith("@")]
    assert ohne and all(" #" not in k for k in g["place"]), "Ortsnamen im Auszug sind eindeutig"
    assert any(" < " in k for k in ohne)


def test_paten_stehen_am_ereignis(falkenrath):
    _, _, g = falkenrath
    rollen = [r["role"] for t in ("person", "family") for d in g[t].values() for f in d["facts"]
              for r in f["event"].get("roles", [])]
    assert "GODP" in rollen and "WITN" in rollen


def test_zweimal_eingelesen_gleicher_auszug(tmp_path, falkenrath):
    _, _, g = falkenrath
    con = _import(tmp_path, (DATEN / "falkenrath-1.7.1.ged").read_bytes())
    try:
        assert auszug(con) == g
    finally:
        con.close()


KLEIN = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Karl /Vater/
1 FAMS @F1@
1 BIRT
2 DATE 1820
2 PLAC Hof 3, Neustadt
0 @I2@ INDI
1 NAME Paul /Kind/
1 FAMC @F1@
1 BAPM
2 DATE 1850
2 _ASSO @I1@
3 RELA Pate
2 _GODP Hans Meier, Bauer
1 NOTE @N1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
1 MARR
2 SOUR @S1@
3 PAGE S. 4
0 @S1@ SOUR
1 TITL Kirchenbuch
0 @N1@ NOTE Eine Notiz
0 TRLR
"""


def _umgestellt(text: str) -> str:
    """Datensätze in umgekehrter Reihenfolge: andere interne Kennungen, gleicher Inhalt."""
    zeilen = text.strip().split("\n")
    kopf, rumpf, ende = [], [], zeilen[-1]
    saetze: list[list[str]] = []
    for z in zeilen[:-1]:
        if z.startswith("0 "):
            saetze.append([z])
        else:
            saetze[-1].append(z)
    kopf, rumpf = saetze[0], saetze[1:]
    return "\n".join(kopf + [z for s in reversed(rumpf) for z in s] + [ende]) + "\n"


def test_reihenfolge_der_datensaetze_aendert_den_auszug_nicht(tmp_path):
    a = _import(tmp_path, KLEIN.encode(), "a.wise")
    b = _import(tmp_path, _umgestellt(KLEIN).encode(), "b.wise")
    try:
        assert auszug(a) == auszug(b)
    finally:
        a.close()
        b.close()


def test_inhalt_aendert_den_auszug(tmp_path):
    a = _import(tmp_path, KLEIN.encode(), "a.wise")
    b = _import(tmp_path, KLEIN.replace("S. 4", "S. 5").encode(), "b.wise")
    try:
        assert auszug(a) != auszug(b)
    finally:
        a.close()
        b.close()


def test_klein_im_einzelnen(tmp_path):
    con = _import(tmp_path, KLEIN.encode())
    try:
        a = Auszug(con)
        g = a.ganz()
        assert a.nicht_erfasst() == {}
    finally:
        con.close()
    paul = g["person"]["@I2@"]
    assert paul["famc"] == ["@F1@"] and paul["notes"] == ["@N1@"]
    taufe = paul["facts"][0]["event"]
    assert [(r["role"], r.get("person"), r.get("free_name")) for r in taufe["roles"]] == [
        ("GODP", "@I1@", None), ("GODP", None, "Hans Meier")]
    assert g["person"]["@I1@"]["facts"][0]["event"]["place"] == "Hof 3 < Neustadt"
    assert "Neustadt" in g["place"] and "Hof 3 < Neustadt" in g["place"]
    f1 = g["family"]["@F1@"]
    assert f1["partners"] == [{"person": "@I1@", "slot": 1}] and f1["children"] == ["@I2@"]
    assert f1["facts"][0]["event"]["citations"] == [{"page": "S. 4", "source": "@S1@"}]
