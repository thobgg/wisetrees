"""Schreibfälle gegen wisetrees (vertrag/schreibfaelle.py, docs/PLAN-M2.md).

Braucht WT_VERTRAG_BAUMDATEI (python -m vertrag.wisetrees setzt sie). Vor jedem Ablauf wird die Baumdatei auf den
Ausgangsstand zurückgesetzt; „sofort annehmen“ wird je Ablauf in der Kontendatei gesetzt. Gegen die Referenz
entfallen diese Tests – die Aufzeichnungen stammen von ihr.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from .faelle import BAUM, ROLLEN
from .schreibfaelle import ABLAEUFE, ausfuehren

AUFZEICHNUNGEN = Path(__file__).with_name("aufzeichnungen") / "schreiben"


@pytest.fixture(scope="module")
def baumdatei():
    p = os.environ.get("WT_VERTRAG_BAUMDATEI")
    if not p:
        pytest.skip("WT_VERTRAG_BAUMDATEI nicht gesetzt (nur gegen wisetrees)")
    pfad = Path(p)
    ausgang = pfad.with_name(pfad.name + ".ausgang")
    shutil.copy2(pfad, ausgang)
    yield pfad
    _zuruecksetzen(pfad, ausgang)
    ausgang.unlink()


def _zuruecksetzen(pfad: Path, ausgang: Path) -> None:
    for rest in (pfad.with_name(pfad.name + "-wal"), pfad.with_name(pfad.name + "-shm")):
        rest.unlink(missing_ok=True)
    shutil.copy(ausgang, pfad)


def _sofort(pfad: Path, konten: tuple) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from core.konten import KontenDB, KontoBaum

    db = KontenDB(pfad.parent.parent / "konten.sqlite")
    try:
        for konto in ROLLEN.values():
            if konto:
                db.kontobaum_setzen(konto, BAUM, KontoBaum(sofort=konto in konten))
    finally:
        db.schliessen()


@pytest.mark.parametrize("ablauf", ABLAEUFE, ids=[a.name for a in ABLAEUFE])
def test_ablauf_wie_aufgezeichnet(ablauf, baumdatei, sitzungen, basis):
    _zuruecksetzen(baumdatei, baumdatei.with_name(baumdatei.name + ".ausgang"))
    _sofort(baumdatei, ablauf.sofort)
    try:
        ist = ausfuehren(sitzungen, ablauf, basis)
    finally:
        _sofort(baumdatei, ())
    for e in ist:
        soll = json.loads((AUFZEICHNUNGEN / ablauf.name / f"{e['nr']:02d}.json").read_text(encoding="utf-8"))
        schritt = f"Schritt {e['nr']} ({e['art']} {e['rolle']} {e.get('aktion') or e.get('fall')})"
        assert (e["status"], e["json"]) == (soll["status"], soll["json"]), schritt
        assert e["antwort"] == soll["antwort"], schritt
