"""GEDCOM 5.5.1 mit GEDCOM-L in eine Baumdatei einlesen (KONZEPT.md 3 und 6).

Grundsatz: Jede Zeile der Datei wird entweder ins Modell übernommen oder als GEDCOM-Rest an der Struktur
aufgehoben, unter der sie stand (E9). Der Importbericht zählt beides; Summe = Zeilen der Datei.

Abbildung, kurz:
- INDI/FAM/_LOC-Ereignisse und -Merkmale → event + event_role (PRINCIPAL: Person, Familie oder Ort). Paten und Zeugen am Ereignis
  (_ASSO/ASSO mit RELA, _GODP, _WITN) werden weitere Beteiligte desselben Ereignisses; ohne Datensatz als
  strukturierter Text (E5). Alter (AGE) gehört an die Beteiligung.
- FAMC/FAMS/HUSB/WIFE/CHIL → family_member; Abstammungsart je Elternteil aus PEDI, ADOP (HUSB/WIFE/BOTH) und
  _FREL/_MREL → parentage.
- _LOC → place mit datierten Namen, Arten (_GOVTYPE), Zugehörigkeiten und Angaben; PLAC am Ereignis → Ort über
  _LOC-Verweis, sonst über die Namenskette. Unsichere Zuordnungen stehen im Bericht.
- Zitate, Notizen, Medienverweise, Aufgaben (_TODO) an ihrem Träger.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from baum import datei as baumdatei
from sqlalchemy import Connection, and_, bindparam, func, insert, select, update

from baum.schema import TRAEGER, XREF_LAENGE
from baum.schema import tabelle as T

from . import datum as gdatum
from .lesen import Datei, Knoten, NichtLesbar, lesen

EREIGNISSE_PERSON = {
    "BIRT", "CHR", "DEAT", "BURI", "CREM", "ADOP", "BAPM", "BARM", "BASM", "BLES", "CHRA", "CONF", "FCOM", "ORDN",
    "NATU", "EMIG", "IMMI", "CENS", "PROB", "WILL", "GRAD", "RETI", "EVEN",
    # Merkmale (5.5.1 „attributes“)
    "CAST", "DSCR", "EDUC", "IDNO", "NATI", "NCHI", "NMR", "OCCU", "PROP", "RELI", "RESI", "SSN", "TITL", "FACT",
}
EREIGNISSE_FAMILIE = {"ANUL", "CENS", "DIV", "DIVF", "ENGA", "MARB", "MARC", "MARR", "MARL", "MARS", "RESI", "EVEN",
                      "NCHI", "FACT"}
RESN = {"none", "privacy", "confidential", "locked"}
PEDI = {"birth": "birth", "adopted": "adopted", "foster": "foster", "sealing": "sealing", "other": "unknown"}
# _FREL/_MREL (verbreitet, nicht GEDCOM-L): Abstammung zum Vater bzw. zur Mutter
REL = {"natural": "birth", "birth": "birth", "adopted": "adopted", "foster": "foster", "step": "step",
       "stepchild": "step", "unknown": "unknown"}


def rolle_aus_rela(text: str | None) -> str:
    """RELA-Text → Rollencode: GEDCOM 7 ROLE, eigene mit X_, sonst OTHER. Der Text selbst bleibt in event_role.rela."""
    t = (text or "").strip().lower()
    if re.search(r"god|pat[ei]|taufzeug", t):
        return "GODP"
    if re.search(r"witn|zeug", t):
        return "WITN"
    if re.search(r"priest|pfarrer|pastor|clergy|geistlich", t):
        return "CLERGY"
    if re.search(r"officiat|standesbeamt", t):
        return "OFFICIATOR"
    if t in ("father", "vater"):
        return "FATH"
    if t in ("mother", "mutter"):
        return "MOTH"
    if re.search(r"neighbo|nachbar", t):
        return "NGHBR"
    if re.search(r"friend|freund", t):
        return "FRIEND"
    if re.search(r"informant|anzeige|melder", t):
        return "X_INFORMANT"
    return "OTHER"


@dataclass
class Bericht:
    datei: str = ""
    gedcom_version: str | None = None
    zeichensatz: str = ""
    zeilen_gesamt: int = 0
    zeilen_uebernommen: int = 0
    zeilen_rest: int = 0
    anzahl: dict = field(default_factory=dict)
    rest_pfade: dict = field(default_factory=dict)
    lesefehler: list = field(default_factory=list)
    datum_unverstanden: list = field(default_factory=list)
    verweis_fehlt: list = field(default_factory=list)
    familien_einseitig: list = field(default_factory=list)
    # Unsichere Ortszuordnungen (KONZEPT.md 6): je Ortstext einmal, mit Zahl der Ereignisse
    orte_unsicher: list = field(default_factory=list)


class Importer:
    def __init__(self, con: Connection, d: Datei, bericht: Bericht):
        self.con, self.d, self.b = con, d, bericht
        self.ids: dict[tuple[str, str], int] = {}       # (Tabelle, xref) → id
        self.rest_pfade: Counter = Counter()
        self._sort = 0
        self.orte: dict[tuple, int] = {}                # Namenskette (klein) → place.id
        self.ort_unsicher: dict[str, dict] = {}
        self.loc_namen: dict[str, list[int]] = {}       # Name (klein) → _LOC-Orte
        self.loc_eltern: dict[int, list[int]] = {}      # _LOC-Ort → übergeordnete _LOC-Orte
        self.famc: dict[tuple[int, int], dict] = {}     # (person, familie) → pedi, status, person_sort
        self.fams: dict[tuple[int, int], int] = {}      # (person, familie) → person_sort
        self.fam_partner: dict[int, dict[int, int]] = {}  # Familie → {Platz: Person}; 1 = HUSB, 2 = WIFE, 3+ = nur FAMS
        self.fam_kinder: dict[int, list[tuple[int, dict]]] = {}
        self.adoptionen: list[tuple[int, int, str]] = []  # (kind, familie, HUSB|WIFE|BOTH)
        self._anweisungen: dict[tuple, object] = {}

    # ── Buchführung ────────────────────────────────────────────────────────────────────────────────

    def _sortnr(self) -> int:
        self._sort += 1
        return self._sort

    def nimm(self, k: Knoten) -> None:
        self.b.zeilen_uebernommen += k.zeilen

    def rest(self, k: Knoten, holder: tuple[str, int], unter: str | None = None) -> None:
        self.ins("gedcom_rest", sort=self._sortnr(), under=unter, gedcom=k.gedcom(), **self.traeger("gedcom_rest", holder))
        self.b.zeilen_rest += k.zeilen_gesamt()
        self.rest_pfade[f"{holder[0]}:{(unter + ':') if unter else ''}{k.tag or '(unlesbar)'}"] += 1

    def wert(self, k: Knoten, holder: tuple[str, int]) -> str | None:
        """Ein Blatt übernehmen; was darunter steht, wird Rest unter dieser Zeile."""
        self.nimm(k)
        for c in k.kinder:
            self.rest(c, holder, unter=k.tag)
        return k.wert

    def kinder(self, k: Knoten, holder: tuple[str, int], handler: dict, unter: str | None = None) -> None:
        for c in k.kinder:
            h = handler.get(c.tag)
            if h is None:
                self.rest(c, holder, unter)
            else:
                h(c)

    def id_von(self, tabelle: str, k: Knoten, holder: tuple[str, int], unter: str | None = None) -> int | None:
        """Zeiger auflösen; fehlt das Ziel, bleibt die Zeile als Rest und steht im Bericht."""
        ziel = self.ids.get((tabelle, k.zeiger or ""))
        if ziel is None:
            self.b.verweis_fehlt.append(f"Zeile {k.zeile}: {k.tag} {k.wert}")
            self.rest(k, holder, unter)
        return ziel

    def ins(self, tab: str, **werte) -> int:
        if not werte:
            return self.con.execute(insert(T(tab)).values()).inserted_primary_key[0]
        return self.con.execute(self._anweisung("ins", tab, werte), werte).inserted_primary_key[0]

    def setze(self, tab: str, id_: int, **werte) -> None:
        if werte:
            self.con.execute(self._anweisung("upd", tab, werte), {**werte, "_id": id_})

    def _anweisung(self, art: str, tab: str, werte: dict):
        """Anweisung je Tabelle und Spaltensatz einmal bauen; danach wechseln nur die Werte (spart viel Zeit)."""
        schluessel = (art, tab, tuple(werte))
        a = self._anweisungen.get(schluessel)
        if a is None:
            t = T(tab)
            if art == "ins":
                a = insert(t).values({k: bindparam(k) for k in werte})
            else:
                a = update(t).where(t.c.id == bindparam("_id")).values({k: bindparam(k) for k in werte})
            self._anweisungen[schluessel] = a
        return a

    def ins_meta(self, key: str, value: str) -> None:
        self.con.execute(insert(T("meta")).values(key=key, value=value))

    def spalte(self, tab: str, spalte: str, id_: int):
        """Wert einer Spalte im Datensatz mit dieser id."""
        t = T(tab)
        return self.con.execute(select(t.c[spalte]).where(t.c.id == id_)).scalar()

    def datum(self, k: Knoten, holder: tuple[str, int], prefix: str = "") -> dict:
        """DATE-Knoten → Spalten. Unverstandenes bleibt als Text und steht im Bericht."""
        text = self.wert(k, holder)
        d = gdatum.lesen(text)
        if d is None:
            return {}
        if not d.gueltig:
            self.b.datum_unverstanden.append(f"Zeile {k.zeile}: {text}")
        return {f"{prefix}date_text": d.text, f"{prefix}date_kind": d.kind, f"{prefix}date_quality": d.quality,
                f"{prefix}date_calendar": d.calendar, f"{prefix}date_from": d.von, f"{prefix}date_to": d.bis}

    # ── Ablauf ─────────────────────────────────────────────────────────────────────────────────────

    def ausfuehren(self) -> None:
        k = self.d.kopf
        self.ins_meta("gedcom_head", k.gedcom())
        self.b.zeilen_uebernommen += k.zeilen_gesamt()

        tabellen = {"INDI": "person", "FAM": "family", "SOUR": "source", "REPO": "repository", "OBJE": "media",
                    "NOTE": "note", "_LOC": "place"}
        for r in self.d.datensaetze:  # 1. Durchgang: Datensätze mit Kennung anlegen
            tab = tabellen.get(r.tag)
            if tab and r.xref:
                if len(r.xref) > XREF_LAENGE:
                    self.b.verweis_fehlt.append(f"Zeile {r.zeile}: Kennung länger als {XREF_LAENGE} Zeichen")
                    self.rest(r, ("tree", 0))
                    continue
                if (tab, r.xref) in self.ids:
                    self.b.verweis_fehlt.append(f"Zeile {r.zeile}: Kennung {r.xref} doppelt")
                    self.rest(r, ("tree", 0))
                    continue
                werte = {"xref": r.xref}
                if tab == "note":
                    werte["text"] = r.wert or ""
                self.ids[(tab, r.xref)] = self.ins(tab, **werte)
            elif r.tag == "TRLR":
                self.nimm(r)
            else:
                self.rest(r, ("tree", 0))

        art = lambda tag: [r for r in self.d.datensaetze if r.tag == tag and r.xref and (tabellen[tag], r.xref) in self.ids]  # noqa: E731
        erledigt = set()
        for tag, f in (("REPO", self.archiv), ("NOTE", self.notiz_datensatz), ("OBJE", self.medium),
                       ("SOUR", self.quelle)):
            for r in art(tag):
                if id(r) not in erledigt:
                    erledigt.add(id(r))
                    f(r)
        loc = art("_LOC")
        for r in loc:
            self.ort_kopf(r)
        for r in loc:
            self.ort(r)
        for r in art("INDI"):
            self.person(r)
        for r in art("FAM"):
            self.familie(r)
        self.mitglieder()
        self.bevorzugte()

        self.b.orte_unsicher = sorted(self.ort_unsicher.values(), key=lambda x: x["ortstext"])
        self.b.rest_pfade = dict(sorted(self.rest_pfade.items()))
        for tab in ("person", "name", "family", "family_member", "parentage", "event", "event_role", "place",
                    "place_name", "place_type", "place_link", "place_attribute", "source", "repository", "citation",
                    "note", "media", "media_link", "task", "person_association", "event_place_detail", "gedcom_rest"):
            self.b.anzahl[tab] = self.con.execute(select(func.count()).select_from(T(tab))).scalar()

    # ── Gemeinsame Unterstrukturen ─────────────────────────────────────────────────────────────────

    def gemeinsam(self, holder: tuple[str, int], tabelle: str | None = None) -> dict:
        """Handler für NOTE, SOUR, OBJE, _TODO, UID, RESN, CHAN – an jedem Datensatz gleich."""
        h = {"NOTE": lambda c: self.notiz(c, holder), "SOUR": lambda c: self.zitat(c, holder),
             "OBJE": lambda c: self.medienverweis(c, holder), "_TODO": lambda c: self.aufgabe(c, holder)}
        if tabelle:
            h["_UID"] = h["UID"] = lambda c: self.uid(c, holder, tabelle)
            h["RESN"] = lambda c: self.resn(c, holder, tabelle)
            h["CHAN"] = lambda c: self.chan(c, holder, tabelle)
        return h

    def uid(self, k: Knoten, holder, tabelle: str) -> None:
        vorhanden = self.spalte(tabelle, "uid", holder[1])
        if vorhanden is None and k.wert and not k.kinder:
            self.nimm(k)
            self.setze(tabelle, holder[1], uid=k.wert)
        else:
            self.rest(k, holder)

    def resn(self, k: Knoten, holder, tabelle: str) -> None:
        if (k.wert or "").lower() in RESN:
            self.setze(tabelle, holder[1], resn=self.wert(k, holder).lower())
        else:
            self.rest(k, holder)

    def chan(self, k: Knoten, holder, tabelle: str) -> None:
        if tabelle not in ("person", "family"):
            self.rest(k, holder)
            return
        self.nimm(k)
        teile = []

        def datum(c):
            self.nimm(c)
            teile.append(c.wert or "")
            self.kinder(c, holder, {"TIME": lambda t: teile.append(self.wert(t, holder) or "")}, unter="CHAN:DATE")

        self.kinder(k, holder, {"DATE": datum}, unter="CHAN")
        self.setze(tabelle, holder[1], changed_at=" ".join(t for t in teile if t) or None)

    @staticmethod
    def traeger(tabelle: str, holder: tuple[str, int]) -> dict | None:
        """Spalte des Trägers in dieser Tabelle ({"person_id": 7}), None wenn der Träger dort nicht vorgesehen ist."""
        if holder[0] not in TRAEGER[tabelle]:
            return None
        return {"on_tree": 1} if holder[0] == "tree" else {f"{holder[0]}_id": holder[1]}

    def notiz(self, k: Knoten, holder) -> None:
        if self.traeger("note_link", holder) is None:
            self.rest(k, holder)
            return
        if k.zeiger:
            nid = self.id_von("note", k, holder)
            if nid is None:
                return
            self.nimm(k)
        else:
            self.nimm(k)
            nid = self.ins("note", text=k.wert or "")
        self.ins("note_link", note_id=nid, sort=self._sortnr(), **self.traeger("note_link", holder))
        for c in k.kinder:
            self.rest(c, ("note", nid))

    def zitat(self, k: Knoten, holder) -> None:
        if self.traeger("citation", holder) is None:
            self.rest(k, holder)
            return
        sid = None
        if k.zeiger:
            sid = self.id_von("source", k, holder)
            if sid is None:
                return
        self.nimm(k)
        zid = self.ins("citation", sort=self._sortnr(), source_id=sid, source_text=None if k.zeiger else k.wert,
                       **self.traeger("citation", holder))
        z = ("citation", zid)

        def quay(c):
            if (c.wert or "").strip() in ("0", "1", "2", "3") and not c.kinder:
                self.setze("citation", zid, quality=int(self.wert(c, z)))
            else:
                self.rest(c, z)

        def even(c):
            self.setze("citation", zid, event_type=self.wert_ohne_kinder(c))
            self.kinder(c, z, {"ROLE": lambda r: self.setze("citation", zid, event_role=self.wert(r, z))}, unter="EVEN")

        def data(c):
            self.nimm(c)
            self.kinder(c, z, {"DATE": lambda d: self.setze("citation", zid, **self.datum(d, z, "data_")),
                               "TEXT": lambda t: self.setze("citation", zid, data_text=self.wert(t, z))}, unter="DATA")

        def text(c):  # TEXT direkt am Zitat (verbreitet, eigentlich DATA:TEXT)
            vorhanden = self.spalte("citation", "data_text", zid)
            if vorhanden is None:
                self.setze("citation", zid, data_text=self.wert(c, z))
            else:
                self.rest(c, z)

        self.kinder(k, z, {"PAGE": lambda c: self.setze("citation", zid, page=self.wert(c, z)), "QUAY": quay,
                           "EVEN": even, "DATA": data, "TEXT": text, "NOTE": lambda c: self.notiz(c, z),
                           "OBJE": lambda c: self.medienverweis(c, z)})

    def wert_ohne_kinder(self, k: Knoten) -> str | None:
        """Wert nehmen, Kinder bearbeitet der Aufrufer selbst."""
        self.nimm(k)
        return k.wert

    def medienverweis(self, k: Knoten, holder) -> None:
        if self.traeger("media_link", holder) is None:
            self.rest(k, holder)
            return
        if k.zeiger:
            mid = self.id_von("media", k, holder)
            if mid is None:
                return
            self.nimm(k)
        else:  # eingebettetes OBJE mit FILE
            self.nimm(k)
            mid = self.ins("media")
            self.medium_inhalt(k, mid, nur_dateien=True)
        lid = self.ins("media_link", media_id=mid, sort=self._sortnr(), **self.traeger("media_link", holder))
        unter = f"OBJE @{k.zeiger}@" if k.zeiger else "OBJE"

        def prim(c):
            if (c.wert or "").upper() in ("Y", "N") and not c.kinder:
                self.setze("media_link", lid, is_primary=int(self.wert(c, holder).upper() == "Y"))
            else:
                self.rest(c, holder, unter)

        def crop(c):  # GEDCOM 7 CROP, kommt auch in 5.5.1-Dateien vor
            self.nimm(c)
            felder = {"TOP": "crop_top", "LEFT": "crop_left", "HEIGHT": "crop_height", "WIDTH": "crop_width"}

            def zahl(x):
                if (x.wert or "").isdigit() and not x.kinder:
                    self.setze("media_link", lid, **{felder[x.tag]: int(self.wert(x, holder))})
                else:
                    self.rest(x, holder, unter + ":CROP")

            self.kinder(c, holder, {t: zahl for t in felder}, unter=unter + ":CROP")

        handler = {"_PRIM": prim, "CROP": crop, "TITL": lambda c: self.setze("media_link", lid, title=self.wert(c, holder))}
        if not k.zeiger:
            handler.update({"FILE": lambda c: None, "TITL": lambda c: None})  # schon in medium_inhalt
        self.kinder(k, holder, handler, unter=unter)

    def aufgabe(self, k: Knoten, holder) -> None:
        if self.traeger("task", holder) is None:
            self.rest(k, holder)
            return
        self.nimm(k)
        tid = self.ins("task", sort=self._sortnr(), text=k.wert, **self.traeger("task", holder))
        t = ("task", tid)
        spalte = lambda s: (lambda c: self.setze("task", tid, **{s: self.wert(c, t)}))  # noqa: E731

        def repo(c):
            rid = self.id_von("repository", c, t)
            if rid is not None:
                self.wert(c, t)
                self.setze("task", tid, repository_id=rid)

        self.kinder(k, t, {"DESC": spalte("description"), "_CAT": spalte("category"), "_PRTY": spalte("priority"),
                           "TYPE": spalte("task_type"), "STAT": spalte("status"), "DATA": spalte("solution"),
                           "_RDATE": spalte("reminder_text"), "_CDATE": spalte("completed_text"),
                           "_WT_USER": spalte("user_name"), "REPO": repo,
                           "DATE": lambda c: self.setze("task", tid, **self.datum(c, t)),
                           "NOTE": lambda c: self.notiz(c, t), "SOUR": lambda c: self.zitat(c, t)})

    # ── Archive, Notizen, Medien, Quellen ──────────────────────────────────────────────────────────

    def archiv(self, r: Knoten) -> None:
        rid = self.ids[("repository", r.xref)]
        h = ("repository", rid)
        self.nimm(r)
        einmal = lambda s: (lambda c: self.einmal(c, h, "repository", s))  # noqa: E731

        def addr(c):
            self.setze("repository", rid, address=self.wert_ohne_kinder(c))
            self.kinder(c, h, {"ADR1": einmal("adr1"), "CITY": einmal("city"), "POST": einmal("postal_code"),
                               "CTRY": einmal("country"), "_NAME": einmal("address_name")}, unter="ADDR")

        self.kinder(r, h, {"NAME": einmal("name"), "ADDR": addr, "PHON": einmal("phone"), "EMAIL": einmal("email"),
                           "WWW": einmal("www"), **self.gemeinsam(h, "repository")})

    def einmal(self, c: Knoten, holder, tabelle: str, spalte: str) -> None:
        """Spalte setzen, wenn sie leer ist; eine zweite Angabe gleicher Art bleibt als Rest."""
        if self.spalte(tabelle, spalte, holder[1]) is None:
            self.setze(tabelle, holder[1], **{spalte: self.wert(c, holder)})
        else:
            self.rest(c, holder)

    def notiz_datensatz(self, r: Knoten) -> None:
        nid = self.ids[("note", r.xref)]
        self.nimm(r)
        for c in r.kinder:
            self.rest(c, ("note", nid))

    def medium(self, r: Knoten) -> None:
        mid = self.ids[("media", r.xref)]
        self.nimm(r)
        self.medium_inhalt(r, mid)

    def medium_inhalt(self, r: Knoten, mid: int, nur_dateien: bool = False) -> None:
        h = ("media", mid)

        def datei(c):
            self.nimm(c)
            fid = self.ins("media_file", media_id=mid, sort=self._sortnr(), path=c.wert or "")

            def form(f):
                self.setze("media_file", fid, format=self.wert_ohne_kinder(f))
                typ = lambda t: self.setze("media_file", fid, media_type=self.wert(t, h))  # noqa: E731
                self.kinder(f, h, {"TYPE": typ, "MEDI": typ}, unter=f"FILE {c.wert}:FORM")

            def titel(t):
                titel_ = self.wert(t, h)
                self.setze("media_file", fid, title=titel_)
                if self.spalte("media", "title", mid) is None:
                    self.setze("media", mid, title=titel_)

            self.kinder(c, h, {"FORM": form, "TITL": titel}, unter=f"FILE {c.wert}")

        handler = {"FILE": datei, "TITL": lambda c: self.setze("media", mid, title=self.wert(c, h))}
        if nur_dateien:
            for c in r.kinder:
                if c.tag in handler:
                    handler[c.tag](c)
            return
        self.kinder(r, h, {**handler, **self.gemeinsam(h, "media")})

    def quelle(self, r: Knoten) -> None:
        sid = self.ids[("source", r.xref)]
        h = ("source", sid)
        self.nimm(r)
        einmal = lambda s: (lambda c: self.einmal(c, h, "source", s))  # noqa: E731

        def data(c):
            self.nimm(c)

            def even(e):
                cid = self.ins("source_coverage", source_id=sid, sort=self._sortnr(), events=self.wert_ohne_kinder(e))
                self.kinder(e, h, {"DATE": lambda d: self.setze("source_coverage", cid, **self.datum(d, h)),
                                   "PLAC": lambda p: self.setze("source_coverage", cid, place_text=self.wert(p, h))},
                            unter="DATA:EVEN")

            self.kinder(c, h, {"EVEN": even, "AGNC": einmal("agency")}, unter="DATA")

        def repo(c):
            rid = None
            if c.zeiger:
                rid = self.id_von("repository", c, h)
                if rid is None:
                    return
            self.nimm(c)
            calns = c.alle("CALN")
            if not calns:
                self.ins("source_repository", source_id=sid, repository_id=rid, sort=self._sortnr())

            def caln(n):
                sr = self.ins("source_repository", source_id=sid, repository_id=rid, sort=self._sortnr(),
                              call_number=self.wert_ohne_kinder(n))
                self.kinder(n, h, {"MEDI": lambda m: self.setze("source_repository", sr, medium=self.wert(m, h))},
                            unter=f"REPO {c.wert or ''}:CALN".strip())

            self.kinder(c, h, {"CALN": caln}, unter=f"REPO {c.wert or ''}".strip())

        self.kinder(r, h, {"TITL": einmal("title"), "ABBR": einmal("abbr"), "AUTH": einmal("author"),
                           "PUBL": einmal("publication"), "TEXT": einmal("text"), "DATA": data, "REPO": repo,
                           **self.gemeinsam(h, "source")})

    # ── Orte ───────────────────────────────────────────────────────────────────────────────────────

    def ort_kopf(self, r: Knoten) -> None:
        """Vorab: Namen und übergeordnete _LOC jedes Ortsdatensatzes, für die Zuordnung von PLAC."""
        pid = self.ids[("place", r.xref)]
        for n in r.alle("NAME"):
            if n.wert:
                self.loc_namen.setdefault(n.wert.strip().lower(), []).append(pid)
        self.loc_eltern[pid] = [self.ids[("place", z.zeiger)] for z in r.alle("_LOC") if ("place", z.zeiger) in self.ids]

    def ort(self, r: Knoten) -> None:
        pid = self.ids[("place", r.xref)]
        h = ("place", pid)
        self.nimm(r)

        def name(c):
            nid = self.ins("place_name", place_id=pid, sort=self._sortnr(), name=self.wert_ohne_kinder(c) or "")
            self.kinder(c, h, {"DATE": lambda d: self.setze("place_name", nid, **self.datum(d, h)),
                               "LANG": lambda x: self.setze("place_name", nid, lang=self.wert(x, h)),
                               "ABBR": lambda x: self.setze("place_name", nid, abbr=self.wert(x, h))},
                        unter=f"NAME {c.wert}")

        def typ(c):
            tid = self.ins("place_type", place_id=pid, sort=self._sortnr(), type_text=self.wert_ohne_kinder(c))

            def govtyp(g):
                if (g.wert or "").isdigit() and not g.kinder:
                    self.setze("place_type", tid, gov_type=int(self.wert(g, h)))
                else:
                    self.rest(g, h, f"TYPE {c.wert}")

            self.kinder(c, h, {"DATE": lambda d: self.setze("place_type", tid, **self.datum(d, h)),
                               "_GOVTYPE": govtyp}, unter=f"TYPE {c.wert}")

        def oberort(c):
            eltern = self.id_von("place", c, h)
            if eltern is None:
                return
            if eltern == pid:
                self.rest(c, h)
                return
            lid = self.ins("place_link", place_id=pid, parent_id=eltern, sort=self._sortnr(), kind=None)
            self.wert_ohne_kinder(c)
            self.kinder(c, h, {"TYPE": lambda t: self.setze("place_link", lid, kind=self.wert(t, h)),
                               "DATE": lambda d: self.setze("place_link", lid, **self.datum(d, h))},
                        unter=f"_LOC @{c.zeiger}@")

        def map_(c):
            self.koordinaten(c, pid, h, unter=None)

        def angabe(art):
            def f(c):
                aid = self.ins("place_attribute", place_id=pid, kind=art, value=self.wert_ohne_kinder(c) or "",
                               sort=self._sortnr())
                self.kinder(c, h, {"TYPE": lambda t: self.setze("place_attribute", aid, subtype=self.wert(t, h)),
                                   "DATE": lambda d: self.setze("place_attribute", aid, **self.datum(d, h))},
                            unter=f"{c.tag} {c.wert}")
            return f

        self.kinder(r, h, {"NAME": name, "TYPE": typ, "_LOC": oberort, "MAP": map_,
                           "_GOV": lambda c: self.einmal(c, h, "place", "gov_id"),
                           "_MAIDENHEAD": lambda c: self.einmal(c, h, "place", "maidenhead"),
                           "_POST": angabe("postal"), "_AIDN": angabe("aidn"), "_DMGD": angabe("demographics"),
                           "_STAE": angabe("state"), "_CTRY": angabe("country"), "RELI": angabe("religion"),
                           "EVEN": lambda c: self.ereignis(c, h, "PRINCIPAL"), **self.gemeinsam(h, "place")})

    @staticmethod
    def _grad(text: str | None) -> float | None:
        m = re.match(r"^\s*([NSEW])?\s*(-?\d+(?:\.\d+)?)\s*$", text or "", re.I)
        if not m:
            return None
        zahl = float(m.group(2))
        return -zahl if (m.group(1) or "").upper() in ("S", "W") else zahl

    def koordinaten(self, c: Knoten, pid: int, holder, unter: str | None) -> bool:
        """MAP mit LATI/LONG an den Ort. Hat der Ort schon andere Koordinaten, bleibt MAP als Rest am Träger.
        True, wenn die Angabe übernommen wurde."""
        lat, lng = self._grad(c.wert_von("LATI")), self._grad(c.wert_von("LONG"))
        sauber = lat is not None and lng is not None and len(c.kinder) == 2 and all(not k.kinder for k in c.kinder)
        pl = T("place")
        alt = self.con.execute(select(pl.c.lat, pl.c.lng).where(pl.c.id == pid)).one()
        if not sauber or (alt[0] is not None and (round(alt[0], 6), round(alt[1], 6)) != (round(lat, 6), round(lng, 6))):
            self.rest(c, holder, unter)
            return False
        self.nimm(c)
        for k in c.kinder:
            self.nimm(k)
        if alt[0] is None:
            self.setze("place", pid, lat=lat, lng=lng)
        return True

    def ort_aus_text(self, text: str, zeile: int) -> int:
        """Ort zur Namenskette „Hof Nr. 3, Bienenbüttel, Uelzen, …“ finden oder anlegen (von oben nach unten).

        Je Stufe: Gibt es genau einen _LOC mit diesem Namen, der zu den Stufen darüber passt (sein übergeordneter
        _LOC trägt den nächsten Namen der Kette), wird er genommen. Passt er nur über den Namen (kein übergeordneter
        _LOC) oder gibt es mehrere, steht die Zuordnung als unsicher im Bericht.
        """
        teile = [t.strip() for t in text.split(",")]
        eltern = None
        for i in range(len(teile) - 1, -1, -1):
            schluessel = tuple(t.lower() for t in teile[i:])
            if schluessel in self.orte:
                eltern = self.orte[schluessel]
                bekannt = self.ort_unsicher.get(", ".join(teile[i:]))
                if bekannt:
                    bekannt["ereignisse"] += 1
                continue
            name = teile[i]
            kandidaten = self.loc_namen.get(name.lower(), [])
            darueber = teile[i + 1].lower() if i + 1 < len(teile) else None

            sicher = [p for p in kandidaten if darueber and self._oberort_heisst(p, darueber)]
            nur_name = [p for p in kandidaten if not self.loc_eltern.get(p)]
            gewaehlt, unsicher = None, None
            if len(sicher) == 1:
                gewaehlt = sicher[0]
            elif not sicher and len(nur_name) == 1 and len(kandidaten) == 1:
                gewaehlt, unsicher = nur_name[0], "nur über den Namen zugeordnet (Ortsdatensatz ohne übergeordneten Ort)"
            elif len(kandidaten) > 1 or len(sicher) > 1:
                unsicher = f"mehrdeutig: {len(kandidaten)} Ortsdatensätze heißen „{name}“, keiner gewählt"
            elif kandidaten:
                unsicher = f"Ortsdatensatz „{name}“ liegt laut Datensatz anderswo, nicht übernommen"
            if gewaehlt is None:
                gewaehlt = self.ins("place")
                self.ins("place_name", place_id=gewaehlt, sort=self._sortnr(), name=name)
            lk = T("place_link")
            if eltern is not None and self.con.execute(
                    select(lk.c.id).where(lk.c.place_id == gewaehlt, lk.c.parent_id == eltern)).first() is None:
                self.ins("place_link", place_id=gewaehlt, parent_id=eltern, sort=self._sortnr(), kind=None)
            if unsicher:
                ortstext = ", ".join(teile[i:])
                e = self.ort_unsicher.setdefault(ortstext, {"ortstext": ortstext, "grund": unsicher, "ort": gewaehlt,
                                                            "ereignisse": 0, "erste_zeile": zeile})
                e["ereignisse"] += 1
            self.orte[schluessel] = gewaehlt
            eltern = gewaehlt
        return eltern

    def _oberort_heisst(self, pid: int, name: str) -> bool:
        """Trägt einer der übergeordneten _LOC dieses Ortes den Namen (klein geschrieben)?"""
        return any(name in [n.lower() for n in self._namen(e)] for e in self.loc_eltern.get(pid, []))

    def _namen(self, pid: int) -> list[str]:
        pn = T("place_name")
        return list(self.con.execute(select(pn.c.name).where(pn.c.place_id == pid)).scalars())

    def plac(self, k: Knoten, eid: int, holder) -> None:
        self.nimm(k)
        loc = k.erstes("_LOC")
        pid = None
        if loc is not None and ("place", loc.zeiger) in self.ids:
            pid = self.ids[("place", loc.zeiger)]
            self.wert(loc, holder)
        elif k.wert:
            pid = self.ort_aus_text(k.wert, k.zeile)
        self.setze("event", eid, place_text=k.wert, place_id=pid)
        if pid is None:
            for c in k.kinder:
                if c is not loc:
                    self.rest(c, holder, "PLAC")
            return

        def vermerk(art: str, attribut: int | None = None) -> None:
            self.ins("event_place_detail", event_id=eid, sort=self._sortnr(), kind=art, place_attribute_id=attribut)

        def gleich_oder_rest(spalte, art):
            def f(c):
                alt = self.spalte("place", spalte, pid)
                if c.kinder or (alt is not None and alt != c.wert):
                    self.rest(c, holder, "PLAC")
                else:
                    self.nimm(c)
                    if alt is None:
                        self.setze("place", pid, **{spalte: c.wert})
                    vermerk(art)
            return f

        def map_(c):
            if self.koordinaten(c, pid, holder, "PLAC"):
                vermerk("map")

        def post(c):
            datum_ = c.erstes("DATE")
            pa = T("place_attribute")
            vorhanden = self.con.execute(select(pa.c.id).where(
                pa.c.place_id == pid, pa.c.kind == "postal", pa.c.value == c.wert,
                func.coalesce(pa.c.date_text, "") == (datum_.wert if datum_ else ""))).first()
            if vorhanden and len(c.kinder) <= 1 and all(x.tag == "DATE" and not x.kinder for x in c.kinder):
                self.nimm(c)
                for x in c.kinder:
                    self.nimm(x)
                vermerk("postal", vorhanden[0])
                return
            aid = self.ins("place_attribute", place_id=pid, kind="postal", value=self.wert_ohne_kinder(c) or "",
                           sort=self._sortnr())
            self.kinder(c, holder, {"DATE": lambda d: self.setze("place_attribute", aid, **self.datum(d, holder))},
                        unter="PLAC:_POST")
            vermerk("postal", aid)

        handler = {"MAP": map_, "_GOV": gleich_oder_rest("gov_id", "gov"),
                   "_MAIDENHEAD": gleich_oder_rest("maidenhead", "maidenhead"), "_POST": post}
        for c in k.kinder:
            if c is loc:
                continue
            h = handler.get(c.tag)
            if h is None:
                self.rest(c, holder, "PLAC")
            else:
                h(c)

    # ── Ereignisse ─────────────────────────────────────────────────────────────────────────────────

    def ereignis(self, k: Knoten, traeger: tuple[str, int], rolle: str, sort: int | None = None,
                 negiert: bool = False, typ: str | None = None) -> int:
        self.nimm(k)
        eid = self.ins("event", type=typ or k.tag, value=None if negiert else k.wert, negated=int(negiert))
        h = ("event", eid)
        spalte = {"person": "person_id", "family": "family_id", "place": "place_id"}[traeger[0]]
        haupt = self.ins("event_role", event_id=eid, role=rolle, sort=0,
                         fact_sort=sort if sort is not None else self._sortnr(), **{spalte: traeger[1]})
        unter_nr = [0]

        def nr():
            unter_nr[0] += 1
            return unter_nr[0]

        def asso(c):
            pid = self.id_von("person", c, h)
            if pid is None:
                return
            self.nimm(c)
            rid = self.ins("event_role", event_id=eid, person_id=pid, role="OTHER", sort=nr())
            r = ("event_role", rid)

            def rela(x):
                text = self.wert(x, r)
                self.setze("event_role", rid, rela=text, role=rolle_aus_rela(text))

            self.kinder(c, r, {"RELA": rela, "ROLE": rela, "NOTE": lambda x: self.notiz(x, r),
                               "SOUR": lambda x: self.zitat(x, r)})

        def frei(rolle_):
            def f(c):
                self.nimm(c)
                text = (c.wert or "").strip()
                name, _, zusatz = text.partition(",")
                rid = self.ins("event_role", event_id=eid, role=rolle_, sort=nr(), free_name=name.strip() or text,
                               free_addition=zusatz.strip() or None, free_text=c.wert)
                r = ("event_role", rid)
                self.kinder(c, r, {"NOTE": lambda x: self.notiz(x, r), "SOUR": lambda x: self.zitat(x, r)})
            return f

        def adop_famc(c):
            fid = self.ids.get(("family", c.zeiger or ""))
            wer = (c.wert_von("ADOP") or "BOTH").upper()
            if traeger[0] != "person" or fid is None or wer not in ("HUSB", "WIFE", "BOTH") or any(
                    x.tag != "ADOP" or x.kinder for x in c.kinder):
                self.rest(c, h)
                return
            self.nimm(c)
            for x in c.kinder:
                self.nimm(x)
            self.adoptionen.append((traeger[1], fid, wer))

        einfach = lambda s: (lambda c: self.setze("event", eid, **{s: self.wert(c, h)}))  # noqa: E731
        handler = {
            "TYPE": einfach("subtype"), "CAUS": einfach("cause"), "AGNC": einfach("agency"),
            "DATE": lambda c: self.setze("event", eid, **self.datum(c, h)),
            "PLAC": lambda c: self.plac(c, eid, h),
            "ADDR": lambda c: self.setze("event", eid, address=self.wert(c, h)),
            "AGE": lambda c: self.setze("event_role", haupt, age=self.wert(c, h)),
            "RESN": lambda c: self.resn(c, h, "event"),
            "_ASSO": asso, "ASSO": asso, "_GODP": frei("GODP"), "_WITN": frei("WITN"),
            **{t: v for t, v in self.gemeinsam(h).items() if t in ("NOTE", "SOUR", "OBJE")},
        }
        if k.tag == "ADOP":
            handler["FAMC"] = adop_famc
        self.kinder(k, h, handler)
        return eid

    # ── Personen ───────────────────────────────────────────────────────────────────────────────────

    def person(self, r: Knoten) -> None:
        pid = self.ids[("person", r.xref)]
        h = ("person", pid)
        self.nimm(r)
        reihe = {"famc": 0, "fams": 0, "fakt": 0, "name": 0, "asso": 0}

        def zaehle(art):
            reihe[art] += 1
            return reihe[art]

        def name(c):
            self.nimm(c)
            nid = self.ins("name", person_id=pid, sort=zaehle("name"), value=c.wert or "")
            n = ("name", nid)
            spalte = lambda s: (lambda x: self.setze("name", nid, **{s: self.wert(x, n)}))  # noqa: E731

            def typ(x):
                text = self.wert(x, n)
                self.setze("name", nid, type=(text or "").lower(), type_text=text)

            self.kinder(c, n, {"GIVN": spalte("given"), "SURN": spalte("surname"), "NPFX": spalte("name_prefix"),
                               "SPFX": spalte("surname_prefix"), "NSFX": spalte("name_suffix"),
                               "NICK": spalte("nickname"), "_RUFNAME": spalte("rufname"), "TYPE": typ,
                               "NOTE": lambda x: self.notiz(x, n), "SOUR": lambda x: self.zitat(x, n)})
            # Fehlen GIVN/SURN, aus dem Namen ableiten (Vornamen /Familienname/ Zusatz)
            m = re.match(r"^([^/]*)/([^/]*)/?(.*)$", c.wert or "")
            nm = T("name")
            alt = self.con.execute(select(nm.c.given, nm.c.surname).where(nm.c.id == nid)).one()
            if m and alt[0] is None and m.group(1).strip():
                self.setze("name", nid, given=m.group(1).strip())
            if m and alt[1] is None and m.group(2).strip():
                self.setze("name", nid, surname=m.group(2).strip())

        def sex(c):
            if (c.wert or "").upper() in ("M", "F", "X", "U") and not c.kinder:
                self.setze("person", pid, sex=self.wert(c, h).upper())
            else:
                self.rest(c, h)

        def famc(c):
            fid = self.ids.get(("family", c.zeiger or ""))
            if fid is None:
                self.id_von("family", c, h)
                return
            self.nimm(c)
            daten = {"pedi": None, "status": None, "person_sort": zaehle("famc")}
            unter = f"FAMC @{c.zeiger}@"

            def pedi(x):
                if (x.wert or "").lower() in PEDI and not x.kinder:
                    daten["pedi"] = PEDI[self.wert(x, h).lower()]
                else:
                    self.rest(x, h, unter)

            self.kinder(c, h, {"PEDI": pedi, "STAT": lambda x: daten.update(status=self.wert(x, h))}, unter=unter)
            self.famc[(pid, fid)] = daten

        def fams(c):
            fid = self.ids.get(("family", c.zeiger or ""))
            if fid is None:
                self.id_von("family", c, h)
                return
            self.nimm(c)
            self.fams[(pid, fid)] = zaehle("fams")
            for x in c.kinder:
                self.rest(x, h, f"FAMS @{c.zeiger}@")

        def asso(c):
            other = self.id_von("person", c, h)
            if other is None:
                return
            self.nimm(c)
            aid = self.ins("person_association", person_id=pid, other_person_id=other, sort=zaehle("asso"))
            a = ("person_association", aid)
            self.kinder(c, a, {"RELA": lambda x: self.setze("person_association", aid, relation=self.wert(x, a)),
                               "NOTE": lambda x: self.notiz(x, a), "SOUR": lambda x: self.zitat(x, a)})

        handler = {"NAME": name, "SEX": sex, "FAMC": famc, "FAMS": fams, "ASSO": asso, **self.gemeinsam(h, "person")}
        for tag in EREIGNISSE_PERSON:
            handler[tag] = lambda c: self.ereignis(c, h, "PRINCIPAL", sort=zaehle("fakt"))
        self.kinder(r, h, handler)

    # ── Familien ───────────────────────────────────────────────────────────────────────────────────

    def familie(self, r: Knoten) -> None:
        fid = self.ids[("family", r.xref)]
        h = ("family", fid)
        self.nimm(r)
        partner = self.fam_partner.setdefault(fid, {})
        kinder = self.fam_kinder.setdefault(fid, [])
        reihe = [0]

        def nr():
            reihe[0] += 1
            return reihe[0]

        def partner_(c):
            pid = self.id_von("person", c, h)
            if pid is None:
                return
            platz = 1 if c.tag == "HUSB" else 2
            if platz in partner or pid in partner.values():
                self.rest(c, h)
                return
            self.nimm(c)
            partner[platz] = pid
            for x in c.kinder:
                self.rest(x, h, f"{c.tag} @{c.zeiger}@")

        def kind(c):
            pid = self.id_von("person", c, h)
            if pid is None:
                return
            self.nimm(c)
            daten = {}
            unter = f"CHIL @{c.zeiger}@"

            def rel(x):
                if (x.wert or "").lower() in REL and not x.kinder:
                    daten[x.tag] = REL[self.wert(x, h).lower()]
                else:
                    self.rest(x, h, unter)

            self.kinder(c, h, {"_FREL": rel, "_MREL": rel}, unter=unter)
            kinder.append((pid, daten))

        def stat(c):
            # GEDCOM-L Familienstand. „NOT MARRIED“ ist ein Nicht-Ereignis (KONZEPT 3.3), sonst ein Merkmal der
            # Familie (Ereignis _STAT mit Wert, Notizen, Zitaten); v1 zeigt es als Fakt „Familienstatus“.
            if (c.wert or "").upper() in ("NOT MARRIED", "NEVER MARRIED"):
                self.ereignis(c, h, "PRINCIPAL", sort=nr(), negiert=True, typ="MARR")
            else:
                self.ereignis(c, h, "PRINCIPAL", sort=nr())

        handler = {"HUSB": partner_, "WIFE": partner_, "CHIL": kind, "_STAT": stat, **self.gemeinsam(h, "family")}
        for tag in EREIGNISSE_FAMILIE:
            handler[tag] = lambda c: self.ereignis(c, h, "PRINCIPAL", sort=nr())
        self.kinder(r, h, handler)

    def mitglieder(self) -> None:
        """Mitgliedschaften aus FAM (HUSB/WIFE/CHIL) und INDI (FAMS/FAMC) zusammenführen, Abstammung je Elternteil."""
        for fid, partner in self.fam_partner.items():
            for platz, pid in sorted(partner.items()):
                ps = self.fams.pop((pid, fid), None)
                if ps is None:
                    self.b.familien_einseitig.append(f"Familie {fid}: Partner {pid} ohne FAMS")
                    ps = 1000 + platz
                self.ins("family_member", family_id=fid, person_id=pid, role="partner", sort=platz, person_sort=ps)
        for (pid, fid), ps in self.fams.items():
            self.b.familien_einseitig.append(f"Person {pid}: FAMS zu Familie {fid} ohne HUSB/WIFE")
            partner = self.fam_partner.setdefault(fid, {})
            platz = max([2, *partner]) + 1
            partner[platz] = pid
            self.ins("family_member", family_id=fid, person_id=pid, role="partner", sort=platz, person_sort=ps)

        for fid, kinder in self.fam_kinder.items():
            for i, (pid, rel) in enumerate(kinder, 1):
                daten = self.famc.pop((pid, fid), None)
                if daten is None:
                    self.b.familien_einseitig.append(f"Familie {fid}: Kind {pid} ohne FAMC")
                    daten = {"pedi": None, "status": None, "person_sort": 1000 + i}
                self.ins("family_member", family_id=fid, person_id=pid, role="child", sort=i,
                         person_sort=daten["person_sort"])
                self.abstammung(fid, pid, daten, rel)
        for (pid, fid), daten in self.famc.items():
            self.b.familien_einseitig.append(f"Person {pid}: FAMC zu Familie {fid} ohne CHIL")
            n = len(self.fam_kinder.setdefault(fid, [])) + 1
            self.ins("family_member", family_id=fid, person_id=pid, role="child", sort=n,
                     person_sort=daten["person_sort"])
            self.abstammung(fid, pid, daten, {})

    def abstammung(self, fid: int, kind: int, daten: dict, rel: dict) -> None:
        partner = self.fam_partner.get(fid, {})
        adop = {w for k, f, w in self.adoptionen if k == kind and f == fid}
        for platz, eltern in sorted(partner.items()):
            art = daten["pedi"] or "birth"
            seite = {1: "HUSB", 2: "WIFE"}.get(platz)
            if seite in adop or (seite and "BOTH" in adop):
                art = "adopted"
            eigen = rel.get({1: "_FREL", 2: "_MREL"}.get(platz, ""))
            if eigen:
                art = eigen
            self.ins("parentage", family_id=fid, child_id=kind, parent_id=eltern, kind=art, status=daten["status"])

    def bevorzugte(self) -> None:
        """Je Träger und Ereignisart ist das erste das bevorzugte (KONZEPT 3.3)."""
        er, e = T("event_role").alias("er"), T("event").alias("e")
        er2, e2 = T("event_role").alias("er2"), T("event").alias("e2")
        erste = (select(func.min(er2.c.fact_sort)).select_from(er2.join(e2, e2.c.id == er2.c.event_id))
                 .where(er2.c.role == er.c.role, e2.c.type == e.c.type, e2.c.negated == 0,
                        er2.c.person_id.is_not_distinct_from(er.c.person_id),
                        er2.c.family_id.is_not_distinct_from(er.c.family_id),
                        er2.c.place_id.is_not_distinct_from(er.c.place_id))
                 .scalar_subquery())
        ids = (select(er.c.id).select_from(er.join(e, e.c.id == er.c.event_id))
               .where(and_(er.c.role == "PRINCIPAL", e.c.negated == 0, er.c.fact_sort == erste)))
        rollen = T("event_role")
        # Erst die Kennungen holen, dann ändern: MariaDB erlaubt keine Unterabfrage auf die Tabelle, die es ändert.
        bevorzugt = list(self.con.execute(ids).scalars())
        for i in range(0, len(bevorzugt), 500):
            self.con.execute(update(rollen).where(rollen.c.id.in_(bevorzugt[i:i + 500])).values(preferred=1))


def importieren(gedcom: bytes, ziel: Path, titel: str = "", dateiname: str = "") -> Bericht:
    """GEDCOM 5.5.1 in eine neue Baumdatei. Wirft NichtLesbar; bei Fehlern bleibt keine halbe Datei liegen."""
    d = lesen(gedcom)
    if d.version and not d.version.startswith("5."):
        raise NichtLesbar(f"GEDCOM {d.version}: dieser Importer liest 5.5.1 (7.0 folgt über gedcom7)")
    b = Bericht(datei=dateiname, gedcom_version=d.version, zeichensatz=d.zeichensatz, zeilen_gesamt=d.zeilen,
                lesefehler=d.fehler)
    con = baumdatei.anlegen(ziel, titel)
    try:
        with con.begin():
            imp = Importer(con, d, b)
            imp.ausfuehren()
            imp.ins_meta("import_report", json.dumps(asdict(b), ensure_ascii=False))
    except BaseException:
        con.close()
        for rest in (ziel, ziel.with_name(ziel.name + "-wal"), ziel.with_name(ziel.name + "-shm")):
            rest.unlink(missing_ok=True)
        raise
    con.close()
    return b
