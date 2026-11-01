"""v1: Fakten eines Datensatzes und die Antworten GET Family und GET Individual.

Reihenfolge der Fakten nach einer festen Tag-Reihenfolge und dem Datumsvergleich: Fakten mit Datum nach Datum, ohne
Datum nach Art, beides ineinander gemischt.
Beschriftungen auf Deutsch, Wortlaut wie in den v1-Aufzeichnungen.
"""

from __future__ import annotations

import re
import sqlite3
from functools import cmp_to_key

from core.konten import ROLLEN

from . import anzeige
from .http import GET_AKTIONEN, Kontext, fehler
from .personen import Bau, _heirat, baum_und_person
from .sicht import BILDFORMATE, sicht_fuer

# Tag-Reihenfolge der Fakten
FAKT_REIHE = ["BIRT", "_HNM", "ALIA", "_AKA", "_AKAN", "ADOP", "_ADPF", "_ADPF", "_BRTM", "CHR", "BAPM", "FCOM", "CONF", "BARM", "BASM", "EDUC", "GRAD", "_DEG", "EMIG", "IMMI", "NATU", "_MILI", "_MILT", "ENGA", "MARB", "MARC", "MARL", "_MARI", "_MBON", "MARR", "_COML", "_STAT", "_SEPR", "DIVF", "MARS", "DIV", "ANUL", "CENS", "OCCU", "RESI", "PROP", "CHRA", "RETI", "FACT", "EVEN", "_NMR", "_NMAR", "NMR", "NCHI", "WILL", "_HOL", "_????_", "DEAT", "_FNRL", "CREM", "BURI", "_INTE", "_YART", "_NLIV", "PROB", "TITL", "COMM", "NATI", "CITN", "CAST", "RELI", "SSN", "IDNO", "TEMP", "SLGC", "BAPL", "CONL", "ENDL", "SLGS", "NO", "ADDR", "PHON", "EMAIL", "_EMAIL", "EMAL", "FAX", "WWW", "URL", "_URL", "_FSFTID", "AFN", "REFN", "_PRMN", "REF", "RIN", "_UID", "OBJE", "NOTE", "SOUR", "CREA", "CHAN", "_TODO"]
_STELLE = {t: i for i, t in enumerate(FAKT_REIHE)}

LABEL = {
    "BIRT": "Geburt", "CHR": "Kindstaufe", "BAPM": "Taufe", "DEAT": "Tod", "BURI": "Bestattung", "CREM": "Einäscherung",
    "OCCU": "Beruf", "RESI": "Wohnsitz", "PROP": "Besitz", "RELI": "Religion", "EDUC": "Ausbildung", "EVEN": "Ereignis",
    "FACT": "Tatsache", "NAME": "Name", "SEX": "Geschlecht", "NOTE": "Notiz", "SOUR": "Quellenangabe",
    "_STAT": "Familienstatus", "MARR": "Heirat", "DIV": "Scheidung", "ENGA": "Verlobung", "MARB": "Aufgebot",
    "MARC": "Ehevertrag", "MARL": "Heiratserlaubnis", "MARS": "Ehevereinbarung", "ANUL": "Annullierung",
    "DIVF": "Scheidungsantrag", "CENS": "Volkszählung", "CONF": "Konfirmation", "FCOM": "Erstkommunion",
    "EMIG": "Auswanderung", "IMMI": "Einwanderung", "NATU": "Einbürgerung", "GRAD": "Bildungsabschluss", "RETI": "Ruhestand",
    "PROB": "Testamentseröffnung", "WILL": "Testament", "ADOP": "Adoption", "BLES": "Segnung", "BARM": "Bar Mitzwa",
    "BASM": "Bat Mitzwa", "CHRA": "Erwachsenentaufe", "ORDN": "Ordination", "NCHI": "Anzahl der Kinder",
    "NMR": "Anzahl der Ehen", "NATI": "Nationalität", "TITL": "Titel", "CAST": "Kaste", "DSCR": "Beschreibung",
    "IDNO": "Kennnummer", "SSN": "Sozialversicherungsnummer", "ASSO": "Beziehung", "RESN": "Einschränkung",
}
# Beschriftung an Familien, wo sie anders lautet als an Personen
LABEL_FAMILIE = {"CENS": "Familienvolkszählung", "RESI": "Familienwohnsitz"}
DETAIL_LABEL = {"CAUS": "Ursache", "AGE": "Alter", "AGNC": "Institution", "ADDR": "Adresse"}
WERT = {"SEX": {"M": "männlich", "F": "weiblich", "U": "unbekannt", "X": "divers"},
        "_STAT": {"UNKNOWN": "Unbekannt", "NOT MARRIED": "unverheiratet", "NEVER MARRIED": "nie verheiratet"}}
MARR_TYP = {"CIVIL": "Standesamtliche Heirat", "RELIGIOUS": "Kirchliche Trauung", "PARTNERS": "Partnerschaft"}
ROLLE_LABEL = {"godparent": {"M": "Pate", "F": "Patin", "U": "Pate"}, "witness": {"M": "Zeuge", "F": "Zeugin", "U": "Zeuge"}}
PATEN = {"godparent", "godfather", "godmother", "pate", "patin", "taufpate", "taufpatin", "gevatter", "gevatterin"}
ZEUGEN = {"witness", "trauzeuge", "trauzeugin", "zeuge", "zeugin"}
MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp",
        "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff", "pdf": "application/pdf"}


def rolle_v1(rela: str | None) -> str:
    r = (rela or "").strip().lower()
    return "godparent" if r in PATEN else "witness" if r in ZEUGEN else "other"


def rolle_label(rela: str | None, rolle: str, sex: str) -> str:
    if rolle in ROLLE_LABEL:
        return ROLLE_LABEL[rolle].get(sex, ROLLE_LABEL[rolle]["U"])
    return rela or ""


# ── Sortierung ──────────────────────────────────────────────────────────────────────────────────────

def _grenzen_vergleich(text: str):
    g = anzeige.datum_grenzen(text)
    if g is None:
        return None
    vorsatz = text.strip().upper().split(" ", 1)[0]
    lo, hi = g
    if vorsatz == "BEF":
        lo = hi = g[0] - 1
    elif vorsatz == "AFT":
        lo = hi = g[1] + 1
    return lo, hi


def _datum_vergleich(a: str, b: str) -> int:
    (amin, amax), (bmin, bmax) = _grenzen_vergleich(a), _grenzen_vergleich(b)
    if amax < bmin:
        return -1
    if amin > bmax and bmax > 0:
        return 1
    if amin < bmin and amax <= bmax:
        return -1
    if amin > bmin and amax >= bmax and bmax > 0:
        return 1
    return 0


def _art_vergleich(a: dict, b: dict) -> int:
    at, bt = (a["tag"] if a["tag"] in _STELLE else "_????_"), (b["tag"] if b["tag"] in _STELLE else "_????_")
    if a["_datum"] and _STELLE["BURI"] < _STELLE[at] < _STELLE["CHAN"]:
        at = "BURI"
    if b["_datum"] and _STELLE["BURI"] < _STELLE[bt] < _STELLE["CHAN"]:
        bt = "BURI"
    if at == bt:
        if a["_datum"] and not b["_datum"]:
            return -1
        if b["_datum"] and not a["_datum"]:
            return 1
        return (a["_reihe"] > b["_reihe"]) - (a["_reihe"] < b["_reihe"])
    return (_STELLE[at] > _STELLE[bt]) - (_STELLE[at] < _STELLE[bt])


def _mit_datum_vergleich(a: dict, b: dict) -> int:
    r = _datum_vergleich(a["_datum"], b["_datum"])
    if r == 0:
        r = _art_vergleich(a, b)
        if r == 0:
            r = (a["_reihe"] > b["_reihe"]) - (a["_reihe"] < b["_reihe"])
    return r


def sortieren(fakten: list[dict]) -> list[dict]:
    for i, f in enumerate(fakten):
        f["_reihe"] = i
    mit = sorted([f for f in fakten if f["_datum"] and _grenzen_vergleich(f["_datum"])], key=cmp_to_key(_mit_datum_vergleich))
    ohne = sorted([f for f in fakten if not (f["_datum"] and _grenzen_vergleich(f["_datum"]))], key=cmp_to_key(_art_vergleich))
    aus, j = [], 0
    for f in mit:
        while j < len(ohne) and _art_vergleich(f, ohne[j]) > 0:
            aus.append(ohne[j])
            j += 1
        aus.append(f)
    return aus + ohne[j:]


# ── Bausteine ──────────────────────────────────────────────────────────────────────────────────────

class Fakten:
    def __init__(self, bau: Bau, con: sqlite3.Connection):
        self.bau, self.s, self.m, self.con = bau, bau.s, bau.m, con
        self.con.row_factory = sqlite3.Row
        self.quellen = {r["id"]: r for r in con.execute("SELECT * FROM source")}

    def q(self, sql, *args):
        return self.con.execute(sql, args).fetchall()

    def zugang_fakt(self, tag: str, resn: str | None) -> str:
        if self.s.fakt_darf(tag, resn, 2):
            return "visitor"
        return "member" if self.s.fakt_darf(tag, resn, 1) else "manager"

    def quelle_darf(self, sid: int, stufe: int | None = None) -> bool:
        r = self.quellen.get(sid)
        return r is not None and self.s.fakt_darf("SOUR", r["resn"], stufe)

    # Notizen ---------------------------------------------------------------------------------------

    def notizen(self, spalte: str, wert: int) -> list[sqlite3.Row]:
        return self.q(f"SELECT n.id, n.xref, n.text, n.resn, l.id AS link FROM note_link l JOIN note n ON n.id = l.note_id "
                      f"WHERE l.{spalte} = ? ORDER BY l.sort", wert)

    def notiz_texte(self, spalte: str, wert: int) -> list[str]:
        return [n["text"] for n in self.notizen(spalte, wert)
                if (n["xref"] is None or self.s.fakt_darf("NOTE", n["resn"])) and n["text"].strip()]

    # Medien ----------------------------------------------------------------------------------------

    def datei_json(self, med_id: int) -> list[dict]:
        med = self.m.medien[med_id]
        aus = []
        for pfad, fmt, typ, titel in med.dateien:
            f = (fmt or pfad.rsplit(".", 1)[-1]).lower()
            bild = f in BILDFORMATE
            adresse = self.bau.bild_url(med)
            aus.append({"xref": med.xref, "title": titel or med.title or "", "mime": MIME.get(f, "application/octet-stream"),
                        "isImage": bild, "thumb": adresse if bild else None, "file": adresse,
                        "url": self.bau.seiten_url("media", med.xref or str(med.id)), "path": pfad, "type": typ or None,
                        "format": fmt or None})
        return aus

    def medium_darf(self, med_id: int) -> bool:
        return self.s.medium_darf(med_id)

    # Zitate ----------------------------------------------------------------------------------------

    def zitat_json(self, z: sqlite3.Row) -> dict | None:
        if z["source_id"] is not None:
            if not self.quelle_darf(z["source_id"]):
                return None
            xref, titel = self.quellen[z["source_id"]]["xref"], self.quellen[z["source_id"]]["title"] or ""
        else:
            xref, titel = "", z["source_text"] or ""
        medien = []
        for r in self.q("SELECT media_id FROM media_link WHERE citation_id = ? ORDER BY sort", z["id"]):
            if self.medium_darf(r[0]):
                medien += self.datei_json(r[0])
        return {"xref": xref, "title": titel, "page": z["page"] or "", "quality": z["quality"],
                "date": anzeige.datum_json(z["data_date_text"], mit_gedcom=True), "text": z["data_text"] or "",
                "notes": self.notiz_texte("citation_id", z["id"]), "media": medien}

    def zitate(self, spalte: str, wert: int) -> list[dict]:
        aus = []
        for z in self.q(f"SELECT * FROM citation WHERE {spalte} = ? ORDER BY sort", wert):
            j = self.zitat_json(z)
            if j is not None:
                aus.append(j)
        return aus

    # Beteiligte --------------------------------------------------------------------------------------

    def verknuepfte(self, event_id: int) -> list[dict]:
        aus = []
        for r in self.q("SELECT * FROM event_role WHERE event_id = ? AND role <> 'PRINCIPAL' AND person_id IS NOT NULL "
                        "ORDER BY sort", event_id):
            pid = r["person_id"]
            if not self.s.name_darf(pid):
                continue
            privat = not self.s.person_darf(pid)
            p = self.m.personen[pid]
            rolle = rolle_v1(r["rela"])
            aus.append({"xref": p.xref, "name": None if privat else self.bau.name(p), "sex": None if privat else p.sex,
                        "rela": r["rela"] or "", "role": rolle, "label": rolle_label(r["rela"], rolle, "U" if privat else p.sex),
                        "private": privat, "access": self.bau.zugang(pid), "level1": False,
                        "notes": self.notiz_texte("event_role_id", r["id"]), "sources": self.zitate("event_role_id", r["id"])})
        return aus

    @staticmethod
    def freie_eintraege(rolle: str, text: str) -> list[dict]:
        rest = re.sub(r"\s+", " ", text or "").strip()
        if not rest:
            return []
        if ";" not in rest:
            return [{"role": rolle, "name": None, "detail": None, "text": rest}]
        aus = []
        for teil in rest.split(";"):
            teil = teil.strip()
            if teil:
                name, _, detail = teil.partition(",")
                aus.append({"role": rolle, "name": name.strip(), "detail": detail.strip() if detail else None, "text": teil})
        return aus

    def notizen_und_freie(self, event_id: int) -> tuple[list, list, list]:
        frei = []
        for r in self.q("SELECT role, free_text FROM event_role WHERE event_id = ? AND free_name IS NOT NULL ORDER BY sort",
                        event_id):
            rolle = "godparent" if r["role"] == "GODP" else "witness" if r["role"] == "WITN" else "other"
            text = r["free_text"] or ""
            frei += self.freie_eintraege(rolle, text if ";" in text else text + ";")
        texte, arten = [], []
        for text in self.notiz_texte("event_id", event_id):
            m = re.match(r"^(paten|taufpaten|gevattern|trauzeugen|zeugen):\s*(.*)$", text.strip(), re.I | re.S)
            texte.append(text)
            if m:
                arten.append("associates")
                frei += self.freie_eintraege("witness" if m.group(1).lower() in ("trauzeugen", "zeugen") else "godparent",
                                             m.group(2))
            else:
                arten.append("note")
        return texte, arten, frei

    # Ein Fakt ----------------------------------------------------------------------------------------

    @staticmethod
    def leer(fid: str, tag: str, label: str, wert: str, roh: str | None, zugang: str) -> dict:
        return {"id": fid, "pending": False, "tag": tag, "label": label, "known": True, "value": wert,
                "gedcomValue": roh if roh is not None and roh != wert else None, "type": "", "typeLabel": None,
                "date": None, "place": None, "address": None, "access": zugang, "extras": [], "notes": [],
                "noteKinds": [], "sources": [], "associates": [], "freeAssociates": [], "noteXref": None,
                "details": [], "_datum": None}

    def ereignis_fakt(self, e) -> dict:
        typ = e.subtype or ""
        if e.type == "MARR" and typ.upper() in MARR_TYP:
            typ = typ.upper()
        typ_label = (MARR_TYP.get(typ, typ) if e.type == "MARR" else typ) if typ else None
        familie = self.q("SELECT family_id FROM event_role WHERE id = ?", e.rolle_id)[0][0] is not None
        standard = LABEL_FAMILIE.get(e.type) if familie else None
        label = typ_label if (typ_label and e.type in ("MARR", "EVEN", "FACT")) else standard or LABEL.get(e.type, e.type)
        roh = e.value or ""
        wert = WERT.get(e.type, {}).get(roh.upper(), roh) if roh else ""
        f = self.leer(f"E{e.rolle_id}", e.type, label, wert, roh if roh else None, self.zugang_fakt(e.type, e.resn))
        f["type"], f["typeLabel"] = typ, typ_label
        f["date"] = anzeige.datum_json(e.date_text, mit_gedcom=True)
        f["_datum"] = e.date_text
        details = {r["kind"]: r for r in self.q("SELECT d.kind, a.value, a.date_text FROM event_place_detail d LEFT JOIN "
                                                "place_attribute a ON a.id = d.place_attribute_id WHERE d.event_id = ? "
                                                "ORDER BY d.sort", e.id)}
        posten = self.q("SELECT a.value, a.date_text FROM event_place_detail d JOIN place_attribute a ON a.id = "
                        "d.place_attribute_id WHERE d.event_id = ? AND d.kind = 'postal' ORDER BY d.sort", e.id)
        ort = self.q("SELECT gov_id, lat, lng, maidenhead FROM place WHERE id = ?", e.place_id)[0] if e.place_id else None
        if e.place_text:
            mit_karte = ort is not None and "map" in details and ort["lat"] is not None
            f["place"] = {"name": e.place_text, "short": e.place_text, "lat": ort["lat"] if mit_karte else None,
                          "lng": ort["lng"] if mit_karte else None}
        if ort is not None:
            if "gov" in details and ort["gov_id"]:
                f["extras"].append({"tag": "PLAC:_GOV", "value": ort["gov_id"], "date": None})
            f["extras"] += [{"tag": "PLAC:_POST", "value": p["value"], "date": p["date_text"]} for p in posten]
            if "maidenhead" in details and ort["maidenhead"]:
                f["extras"].append({"tag": "PLAC:_MAIDENHEAD", "value": ort["maidenhead"], "date": None})
        f["address"] = e.address
        f["notes"], f["noteKinds"], f["freeAssociates"] = self.notizen_und_freie(e.id)
        f["sources"] = self.zitate("event_id", e.id)
        f["associates"] = self.verknuepfte(e.id)
        for tag, wert_ in (("CAUS", e.cause),):
            if wert_:
                f["details"].append({"tag": tag, "label": DETAIL_LABEL[tag], "value": wert_, "level": 0})
        alter = self.q("SELECT age FROM event_role WHERE id = ?", e.rolle_id)[0][0]
        if alter:
            f["details"].append({"tag": "AGE", "label": DETAIL_LABEL["AGE"], "value": alter, "level": 0})
        return f

    def zitat_fakt(self, z: sqlite3.Row) -> dict | None:
        """Allgemeiner Quellenverweis am Datensatz (1 SOUR): der Fakt ist selbst der Verweis."""
        if z["source_id"] is not None and z["source_id"] not in self.quellen:
            return None
        titel = self.quellen[z["source_id"]]["title"] if z["source_id"] else (z["source_text"] or "")
        roh = f"@{self.quellen[z['source_id']]['xref']}@" if z["source_id"] else z["source_text"]
        resn = self.quellen[z["source_id"]]["resn"] if z["source_id"] else z["resn"]
        f = self.leer(f"Q{z['id']}", "SOUR", LABEL["SOUR"], titel or "", roh, self.zugang_fakt("SOUR", resn))
        f["notes"] = self.notiz_texte("citation_id", z["id"])
        f["noteKinds"] = ["note"] * len(f["notes"])
        j = self.zitat_json(z)
        f["sources"] = [j] if j else []
        return f

    def datensatz_fakten(self, spalte: str, wert: int, ereignisse: list) -> list[dict]:
        """Alle sichtbaren Fakten eines Datensatzes (Person oder Familie), sortiert."""
        fakten = []
        if spalte == "person_id":
            p = self.m.personen[wert]
            for n in p.namen:
                f = self.leer(f"N{n['id']}", "NAME", LABEL["NAME"], n["value"], None, self.zugang_fakt("NAME", n["resn"]))
                f["notes"] = self.notiz_texte("name_id", n["id"])
                f["noteKinds"] = ["note"] * len(f["notes"])
                f["sources"] = self.zitate("name_id", n["id"])
                if n["type"]:
                    f["type"] = n["type_text"] or n["type"]
                if self.s.fakt_darf("NAME", n["resn"]):
                    fakten.append(f)
            sex = self.leer(f"X{p.id}", "SEX", LABEL["SEX"], WERT["SEX"].get(p.sex, p.sex), p.sex, "visitor")
            fakten.append(sex)
        for e in ereignisse:
            if not e.negated and self.s.fakt_darf(e.type, e.resn):
                fakten.append(self.ereignis_fakt(e))
        for n in self.notizen(spalte, wert):
            darf = self.s.fakt_darf("NOTE", n["resn"]) if n["xref"] else True
            if darf:
                f = self.leer(f"T{n['link']}", "NOTE", LABEL["NOTE"], n["text"], None, self.zugang_fakt("NOTE", n["resn"] if n["xref"] else None))
                f["noteXref"] = n["xref"]
                fakten.append(f)
        for z in self.q(f"SELECT * FROM citation WHERE {spalte} = ? ORDER BY sort", wert):
            if self.s.fakt_darf("SOUR", None):
                f = self.zitat_fakt(z)
                if f is not None:
                    fakten.append(f)
        if spalte == "person_id":
            for a in self.q("SELECT * FROM person_association WHERE person_id = ? ORDER BY sort", wert):
                if not self.s.name_darf(a["other_person_id"]):
                    continue
                q = self.m.personen[a["other_person_id"]]
                privat = not self.s.person_darf(q.id)
                f = self.leer(f"A{a['id']}", "ASSO", LABEL["ASSO"], self.bau.name(q), f"@{q.xref}@", "visitor")
                rolle = rolle_v1(a["relation"])
                f["associates"] = [{"xref": q.xref, "name": None if privat else self.bau.name(q),
                                    "sex": None if privat else q.sex, "rela": a["relation"] or "", "role": rolle,
                                    "label": rolle_label(a["relation"], rolle, "U" if privat else q.sex), "private": privat,
                                    "access": self.bau.zugang(q.id), "level1": True,
                                    "notes": self.notiz_texte("person_association_id", a["id"]),
                                    "sources": self.zitate("person_association_id", a["id"])}]
                fakten.append(f)
        for r in self.q(f"SELECT id, gedcom FROM gedcom_rest WHERE {spalte} = ? AND under IS NULL ORDER BY sort", wert):
            kopf = r["gedcom"].split("\n", 1)[0]
            m = re.match(r"^\d+ (\S+)(?: (.*))?$", kopf)
            if m:
                f = self.leer(f"R{r['id']}", m.group(1), LABEL.get(m.group(1), m.group(1)), m.group(2) or "", None,
                              self.zugang_fakt(m.group(1), None))
                f["known"] = m.group(1) in LABEL
                datum = re.search(r"\n2 DATE (.+)", r["gedcom"])
                f["_datum"] = datum.group(1) if datum else None
                f["date"] = anzeige.datum_json(f["_datum"], mit_gedcom=True)
                fakten.append(f)
        aus = sortieren(fakten)
        if spalte == "person_id":
            self._paten_aus_asso(aus)
        for f in aus:
            f.pop("_datum", None)
            f.pop("_reihe", None)
        return aus

    @staticmethod
    def _paten_aus_asso(fakten: list[dict]) -> None:
        """Paten aus „1 ASSO“ zusätzlich an die Taufe (CHR, sonst BAPM) hängen."""
        ziel = next((f for t in ("CHR", "BAPM") for f in fakten if f["tag"] == t), None)
        if ziel is None:
            return
        for f in fakten:
            if f["tag"] == "ASSO":
                ziel["associates"] += [a for a in f["associates"] if a["role"] == "godparent"]

    # Medien, Aufgaben, Kennungen ------------------------------------------------------------------------

    def medien_json(self, spalte: str, wert: int, haupt_xref: str | None) -> list[dict]:
        aus = []
        for r in self.q(f"SELECT * FROM media_link WHERE {spalte} = ? ORDER BY sort", wert):
            if not self.medium_darf(r["media_id"]):
                continue
            med = self.m.medien[r["media_id"]]
            crop = None
            if any(r[k] is not None for k in ("crop_top", "crop_left", "crop_height", "crop_width")):
                crop = {"top": r["crop_top"], "left": r["crop_left"], "height": r["crop_height"], "width": r["crop_width"]}
            for d in self.datei_json(med.id):
                aus.append({**d, "factId": f"M{r['id']}", "primary": haupt_xref is not None and med.xref == haupt_xref,
                            "highlighted": bool(r["is_primary"]), "crop": crop})
        return aus

    def aufgaben(self, spalte: str, wert: int, xref: str, art: str, name: str) -> list[dict]:
        aus = []
        for t in self.q(f"SELECT * FROM task WHERE {spalte} = ? ORDER BY sort", wert):
            notizen = self.notiz_texte("task_id", t["id"])
            repo = self.q("SELECT xref, name, resn FROM repository WHERE id = ?", t["repository_id"]) \
                if t["repository_id"] else []
            datum = anzeige.datum_json(t["date_text"], mit_gedcom=True)
            aus.append({"record": xref, "recordType": art, "name": name, "factId": f"K{t['id']}", "text": t["text"] or "",
                        "date": datum, "jd": datum["jd"] if datum else None, "user": t["user_name"] or "",
                        "note": notizen[0] if notizen else "", "pending": False, "description": t["description"],
                        "category": t["category"], "priority": t["priority"], "taskType": t["task_type"],
                        "status": t["status"], "reminder": anzeige.datum_json(t["reminder_text"], mit_gedcom=True),
                        "completed": anzeige.datum_json(t["completed_text"], mit_gedcom=True), "solution": t["solution"],
                        # ein verborgenes Archiv behält die Kennung, verliert den Namen
                        "repository": {"xref": repo[0]["xref"],
                                       "name": repo[0]["name"] if self.s.fakt_darf("REPO", repo[0]["resn"]) else None}
                        if repo else None})
        return aus

    def uids(self, tabelle: str, wert: int) -> list[str]:
        erste = self.q(f"SELECT uid FROM {tabelle} WHERE id = ?", wert)[0][0]
        weitere = [r[0].split(" ", 2)[2] for r in self.q(f"SELECT gedcom FROM gedcom_rest WHERE {tabelle}_id = ? AND under "
                                                         "IS NULL AND gedcom LIKE '1 _UID %'", wert)]
        return [u for u in [erste, *weitere] if u]

    # Familie -----------------------------------------------------------------------------------------

    def familien_name(self, f) -> str:
        # fehlender Partner: „… …“ (Vor- und Familienname unbekannt)
        ohne = f"{anzeige.UNBEKANNT} {anzeige.UNBEKANNT}"
        teile = [self.bau.name(self.m.personen[f.partner[k]]) if k in f.partner else ohne for k in (1, 2)]
        return " + ".join(teile)

    def familie_json(self, fid: int, bezug: int | None = None, mit_zahlen: bool = False) -> dict:
        f = self.m.familien[fid]
        kinder = []
        for k in f.kinder:
            heiraten = []
            for kf in self.m.personen[k].fams:
                fam = self.m.familien[kf]
                partner = next((q for q in fam.partner.values() if q != k), None)
                h = _heirat(self.bau, fam)
                heiraten.append({"family": fam.xref,
                                 "spouse": self.bau.name(self.m.personen[partner]) if partner and self.s.name_darf(partner) else "",
                                 "date": anzeige.datum_json(h[0]) if h else None,
                                 "place": self.bau.ort_json(h[1]) if h else None})
            kinder.append({**self.bau.person_kurz(k, mit_zahlen), "marriages": heiraten})
        partner = None
        if bezug is not None:
            partner = next((q for q in f.partner.values() if q != bezug), None)
        h = _heirat(self.bau, f)
        darf = self.s.familie_darf(fid)
        return {
            "xref": f.xref,
            "name": self.familien_name(f),
            "url": self.bau.seiten_url("family", f.xref),
            "husband": self.bau.person_kurz(f.partner[1], mit_zahlen) if 1 in f.partner else None,
            "wife": self.bau.person_kurz(f.partner[2], mit_zahlen) if 2 in f.partner else None,
            "spouse": self.bau.person_kurz(partner, mit_zahlen) if partner else None,
            "marriage": self.bau.ereignis_json(*h) if h else None,
            "facts": self.datensatz_fakten("family_id", fid, f.fakten) if darf else [],
            "children": kinder,
            "access": "visitor" if self.s.familie_darf(fid, 2) else "member" if self.s.familie_darf(fid, 1) else "manager",
            "uids": self.uids("family", fid) if darf else [],
        }


# ── GET Family ────────────────────────────────────────────────────────────────────────────────────────

def _oeffnen(ctx: Kontext):
    return ctx.app.state.baeume.baum(ctx.baum_name).oeffnen()


def family(ctx: Kontext):
    try:
        s = sicht_fuer(ctx, ctx.baum_name or "")
    except Exception:  # noqa: BLE001
        return fehler(404, "tree-not-found")
    fid = s.m.familie_xref.get(ctx.params.get("xref") or "")
    if fid is None:
        return fehler(404, "not-found")
    if not s.familie_darf(fid):
        return fehler(403, "private")
    bau = Bau(ctx, s)
    con = _oeffnen(ctx)
    try:
        fk = Fakten(bau, con)
        j = fk.familie_json(fid)
        f = s.m.familien[fid]
        j["media"] = fk.medien_json("family_id", fid, None)
        j["tasks"] = fk.aufgaben("family_id", fid, f.xref, "FAM", j["name"])
        j["lastChange"] = None
        return j
    finally:
        con.close()


# ── GET Individual ────────────────────────────────────────────────────────────────────────────────────

def _verwandtschaft(bau: Bau, von: int, zu: int) -> str:
    """Nahe Verwandtschaft von „zu“ aus Sicht von „von“: direkte Linie, Geschwister, Partner. Sonst leer."""
    m = bau.m
    sex = m.personen[zu].sex

    def eltern(pid):
        return [q for fid in m.personen[pid].famc for q in m.familien[fid].partner.values()]

    def wort(m_, f_, n_):
        return m_ if sex == "M" else f_ if sex == "F" else n_

    # Vorfahren
    stufe, ebene = {von}, 0
    while stufe and ebene < 12:
        ebene += 1
        stufe = {q for p in stufe for q in eltern(p)}
        if zu in stufe:
            if ebene == 1:
                return wort("Vater", "Mutter", "Elternteil")
            if ebene == 2:
                return wort("Großvater", "Großmutter", "Großelternteil")
            ur = "Ur" * (ebene - 2)
            return ur + wort("großvater", "großmutter", "großelternteil")
    # Nachkommen
    stufe, ebene = {zu}, 0
    while stufe and ebene < 12:
        ebene += 1
        stufe = {q for p in stufe for q in eltern(p)}
        if von in stufe:
            if ebene == 1:
                return wort("Sohn", "Tochter", "Kind")
            if ebene == 2:
                return wort("Enkel", "Enkelin", "Enkelkind")
            return "Ur" * (ebene - 2) + wort("enkel", "enkelin", "enkelkind")
    if set(eltern(von)) & set(eltern(zu)):
        return wort("Bruder", "Schwester", "Geschwister")
    for fid in m.personen[von].fams:
        if zu in m.familien[fid].partner.values():
            return wort("Ehemann", "Ehefrau", "Ehepartner")
    return ""


def _gegenrichtung(fk: Fakten, pid: int) -> list[dict]:
    bau, s, m = fk.bau, fk.s, fk.m
    p = m.personen[pid]
    eintraege = []
    rollen = fk.q("""SELECT er.id, er.rela, e.id AS event_id, e.type, e.subtype, e.date_text, e.place_text, e.resn,
                            h.person_id, h.family_id, h.id AS haupt
                     FROM event_role er JOIN event e ON e.id = er.event_id
                     JOIN event_role h ON h.event_id = e.id AND h.role = 'PRINCIPAL'
                     WHERE er.person_id = ? AND er.role <> 'PRINCIPAL' ORDER BY er.id""", pid)
    for r in rollen:
        if r["person_id"] is not None:
            if not s.person_darf(r["person_id"]):
                continue
            rec, art, name = m.personen[r["person_id"]], "INDI", bau.name(m.personen[r["person_id"]])
            mann = frau = None
        else:
            if not s.familie_darf(r["family_id"]):
                continue
            rec, art = m.familien[r["family_id"]], "FAM"
            name = fk.familien_name(rec)
            mann = m.personen[rec.partner[1]].xref if 1 in rec.partner and s.person_darf(rec.partner[1]) else None
            frau = m.personen[rec.partner[2]].xref if 2 in rec.partner and s.person_darf(rec.partner[2]) else None
        if not s.fakt_darf(r["type"], r["resn"]):
            continue
        typ = r["subtype"] or ""
        if r["type"] == "MARR" and typ.upper() in MARR_TYP:
            typ = typ.upper()
        label = (MARR_TYP.get(typ, typ) if r["type"] == "MARR" else typ) if (typ and r["type"] in ("MARR", "EVEN", "FACT")) \
            else LABEL.get(r["type"], r["type"])
        rolle = rolle_v1(r["rela"])
        datum = anzeige.datum_json(r["date_text"])
        eintraege.append({
            "record": rec.xref, "recordType": art, "name": name, "tag": r["type"], "label": label,
            "factId": f"E{r['haupt']}", "date": datum, "place": bau.ort_json(r["place_text"]), "rela": r["rela"] or "",
            "role": rolle, "label2": rolle_label(r["rela"], rolle, p.sex), "level1": False,
            "url": bau.seiten_url("individual" if art == "INDI" else "family", rec.xref), "husband": mann, "wife": frau,
        })
    reihe = sorted(range(len(eintraege)), key=lambda i: (eintraege[i]["date"]["jd"] if eintraege[i]["date"] else 2**63, i))
    return [eintraege[i] for i in reihe]


def individual(ctx: Kontext):
    r = baum_und_person(ctx)
    if not isinstance(r, tuple):
        return r
    bau, pid = r
    s, m = bau.s, bau.m
    p = m.personen[pid]
    con = _oeffnen(ctx)
    try:
        fk = Fakten(bau, con)
        eltern = [fk.familie_json(fid, None, True) for fid in p.famc]
        partner = [fk.familie_json(fid, pid, True) for fid in p.fams]
        eigene_eltern = {q for fid in p.famc for q in m.familien[fid].partner.values()}
        stief = []
        for fid in p.famc:
            for q in m.familien[fid].partner.values():
                for sf in m.personen[q].fams:
                    if sf not in p.famc and sf not in [x for x, _ in stief]:
                        stief.append((sf, q))
        stief_json = [{"parent": m.personen[q].xref if q in eigene_eltern else None, **fk.familie_json(sf, q, True)}
                      for sf, q in stief]
        bezug = ctx.params.get("relativeTo") or ""
        verwandt = ""
        if bezug and bezug != p.xref:
            other = m.person_xref.get(bezug)
            if other is not None and s.person_darf(other):
                verwandt = _verwandtschaft(bau, other, pid)
        rolle = ctx.konten.rolle(ctx.konto, ctx.baum_name)
        haupt = bau.hauptbild(p)
        name = bau.name(p)
        return {
            "person": bau.person_kurz(pid, True),
            "relationship": verwandt,
            "canEdit": ROLLEN.index(rolle) >= ROLLEN.index("editor") and p.resn != "locked" or rolle == "manager",
            "facts": fk.datensatz_fakten("person_id", pid, p.fakten),
            "parentFamilies": eltern,
            "spouseFamilies": partner,
            "stepFamilies": stief_json,
            "media": fk.medien_json("person_id", pid, haupt[0].xref if haupt else None),
            "associatedIn": _gegenrichtung(fk, pid),
            "tasks": fk.aufgaben("person_id", pid, p.xref, "INDI", name),
            "lastChange": None,
            "uids": fk.uids("person", pid),
        }
    finally:
        con.close()


GET_AKTIONEN["Family"] = family
GET_AKTIONEN["Individual"] = individual


# ── Bilder und Dateien (eigene Adressen, für die Apps undurchsichtig) ─────────────────────────────────

def medien(ctx: Kontext):
    from fastapi.responses import FileResponse

    from .http import _nicht_gefunden

    try:
        s = sicht_fuer(ctx, ctx.baum_name or "")
    except Exception:  # noqa: BLE001
        return _nicht_gefunden()
    kennung = ctx.params.get("xref") or ""
    med = next((m for m in s.m.medien.values() if (m.xref or str(m.id)) == kennung), None)
    if med is None or not s.medium_darf(med.id) or not med.dateien:
        return _nicht_gefunden()
    ordner = (ctx.einstellungen.medien / ctx.baum_name).resolve()
    datei = (ordner / med.dateien[0][0]).resolve()
    if not datei.is_relative_to(ordner) or not datei.is_file():
        return _nicht_gefunden()
    fmt = (med.dateien[0][1] or datei.suffix.lstrip(".")).lower()
    return FileResponse(datei, media_type=MIME.get(fmt, "application/octet-stream"))


GET_AKTIONEN["medien"] = medien


# ── GET Tags: Faktenarten, die ein Client zum Anlegen anbieten kann ─────────────────────────────────────

# Auswahl und Merkmal „Ereignis“ nach den v1-Aufzeichnungen; Beschriftungen aus LABEL/LABEL_FAMILIE.
TAGS = {
    "INDI": [("BIRT", True), ("CHR", True), ("BAPM", True), ("CONF", False), ("DEAT", True), ("BURI", True),
             ("CREM", True), ("OCCU", False), ("RESI", False), ("EDUC", False), ("GRAD", False), ("RELI", False),
             ("NATI", False), ("TITL", False), ("EMIG", False), ("IMMI", False), ("NATU", False), ("CENS", False),
             ("RETI", False), ("EVEN", False), ("FACT", False), ("NOTE", False)],
    "FAM": [("MARR", True), ("ENGA", True), ("MARB", False), ("DIV", True), ("CENS", False), ("RESI", False),
            ("EVEN", False), ("NOTE", False)],
}


def tags(ctx: Kontext):
    if ctx.app.state.baeume.baum(ctx.baum_name or "") is None:
        return fehler(404, "tree-not-found")
    art = ctx.params.get("type") or "INDI"
    if art not in TAGS:
        return fehler(400, "invalid-type")
    familie = art == "FAM"
    return {"type": art, "data": [{"tag": t, "label": (LABEL_FAMILIE.get(t) if familie else None) or LABEL[t],
                                   "isEvent": ereignis} for t, ereignis in TAGS[art]]}


GET_AKTIONEN["Tags"] = tags
