"""v1-HTTP-Schicht: Adressform mit Unterpfad, Sitzung für Besucher, keine 401 (docs/API-V1.md 1–3)."""

from __future__ import annotations

import json
import urllib.request

from vertrag.client import Sitzung


def test_unterpfad_im_route_parameter(server):
    s = Sitzung(server + "/familie/wisetrees")  # wie hinter einem Proxy unter /familie/wisetrees
    a = s.get("Info")
    assert a.status == 200 and a.ist_json
    assert a.json["user"]["loggedIn"] is False and a.json["csrf"]
    assert s.url("/x").startswith(server + "/familie/wisetrees/index.php?route=%2Ffamilie%2Fwisetrees%2Fx")


def test_besucher_bekommt_sitzung_mit_gleichbleibendem_token(server):
    s = Sitzung(server)
    eins, zwei = s.info()["csrf"], s.info()["csrf"]
    assert eins == zwei
    assert Sitzung(server).info()["csrf"] != eins


def test_unbekannte_aktion_und_route(server):
    s = Sitzung(server)
    for a in (s.get("GibtEsNicht"), s.holen(s.url("/tree/x/individual/I1"))):
        assert a.status == 404 and not a.ist_json


def test_falsches_passwort_wird_gesperrt(server, einstellungen):
    import main  # noqa: F401
    s = Sitzung(server)
    for _ in range(6):
        assert s.anmelden("niemand", "falsch")["user"]["loggedIn"] is False


def test_healthz_bleibt_json(server):
    with urllib.request.urlopen(server + "/healthz") as r:
        assert json.loads(r.read())["ok"] is True


def test_startseite_statt_404_auch_nach_dem_anmelden(server):
    s = Sitzung(server)
    a = s.holen(server + "/index.php")
    assert a.status == 200 and "wisetrees läuft" in a.daten.decode() and "Nicht angemeldet" in a.daten.decode()
    assert s.holen(s.url("/")).status == 200


def test_app_seite_nennt_die_adresse(server):
    s = Sitzung(server + "/familie")
    a = s.holen(s.url("/familie/wisetrees/app"))
    text = a.daten.decode()
    assert a.status == 200 and f"<code>{server}/familie</code>" in text


def test_info_meldet_features(server):
    """E17: Info.features nennt die vollständig angebotenen Fähigkeiten (Meilenstein 1: nur lesen)."""
    assert Sitzung(server).info()["features"] == ["read"]


def test_url_felder_zeigen_auf_die_startseite(einstellungen, server):
    from gedcom.import551 import importieren
    ged = b"0 HEAD\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Alt /Tot/\n1 DEAT Y\n0 TRLR\n"
    importieren(ged, einstellungen.baeume / "probe.wise")
    s = Sitzung(server + "/familie")
    url = s.get("Individual", "probe", {"xref": "I1"}).json["person"]["url"]
    assert url == server + "/familie/index.php"
    assert "wisetrees läuft" in s.holen(url).daten.decode()


def test_nackte_adresse_fuehrt_zur_startseite(server):
    s = Sitzung(server)
    a = s.holen(server + "/")
    assert a.status == 302 and a.location == "index.php"
