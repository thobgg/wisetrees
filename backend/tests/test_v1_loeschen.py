"""DeleteFact (docs/PLAN-M2.md, Schritt 4): was mit dem Fakt wegfällt und was bleibt; Geschlecht ohne Angabe (E22)."""

from __future__ import annotations

from sqlalchemy import func, insert, select

from baum import datei
from baum.schema import tabelle as T
from core.konten import KontoBaum
from gedcom.import551 import importieren
from vertrag.client import Sitzung

GED = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Hans /Alt/
1 SEX M
1 BIRT
2 DATE 1850
2 NOTE eingebettet
2 SOUR @S1@
3 NOTE am Zitat
1 OCCU Bauer
2 NOTE @N1@
1 DEAT Y
0 @I2@ INDI
1 NAME Ohne /Geschlecht/
1 DEAT Y
0 @S1@ SOUR
1 TITL Kirchenbuch
0 @N1@ NOTE Gemeinsame Notiz
0 TRLR
"""
PASSWORT = "geheim-geheim"


def _verwalter(app, einstellungen, server, sofort=True):
    importieren(GED.encode(), einstellungen.baeume / "probe.wise")
    k = app.state.konten
    k.anlegen("verwalter", PASSWORT)
    k.rolle_setzen("verwalter", "probe", "manager")
    k.kontobaum_setzen("verwalter", "probe", KontoBaum(sofort=sofort))
    s = Sitzung(server)
    assert s.anmelden("verwalter", PASSWORT)["user"]["loggedIn"]
    return s


def _fakt(s, xref, tag):
    return next(f["id"] for f in s.get("Individual", "probe", {"xref": xref}).json["facts"] if f["tag"] == tag)


def _anzahl(einstellungen, tab, **wo):
    con = datei.oeffnen(einstellungen.baeume / "probe.wise")
    try:
        t = T(tab)
        q = select(func.count()).select_from(t)
        for k, v in wo.items():
            q = q.where(t.c[k].is_(None) if v is None else t.c[k] == v)
        return con.execute(q).scalar()
    finally:
        con.close()


def test_ereignis_mit_eingebetteten_notizen_und_zitat(app, einstellungen, server):
    s = _verwalter(app, einstellungen, server)
    notizen = _anzahl(einstellungen, "note")
    a = s.post("DeleteFact", "probe", {"xref": "I1"}, {"factId": _fakt(s, "I1", "BIRT")})
    assert a.json == {"ok": True, "xref": "I1", "pending": False}
    assert _anzahl(einstellungen, "event", type="BIRT") == 0
    assert _anzahl(einstellungen, "citation") == 0                  # Zitat hing am Ereignis
    assert _anzahl(einstellungen, "note") == notizen - 2            # beide eingebetteten Notizen weg
    assert _anzahl(einstellungen, "source") == 1                    # die Quelle selbst bleibt


def test_notiz_als_datensatz_bleibt(app, einstellungen, server):
    s = _verwalter(app, einstellungen, server)
    s.post("DeleteFact", "probe", {"xref": "I1"}, {"factId": _fakt(s, "I1", "OCCU")})
    assert _anzahl(einstellungen, "note", xref="N1") == 1
    assert _anzahl(einstellungen, "note_link") == 2                 # nur noch BIRT: eingebettet und am Zitat


def test_geteiltes_ereignis_nur_eigene_beteiligung(app, einstellungen, server):
    s = _verwalter(app, einstellungen, server)
    con = datei.oeffnen(einstellungen.baeume / "probe.wise")
    try:
        er = T("event_role")
        with con.begin():
            occu = con.execute(select(er.c.event_id).where(er.c.person_id == 1, er.c.role == "PRINCIPAL")
                               .order_by(er.c.fact_sort)).all()[1][0]
            con.execute(insert(er).values(event_id=occu, person_id=2, role="PRINCIPAL", sort=1, fact_sort=9))
    finally:
        con.close()
    s.post("DeleteFact", "probe", {"xref": "I1"}, {"factId": _fakt(s, "I1", "OCCU")})
    assert "OCCU" not in [f["tag"] for f in s.get("Individual", "probe", {"xref": "I1"}).json["facts"]]
    assert "OCCU" in [f["tag"] for f in s.get("Individual", "probe", {"xref": "I2"}).json["facts"]]
    assert _anzahl(einstellungen, "event", type="OCCU") == 1


def test_offen_angelegten_fakt_aendern_und_loeschen(app, einstellungen, server):
    s = _verwalter(app, einstellungen, server, sofort=False)
    s.post("Fact", "probe", {"xref": "I1"}, {"tag": "RESI", "place": "Celle"})
    fid = _fakt(s, "I1", "RESI")
    assert "n" in fid                                                # über den Schritt angesprochen
    assert s.post("Fact", "probe", {"xref": "I1"}, {"factId": fid, "date": "1900"}).json["ok"] is True
    resi = next(f for f in s.get("Individual", "probe", {"xref": "I1"}).json["facts"] if f["tag"] == "RESI")
    assert resi["date"]["year"] == 1900 and resi["id"] == fid
    assert s.post("DeleteFact", "probe", {"xref": "I1"}, {"factId": fid}).json["pending"] is True
    assert "RESI" not in [f["tag"] for f in s.get("Individual", "probe", {"xref": "I1"}).json["facts"]]
    assert s.post("Accept", "probe", {}, {}).json == {"ok": True, "pending": 0}
    assert _anzahl(einstellungen, "event", type="RESI") == 0


def test_geschlecht_ohne_angabe(app, einstellungen, server):
    s = _verwalter(app, einstellungen, server)
    i2 = s.get("Individual", "probe", {"xref": "I2"}).json
    assert i2["person"]["sex"] == "U" and "SEX" not in [f["tag"] for f in i2["facts"]]
    s.post("DeleteFact", "probe", {"xref": "I1"}, {"factId": _fakt(s, "I1", "SEX")})
    i1 = s.get("Individual", "probe", {"xref": "I1"}).json
    assert i1["person"]["sex"] == "U" and "SEX" not in [f["tag"] for f in i1["facts"]]
    assert _anzahl(einstellungen, "person", sex=None) == 2
