"""Offene Änderungen (KONZEPT.md E21): Besucher und Mitglieder sehen nie etwas Offenes; Lesen mit offenem Stand
verändert die Baumdatei nicht; Moderation nimmt an und verwirft."""

from __future__ import annotations

import json

from baum import aenderungen as ae
from baum import datei
from gedcom.import551 import importieren
from vertrag.client import Sitzung

GED = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Hans /Alt/
1 SEX M
1 OCCU Tischler
1 DEAT Y
1 FAMS @F1@
0 @I2@ INDI
1 NAME Grete /Alt/
1 SEX F
1 DEAT Y
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1900
0 TRLR
"""
PASSWORT = "geheim-geheim"
NEU = ("Schmied", "Wollin", "Johann")


def _anmelden(server, name):
    s = Sitzung(server)
    if name is None:
        s.info()
    else:
        assert s.anmelden(name, PASSWORT)["user"]["loggedIn"]
    return s


def _aufbauen(app, einstellungen, server):
    importieren(GED.encode(), einstellungen.baeume / "probe.wise")
    k = app.state.konten
    for name, rolle in (("mitglied", "member"), ("bearbeiter", "editor"), ("moderator", "moderator")):
        k.anlegen(name, PASSWORT, real_name="Probe-Bearbeiter" if name == "bearbeiter" else "")
        k.rolle_setzen(name, "probe", rolle)
    s = {r: _anmelden(server, r) for r in ("mitglied", "bearbeiter", "moderator")}
    s[None] = _anmelden(server, None)
    b = s["bearbeiter"]
    occu = next(f["id"] for f in b.get("Individual", "probe", {"xref": "I1"}).json["facts"] if f["tag"] == "OCCU")
    name = next(f["id"] for f in b.get("Individual", "probe", {"xref": "I1"}).json["facts"] if f["tag"] == "NAME")
    for rumpf in ({"factId": occu, "value": "Schmied"}, {"tag": "RESI", "place": "Wollin"},
                  {"factId": name, "value": "Johann /Alt/"}):
        a = b.post("Fact", "probe", {"xref": "I1"}, rumpf)
        assert a.json == {"ok": True, "xref": "I1", "pending": True}
    a = b.post("Fact", "probe", {"xref": "F1"}, {"tag": "DIV", "date": "1920"})
    assert a.json["pending"] is True
    return s


def _lesen(s: Sitzung) -> str:
    """Alles, was eine Rolle über den Baum lesen kann, als ein Text."""
    suche = [s.get("Individuals", "probe", p).json for p in ({}, {"q": "Johann"}, {"q": "Schmied", "scope": "all"})]
    for j in suche:
        j.pop("query")                                          # das Echo der Suchworte zählt nicht
    teile = [s.get("Info", None, {}).json, *suche,
             s.get("Pedigree", "probe", {"xref": "I1"}).json, s.get("Descendants", "probe", {"xref": "I1"}).json]
    for xref in ("I1", "I2"):
        teile.append(s.get("Individual", "probe", {"xref": xref}).json)
    teile.append(s.get("Family", "probe", {"xref": "F1"}).json)
    return json.dumps(teile, ensure_ascii=False)


def test_besucher_und_mitglieder_sehen_nie_offenes(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server)
    for rolle in (None, "mitglied"):
        text = _lesen(s[rolle])
        assert '"pending": true' not in text, rolle
        assert not any(w in text for w in NEU), rolle
        assert '"DIV"' not in text, rolle
        info = s[rolle].get("Info", None, {}).json
        assert all(t["pending"] == 0 for t in info["trees"])
        assert s[rolle].get("Pending", "probe", {}).json["error"] == "not-moderator"
    # Bearbeiter sehen sie, mit pending: true
    ind = s["bearbeiter"].get("Individual", "probe", {"xref": "I1"}).json
    offen = {f["tag"]: f["value"] for f in ind["facts"] if f["pending"]}
    assert offen == {"OCCU": "Schmied", "RESI": "", "NAME": "Johann /Alt/"}
    assert ind["person"]["name"] == "Hans Alt"                  # Kurzform bleibt beim angenommenen Stand
    fam = s["bearbeiter"].get("Family", "probe", {"xref": "F1"}).json
    assert [f["tag"] for f in fam["facts"] if f["pending"]] == ["DIV"]


def test_lesen_mit_offenem_stand_aendert_die_datei_nicht(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server)
    for rolle in ("bearbeiter", "moderator"):
        _lesen(s[rolle])
    con = datei.oeffnen(einstellungen.baeume / "probe.wise")
    try:
        assert len(ae.offene_saetze(con)) == 4
        with ae.offener_stand(con) as stand:
            assert "event" in stand.beruehrt and "name" in stand.beruehrt
        assert len(ae.offene_saetze(con)) == 4
    finally:
        con.close()
    assert '"Schmied"' not in _lesen(s[None])


def test_moderation(app, einstellungen, server):
    s = _aufbauen(app, einstellungen, server)
    m = s["moderator"]
    p = m.get("Pending", "probe", {}).json["data"]
    # users: Anzeigenamen der Konten (wie Info.user.realName)
    assert [(d["xref"], d["type"], d["kind"], d["changes"], d["users"]) for d in p] == [
        ("I1", "INDI", "changed", 3, ["Probe-Bearbeiter"]), ("F1", "FAM", "changed", 1, ["Probe-Bearbeiter"])]
    assert m.get("Info", None, {}).json["trees"][0]["pending"] == 2
    assert s["bearbeiter"].post("Accept", "probe", {"xref": "I1"}, {}).json["error"] == "not-moderator"
    assert m.post("Accept", "probe", {"xref": "I9"}, {}).json["error"] == "not-found"
    assert m.post("Reject", "probe", {"xref": "F1"}, {}).json == {"ok": True, "pending": 1}
    assert m.post("Accept", "probe", {}, {}).json == {"ok": True, "pending": 0}
    besucher = _lesen(s[None])
    assert "Schmied" in besucher and "Wollin" in besucher and '"DIV"' not in besucher
    assert '"pending": true' not in _lesen(s["bearbeiter"])
