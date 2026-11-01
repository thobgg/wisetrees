"""Schreibfälle der Vertragstests (docs/PLAN-M2.md): Abläufe aus Schreiben und Lesen mit verschiedenen Rollen.

Vor jedem Ablauf steht der Baum auf dem Ausgangsstand (Falkenrath 1.7.1). Eine factId ist je Server verschieden;
im Rumpf steht darum ein Platzhalter "<fakt:TAG:n>" – der n-te Fakt dieser Art am Datensatz aus `xref`, so wie ihn
die schreibende Rolle sieht. Er wird vor dem Schreiben bei dem jeweiligen Server nachgeschlagen.

Aufgezeichnet nach aufzeichnungen/schreiben/<ablauf>/<nr>.json.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .faelle import BAUM, Fall
from .normalisieren import normalisieren

PLATZHALTER = re.compile(r"^<fakt:([A-Z_0-9]+):(\d+)>$")


@dataclass(frozen=True)
class Schreiben:
    rolle: str
    aktion: str
    params: dict = field(default_factory=dict)
    rumpf: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Lesen:
    rolle: str
    fall: Fall


@dataclass(frozen=True)
class Ablauf:
    name: str
    zweck: str
    schritte: tuple
    sofort: tuple = ()          # Konten, deren Änderungen sofort gelten („sofort annehmen“)


def _i(xref: str) -> Fall:
    return Fall("Individual", {"xref": xref})


ABLAEUFE: list[Ablauf] = [
    Ablauf("fakt-aendern-sofort", "Verwalter mit sofort annehmen ändert den Beruf; alle sehen es",
           (Schreiben("verwalter", "Fact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>", "value": "Schmied"}),
            Lesen("besucher", _i("I21")), Lesen("verwalter", _i("I21"))),
           sofort=("verwalter",)),
    Ablauf("fakt-neu-sofort", "Neuer Wohnort mit Datum, Ort und Notiz",
           (Schreiben("verwalter", "Fact", {"xref": "I21"},
                      {"tag": "RESI", "date": "1930", "place": "Bienenbüttel, Uelzen, Niedersachsen, Deutschland",
                       "note": "laut Adressbuch"}),
            Lesen("besucher", _i("I21")), Lesen("verwalter", _i("I21"))),
           sofort=("verwalter",)),
    Ablauf("fakt-neuer-ort", "Ort, den es im Baum noch nicht gibt, unter einem vorhandenen Kreis",
           (Schreiben("verwalter", "Fact", {"xref": "I21"},
                      {"tag": "RESI", "place": "Neudorf, Uelzen, Niedersachsen, Deutschland"}),
            Lesen("verwalter", _i("I21")),
            Schreiben("verwalter", "Fact", {"xref": "I22"},
                      {"tag": "RESI", "place": "Neudorf, Uelzen, Niedersachsen, Deutschland"}),
            Lesen("verwalter", _i("I22"))),
           sofort=("verwalter",)),
    Ablauf("fakt-ohne-angaben", "Neuer Tod ohne Datum und Ort, dann Datum dazu",
           (Schreiben("verwalter", "Fact", {"xref": "I130"}, {"tag": "DEAT"}),
            Lesen("verwalter", _i("I130")),
            Schreiben("verwalter", "Fact", {"xref": "I130"}, {"factId": "<fakt:DEAT:0>", "date": "ABT 1900"}),
            Lesen("verwalter", _i("I130"))),
           sofort=("verwalter",)),
    Ablauf("fakt-felder-leeren", "Ort entfernen, Typ und Adresse setzen, Heiratsart",
           (Schreiben("verwalter", "Fact", {"xref": "F8"}, {"factId": "<fakt:MARR:0>", "type": "civil",
                                                          "address": "Kirchstraße 1\n29553 Bienenbüttel"}),
            Lesen("verwalter", Fall("Family", {"xref": "F8"})),
            Schreiben("verwalter", "Fact", {"xref": "F8"}, {"factId": "<fakt:MARR:0>", "place": "", "address": ""}),
            Lesen("verwalter", Fall("Family", {"xref": "F8"}))),
           sofort=("verwalter",)),
    Ablauf("name-aendern-sofort", "Name mit zweitem Vornamen",
           (Schreiben("verwalter", "Fact", {"xref": "I21"},
                      {"factId": "<fakt:NAME:0>", "value": "Heinrich Wilhelm /Falkenrath/"}),
            Lesen("besucher", _i("I21")), Lesen("verwalter", Fall("Individuals", {"q": "Wilhelm"}))),
           sofort=("verwalter",)),
    Ablauf("fakt-offen", "Bearbeiter ohne sofort annehmen: offen, Besucher und Mitglied sehen den alten Stand",
           (Schreiben("bearbeiter", "Fact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>", "value": "Schmied"}),
            Lesen("besucher", _i("I21")), Lesen("mitglied", _i("I21")))),
    Ablauf("fakt-fehler", "Fehlerwege",
           (Schreiben("mitglied", "Fact", {"xref": "I21"}, {"tag": "OCCU", "value": "x"}),
            Schreiben("besucher", "Fact", {"xref": "I21"}, {"tag": "OCCU", "value": "x"}),
            Schreiben("verwalter", "Fact", {"xref": "I99999"}, {"tag": "OCCU", "value": "x"}),
            Schreiben("verwalter", "Fact", {"xref": "I21"}, {"factId": "gibtesnicht", "value": "x"}),
            Schreiben("verwalter", "Fact", {"xref": "I21"}, {"tag": "BIRT", "date": "irgendwann"}),
            Schreiben("verwalter", "Fact", {"xref": "I21"}, {"tag": "FAMS", "value": "@F1@"}),
            Schreiben("verwalter", "Fact", {"xref": "I21"}, {"tag": "OCCU", "value": "@I1@"}),
            Schreiben("verwalter", "Fact", {"xref": "I21"}, {"factId": "<fakt:NAME:0>", "value": "Hein /rich"}),
            Lesen("verwalter", _i("I21"))),
           sofort=("verwalter",)),
]


def _platzhalter(sitzung, aktion_xref: str, rumpf: dict) -> dict:
    """Platzhalter "<fakt:TAG:n>" durch die factId ersetzen, wie die schreibende Rolle sie sieht."""
    aus = {}
    for k, v in rumpf.items():
        m = PLATZHALTER.match(v) if isinstance(v, str) else None
        if m:
            art = "Family" if aktion_xref.startswith("F") else "Individual"
            fakten = sitzung.get(art, BAUM, {"xref": aktion_xref}).json.get("facts", [])
            passende = [f for f in fakten if f.get("tag") == m.group(1)]
            v = passende[int(m.group(2))]["id"] if int(m.group(2)) < len(passende) else "fehlt"
        aus[k] = v
    return aus


def ausfuehren(sitzungen: dict, ablauf: Ablauf, basis: str) -> list[dict]:
    """Ablauf gegen einen Server; je Schritt ein Eintrag wie in den Aufzeichnungen."""
    eintraege = []
    for nr, s in enumerate(ablauf.schritte, 1):
        if isinstance(s, Schreiben):
            sitzung = sitzungen[s.rolle]
            rumpf = _platzhalter(sitzungen["verwalter"], s.params.get("xref", ""), s.rumpf)
            a = sitzung.post(s.aktion, BAUM, s.params, rumpf)
            eintrag = {"nr": nr, "art": "schreiben", "rolle": s.rolle, "aktion": s.aktion, "params": s.params,
                       "rumpf": s.rumpf}
        else:
            a = sitzungen[s.rolle].get(s.fall.aktion, BAUM if s.fall.mit_baum else None, s.fall.params)
            eintrag = {"nr": nr, "art": "lesen", "rolle": s.rolle, "fall": s.fall.name}
        eintrag.update(status=a.status, json=a.ist_json, antwort=normalisieren(a.json, basis) if a.ist_json else None)
        eintraege.append(eintrag)
    return eintraege
