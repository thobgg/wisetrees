"""GEDCOM 5.5.1 als neuen Baum einlesen.

    python werkzeuge/importieren.py NAME datei.ged [--titel "Titel"]

Legt <daten>/baeume/NAME.wise an (Datenordner aus WISETREES_DATEN, Standard /data) und gibt den Importbericht aus.
Bilder gehören nach <daten>/medien/NAME/ (Pfade wie in den FILE-Zeilen der Datei).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import config  # noqa: E402
from gedcom.import551 import importieren  # noqa: E402
from gedcom.lesen import NichtLesbar  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", help="Name des Baums (Buchstaben, Ziffern, - und _)")
    p.add_argument("datei", type=Path)
    p.add_argument("--titel", default="")
    a = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.name):
        sys.exit("Name: nur Buchstaben, Ziffern, - und _")
    ziel = config.laden().baeume / f"{a.name}.wise"
    if ziel.exists():
        sys.exit(f"Den Baum gibt es schon: {ziel}")
    try:
        b = importieren(a.datei.read_bytes(), ziel, a.titel or a.name, a.datei.name)
    except NichtLesbar as e:
        sys.exit(f"Nicht lesbar: {e}")
    print(f"{ziel}: {b.anzahl['person']} Personen, {b.anzahl['family']} Familien, {b.anzahl['source']} Quellen")
    print(f"Zeilen {b.zeilen_gesamt}: übernommen {b.zeilen_uebernommen}, als Rest {b.zeilen_rest}")
    for o in b.orte_unsicher:
        print(f"Unsichere Ortszuordnung: {o['ortstext']} ({o['ereignisse']} Ereignisse) – {o['grund']}")
    for z in b.datum_unverstanden[:20]:
        print(f"Datum nicht verstanden: {z}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
