"""Vertragstests v1 (KONZEPT.md 4.3, docs/API-V1.md).

Je Rolle und Fall: dieselbe Anfrage wie bei der Aufzeichnung, Antwort normalisiert und verglichen.
Dazu Abläufe aus docs/API-V1.md, die keine Aufzeichnung brauchen (Anmelden, Abmelden, CSRF, Bilder).
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from . import schema
from .client import Sitzung
from .faelle import BAUM, FAELLE, ROLLEN
from .normalisieren import normalisieren

AUFZEICHNUNGEN = Path(__file__).with_name("aufzeichnungen")

FAELLE_JE_ROLLE = [pytest.param(rolle, fall, id=f"{rolle}-{fall.name}") for rolle in ROLLEN for fall in FAELLE]


def _aufzeichnung(rolle, fall) -> dict:
    datei = AUFZEICHNUNGEN / rolle / f"{fall.name}.json"
    if not datei.is_file():
        pytest.fail(f"keine Aufzeichnung {datei.relative_to(AUFZEICHNUNGEN)} – Aufzeichnung fehlt")
    return json.loads(datei.read_text(encoding="utf-8"))


def _holen(sitzungen, rolle, fall):
    return sitzungen[rolle].get(fall.aktion, BAUM if fall.mit_baum else None, fall.params)


# --- Vergleich mit der Aufzeichnung (E11 b) -------------------------------------------------------

@pytest.mark.parametrize("rolle,fall", FAELLE_JE_ROLLE)
def test_antwort_wie_aufgezeichnet(sitzungen, basis, rolle, fall):
    erwartet = _aufzeichnung(rolle, fall)
    a = _holen(sitzungen, rolle, fall)
    assert a.status == erwartet["status"]
    assert a.ist_json == erwartet["json"], f"Content-Type {a.content_type!r}"
    assert normalisieren(a.json, basis) == erwartet["antwort"]


# --- Form laut openapi.json 1.25.1 (E11 c) -------------------------------------------------------------

def test_antworten_passen_zum_schema(sitzungen):
    """Alle Fälle aller Rollen in einem Test, damit das bekannte Scheitern als eines zählt."""
    abweichungen = []
    for rolle in ROLLEN:
        for fall in FAELLE:
            a = _holen(sitzungen, rolle, fall)
            if isinstance(a.json, dict) and a.json.get("ok") is False:
                continue  # Form der Fehlerantworten prüft test_fehlerantworten
            abweichungen += [f"{rolle} {fall.name}: {z}" for z in schema.fehler(fall.aktion, fall.mit_baum, a.json)]
    assert abweichungen == [], f"{len(abweichungen)} Abweichungen, z. B. {abweichungen[:3]}"


@pytest.mark.parametrize("rolle,fall", FAELLE_JE_ROLLE)
def test_fehlerantworten(sitzungen, rolle, fall):
    """Fachliche Fehler: HTTP 200, JSON, {ok: false, error, status} (docs/API-V1.md 2)."""
    a = _holen(sitzungen, rolle, fall)
    assert a.status == 200
    if isinstance(a.json, dict) and a.json.get("ok") is False:
        assert isinstance(a.json.get("error"), str) and a.json["error"]
        assert isinstance(a.json.get("status"), int)


# --- Abläufe aus docs/API-V1.md ---------------------------------------------------------------------

def test_info_meldet_stufe_und_modul(basis):
    info = Sitzung(basis).info()
    assert isinstance(info["api"], int) and info["api"] > 0
    assert info["module"]
    assert info["csrf"]


def test_anmelden_und_abmelden(basis, passwort):
    s = Sitzung(basis)
    assert s.info()["user"]["loggedIn"] is False
    assert s.anmelden("verwalter", passwort)["user"]["loggedIn"] is True
    assert s.abmelden()["user"]["loggedIn"] is False


def test_anmelden_mit_falschem_passwort(basis):
    s = Sitzung(basis)
    assert s.anmelden("verwalter", "falsch")["user"]["loggedIn"] is False


def test_anmelden_mit_falschem_csrf_meldet_nicht_an(basis, passwort):
    s = Sitzung(basis)
    s.info()
    a = s.formular("/login", {"_csrf": "falsch", "username": "verwalter", "password": passwort})
    assert a.status not in (401, 407)
    assert s.info()["user"]["loggedIn"] is False


def test_schreiben_mit_falschem_csrf_leitet_um(sitzungen):
    """Ungültiges Token: Umleitung ohne JSON, nichts ausgeführt (docs/API-V1.md 4). Pair ist harmlos."""
    s = sitzungen["verwalter"]
    req = urllib.request.Request(s.url(s.api_route("Pair", None)), data=b'{"code": "000000"}', method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-CSRF-TOKEN", "falsch")
    a = s.senden(req)
    assert a.status == 302
    assert not a.ist_json


def test_unbekanntes_modul_404_ohne_json(sitzungen):
    """Der Client erkennt daran, dass es den Modulnamen nicht gibt (docs/API-V1.md 1)."""
    s = sitzungen["besucher"]
    a = s.holen(s.url("/module/_gibtesnicht_/Info"))
    assert a.status == 404
    assert not a.ist_json


@pytest.mark.parametrize("rolle", ["besucher", "verwalter"])
def test_portraet_laedt_mit_sitzung(sitzungen, rolle):
    """thumb ist undurchsichtig, muss aber mit derselben Sitzung ein Bild liefern (docs/API-V1.md 5)."""
    s = sitzungen[rolle]
    a = s.get("Individual", BAUM, {"xref": "I21"})
    thumb = a.json["person"]["thumb"]
    assert thumb, "I21 hat ein Porträt"
    bild = s.holen(thumb)
    assert bild.status == 200
    assert bild.content_type.startswith("image/")
    assert len(bild.daten) > 100
