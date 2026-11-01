"""Unterschiede einer wisetrees-Antwort zur Aufzeichnung, Pfad für Pfad (Werkzeug für die Entwicklung).

    .venv/bin/python -m vertrag.vergleich verwalter "Pedigree__xref=I1" [weitere Fälle …]
"""

from __future__ import annotations

import json
import sys

from .client import Sitzung
from .faelle import BAUM, FAELLE, PASSWORT, ROLLEN
from .normalisieren import normalisieren
from .test_vertrag import AUFZEICHNUNGEN
from .wisetrees import aufsetzen, starten


def unterschiede(a, b, pfad="$", aus=None, grenze=40):
    aus = [] if aus is None else aus
    if len(aus) >= grenze:
        return aus
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(dict.fromkeys([*a, *b])):
            if k not in a:
                aus.append(f"{pfad}.{k}: fehlt bei wisetrees (erwartet {json.dumps(b[k], ensure_ascii=False)[:120]})")
            elif k not in b:
                aus.append(f"{pfad}.{k}: zu viel ({json.dumps(a[k], ensure_ascii=False)[:120]})")
            else:
                unterschiede(a[k], b[k], f"{pfad}.{k}", aus, grenze)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            aus.append(f"{pfad}: {len(a)} Einträge statt {len(b)}")
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            unterschiede(x, y, f"{pfad}[{i}]", aus, grenze)
    elif a != b:
        aus.append(f"{pfad}: {json.dumps(a, ensure_ascii=False)[:120]} statt {json.dumps(b, ensure_ascii=False)[:120]}")
    return aus


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rolle, namen = argv[0], argv[1:]
    p, basis = starten(aufsetzen())
    try:
        s = Sitzung(basis)
        if ROLLEN[rolle]:
            s.anmelden(ROLLEN[rolle], PASSWORT)
        else:
            s.info()
        for fall in FAELLE:
            if namen and fall.name not in namen:
                continue
            erwartet = json.loads((AUFZEICHNUNGEN / rolle / f"{fall.name}.json").read_text(encoding="utf-8"))["antwort"]
            a = s.get(fall.aktion, BAUM if fall.mit_baum else None, fall.params)
            u = unterschiede(normalisieren(a.json, basis), erwartet)
            print(f"== {rolle} {fall.name}: {'gleich' if not u else str(len(u)) + ' Unterschiede'}")
            for z in u:
                print("   ", z)
    finally:
        p.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
