"""Schreibfälle der Vertragstests (docs/PLAN-M2.md): Abläufe aus Schreiben und Lesen mit verschiedenen Rollen.

Vor jedem Ablauf steht der Baum auf dem Ausgangsstand (Falkenrath 1.7.1). Eine factId ist je Server verschieden;
im Rumpf steht darum ein Platzhalter "<fakt:TAG:n>" – der n-te Fakt dieser Art am Datensatz aus `xref`, so wie ihn
die schreibende Rolle sieht. Er wird vor dem Schreiben bei dem jeweiligen Server nachgeschlagen.

Neu angelegte Datensätze werden über Platzhalter angesprochen: "<neu>" ist die xref, "<familie>" die Familie aus der
letzten Schreibantwort, die eine solche Angabe hatte. Ihre Kennungen vergibt jeder Server selbst; in den Antworten
stehen sie darum als "<neu1>", "<neu2>" … in der Reihenfolge, in der sie in Schreibantworten auftauchten.

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
    # Schritt 3: offene Änderungen sehen, annehmen, verwerfen
    Ablauf("offen-sichtbarkeit", "Bearbeiter ändert offen; wer sieht was; Moderator nimmt an",
           (Schreiben("bearbeiter", "Fact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>", "value": "Schmied"}),
            *[Lesen(r, _i("I21")) for r in ("besucher", "mitglied", "bearbeiter", "moderator", "verwalter")],
            Lesen("moderator", Fall("Pending")), Lesen("moderator", Fall("Info", mit_baum=False)),
            Lesen("bearbeiter", Fall("Info", mit_baum=False)),
            Schreiben("moderator", "Accept", {"xref": "I21"}),
            Lesen("besucher", _i("I21")), Lesen("moderator", Fall("Pending")))),
    Ablauf("offen-neu-verwerfen", "Neuer Fakt offen, Bearbeiter sieht ihn, Moderator verwirft",
           (Schreiben("bearbeiter", "Fact", {"xref": "I22"}, {"tag": "RESI", "date": "1950", "place": "Celle"}),
            Lesen("bearbeiter", _i("I22")), Lesen("mitglied", _i("I22")),
            Schreiben("moderator", "Reject", {"xref": "I22"}),
            Lesen("bearbeiter", _i("I22")), Lesen("moderator", Fall("Pending")))),
    Ablauf("offen-zweimal", "Zwei offene Änderungen bauen aufeinander auf; alle des Baums annehmen",
           (Schreiben("bearbeiter", "Fact", {"xref": "I130"}, {"factId": "<fakt:OCCU:0>", "value": "Bauer"}),
            Schreiben("bearbeiter", "Fact", {"xref": "I130"}, {"factId": "<fakt:OCCU:0>", "value": "Vollbauer"}),
            Schreiben("bearbeiter", "Fact", {"xref": "F8"}, {"factId": "<fakt:MARR:0>", "type": "religious"}),
            Lesen("bearbeiter", _i("I130")), Lesen("moderator", Fall("Pending")),
            Schreiben("moderator", "Accept"),
            Lesen("besucher", _i("I130")), Lesen("verwalter", Fall("Family", {"xref": "F8"})),
            Lesen("moderator", Fall("Pending")))),
    Ablauf("offen-name", "Offene Namensänderung: Liste und Suche",
           (Schreiben("bearbeiter", "Fact", {"xref": "I21"}, {"factId": "<fakt:NAME:0>", "value": "Heinz /Falkenrath/"}),
            Lesen("bearbeiter", Fall("Individuals", {"q": "Heinrich"})),
            Lesen("bearbeiter", Fall("Individuals", {"q": "Heinz"})),
            Lesen("besucher", Fall("Individuals", {"q": "Heinrich"})),
            Lesen("bearbeiter", _i("I21")))),
    Ablauf("moderation-rechte", "Wer darf offene Änderungen sehen und freigeben",
           (Schreiben("bearbeiter", "Fact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>", "value": "Schmied"}),
            Lesen("bearbeiter", Fall("Pending")), Lesen("mitglied", Fall("Pending")),
            Schreiben("bearbeiter", "Accept", {"xref": "I21"}), Schreiben("mitglied", "Reject", {"xref": "I21"}),
            Schreiben("moderator", "Accept", {"xref": "I99999"}),
            Lesen("verwalter", Fall("Pending")))),
    # Schritt 4: Fakten löschen
    Ablauf("loeschen-sofort", "Verwalter mit sofort annehmen löscht den Beruf",
           (Schreiben("verwalter", "DeleteFact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>"}),
            Lesen("besucher", _i("I21"))),
           sofort=("verwalter",)),
    Ablauf("loeschen-offen", "Bearbeiter löscht offen; wer sieht was; Moderator nimmt an",
           (Schreiben("bearbeiter", "DeleteFact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>"}),
            Lesen("bearbeiter", _i("I21")), Lesen("mitglied", _i("I21")), Lesen("moderator", Fall("Pending")),
            Schreiben("moderator", "Accept", {"xref": "I21"}),
            Lesen("besucher", _i("I21")))),
    Ablauf("loeschen-taufe-paten", "Taufe mit Paten löschen: Paten verlieren den Eintrag",
           (Schreiben("verwalter", "DeleteFact", {"xref": "I77"}, {"factId": "<fakt:CHR:0>"}),
            Lesen("verwalter", _i("I77")), Lesen("verwalter", _i("I21")), Lesen("besucher", _i("I71"))),
           sofort=("verwalter",)),
    Ablauf("loeschen-taufe-offen", "Taufe mit Paten offen löschen: Sicht des Paten",
           (Schreiben("bearbeiter", "DeleteFact", {"xref": "I77"}, {"factId": "<fakt:CHR:0>"}),
            Lesen("bearbeiter", _i("I21")), Lesen("mitglied", _i("I21")), Lesen("bearbeiter", _i("I77")))),
    Ablauf("loeschen-weitere", "Notiz, Quellenangabe und Verknüpfung am Datensatz löschen",
           (Schreiben("verwalter", "DeleteFact", {"xref": "I111"}, {"factId": "<fakt:NOTE:0>"}),
            Lesen("verwalter", _i("I111")),
            Schreiben("verwalter", "DeleteFact", {"xref": "I271"}, {"factId": "<fakt:SOUR:0>"}),
            Lesen("verwalter", _i("I271")),
            Schreiben("verwalter", "DeleteFact", {"xref": "I58"}, {"factId": "<fakt:ASSO:0>"}),
            Lesen("verwalter", _i("I58"))),
           sofort=("verwalter",)),
    Ablauf("loeschen-name-geschlecht", "Geschlecht und einzigen Namen löschen",
           (Schreiben("verwalter", "DeleteFact", {"xref": "I130"}, {"factId": "<fakt:SEX:0>"}),
            Schreiben("verwalter", "DeleteFact", {"xref": "I130"}, {"factId": "<fakt:NAME:0>"}),
            Lesen("verwalter", _i("I130")), Lesen("verwalter", Fall("Individuals", {"q": "Mohwinkel"}))),
           sofort=("verwalter",)),
    Ablauf("loeschen-familie", "Heirat an der Familie löschen",
           (Schreiben("verwalter", "DeleteFact", {"xref": "F8"}, {"factId": "<fakt:MARR:0>"}),
            Lesen("verwalter", Fall("Family", {"xref": "F8"})), Lesen("verwalter", _i("I21"))),
           sofort=("verwalter",)),
    Ablauf("loeschen-neu-offen", "Offen angelegten Fakt wieder löschen",
           (Schreiben("bearbeiter", "Fact", {"xref": "I22"}, {"tag": "RESI", "place": "Celle"}),
            Schreiben("bearbeiter", "DeleteFact", {"xref": "I22"}, {"factId": "<fakt:RESI:0>"}),
            Lesen("bearbeiter", _i("I22")), Lesen("moderator", Fall("Pending")))),
    Ablauf("loeschen-fehler", "Fehlerwege beim Löschen",
           (Schreiben("mitglied", "DeleteFact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>"}),
            Schreiben("besucher", "DeleteFact", {"xref": "I21"}, {"factId": "<fakt:OCCU:0>"}),
            Schreiben("verwalter", "DeleteFact", {"xref": "I99999"}, {"factId": "E1"}),
            Schreiben("verwalter", "DeleteFact", {"xref": "I21"}, {"factId": "gibtesnicht"}),
            Schreiben("verwalter", "DeleteFact", {"xref": "I21"}, {}),
            Lesen("verwalter", _i("I21"))),
           sofort=("verwalter",)),
    # Schritt 5: Personen anlegen, verknüpfen, lösen, Datensätze löschen
    Ablauf("person-neu-sofort", "Person ohne Verwandte mit Geburt und Tod",
           (Schreiben("verwalter", "AddIndividual", {}, {"given": "Karl", "surname": "Probst", "sex": "M",
                                                         "birthDate": "1901", "birthPlace": "Celle", "dead": True}),
            Lesen("verwalter", _i("<neu>")), Lesen("besucher", Fall("Individuals", {"q": "Probst"}))),
           sofort=("verwalter",)),
    Ablauf("person-kind-offen", "Bearbeiter legt ein Kind offen an; wer sieht was; Moderator nimmt an",
           (Schreiben("bearbeiter", "AddIndividual", {}, {"relation": "child", "relativeTo": "I21", "family": "F8",
                                                          "given": "Marie", "surname": "Falkenrath", "sex": "F",
                                                          "birthDate": "1930"}),
            Lesen("bearbeiter", _i("<neu>")), Lesen("mitglied", _i("<neu>")),
            Lesen("bearbeiter", Fall("Family", {"xref": "F8"})), Lesen("mitglied", Fall("Family", {"xref": "F8"})),
            Lesen("bearbeiter", _i("I21")), Lesen("bearbeiter", Fall("Individuals", {"q": "Marie"})),
            Lesen("moderator", Fall("Pending")),
            Schreiben("moderator", "Accept"),
            Lesen("besucher", Fall("Family", {"xref": "F8"})), Lesen("besucher", _i("<neu>")))),
    Ablauf("person-eltern", "Vater und Mutter zu einer Person ohne Eltern",
           (Schreiben("verwalter", "AddIndividual", {}, {"relation": "father", "relativeTo": "I6", "given": "Jan",
                                                         "surname": "Wolniak"}),
            Lesen("verwalter", Fall("Family", {"xref": "<familie>"})),
            Schreiben("verwalter", "AddIndividual", {}, {"relation": "mother", "relativeTo": "I6", "given": "Ewa",
                                                         "surname": "Nowak", "sex": "M"}),
            Lesen("verwalter", Fall("Family", {"xref": "<familie>"})), Lesen("verwalter", _i("I6")),
            Schreiben("verwalter", "AddIndividual", {}, {"relation": "father", "relativeTo": "I6", "given": "X"})),
           sofort=("verwalter",)),
    Ablauf("person-partner", "Partner mit Heirat anlegen",
           (Schreiben("verwalter", "AddIndividual", {}, {"relation": "spouse", "relativeTo": "I130", "given": "Sophie",
                                                         "surname": "Meyer", "sex": "F", "marriageDate": "1870",
                                                         "marriagePlace": "Celle"}),
            Lesen("verwalter", Fall("Family", {"xref": "<familie>"})), Lesen("verwalter", _i("I130"))),
           sofort=("verwalter",)),
    Ablauf("person-fehler", "Fehlerwege beim Anlegen",
           (Schreiben("mitglied", "AddIndividual", {}, {"given": "X"}),
            Schreiben("verwalter", "AddIndividual", {}, {"relation": "cousin", "given": "X"}),
            Schreiben("verwalter", "AddIndividual", {}, {"given": " ", "surname": ""}),
            Schreiben("verwalter", "AddIndividual", {}, {"given": "X", "birthDate": "irgendwann"}),
            Schreiben("verwalter", "AddIndividual", {}, {"given": "X", "birthPlace": "@P1@"}),
            Schreiben("verwalter", "AddIndividual", {}, {"relation": "child", "relativeTo": "I15", "given": "X"}),
            Schreiben("verwalter", "AddIndividual", {}, {"relation": "child", "relativeTo": "I15", "family": "F1",
                                                         "given": "X"}),
            Schreiben("verwalter", "AddIndividual", {}, {"relation": "child", "relativeTo": "I99999", "given": "X"}),
            Lesen("verwalter", Fall("Individuals", {"q": "X"}))),
           sofort=("verwalter",)),
    Ablauf("verknuepfen", "Zwei Personen als Paar verknüpfen, dann doppelt",
           (Schreiben("verwalter", "Link", {}, {"individual": "I4", "relation": "spouse", "relativeTo": "I91",
                                                "marriageDate": "1950"}),
            Lesen("verwalter", Fall("Family", {"xref": "<familie>"})), Lesen("verwalter", _i("I4")),
            Schreiben("verwalter", "Link", {}, {"individual": "I4", "relation": "spouse", "relativeTo": "I91"}),
            Schreiben("verwalter", "Link", {}, {"individual": "I4", "relation": "child", "relativeTo": "I4"}),
            Schreiben("verwalter", "Link", {}, {"individual": "I4", "relation": "sibling", "relativeTo": "I91"})),
           sofort=("verwalter",)),
    Ablauf("verknuepfen-offen", "Kind offen in eine Familie verknüpfen",
           (Schreiben("bearbeiter", "Link", {}, {"individual": "I7", "relation": "child", "relativeTo": "I21",
                                                 "family": "F8"}),
            Lesen("bearbeiter", Fall("Family", {"xref": "F8"})), Lesen("mitglied", Fall("Family", {"xref": "F8"})),
            Lesen("bearbeiter", _i("I7")), Lesen("moderator", Fall("Pending")))),
    Ablauf("loesen", "Kind aus der Familie lösen, dann noch einmal",
           (Schreiben("verwalter", "Unlink", {}, {"family": "F8", "individual": "I23"}),
            Lesen("verwalter", Fall("Family", {"xref": "F8"})), Lesen("verwalter", _i("I23")),
            Schreiben("verwalter", "Unlink", {}, {"family": "F8", "individual": "I23"}),
            Schreiben("mitglied", "Unlink", {}, {"family": "F8", "individual": "I15"})),
           sofort=("verwalter",)),
    Ablauf("datensatz-loeschen", "Person löschen: Verweise verschwinden",
           (Schreiben("verwalter", "DeleteRecord", {"xref": "I25"}),
            Lesen("verwalter", Fall("Family", {"xref": "F8"})), Lesen("verwalter", _i("I25")),
            Lesen("verwalter", _i("I21")),
            Schreiben("verwalter", "DeleteRecord", {"xref": "I99999"})),
           sofort=("verwalter",)),
    Ablauf("datensatz-loeschen-familie", "Partner ohne Heirat anlegen und wieder löschen: Familie fällt weg",
           (Schreiben("verwalter", "AddIndividual", {}, {"relation": "spouse", "relativeTo": "I130", "given": "Lene",
                                                         "surname": "Busch", "sex": "F"}),
            Schreiben("verwalter", "DeleteRecord", {"xref": "<neu>"}),
            Lesen("verwalter", _i("I130")), Lesen("verwalter", Fall("Family", {"xref": "<familie>"}))),
           sofort=("verwalter",)),
    Ablauf("datensatz-loeschen-offen", "Bearbeiter löscht eine Person offen",
           (Schreiben("bearbeiter", "DeleteRecord", {"xref": "I25"}),
            Lesen("bearbeiter", _i("I25")), Lesen("bearbeiter", Fall("Family", {"xref": "F8"})),
            Lesen("mitglied", Fall("Family", {"xref": "F8"})), Lesen("moderator", Fall("Pending")),
            Schreiben("moderator", "Reject"),
            Lesen("bearbeiter", Fall("Family", {"xref": "F8"})))),
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


def _neue(werte: dict, merk: dict) -> dict:
    return {k: merk.get(v, v) if isinstance(v, str) else v for k, v in werte.items()}


def _kennungen(wert, neue: dict[str, str]):
    """Vom Server vergebene Kennungen durch "<neuN>" ersetzen (auch als Verweis "@…@")."""
    if isinstance(wert, dict):
        return {k: _kennungen(v, neue) for k, v in wert.items()}
    if isinstance(wert, list):
        return [_kennungen(v, neue) for v in wert]
    if isinstance(wert, str):
        if wert in neue:
            return neue[wert]
        if wert.startswith("@") and wert.endswith("@") and wert[1:-1] in neue:
            return f"@{neue[wert[1:-1]]}@"
    return wert


def ausfuehren(sitzungen: dict, ablauf: Ablauf, basis: str) -> list[dict]:
    """Ablauf gegen einen Server; je Schritt ein Eintrag wie in den Aufzeichnungen."""
    eintraege = []
    merk: dict[str, str] = {}
    neue: dict[str, str] = {}
    for nr, s in enumerate(ablauf.schritte, 1):
        if isinstance(s, Schreiben):
            sitzung = sitzungen[s.rolle]
            params = _neue(s.params, merk)
            rumpf = _platzhalter(sitzungen["verwalter"], params.get("xref", ""), _neue(s.rumpf, merk))
            a = sitzung.post(s.aktion, BAUM, params, rumpf)
            if a.ist_json and isinstance(a.json, dict) and a.json.get("ok"):
                if s.aktion == "AddIndividual":
                    merk["<neu>"] = a.json.get("xref") or ""
                    neue.setdefault(merk["<neu>"], f"<neu{len(neue) + 1}>")
                if a.json.get("family"):
                    merk["<familie>"] = a.json["family"]
                    # auch eine vorhandene Familie: harmlos, beide Server ersetzen sie gleich
                    neue.setdefault(a.json["family"], f"<neu{len(neue) + 1}>")
            eintrag = {"nr": nr, "art": "schreiben", "rolle": s.rolle, "aktion": s.aktion, "params": s.params,
                       "rumpf": s.rumpf}
        else:
            a = sitzungen[s.rolle].get(s.fall.aktion, BAUM if s.fall.mit_baum else None, _neue(s.fall.params, merk))
            eintrag = {"nr": nr, "art": "lesen", "rolle": s.rolle, "fall": s.fall.name}
        antwort = normalisieren(_kennungen(a.json, neue), basis) if a.ist_json else None
        eintrag.update(status=a.status, json=a.ist_json, antwort=antwort)
        eintraege.append(eintrag)
    return eintraege
