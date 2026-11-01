"""Verwaltung im Browser, Stufe 1 (KONZEPT.md E18)."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pytest

from core.konten import KontenDB
from vertrag.client import Sitzung

DATEN = Path(__file__).parent / "daten"
KLEIN = (b"0 HEAD\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Anna /Alt/\n1 DEAT Y\n"
         b"0 @I2@ INDI\n1 NAME Bernd /Alt/\n1 DEAT Y\n0 TRLR\n")


class Browser(Sitzung):
    """Test-Client mit den Formularen der Verwaltung."""

    def seite(self, teil: str = "", **params) -> str:
        a = self.holen(self.url(f"/wisetrees/verwaltung{teil}", params))
        assert a.status == 200, a.status
        text = a.daten.decode()
        m = re.search(r'name="_csrf" value="([^"]+)"', text)
        if m:
            self.csrf = m.group(1)
        return text

    def senden_formular(self, aktion: str, felder: dict):
        a = self.formular(f"/wisetrees/verwaltung/{aktion}", {"_csrf": self.csrf, **felder})
        return a

    def hochladen(self, baum: str, inhalt: bytes, titel: str = "", dateiname: str = "baum.ged"):
        grenze = uuid.uuid4().hex
        teile = []
        for k, v in (("_csrf", self.csrf), ("baum", baum), ("titel", titel)):
            teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="datei"; filename="{dateiname}"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n".encode() + inhalt + b"\r\n")
        teile.append(f"--{grenze}--\r\n".encode())
        req = urllib.request.Request(self.url("/wisetrees/verwaltung/baum-hochladen"), data=b"".join(teile),
                                     method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={grenze}")
        return self.senden(req)


def meldung(a) -> tuple[str, str]:
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(a.location or "").query)
    return q.get("meldung", [""])[0], q.get("name", [""])[0]


@pytest.fixture
def admin(einstellungen, server):
    db = KontenDB(einstellungen.konten_db)
    db.anlegen("chef", "chef-passwort", is_admin=True)
    db.anlegen("anna", "anna-passwort")
    db.schliessen()
    b = Browser(server)
    b.seite()
    a = b.senden_formular("anmelden", {"name": "chef", "passwort": "chef-passwort"})
    assert a.status == 303 and meldung(a)[0] == "angemeldet"
    return b


def test_ohne_anmeldung_nur_das_formular(server):
    b = Browser(server)
    text = b.seite()
    assert 'name="passwort"' in text and "Neues Konto" not in text
    # Aktionen ohne Anmeldung: nichts passiert, zurück zur Übersicht
    a = b.senden_formular("konto-anlegen", {"name": "x", "passwort": "12345678", "passwort2": "12345678"})
    assert a.status == 303 and "meldung" not in (a.location or "")


def test_falsches_passwort_und_csrf(einstellungen, server):
    KontenDB(einstellungen.konten_db).anlegen("chef", "chef-passwort", is_admin=True)
    b = Browser(server)
    b.seite()
    a = b.senden_formular("anmelden", {"name": "chef", "passwort": "falsch"})
    assert meldung(a)[0] == "anmeldung-fehlgeschlagen"
    b.csrf = "falsch"
    a = b.senden_formular("anmelden", {"name": "chef", "passwort": "chef-passwort"})
    assert a.status == 303 and meldung(a)[0] == ""          # ohne gültiges Token nichts ausgeführt
    assert 'name="passwort"' in b.seite()                    # weiter nicht angemeldet


def test_konto_ohne_adminrecht_sieht_nur_den_hinweis(einstellungen, server):
    KontenDB(einstellungen.konten_db).anlegen("anna", "anna-passwort")
    b = Browser(server)
    b.seite()
    b.senden_formular("anmelden", {"name": "anna", "passwort": "anna-passwort"})
    text = b.seite()
    assert "nur Administratoren" in text and "Neues Konto" not in text
    a = b.senden_formular("konto-anlegen", {"name": "x", "passwort": "12345678", "passwort2": "12345678"})
    assert meldung(a)[0] == ""
    assert KontenDB(einstellungen.konten_db).konto("x") is None


def test_konten_anlegen_rollen_passwort_loeschen(admin, einstellungen):
    b = admin
    b.seite()
    assert meldung(b.senden_formular("konto-anlegen", {"name": "bernd", "passwort": "kurz", "passwort2": "kurz"}))[0] \
        == "passwort-kurz"
    assert meldung(b.senden_formular("konto-anlegen", {"name": "bernd", "passwort": "12345678",
                                                       "passwort2": "87654321"}))[0] == "passwort-ungleich"
    assert meldung(b.senden_formular("konto-anlegen", {"name": "anna", "passwort": "12345678",
                                                       "passwort2": "12345678"}))[0] == "konto-gibt-es"
    a = b.senden_formular("konto-anlegen", {"name": "bernd", "anzeigename": "Bernd <b>", "passwort": "bernd-pw-1",
                                            "passwort2": "bernd-pw-1"})
    assert meldung(a) == ("konto-angelegt", "bernd")
    text = b.seite(meldung="konto-angelegt", name="<script>")
    assert "Bernd &lt;b&gt;" in text and "<script>" not in text   # alles maskiert
    db = KontenDB(einstellungen.konten_db)
    assert db.pruefen("bernd", "bernd-pw-1") is not None

    b.hochladen("probe", KLEIN)
    a = b.senden_formular("rollen-setzen", {"name": "bernd", "rolle:probe": "member"})
    assert meldung(a) == ("rolle-gesetzt", "bernd")
    assert db.rolle(db.konto("bernd"), "probe") == "member"

    a = b.senden_formular("passwort-setzen", {"name": "bernd", "passwort": "neu-neu-neu", "passwort2": "neu-neu-neu"})
    assert meldung(a)[0] == "passwort-gesetzt" and db.pruefen("bernd", "neu-neu-neu") is not None

    assert meldung(b.senden_formular("konto-loeschen", {"name": "chef"}))[0] == "selbst"
    assert meldung(b.senden_formular("konto-loeschen", {"name": "bernd"})) == ("konto-geloescht", "bernd")
    assert db.konto("bernd") is None and db.rollen().get("bernd") is None
    db.schliessen()


def test_baum_hochladen_bericht_und_loeschen(admin, einstellungen, server):
    b = admin
    b.seite()
    assert meldung(b.hochladen("../x", KLEIN))[0] == "baumname-ungueltig"
    a = b.hochladen("falkenrath", (DATEN / "falkenrath-1.7.1.ged").read_bytes(), "Falkenrath",
                    "falkenrath-1.7.1.ged")
    assert meldung(a) == ("baum-eingelesen", "falkenrath")
    assert meldung(b.hochladen("falkenrath", KLEIN))[0] == "baum-gibt-es"
    assert meldung(b.hochladen("kaputt", b"kein gedcom"))[0] == "nicht-lesbar"
    assert not (einstellungen.baeume / "kaputt.wise").exists()
    text = b.seite()
    assert "<code>falkenrath</code>" in text and "<td>492</td>" in text
    assert "falkenrath-1.7.1.ged: 26122 Zeilen, als Rest" in text
    # Der neue Baum ist sofort über die Schnittstelle da
    app = Sitzung(server)
    app.anmelden("chef", "chef-passwort")
    assert [t["name"] for t in app.info()["trees"]] == ["falkenrath"]

    db = KontenDB(einstellungen.konten_db)
    db.rolle_setzen("anna", "falkenrath", "member")
    assert meldung(b.senden_formular("baum-loeschen", {"baum": "falkenrath", "bestaetigung": "falken"}))[0] \
        == "bestaetigung-fehlt"
    assert (einstellungen.baeume / "falkenrath.wise").exists()
    a = b.senden_formular("baum-loeschen", {"baum": "falkenrath", "bestaetigung": "falkenrath"})
    assert meldung(a) == ("baum-geloescht", "falkenrath")
    assert not (einstellungen.baeume / "falkenrath.wise").exists()
    assert db.rollen() == {}
    db.schliessen()


def test_eigenes_passwort_aendern(einstellungen, server):
    KontenDB(einstellungen.konten_db).anlegen("anna", "anna-passwort")
    b = Browser(server)
    b.seite()
    b.senden_formular("anmelden", {"name": "anna", "passwort": "anna-passwort"})
    b.seite("/passwort")
    a = b.senden_formular("passwort", {"bisher": "falsch", "passwort": "neues-pw-1", "passwort2": "neues-pw-1"})
    assert meldung(a)[0] == "passwort-falsch"
    a = b.senden_formular("passwort", {"bisher": "anna-passwort", "passwort": "neues-pw-1", "passwort2": "neues-pw-1"})
    assert meldung(a)[0] == "passwort-geaendert"
    assert 'name="passwort"' in b.seite()          # alle Sitzungen beendet, auch diese
    db = KontenDB(einstellungen.konten_db)
    assert db.pruefen("anna", "neues-pw-1") is not None and db.pruefen("anna", "anna-passwort") is None
    db.schliessen()


def test_abmelden_und_startseite_verlinkt(admin, server):
    b = admin
    start = b.holen(server + "/index.php").daten.decode()
    assert "wisetrees%2Fverwaltung" in start
    b.seite()
    a = b.senden_formular("abmelden", {})
    assert a.status == 303
    assert 'name="passwort"' in b.seite()


def test_seiten_nicht_einbettbar_und_nicht_zwischengespeichert(server):
    url = Browser(server).url("/wisetrees/verwaltung")
    with urllib.request.urlopen(url) as r:
        assert r.headers["X-Frame-Options"] == "DENY" and r.headers["Cache-Control"] == "no-store"
        assert "Neues Konto" not in r.read().decode()


def test_datenschutz_einstellen(admin, einstellungen, server):
    from baum import datei, datenschutz

    b = admin
    b.seite()
    b.hochladen("probe", KLEIN)
    text = b.seite("/datenschutz", baum="probe")
    assert "Datenschutz an" in text and "<code>SSN</code>" in text      # Vorgaberegeln stehen da
    a = b.senden_formular("datenschutz-speichern", {"baum": "probe", "enabled": "1", "members_only": "1",
                                                    "show_dead_people": "1", "show_living_names": "0",
                                                    "max_alive_age": "90", "keep_alive_years_birth": "100",
                                                    "keep_alive_years_death": "x"})
    assert meldung(a)[0] == "datenschutz-gespeichert"
    assert meldung(b.senden_formular("regel-setzen", {"baum": "probe", "xref": "@I1@", "tag": "occu",
                                                      "resn": "confidential"}))[0] == "regel-gesetzt"
    assert meldung(b.senden_formular("regel-setzen", {"baum": "probe", "tag": "SOUR", "entfernen": "1"}))[0] \
        == "regel-entfernt"
    assert meldung(b.senden_formular("regel-setzen", {"baum": "probe", "resn": "privacy"}))[0] == "regel-ungueltig"
    assert meldung(b.senden_formular("regel-setzen", {"baum": "probe", "tag": "X; DROP", "resn": "privacy"}))[0] \
        == "regel-ungueltig"
    con = datei.oeffnen(einstellungen.baeume / "probe.wise")
    e, r = datenschutz.laden(con)
    con.close()
    assert (e.members_only, e.show_dead_people, e.show_living_names, e.show_private_relationships) == (True, 1, 0, False)
    assert (e.max_alive_age, e.keep_alive_years_birth, e.keep_alive_years_death) == (90, 100, 0)
    assert r.fakt_am_datensatz == {("I1", "OCCU"): 0} and "SOUR" not in r.art

    # wirkt sofort: Besucher sehen den Baum nicht mehr
    app = Sitzung(server)
    assert app.info()["trees"] == []
    assert app.get("Individuals", "probe").status == 302


def test_datenschutz_nur_fuer_administratoren(einstellungen, server):
    KontenDB(einstellungen.konten_db).anlegen("anna", "anna-passwort")
    b = Browser(server)
    b.seite()
    b.senden_formular("anmelden", {"name": "anna", "passwort": "anna-passwort"})
    a = b.holen(b.url("/wisetrees/verwaltung/datenschutz", {"baum": "probe"}))
    assert a.status == 303
    a = b.senden_formular("datenschutz-speichern", {"baum": "probe", "enabled": "0"})
    assert meldung(a)[0] == ""
