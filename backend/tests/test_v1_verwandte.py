"""AddIndividual, Link, Unlink, DeleteRecord (docs/PLAN-M2.md, Schritt 5): Zusammenhänge zwischen Sätzen,
Aufräumen beim Löschen, nichts Offenes für Besucher."""

from __future__ import annotations

import json

from sqlalchemy import func, select

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
1 DEAT Y
1 FAMS @F1@
0 @I2@ INDI
1 NAME Grete /Alt/
1 SEX F
1 DEAT Y
1 FAMS @F1@
0 @I3@ INDI
1 NAME Paul /Alt/
1 SEX M
1 DEAT Y
1 FAMC @F1@
1 ASSO @I1@
2 RELA Pate
0 @I4@ INDI
1 NAME Lina /Neu/
1 SEX F
1 DEAT Y
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 1875
0 TRLR
"""
PASSWORT = "geheim-geheim"


def _aufbauen(app, einstellungen, server, sofort=False):
    importieren(GED.encode(), einstellungen.baeume / "probe.wise")
    k = app.state.konten
    s = {}
    for name, rolle in (("bearbeiter", "editor"), ("moderator", "moderator"), ("mitglied", "member")):
        k.anlegen(name, PASSWORT)
        k.rolle_setzen(name, "probe", rolle)
        k.kontobaum_setzen(name, "probe", KontoBaum(sofort=sofort))
        s[name] = Sitzung(server)
        assert s[name].anmelden(name, PASSWORT)["user"]["loggedIn"]
    s[None] = Sitzung(server)
    s[None].info()
    return s


def _anzahl(einstellungen, tab) -> int:
    con = datei.oeffnen(einstellungen.baeume / "probe.wise")
    try:
        return con.execute(select(func.count()).select_from(T(tab))).scalar()
    finally:
        con.close()


def _kinder(s, xref="F1"):
    return [k["xref"] for k in s.get("Family", "probe", {"xref": xref}).json["children"]]


def test_offenes_kind_annehmen_ueber_die_person(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server)
    a = s["bearbeiter"].post("AddIndividual", "probe", {}, {"relation": "child", "relativeTo": "I1", "given": "Emma",
                                                            "surname": "Alt", "sex": "F"})
    neu = a.json["xref"]
    assert a.status == 201 and a.json["pending"] is True and a.json["family"] == "F1"
    assert _kinder(s["bearbeiter"]) == ["I3", neu] and _kinder(s["mitglied"]) == ["I3"]
    p = s["moderator"].get("Pending", "probe", {}).json["data"]
    assert [(d["xref"], d["kind"], d["changes"]) for d in p] == [(neu, "new", 2), ("F1", "changed", 1)]
    # Nur die Person annehmen: die Verknüpfung im Satz der Familie gehört dazu und wird mitgenommen
    assert s["moderator"].post("Accept", "probe", {"xref": neu}, {}).json == {"ok": True, "pending": 0}
    assert _kinder(s["mitglied"]) == ["I3", neu]


def test_verknuepfung_verwerfen_nimmt_die_abhaengigen_mit(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server)
    a = s["bearbeiter"].post("Link", "probe", {}, {"individual": "I4", "relation": "child", "relativeTo": "I2"})
    assert a.json == {"ok": True, "xref": "I4", "pending": True, "family": "F1"}
    assert s["moderator"].post("Reject", "probe", {"xref": "F1"}, {}).json == {"ok": True, "pending": 0}
    assert _kinder(s["bearbeiter"]) == ["I3"]


def test_offen_loesen_und_nur_die_person_annehmen(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server)
    assert s["bearbeiter"].post("Unlink", "probe", {}, {"family": "F1", "individual": "I3"}).json["pending"] is True
    assert _kinder(s["bearbeiter"]) == ["I3"]                      # bis zum Annehmen noch verknüpft
    assert s["moderator"].post("Accept", "probe", {"xref": "I3"}, {}).json == {"ok": True, "pending": 0}
    assert _kinder(s["mitglied"]) == []
    assert _anzahl(einstellungen, "parentage") == 0


def test_familie_loeschen(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server, sofort=True)
    ereignisse = _anzahl(einstellungen, "event")
    a = s["bearbeiter"].post("DeleteRecord", "probe", {"xref": "F1"}, {})
    assert a.json == {"ok": True, "xref": "F1", "pending": False}
    assert _anzahl(einstellungen, "family") == 0 and _anzahl(einstellungen, "family_member") == 0
    assert _anzahl(einstellungen, "event") == ereignisse - 1        # nur die Heirat; Ereignisse der Personen bleiben
    i1 = s["mitglied"].get("Individual", "probe", {"xref": "I1"}).json
    assert i1["spouseFamilies"] == []


def test_person_loeschen_raeumt_auf(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server, sofort=True)
    notizen, ereignisse = _anzahl(einstellungen, "note"), _anzahl(einstellungen, "event")
    assert s["bearbeiter"].post("DeleteRecord", "probe", {"xref": "I1"}, {}).json["ok"] is True
    assert _anzahl(einstellungen, "note") == notizen - 1            # eingebettete Notiz der Geburt
    assert _anzahl(einstellungen, "event") == ereignisse - 2        # BIRT und DEAT von I1
    assert _anzahl(einstellungen, "person_association") == 0       # Verknüpfung von I3 auf I1
    assert s["mitglied"].get("Family", "probe", {"xref": "F1"}).json["husband"] is None


def test_besucher_sehen_nichts_offenes(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server)
    b = s["bearbeiter"]
    neu = b.post("AddIndividual", "probe", {}, {"relation": "spouse", "relativeTo": "I3", "given": "Rosa",
                                                "surname": "Neu", "dead": True}).json
    b.post("Link", "probe", {}, {"individual": "I4", "relation": "child", "relativeTo": "I2"})
    b.post("DeleteRecord", "probe", {"xref": "I1"}, {})
    for rolle in (None, "mitglied"):
        t = s[rolle]
        assert t.get("Individual", "probe", {"xref": neu["xref"]}).json["error"] == "not-found"
        assert t.get("Family", "probe", {"xref": neu["family"]}).json["error"] == "not-found"
        text = json.dumps([t.get("Family", "probe", {"xref": "F1"}).json,
                           t.get("Individual", "probe", {"xref": "I3"}).json,
                           t.get("Individual", "probe", {"xref": "I1"}).json,
                           t.get("Pedigree", "probe", {"xref": "I4"}).json], ensure_ascii=False)
        assert "Rosa" not in text and '"pending": true' not in text
        assert _kinder(t) == ["I3"]
        i1 = t.get("Individual", "probe", {"xref": "I1"}).json
        assert len(i1["facts"]) > 0 and i1["canEdit"] is False
    # Bearbeiter sehen alles Offene, auch im Diagramm
    assert b.get("Pedigree", "probe", {"xref": "I4"}).json["ancestors"][1]["person"]["xref"] == "I1"
    assert b.get("Individual", "probe", {"xref": "I1"}).json["facts"] == []
