"""Baumdatei als GEDCOM 5.5.1 mit GEDCOM-L ausgeben (KONZEPT.md 6, E24–E26).

Spiegelbild des Imports (import551.py): Was der Import in Spalten übernimmt, schreibt der Export an dieselbe Stelle
zurück; GEDCOM-Reste (E9) kommen an die Struktur, unter der sie standen. Ziel ist ein Rundlauf ohne Verlust:
Import → Export → Import ergibt denselben Modellauszug. Ein zeilengleicher Export der Ausgangsdatei ist kein Ziel,
wohl aber ein fester Punkt: Export → Import → Export ergibt dieselben Bytes.

Was sich in 5.5.1 nicht verlustfrei schreiben lässt (z. B. ein Ereignis mit mehreren Hauptbeteiligten, E26), steht
im Exportbericht.
"""

from __future__ import annotations

import datetime
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, select

from baum.schema import TRAEGER
from baum.schema import tabelle as T

from .lesen import lesen

ZEILE_MAX = 255          # Zeichen je Zeile (5.5.1); längere Werte werden mit CONC fortgesetzt
VERSION = (Path(__file__).resolve().parent.parent / "version.txt").read_text().strip()

# Kopfzeilen der eingelesenen Datei, die der Export selbst schreibt
KOPF_EIGEN = {"SOUR", "DEST", "DATE", "GEDC", "CHAR", "FILE"}

# Rollencode → RELA-Text, wenn die Beteiligung keinen eigenen Text hat (rolle_aus_rela ergibt wieder den Code)
RELA_TEXT = {"GODP": "godparent", "WITN": "witness", "CLERGY": "clergy", "OFFICIATOR": "officiator",
             "FATH": "father", "MOTH": "mother", "NGHBR": "neighbor", "FRIEND": "friend",
             "X_INFORMANT": "informant"}
PEDI_TEXT = {"adopted": "adopted", "foster": "foster", "sealing": "sealing", "unknown": "other"}
REL_TEXT = {"birth": "natural", "adopted": "adopted", "foster": "foster", "step": "step", "unknown": "unknown"}


@dataclass
class Exportbericht:
    zeilen: int = 0
    datensaetze: dict = field(default_factory=dict)
    geteilte_ereignisse: list = field(default_factory=list)     # E26
    nicht_verlustfrei: list = field(default_factory=list)


class E:
    """Eine Struktur der Ausgabe: Tag, Wert, Kennung, Kinder; oder ein Rest als fertiger GEDCOM-Text."""

    __slots__ = ("tag", "wert", "xref", "kinder", "roh")

    def __init__(self, tag: str, wert: str | None = None, xref: str | None = None, roh: str | None = None):
        self.tag, self.wert, self.xref, self.kinder, self.roh = tag, wert, xref, [], roh

    def neu(self, tag: str, wert=None) -> E:
        k = E(tag, None if wert is None else str(wert))
        self.kinder.append(k)
        return k

    def falls(self, tag: str, wert) -> E | None:
        """Kind nur, wenn es einen Wert gibt."""
        return None if wert is None or wert == "" else self.neu(tag, wert)

    def bezeichnung(self) -> str:
        return f"{self.tag} {self.wert}" if self.wert else self.tag

    def pfad(self, under: str) -> E:
        """Die Struktur, unter der ein Rest stand („PLAC“, „FAMC @F1@“, „FILE a.jpg:FORM“); fehlt sie, wird sie
        angelegt."""
        if not under:
            return self
        for k in self.kinder:
            if k.roh is not None:
                continue
            for b in dict.fromkeys((k.bezeichnung(), k.tag)):
                if under == b:
                    return k
                if under.startswith(b + ":"):
                    return k.pfad(under[len(b) + 1:])
        kopf, _, rest = under.partition(":")
        tag, _, wert = kopf.partition(" ")
        return self.neu(tag, wert or None).pfad(rest)


def _wert_zeilen(level: int, kopf: str, wert: str | None) -> list[str]:
    """Kopfzeile mit Wert; Zeilenumbrüche als CONT, lange Zeilen mit CONC (nicht an Leerzeichen getrennt)."""
    if wert is None:
        return [kopf]
    if wert.startswith("@") and not re.fullmatch(r"@[^@#][^@]*@", wert):
        wert = "@" + wert
    aus = []
    fort = f"{level + 1} CONC "
    for i, teil in enumerate(wert.split("\n")):
        vorn = kopf if i == 0 else f"{level + 1} CONT"
        while True:
            platz = max(ZEILE_MAX - len(vorn) - 1, 20)
            if len(teil) <= platz:
                aus.append(vorn + (f" {teil}" if teil else ""))
                break
            schnitt = platz
            while schnitt > 1 and (teil[schnitt - 1] == " " or teil[schnitt] == " "):
                schnitt -= 1
            if schnitt <= 1:
                schnitt = platz
            aus.append(f"{vorn} {teil[:schnitt]}")
            teil = teil[schnitt:]
            vorn = fort.rstrip()
    return aus


def _rest_zeilen(level: int, roh: str) -> list[str]:
    """Rest mit verschobenen Stufen; überlange Zeilen bekommen CONC."""
    zeilen = roh.split("\n")
    m = re.match(r"^(\d+) ", zeilen[0])
    if not m:
        return zeilen
    versatz = level - int(m.group(1))
    aus = []
    for z in zeilen:
        m = re.match(r"^(\d+) ((?:@[^@ ]+@ )?[A-Za-z0-9_]+)(?: (.*))?$", z)
        if not m:
            aus.append(z)
            continue
        lv = int(m.group(1)) + versatz
        aus += _wert_zeilen(lv, f"{lv} {m.group(2)}", m.group(3))
    return aus


def _zeilen(e: E, level: int) -> list[str]:
    if e.roh is not None:
        return _rest_zeilen(level, e.roh)
    kopf = f"{level} " + (f"@{e.xref}@ " if e.xref else "") + e.tag
    aus = _wert_zeilen(level, kopf, e.wert)
    for k in e.kinder:
        aus += _zeilen(k, level + 1)
    return aus


def _grad(zahl: float, plus: str, minus: str) -> str:
    text = repr(abs(zahl))
    if "e" in text:
        text = f"{abs(zahl):.15f}".rstrip("0").rstrip(".")
    return (minus if zahl < 0 else plus) + text


class Exporter:
    def __init__(self, con: Connection, heute: datetime.datetime | None = None):
        self.con = con
        self.heute = heute or datetime.datetime.now()
        self.b = Exportbericht()
        self.z: dict[str, dict[int, dict]] = {}
        for t in ("person", "name", "family", "family_member", "parentage", "place", "place_name", "place_type",
                  "place_link", "place_attribute", "event", "event_role", "event_place_detail", "person_association",
                  "repository", "source", "source_coverage", "source_repository", "note", "media", "media_file",
                  "task", "citation", "note_link", "media_link", "gedcom_rest"):
            self.z[t] = {r["id"]: dict(r) for r in con.execute(select(T(t)).order_by(T(t).c.id)).mappings()}
        self.meta = dict(con.execute(select(T("meta").c.key, T("meta").c.value)).all())
        self.an: dict[str, dict] = {}
        for t, typen in TRAEGER.items():
            nach = defaultdict(list)
            for r in self._sortiert(t):
                for typ in typen:
                    if typ == "tree":
                        if r.get("on_tree"):
                            nach[("tree", None)].append(r)
                    elif r.get(f"{typ}_id") is not None:
                        nach[(typ, r[f"{typ}_id"])].append(r)
            self.an[t] = nach
        self.nach = {}
        for t, spalte in (("name", "person_id"), ("place_name", "place_id"), ("place_type", "place_id"),
                          ("place_link", "place_id"), ("place_attribute", "place_id"), ("source_coverage", "source_id"),
                          ("source_repository", "source_id"), ("media_file", "media_id"),
                          ("person_association", "person_id"), ("event_place_detail", "event_id"),
                          ("parentage", "family_id"), ("event_role", "event_id")):
            g = defaultdict(list)
            for r in self._sortiert(t):
                g[r[spalte]].append(r)
            self.nach[(t, spalte)] = g
        self.haupt = defaultdict(list)
        for r in sorted(self.z["event_role"].values(), key=lambda r: (r["fact_sort"] or 0, r["id"])):
            if r["role"] == "PRINCIPAL":
                for typ in ("person", "family", "place"):
                    if r[f"{typ}_id"] is not None:
                        self.haupt[(typ, r[f"{typ}_id"])].append(r)
        self.mitglied_person = defaultdict(list)
        self.mitglied_familie = defaultdict(list)
        for r in sorted(self.z["family_member"].values(), key=lambda r: (r["person_sort"], r["id"])):
            self.mitglied_person[r["person_id"]].append(r)
        for r in sorted(self.z["family_member"].values(), key=lambda r: (r["sort"], r["id"])):
            self.mitglied_familie[r["family_id"]].append(r)

    def _sortiert(self, t: str) -> list[dict]:
        return sorted(self.z[t].values(), key=lambda r: (r.get("sort", 0), r["id"]))

    def xref(self, t: str, id_: int | None) -> str | None:
        if id_ is None:
            return None
        x = self.z[t][id_]["xref"]
        return f"@{x}@" if x else None

    def verlust(self, text: str) -> None:
        self.b.nicht_verlustfrei.append(text)

    # ── Anhänge an jedem Träger ────────────────────────────────────────────────────────────────────

    def anhaenge(self, e: E, typ: str, id_: int | None, ohne_reste: bool = False) -> None:
        """Notizen, Zitate, Medien, Aufgaben in dieser Reihenfolge; Reste zuletzt an ihrer Stelle."""
        k = (typ, id_)
        for r in self.an["note_link"].get(k, []):
            self.notiz(e, r)
        for r in self.an["citation"].get(k, []):
            self.zitat(e, r)
        for r in self.an["media_link"].get(k, []):
            self.medienverweis(e, r)
        for r in self.an["task"].get(k, []):
            self.aufgabe(e, r)
        if not ohne_reste:
            self.reste(e, typ, id_)

    def reste(self, e: E, typ: str, id_: int | None) -> None:
        for r in self.an["gedcom_rest"].get((typ, id_), []):
            e.pfad(r["under"] or "").kinder.append(E("", roh=r["gedcom"]))

    def notiz(self, e: E, link: dict) -> None:
        n = self.z["note"][link["note_id"]]
        if n["xref"]:
            e.neu("NOTE", f"@{n['xref']}@")
            return
        k = e.neu("NOTE", n["text"])
        if n["resn"]:
            self.verlust(f"Sperrvermerk an eingebetteter Notiz {n['id']}")
        self.reste(k, "note", n["id"])

    def zitat(self, e: E, z: dict) -> None:
        k = e.neu("SOUR", self.xref("source", z["source_id"]) if z["source_id"] else z["source_text"])
        k.falls("PAGE", z["page"])
        if z["event_type"] is not None or z["event_role"] is not None:
            ev = k.neu("EVEN", z["event_type"])
            ev.falls("ROLE", z["event_role"])
        if z["data_text"] is not None or z["data_date_text"] is not None:
            d = k.neu("DATA")
            d.falls("DATE", z["data_date_text"])
            d.falls("TEXT", z["data_text"])
        k.falls("QUAY", z["quality"])
        self.anhaenge(k, "citation", z["id"])

    def medienverweis(self, e: E, link: dict) -> None:
        m = self.z["media"][link["media_id"]]
        if m["xref"]:
            k = e.neu("OBJE", f"@{m['xref']}@")
            k.falls("TITL", link["title"])
        else:
            k = e.neu("OBJE")
            self.dateien(k, m)
            k.falls("TITL", m["title"])
        if link["is_primary"]:
            k.neu("_PRIM", "Y")
        if any(link[f"crop_{s}"] is not None for s in ("top", "left", "height", "width")):
            c = k.neu("CROP")
            for s in ("top", "left", "height", "width"):
                c.falls(s.upper(), link[f"crop_{s}"])
        # Reste der Verknüpfung stehen am Träger unter „OBJE …“ und kommen mit dessen Resten

    def dateien(self, e: E, m: dict) -> None:
        for f in self.nach[("media_file", "media_id")].get(m["id"], []):
            d = e.neu("FILE", f["path"])
            if f["format"] is not None or f["media_type"] is not None:
                fo = d.neu("FORM", f["format"])
                fo.falls("TYPE", f["media_type"])
            d.falls("TITL", f["title"])

    def aufgabe(self, e: E, t: dict) -> None:
        k = e.neu("_TODO", t["text"])
        for tag, spalte in (("DESC", "description"), ("_CAT", "category"), ("_PRTY", "priority"),
                            ("TYPE", "task_type"), ("STAT", "status"), ("DATA", "solution"),
                            ("_RDATE", "reminder_text"), ("_CDATE", "completed_text"), ("_WT_USER", "user_name")):
            k.falls(tag, t[spalte])
        k.falls("REPO", self.xref("repository", t["repository_id"]))
        k.falls("DATE", t["date_text"])
        self.anhaenge(k, "task", t["id"])

    def gemeinsam(self, e: E, typ: str, r: dict) -> None:
        """_UID, RESN, CHAN an Datensätzen."""
        e.falls("_UID", r.get("uid"))
        e.falls("RESN", r.get("resn"))
        if r.get("changed_at"):
            datum, zeit = r["changed_at"], None
            m = re.match(r"^(.*?)\s+(\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)$", datum)
            if m:
                datum, zeit = m.group(1), m.group(2)
            d = e.neu("CHAN").neu("DATE", datum)
            d.falls("TIME", zeit)

    # ── Ereignisse ─────────────────────────────────────────────────────────────────────────────────

    def ereignis(self, e: E, haupt: dict, traeger: str) -> None:
        ev = self.z["event"][haupt["event_id"]]
        rollen = self.nach[("event_role", "event_id")].get(ev["id"], [])
        hauptbeteiligte = [r for r in rollen if r["role"] == "PRINCIPAL"]
        if len(hauptbeteiligte) > 1 and haupt is hauptbeteiligte[0]:
            self.b.geteilte_ereignisse.append(f"{traeger}: {ev['type']} (Ereignis {ev['id']}, "
                                              f"{len(hauptbeteiligte)} Hauptbeteiligte)")
        if ev["type"] == "MARR" and ev["negated"] and haupt["family_id"] is not None:
            k = e.neu("_STAT", "NOT MARRIED")
        else:
            if ev["negated"]:
                self.verlust(f"{traeger}: „hat nicht stattgefunden“ bei {ev['type']} gibt es in 5.5.1 nicht")
            k = e.neu(ev["type"], ev["value"])
        k.falls("TYPE", ev["subtype"])
        k.falls("DATE", ev["date_text"])
        self.plac(k, ev)
        k.falls("ADDR", ev["address"])
        k.falls("CAUS", ev["cause"])
        k.falls("AGNC", ev["agency"])
        k.falls("AGE", haupt["age"])
        k.falls("RESN", ev["resn"])
        if ev["description"]:
            self.verlust(f"{traeger}: Beschreibung an {ev['type']} hat in 5.5.1 keinen Platz")
        for spalte in ("occupation", "residence", "remark"):
            if haupt[spalte]:
                self.verlust(f"{traeger}: {spalte} an der Beteiligung hat in 5.5.1 keinen Platz")
        if ev["type"] == "ADOP" and haupt["person_id"] is not None:
            self.adoption(k, haupt["person_id"])
        for r in rollen:
            if r["role"] != "PRINCIPAL":
                self.beteiligung(k, r, traeger)
        self.anhaenge(k, "event", ev["id"], ohne_reste=True)
        if any(self.an[t].get(("event_role", haupt["id"])) for t in ("note_link", "citation", "gedcom_rest")):
            self.verlust(f"{traeger}: Anhänge an der Hauptbeteiligung von {ev['type']} stehen am Ereignis")
            self.anhaenge(k, "event_role", haupt["id"])
        self.reste(k, "event", ev["id"])

    def plac(self, k: E, ev: dict) -> None:
        details = self.nach[("event_place_detail", "event_id")].get(ev["id"], [])
        if ev["place_text"] is None and not details:
            return
        p = k.neu("PLAC", ev["place_text"])
        ort = self.z["place"].get(ev["place_id"]) if ev["place_id"] else None
        if ort and ort["xref"] and self.mit_loc.get(ev["id"], True):
            p.neu("_LOC", f"@{ort['xref']}@")
        for d in details:
            if ort is None:
                break
            if d["kind"] == "map" and ort["lat"] is not None:
                m = p.neu("MAP")
                m.neu("LATI", _grad(ort["lat"], "N", "S"))
                m.neu("LONG", _grad(ort["lng"], "E", "W"))
            elif d["kind"] == "gov":
                p.falls("_GOV", ort["gov_id"])
            elif d["kind"] == "maidenhead":
                p.falls("_MAIDENHEAD", ort["maidenhead"])
            elif d["kind"] == "postal":
                a = self.z["place_attribute"][d["place_attribute_id"]]
                pk = p.neu("_POST", a["value"])
                pk.falls("DATE", a["date_text"])

    def adoption(self, k: E, kind: int) -> None:
        """ADOP mit FAMC und ADOP HUSB/WIFE/BOTH aus der Abstammung je Elternteil (Spiegel des Imports)."""
        for m in self.mitglied_person.get(kind, []):
            if m["role"] != "child":
                continue
            plaetze = self.plaetze(m["family_id"])
            arten = {plaetze.get(a["parent_id"]): a["kind"] for a in self.nach[("parentage", "family_id")]
                     .get(m["family_id"], []) if a["child_id"] == kind}
            adoptiert = {p for p, art in arten.items() if art == "adopted" and p in (1, 2)}
            if not adoptiert:
                continue
            f = k.neu("FAMC", self.xref("family", m["family_id"]))
            f.neu("ADOP", "BOTH" if adoptiert == {1, 2} else {1: "HUSB", 2: "WIFE"}[next(iter(adoptiert))])

    def beteiligung(self, k: E, r: dict, traeger: str) -> None:
        if r["person_id"] is not None:
            b = k.neu("_ASSO", self.xref("person", r["person_id"]))
            b.falls("RELA", r["rela"] or RELA_TEXT.get(r["role"]))
            if not r["rela"] and r["role"] not in RELA_TEXT:
                self.verlust(f"{traeger}: Rolle {r['role']} ohne Text lässt sich in 5.5.1 nicht ausdrücken")
        elif r["free_name"] is not None and r["role"] in ("GODP", "WITN"):
            text = r["free_text"] or ", ".join(x for x in (r["free_name"], r["free_addition"]) if x)
            b = k.neu("_GODP" if r["role"] == "GODP" else "_WITN", text)
        else:
            self.verlust(f"{traeger}: Beteiligte(r) {r['free_name'] or r['family_id'] or r['place_id']} "
                         f"als {r['role']} lässt sich in 5.5.1 nicht ausdrücken")
            return
        for spalte in ("age", "occupation", "residence", "remark", "resn"):
            if r[spalte]:
                self.verlust(f"{traeger}: {spalte} an Beteiligung {r['role']} hat in 5.5.1 keinen Platz")
        self.anhaenge(b, "event_role", r["id"])

    def fakten(self, e: E, typ: str, id_: int, traeger: str) -> None:
        for r in self.haupt.get((typ, id_), []):
            self.ereignis(e, r, traeger)

    # ── Datensätze ─────────────────────────────────────────────────────────────────────────────────

    def plaetze(self, fid: int) -> dict[int, int]:
        """Person → Platz in der Familie (1 = HUSB, 2 = WIFE, 3+ nur FAMS)."""
        return {m["person_id"]: m["sort"] for m in self.mitglied_familie.get(fid, []) if m["role"] == "partner"}

    def person(self, p: dict) -> E:
        x = f"@{p['xref']}@"
        e = E("INDI", xref=p["xref"])
        for n in self.nach[("name", "person_id")].get(p["id"], []):
            k = e.neu("NAME", n["value"])
            k.falls("TYPE", n["type_text"])
            for tag, spalte in (("NPFX", "name_prefix"), ("GIVN", "given"), ("NICK", "nickname"),
                                ("_RUFNAME", "rufname"), ("SPFX", "surname_prefix"), ("SURN", "surname"),
                                ("NSFX", "name_suffix")):
                k.falls(tag, n[spalte])
            if n["resn"]:
                self.verlust(f"{x}: Sperrvermerk am Namen hat in 5.5.1 keinen Platz")
            self.anhaenge(k, "name", n["id"])
        if p["sex"] != "U":
            e.neu("SEX", p["sex"])
        self.fakten(e, "person", p["id"], x)
        for m in self.mitglied_person.get(p["id"], []):
            if m["role"] == "child":
                f = e.neu("FAMC", self.xref("family", m["family_id"]))
                arten = [a for a in self.nach[("parentage", "family_id")].get(m["family_id"], [])
                         if a["child_id"] == p["id"]]
                kinds = {a["kind"] for a in arten}
                if len(kinds) == 1 and next(iter(kinds)) in PEDI_TEXT:
                    f.neu("PEDI", PEDI_TEXT[next(iter(kinds))])
                status = {a["status"] for a in arten}
                if len(status) == 1:
                    f.falls("STAT", next(iter(status)))
            else:
                e.neu("FAMS", self.xref("family", m["family_id"]))
        for a in self.nach[("person_association", "person_id")].get(p["id"], []):
            k = e.neu("ASSO", self.xref("person", a["other_person_id"]))
            k.falls("RELA", a["relation"])
            self.anhaenge(k, "person_association", a["id"])
        self.gemeinsam(e, "person", p)
        self.anhaenge(e, "person", p["id"])
        return e

    def familie(self, f: dict) -> E:
        x = f"@{f['xref']}@"
        e = E("FAM", xref=f["xref"])
        plaetze = self.plaetze(f["id"])
        for pid, platz in sorted(plaetze.items(), key=lambda i: i[1]):
            if platz in (1, 2):
                e.neu("HUSB" if platz == 1 else "WIFE", self.xref("person", pid))
        abst = defaultdict(dict)
        for a in self.nach[("parentage", "family_id")].get(f["id"], []):
            abst[a["child_id"]][plaetze.get(a["parent_id"])] = a["kind"]
        for m in self.mitglied_familie.get(f["id"], []):
            if m["role"] != "child":
                continue
            k = e.neu("CHIL", self.xref("person", m["person_id"]))
            arten = abst.get(m["person_id"], {})
            if len(set(arten.values())) > 1:
                for platz, tag in ((1, "_FREL"), (2, "_MREL")):
                    if platz in arten:
                        if arten[platz] in REL_TEXT:
                            k.neu(tag, REL_TEXT[arten[platz]])
                        else:
                            self.verlust(f"{x}: Abstammung {arten[platz]} je Elternteil gibt es in 5.5.1 nicht")
                if any(p not in (1, 2) and art != arten.get(1, art) for p, art in arten.items()):
                    self.verlust(f"{x}: Abstammung zu einem dritten Partner lässt sich in 5.5.1 nicht ausdrücken")
        self.fakten(e, "family", f["id"], x)
        self.gemeinsam(e, "family", f)
        self.anhaenge(e, "family", f["id"])
        return e

    def ort(self, p: dict) -> E:
        e = E("_LOC", xref=p["xref"])
        for n in self.nach[("place_name", "place_id")].get(p["id"], []):
            k = e.neu("NAME", n["name"])
            k.falls("DATE", n["date_text"])
            k.falls("LANG", n["lang"])
            k.falls("ABBR", n["abbr"])
        for t in self.nach[("place_type", "place_id")].get(p["id"], []):
            k = e.neu("TYPE", t["type_text"])
            k.falls("DATE", t["date_text"])
            k.falls("_GOVTYPE", t["gov_type"])
        for link in self.nach[("place_link", "place_id")].get(p["id"], []):
            eltern = self.z["place"][link["parent_id"]]
            if not eltern["xref"]:
                continue  # entsteht beim Import wieder aus dem Ortstext der Ereignisse
            k = e.neu("_LOC", f"@{eltern['xref']}@")
            k.falls("TYPE", link["kind"])
            k.falls("DATE", link["date_text"])
        if p["lat"] is not None:
            m = e.neu("MAP")
            m.neu("LATI", _grad(p["lat"], "N", "S"))
            m.neu("LONG", _grad(p["lng"], "E", "W"))
        e.falls("_GOV", p["gov_id"])
        e.falls("_MAIDENHEAD", p["maidenhead"])
        tags = {"postal": "_POST", "aidn": "_AIDN", "demographics": "_DMGD", "state": "_STAE", "country": "_CTRY",
                "religion": "RELI"}
        for a in self.nach[("place_attribute", "place_id")].get(p["id"], []):
            k = e.neu(tags[a["kind"]], a["value"])
            k.falls("TYPE", a["subtype"])
            k.falls("DATE", a["date_text"])
        self.fakten(e, "place", p["id"], f"@{p['xref']}@")
        self.gemeinsam(e, "place", p)
        self.anhaenge(e, "place", p["id"])
        return e

    def quelle(self, s: dict) -> E:
        e = E("SOUR", xref=s["xref"])
        for tag, spalte in (("AUTH", "author"), ("TITL", "title"), ("ABBR", "abbr"), ("PUBL", "publication")):
            e.falls(tag, s[spalte])
        abdeckung = self.nach[("source_coverage", "source_id")].get(s["id"], [])
        if abdeckung or s["agency"]:
            d = e.neu("DATA")
            for c in abdeckung:
                k = d.neu("EVEN", c["events"])
                k.falls("DATE", c["date_text"])
                k.falls("PLAC", c["place_text"])
            d.falls("AGNC", s["agency"])
        e.falls("TEXT", s["text"])
        letzte = None
        for r in self.nach[("source_repository", "source_id")].get(s["id"], []):
            if r["call_number"] is None or letzte is None or letzte[0] != r["repository_id"]:
                k = e.neu("REPO", self.xref("repository", r["repository_id"]))
                letzte = (r["repository_id"], k) if r["call_number"] is not None else None
            else:
                k = letzte[1]
            if r["call_number"] is not None:
                c = k.neu("CALN", r["call_number"])
                c.falls("MEDI", r["medium"])
            elif r["medium"]:
                self.verlust(f"@{s['xref']}@: Medium ohne Signatur")
        self.gemeinsam(e, "source", s)
        self.anhaenge(e, "source", s["id"])
        return e

    def archiv(self, r: dict) -> E:
        e = E("REPO", xref=r["xref"])
        e.falls("NAME", r["name"])
        if any(r[s] is not None for s in ("address", "adr1", "city", "postal_code", "country", "address_name")):
            a = e.neu("ADDR", r["address"])
            for tag, spalte in (("_NAME", "address_name"), ("ADR1", "adr1"), ("CITY", "city"),
                                ("POST", "postal_code"), ("CTRY", "country")):
                a.falls(tag, r[spalte])
        for tag, spalte in (("PHON", "phone"), ("EMAIL", "email"), ("WWW", "www")):
            e.falls(tag, r[spalte])
        self.gemeinsam(e, "repository", r)
        self.anhaenge(e, "repository", r["id"])
        return e

    def notiz_datensatz(self, n: dict) -> E:
        e = E("NOTE", n["text"], xref=n["xref"])
        if n["resn"]:
            self.verlust(f"@{n['xref']}@: Sperrvermerk an Notiz")
        self.reste(e, "note", n["id"])
        return e

    def medium(self, m: dict) -> E:
        e = E("OBJE", xref=m["xref"])
        titel = [f["title"] for f in self.nach[("media_file", "media_id")].get(m["id"], []) if f["title"] is not None]
        if not titel or m["title"] != titel[0]:   # sonst leitet der Import den Titel aus FILE:TITL ab
            e.falls("TITL", m["title"])
        self.dateien(e, m)
        self.gemeinsam(e, "media", m)
        self.anhaenge(e, "media", m["id"])
        return e

    # ── Ganze Datei ────────────────────────────────────────────────────────────────────────────────

    def kopf(self) -> E:
        e = E("HEAD")
        e.neu("CHAR", "UTF-8")
        s = e.neu("SOUR", "WISE")
        s.neu("NAME", "wisetrees")
        s.neu("VERS", VERSION)
        s.neu("CORP", "Thomas Bugge")
        d = e.neu("DATE", self.heute.strftime("%d %b %Y").upper())
        d.neu("TIME", self.heute.strftime("%H:%M:%S"))
        g = e.neu("GEDC")
        a = g.neu("VERS", "5.5.1").neu("_ADDENDUM", "GEDCOM-L Addendum")
        a.neu("VERS", "R2 (2020-12-01)")
        a.neu("WWW", "https://genealogy.net/GEDCOM")
        g.neu("FORM", "LINEAGE-LINKED")
        alt = self.meta.get("gedcom_head")
        if alt:
            k = lesen((alt + "\n0 TRLR\n").encode()).kopf
            for c in k.kinder:
                if c.tag not in KOPF_EIGEN:
                    e.kinder.append(E("", roh=c.gedcom()))
        return e

    def orte_mit_loc(self) -> None:
        """Ob am PLAC eines Ereignisses der _LOC-Verweis steht.

        Ohne Verweis ordnet der Import den Ort über den Ortstext zu (import551.ort_aus_text) und legt dabei die
        Ortskette an. Gehört ein Ort mit Kennung einem Ort ohne Kennung zu, entsteht diese Zugehörigkeit beim Import
        nur aus dem Ortstext. Dann bleibt der Verweis weg, wenn die Zuordnung über den Text genau diesen Ort ergibt
        und nichts anlegt, was nicht schon im Modell steht. Sonst steht der Verweis da (für andere Programme)."""
        self.mit_loc: dict[int, bool] = {}
        orte = self.z["place"]
        namen = defaultdict(list)
        for n in self._sortiert("place_name"):
            namen[n["place_id"]].append(n["name"])
        loc_namen = defaultdict(list)
        for pid, liste in namen.items():
            if orte[pid]["xref"]:
                for n in liste:
                    if n:
                        loc_namen[n.strip().lower()].append(pid)
        links = {(k["place_id"], k["parent_id"]) for k in self.z["place_link"].values()}
        loc_eltern = defaultdict(list)
        ohne = {}
        for k in self._sortiert("place_link"):
            if orte[k["place_id"]]["xref"] and orte[k["parent_id"]]["xref"]:
                loc_eltern[k["place_id"]].append(k["parent_id"])
        for pid, p in orte.items():
            if not p["xref"] and namen.get(pid):
                eltern = [k["parent_id"] for k in self.nach[("place_link", "place_id")].get(pid, [])] or [None]
                for e in eltern:
                    ohne.setdefault((e, namen[pid][0].lower()), pid)

        def heisst(pid: int, name: str) -> bool:
            return any(name in [n.lower() for n in namen.get(e, [])] for e in loc_eltern.get(pid, []))

        def zuordnung(text: str) -> int | None:
            teile = [t.strip() for t in text.split(",")]
            eltern = None
            for i in range(len(teile) - 1, -1, -1):
                name = teile[i]
                kandidaten = loc_namen.get(name.lower(), [])
                darueber = teile[i + 1].lower() if i + 1 < len(teile) else None
                sicher = [p for p in kandidaten if darueber and heisst(p, darueber)]
                nur_name = [p for p in kandidaten if not loc_eltern.get(p)]
                if len(sicher) == 1:
                    gewaehlt = sicher[0]
                elif not sicher and len(nur_name) == 1 and len(kandidaten) == 1:
                    gewaehlt = nur_name[0]
                else:
                    gewaehlt = ohne.get((eltern, name.lower()))
                    if gewaehlt is None:
                        return None
                if eltern is not None and (gewaehlt, eltern) not in links:
                    return None
                eltern = gewaehlt
            return eltern

        # Orte mit Kennung, die einem Ort ohne Kennung zugehören: Diese Zugehörigkeit entsteht nur aus dem Ortstext
        braucht_text = {k["place_id"] for k in self.z["place_link"].values()
                        if orte[k["place_id"]]["xref"] and not orte[k["parent_id"]]["xref"]}
        for ev in self.z["event"].values():
            p = orte.get(ev["place_id"]) if ev["place_id"] else None
            if p and p["xref"]:
                self.mit_loc[ev["id"]] = not (p["id"] in braucht_text and ev["place_text"]
                                              and zuordnung(ev["place_text"]) == p["id"])

    def ausgeben(self) -> str:
        self.orte_mit_loc()
        saetze = [self.kopf()]
        for t, f in (("person", self.person), ("family", self.familie), ("place", self.ort),
                     ("source", self.quelle), ("repository", self.archiv), ("media", self.medium),
                     ("note", self.notiz_datensatz)):
            n = 0
            for r in self.z[t].values():
                if r["xref"]:
                    saetze.append(f(r))
                    n += 1
            self.b.datensaetze[t] = n
        for r in self.an["gedcom_rest"].get(("tree", None), []):
            saetze.append(E("", roh=r["gedcom"]))
        saetze.append(E("TRLR"))
        zeilen = [z for s in saetze for z in _zeilen(s, 0)]
        self.b.zeilen = len(zeilen)
        return "\n".join(zeilen) + "\n"


def exportieren(con: Connection, heute: datetime.datetime | None = None) -> tuple[bytes, Exportbericht]:
    """Den angenommenen Stand des Baums als GEDCOM 5.5.1 (UTF-8)."""
    ex = Exporter(con, heute)
    return ex.ausgeben().encode("utf-8"), ex.b
