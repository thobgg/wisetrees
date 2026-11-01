"""Vertragstests mit anderen Datenschutz-Einstellungen (KONZEPT.md E19, vertrag/varianten.py).

Braucht WT_VERTRAG_BAUMDATEI: die Baumdatei des wisetrees-Servers, in der die Einstellungen je Variante gesetzt
werden (python -m vertrag.wisetrees setzt sie). Gegen die Referenz entfallen diese Tests – die Aufzeichnungen
stammen von ihr.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from .faelle import BAUM, ROLLEN
from .normalisieren import normalisieren
from .varianten import FAELLE_VARIANTEN, RELATIONSHIP_OFFEN, VARIANTEN

AUFZEICHNUNGEN = Path(__file__).with_name("aufzeichnungen") / "varianten"


def _baumdatei() -> Path | None:
    p = os.environ.get("WT_VERTRAG_BAUMDATEI")
    return Path(p) if p else None


def _einstellen(pfad: Path, variante) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from baum import datei, datenschutz
    from baum.schema import privacy_rule
    from core.konten import KontenDB, KontoBaum

    db = KontenDB(pfad.parent.parent / "konten.sqlite")
    try:
        for konto in ROLLEN.values():
            if konto:
                werte = (variante.wisetrees_konten.get(konto, {}) if variante else {})
                db.kontobaum_setzen(konto, BAUM, KontoBaum(**werte))
    finally:
        db.schliessen()

    con = datei.oeffnen(pfad)
    try:
        with con.begin():
            e = datenschutz.Einstellungen(**(variante.wisetrees if variante else {}))
            datenschutz.einstellungen_speichern(con, e)
            con.execute(privacy_rule.delete())
            datenschutz.vorgaben_anlegen(con)
            for xref, tag, resn in (variante.regeln if variante else ()):
                datenschutz.regel_setzen(con, xref, tag, resn)
    finally:
        con.close()


@pytest.fixture(scope="module", params=VARIANTEN, ids=[v.name for v in VARIANTEN])
def variante(request, basis):
    pfad = _baumdatei()
    if pfad is None:
        pytest.skip("WT_VERTRAG_BAUMDATEI nicht gesetzt (nur gegen wisetrees)")
    _einstellen(pfad, request.param)
    yield request.param
    _einstellen(pfad, None)


@pytest.mark.parametrize("rolle,fall", [pytest.param(r, f, id=f"{r}-{f.name}") for r in ROLLEN for f in FAELLE_VARIANTEN])
def test_variante_wie_aufgezeichnet(variante, sitzungen, basis, rolle, fall):
    # Nur Abweichungen sind aufgehoben; fehlt die Datei, gilt die Hauptaufzeichnung (gleiche Antwort).
    datei = AUFZEICHNUNGEN / variante.name / rolle / f"{fall.name}.json"
    if not datei.is_file():
        datei = AUFZEICHNUNGEN.parent / rolle / f"{fall.name}.json"
    erwartet = json.loads(datei.read_text(encoding="utf-8"))
    a = sitzungen[rolle].get(fall.aktion, BAUM if fall.mit_baum else None, fall.params)
    assert a.status == erwartet["status"]
    assert a.ist_json == erwartet["json"], f"Content-Type {a.content_type!r}"
    if not a.ist_json:
        return
    ist = normalisieren(a.json, basis)
    soll = erwartet["antwort"]
    if (variante.name, rolle, fall.name) in RELATIONSHIP_OFFEN:
        r_ist, r_soll = ist.pop("relationship", None), soll.pop("relationship", None)
        assert ist == soll                      # alles außer der Bezeichnung muss stimmen
        if r_ist == r_soll:
            pytest.fail("relationship stimmt jetzt – Eintrag aus RELATIONSHIP_OFFEN entfernen")
        pytest.xfail(f"relationship: {r_ist!r} statt {r_soll!r} (Fähigkeit relationship, später)")
    assert ist == soll
