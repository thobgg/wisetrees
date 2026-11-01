"""Leseschicht (KONZEPT.md 5.2, 5.3, E4 a): Baummodell im Speicher, darüber Sichtbarkeit je Rolle.

Keine v1-Route liest an dieser Schicht vorbei. Das Modell enthält nur den angenommenen Stand. Bearbeiter und höher
sehen in den Fakten eines Datensatzes (Individual, Family) zusätzlich die offenen Änderungen
(baum/aenderungen.offener_stand, Fakten mit pending: true); Liste, Suche, Namen in Kurzform und Verwandtschaft
bleiben beim angenommenen Stand (E21). Die Sichtbarkeit wird danach angewendet.

Sichtbarkeit nach den Datenschutz-Einstellungen des Baums (E19, baum/datenschutz.py); die Vorgaben:
  Zugriffsstufen: Besucher 2, Mitglied/Bearbeiter/Moderator 1, Verwalter 0.
  Person: RESN (confidential → nur Verwalter, privacy → ab Mitglied, none → alle); Verwalter sehen alles;
          Verstorbene sehen alle (SHOW_DEAD_PEOPLE = 2); Lebende ab Mitglied.
  Name:   Namen Lebender ab Mitglied (SHOW_LIVING_NAMES = 1) oder wenn die Person sichtbar ist.
  Fakt:   RESN wie oben; Standard-Sperrvermerke SOUR und REPO privacy, SSN confidential.
  Lebend: Regel aus KONZEPT.md 5.2 (self.e.max_alive_age 120, Ableitung über Angehörige).
"""

from __future__ import annotations

import datetime
import os
import threading
from dataclasses import dataclass, field

from sqlalchemy import Connection, select

from baum import datenschutz
from baum.datei import Zeile
from baum.schema import tabelle as T
from gedcom.datum import jd_gregorianisch
from v1.anzeige import jahr_aus_jd

STUFE = {"visitor": 2, "member": 1, "editor": 1, "moderator": 1, "manager": 0}
TOD = ("DEAT", "BURI", "CREM")
GEBURT = ("BIRT", "CHR", "BAPM")


@dataclass(slots=True)
class Ereignis:
    id: int
    type: str
    subtype: str | None
    value: str | None
    negated: bool
    place_id: int | None
    place_text: str | None
    address: str | None
    cause: str | None
    date_text: str | None
    date_from: int | None
    date_to: int | None
    resn: str | None
    rolle_id: int = 0          # event_role der Hauptbeteiligung (v1: factId)
    fact_sort: int = 0

    @property
    def datum_ok(self) -> bool:
        return self.date_from is not None or self.date_to is not None

    @property
    def datum_max(self) -> int | None:
        return self.date_to if self.date_to is not None else self.date_from


@dataclass(slots=True)
class Person:
    id: int
    xref: str
    sex: str
    resn: str | None
    uid: str | None
    namen: list = field(default_factory=list)       # Zeilen aus name, nach sort
    fakten: list[Ereignis] = field(default_factory=list)
    famc: list[int] = field(default_factory=list)  # Familien als Kind, nach person_sort
    fams: list[int] = field(default_factory=list)  # Familien als Partner, nach person_sort
    weitere_daten: list[int] = field(default_factory=list)  # weitere „2 DATE“ (Aufgaben, CHAN): spätester Tag
    medien: list[tuple[int, bool]] = field(default_factory=list)  # (media.id, Hauptbild) nach Reihenfolge
    mit_sex: bool = True       # Geschlecht angegeben (E22); ohne Angabe steht in sex „U“


@dataclass(slots=True)
class Medium:
    id: int
    xref: str | None
    title: str | None
    resn: str | None
    dateien: list[tuple[str, str | None, str | None, str | None]] = field(default_factory=list)  # Pfad, Format, Art, Titel


BILDFORMATE = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff"}


@dataclass(slots=True)
class Familie:
    id: int
    xref: str
    resn: str | None
    uid: str | None
    partner: dict = field(default_factory=dict)     # Platz (1 = HUSB, 2 = WIFE) → person.id
    kinder: list[int] = field(default_factory=list)
    fakten: list[Ereignis] = field(default_factory=list)
    weitere_daten: list[int] = field(default_factory=list)


class Modell:
    """Der angenommene Stand eines Baums im Speicher."""

    def __init__(self, con: Connection):
        self.personen: dict[int, Person] = {}
        self.familien: dict[int, Familie] = {}
        self.person_xref: dict[str, int] = {}
        self.medien: dict[int, Medium] = {}
        self.quellen_resn: dict[int, str | None] = {}
        self.quellen_xref: dict[int, str] = {}
        self.quellen_archive: dict[int, list[int]] = {}      # Quelle → Archive (REPO)
        self.archive: dict[int, tuple[str, str | None]] = {}  # Archiv → (xref, resn)
        self.einst, self.regeln = datenschutz.laden(con)
        # Medium → Datensätze, die es verwenden (auch über Ereignisse und Zitate): ("person"|"family"|"source", id)
        self.medien_traeger: dict[int, set[tuple[str, int]]] = {}
        self.familie_xref: dict[str, int] = {}
        # Was nur vom Baum abhängt (Sortierung der Personenliste, Suchtexte): einmal berechnet, gilt bis zum
        # Neuladen des Modells
        self.zwischen: dict = {}
        gleich: dict[str, str] = {}

        def g(text):
            return gleich.setdefault(text, text) if text else text

        pe, na, fa, fm = T("person"), T("name"), T("family"), T("family_member")
        er, me, mf, ml = T("event_role"), T("media"), T("media_file"), T("media_link")
        for r in con.execute(select(pe.c.id, pe.c.xref, pe.c.sex, pe.c.resn, pe.c.uid)):
            self.personen[r[0]] = Person(r[0], r[1], r[2] or "U", r[3], r[4], mit_sex=r[2] is not None)
            self.person_xref[r[1]] = r[0]
        for r in con.execute(select(na).order_by(na.c.person_id, na.c.sort)):
            self.personen[r.person_id].namen.append(Zeile(r))
        for r in con.execute(select(fa.c.id, fa.c.xref, fa.c.resn, fa.c.uid)):
            self.familien[r[0]] = Familie(r[0], r[1], r[2], r[3])
            self.familie_xref[r[1]] = r[0]
        for r in con.execute(select(fm.c.family_id, fm.c.person_id, fm.c.role, fm.c.sort, fm.c.person_sort)
                             .order_by(fm.c.person_id, fm.c.person_sort)):
            f, p = self.familien[r[0]], self.personen[r[1]]
            if r[2] == "partner":
                f.partner[r[3]] = p.id
                p.fams.append(f.id)
            else:
                p.famc.append(f.id)
        kinder: dict[int, list[int]] = {}
        for r in con.execute(select(fm.c.family_id, fm.c.person_id).where(fm.c.role == "child")
                             .order_by(fm.c.family_id, fm.c.sort)):
            kinder.setdefault(r[0], []).append(r[1])
        for f in self.familien.values():
            f.kinder = kinder.get(f.id, [])
        for r in con.execute(_ereignisse().where((er.c.person_id.is_not(None)) | (er.c.family_id.is_not(None)))):
            (self.personen[r[15]] if r[15] else self.familien[r[16]]).fakten.append(_ereignis(r, g))
        for r in con.execute(select(me.c.id, me.c.xref, me.c.title, me.c.resn)):
            self.medien[r[0]] = Medium(r[0], r[1], r[2], r[3])
        for r in con.execute(select(mf.c.media_id, mf.c.path, mf.c.format, mf.c.media_type, mf.c.title)
                             .order_by(mf.c.media_id, mf.c.sort)):
            self.medien[r[0]].dateien.append((r[1], r[2], r[3], r[4]))
        for r in con.execute(select(ml.c.person_id, ml.c.media_id, ml.c.is_primary)
                             .where(ml.c.person_id.is_not(None)).order_by(ml.c.sort)):
            self.personen[r[0]].medien.append((r[1], bool(r[2])))
        so, ta = T("source"), T("task")
        for r in con.execute(select(so.c.id, so.c.resn, so.c.xref)):
            self.quellen_resn[r[0]] = r[1]
            self.quellen_xref[r[0]] = r[2]
        re_, sr = T("repository"), T("source_repository")
        for r in con.execute(select(re_.c.id, re_.c.xref, re_.c.resn)):
            self.archive[r[0]] = (r[1], r[2])
        for r in con.execute(select(sr.c.source_id, sr.c.repository_id).where(sr.c.repository_id.is_not(None))
                             .order_by(sr.c.sort)):
            self.quellen_archive.setdefault(r[0], []).append(r[1])
        self._medien_traeger(con)
        for r in con.execute(select(ta.c.person_id, ta.c.family_id, ta.c.date_from, ta.c.date_to)
                             .where(ta.c.date_from.is_not(None))):
            ziel = self.personen.get(r[0]) if r[0] else self.familien.get(r[1])
            if ziel is not None:
                ziel.weitere_daten.append(r[3] if r[3] is not None else r[2])


    def _medien_traeger(self, con: Connection) -> None:
        """Welcher Datensatz verweist irgendwo in sich (auch über Ereignisse und Zitate) auf das Medium."""
        er, na, ci, ml = T("event_role"), T("name"), T("citation"), T("media_link")
        haupt = {r[0]: (("person", r[1]) if r[1] else ("family", r[2]) if r[2] else None) for r in con.execute(
            select(er.c.event_id, er.c.person_id, er.c.family_id).where(er.c.role == "PRINCIPAL"))}
        rolle_ereignis = {r[0]: r[1] for r in con.execute(select(er.c.id, er.c.event_id))}
        name_person = {r[0]: r[1] for r in con.execute(select(na.c.id, na.c.person_id))}
        zitat = {r[0]: tuple(r[1:]) for r in con.execute(
            select(ci.c.id, ci.c.person_id, ci.c.family_id, ci.c.name_id, ci.c.event_id, ci.c.event_role_id))}

        def datensatz(person=None, family=None, source=None, event=None, citation=None, name=None, event_role=None):
            if person:
                return ("person", person)
            if family:
                return ("family", family)
            if source:
                return ("source", source)
            if name:
                return ("person", name_person.get(name))
            if event_role:
                event = rolle_ereignis.get(event_role)
            if event:
                return haupt.get(event)
            if citation and citation in zitat:
                p, f, n, e, er_ = zitat[citation]
                return datensatz(person=p, family=f, name=n, event=e, event_role=er_)
            return None

        for r in con.execute(select(ml.c.media_id, ml.c.person_id, ml.c.family_id, ml.c.source_id, ml.c.event_id,
                                    ml.c.citation_id)):
            d = datensatz(person=r[1], family=r[2], source=r[3], event=r[4], citation=r[5])
            if d and d[1]:
                self.medien_traeger.setdefault(r[0], set()).add(d)


def _ereignisse():
    """Hauptbeteiligungen an Ereignissen, nach Platz am Datensatz."""
    ev, er = T("event"), T("event_role")
    return (select(ev.c.id, ev.c.type, ev.c.subtype, ev.c.value, ev.c.negated, ev.c.place_id, ev.c.place_text,
                   ev.c.address, ev.c.cause, ev.c.date_text, ev.c.date_from, ev.c.date_to, ev.c.resn, er.c.id,
                   er.c.fact_sort, er.c.person_id, er.c.family_id)
            .select_from(er.join(ev, ev.c.id == er.c.event_id)).where(er.c.role == "PRINCIPAL")
            .order_by(er.c.fact_sort))


def _ereignis(r, g=lambda x: x) -> Ereignis:
    # g: wiederkehrende Texte (Art, Ort, Ursache, Sperrvermerk …) nur einmal im Speicher halten
    return Ereignis(r[0], g(r[1]), g(r[2]), g(r[3]), bool(r[4]), r[5], g(r[6]), g(r[7]), g(r[8]), g(r[9]),
                    r[10], r[11], g(r[12]), rolle_id=r[13], fact_sort=r[14])


def ereignisse_aus(con: Connection, spalte: str, wert: int) -> list[Ereignis]:
    """Ereignisse eines Datensatzes direkt aus der Datenbank (für den Stand mit offenen Änderungen)."""
    return [_ereignis(r) for r in con.execute(_ereignisse().where(T("event_role").c[spalte] == wert))]


def namen_aus(con: Connection, person_id: int) -> list[Zeile]:
    na = T("name")
    return [Zeile(r) for r in con.execute(select(na).where(na.c.person_id == person_id).order_by(na.c.sort))]


_CACHE: dict[str, tuple[float, Modell]] = {}
_LOCK = threading.Lock()


def modell(pfad: str, oeffnen) -> Modell:
    """Modell eines Baums, neu geladen, sobald sich die Datei ändert."""
    stand = max(os.path.getmtime(p) for p in (pfad, pfad + "-wal") if os.path.exists(p))
    with _LOCK:
        alt = _CACHE.get(pfad)
        if alt and alt[0] == stand:
            return alt[1]
    con = oeffnen()
    try:
        m = Modell(con)
    finally:
        con.close()
    with _LOCK:
        _CACHE[pfad] = (stand, m)
    return m


class Sicht:
    """Ein Baum, gesehen mit einer Zugriffsstufe (0 Verwalter, 1 Mitglied, 2 Besucher) an einem Tag."""

    def __init__(self, m: Modell, stufe: int, heute: datetime.date, eigene: str = "", pfad: int = 0):
        self.m, self.stufe = m, stufe
        # E19 B: eigene Person des Kontos („Das bin ich“) und Verwandtschaftsschutz in Schritten
        self.eigene = m.person_xref.get(eigene) if eigene else None
        self.pfad = pfad
        self._verwandte: set[int] | None = None
        self.e, self.r = m.einst, m.regeln
        self.heute_jahr = heute.year
        self.heute_jd = jd_gregorianisch(heute.year, heute.month, heute.day)
        self._tot: dict[int, bool] = {}

    # ── Lebend oder tot (KONZEPT 5.2) ──────────────────────────────────────────────────────────────

    def _daten(self, p: Person) -> list[int]:
        return [e.datum_max for e in p.fakten if e.datum_ok and not e.negated] + p.weitere_daten

    def _familien_daten(self, f: Familie) -> list[int]:
        return [e.datum_max for e in f.fakten if e.datum_ok and not e.negated] + f.weitere_daten

    def ist_tot(self, pid: int) -> bool:
        if pid not in self._tot:
            self._tot[pid] = self._ist_tot(self.m.personen[pid])
        return self._tot[pid]

    def _ist_tot(self, p: Person) -> bool:
        grenze = lambda jahre: self.heute_jd - 365 * jahre  # noqa: E731
        for e in p.fakten:
            if e.type in TOD and not e.negated and ((e.value or "").upper() == "Y" or e.date_text or e.place_text):
                return True
        daten = self._daten(p)
        if daten:
            if any(d <= grenze(self.e.max_alive_age) for d in daten):
                return True
            if any(e.type == "BIRT" and e.date_text for e in p.fakten):
                return False
        for fid in p.famc:
            for eltern in self.m.familien[fid].partner.values():
                if any(d <= grenze(self.e.max_alive_age + 45) for d in self._daten(self.m.personen[eltern])):
                    return True
        for fid in p.fams:
            f = self.m.familien[fid]
            if any(d <= grenze(self.e.max_alive_age - 10) for d in self._familien_daten(f)):
                return True
            for partner in f.partner.values():
                if partner != p.id and any(d <= grenze(self.e.max_alive_age + 40) for d in self._daten(self.m.personen[partner])):
                    return True
            for kind in f.kinder:
                k = self.m.personen[kind]
                if any(d <= grenze(self.e.max_alive_age - 15) for d in self._daten(k)):
                    return True
                for kf in k.fams:
                    for enkel in self.m.familien[kf].kinder:
                        if any(d <= grenze(self.e.max_alive_age - 30) for d in self._daten(self.m.personen[enkel])):
                            return True
        return False

    # ── Sichtbarkeit ───────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resn(resn: str | None, stufe: int) -> bool | None:
        if resn == "confidential":
            return stufe <= 0
        if resn == "privacy":
            return stufe <= 1
        if resn == "none":
            return True
        return None

    def _datensatz(self, xref: str | None, resn: str | None, stufe: int) -> bool | None:
        """Was für jeden Datensatz zuerst gilt: Schutz aus, Sperrvermerk, Regel für den Datensatz, Verwalter.
        None = die Regeln der Datensatzart entscheiden."""
        if not self.e.enabled:
            return True
        r = self._resn(resn, stufe)
        if r is not None:
            return r
        if xref and xref in self.r.datensatz:
            return self.r.datensatz[xref] >= stufe
        if stufe <= 0:
            return True
        return None

    def _art(self, art: str, stufe: int) -> bool:
        """Regel für eine Datensatzart (SOUR, REPO, OBJE, NOTE …); ohne Regel öffentlich."""
        return self.r.art[art] >= stufe if art in self.r.art else True

    def _noch_geschuetzt(self, p: Person) -> bool:
        """Verstorbene bleiben privat, solange Geburt oder Tod jünger sind als eingestellt."""
        for jahre, arten in ((self.e.keep_alive_years_birth, GEBURT), (self.e.keep_alive_years_death, TOD)):
            if jahre:
                for e in p.fakten:
                    if (e.type in arten and e.date_from is not None and e.date_to is not None
                            and jahr_aus_jd((e.date_from + e.date_to) // 2) + jahre > self.heute_jahr):
                        return True
        return False

    def person_darf(self, pid: int, stufe: int | None = None) -> bool:
        stufe = self.stufe if stufe is None else stufe
        p = self.m.personen[pid]
        # Die eigene Person ist immer sichtbar – vor Sperrvermerk und Regeln, aber nur mit der eigenen Stufe.
        if self.e.enabled and pid == self.eigene and stufe == self.stufe:
            return True
        r = self._datensatz(p.xref, p.resn, stufe)
        if r is not None:
            return r
        if self.e.show_dead_people >= stufe and self.ist_tot(pid) and not self._noch_geschuetzt(p):
            return True
        if self.eigene is not None and self.pfad > 0:
            # Verwandtschaftsschutz: Lebende nur, wenn nah genug verwandt – unabhängig von der Stufe
            return pid in self.verwandte()
        return stufe <= 1

    def verwandte(self) -> set[int]:
        """Personen bis self.pfad Schritte von der eigenen Person; ein Schritt ist Person → Familie → Person
        (Eltern, Partner, Kinder, Geschwister über die gemeinsame Familie)."""
        if self._verwandte is None:
            gesehen, rand = {self.eigene}, {self.eigene}
            for _ in range(self.pfad):
                neu = set()
                for pid in rand:
                    p = self.m.personen[pid]
                    for fid in (*p.famc, *p.fams):
                        f = self.m.familien[fid]
                        neu.update(q for q in (*f.partner.values(), *f.kinder) if q not in gesehen)
                gesehen |= neu
                rand = neu
            self._verwandte = gesehen
        return self._verwandte

    def name_darf(self, pid: int, stufe: int | None = None) -> bool:
        stufe = self.stufe if stufe is None else stufe
        return self.e.show_living_names >= stufe or self.person_darf(pid, stufe)

    def familie_darf(self, fid: int, stufe: int | None = None) -> bool:
        """Familie: sichtbar, wenn alle Mitglieder sichtbar sind (nach Sperrvermerk und Regeln)."""
        stufe = self.stufe if stufe is None else stufe
        f = self.m.familien[fid]
        r = self._datensatz(f.xref, f.resn, stufe)
        if r is not None:
            return r
        return all(self.person_darf(p, stufe) for p in [*f.partner.values(), *f.kinder])

    def archiv_darf(self, rid: int, stufe: int | None = None) -> bool:
        stufe = self.stufe if stufe is None else stufe
        xref, resn = self.m.archive[rid]
        r = self._datensatz(xref, resn, stufe)
        return r if r is not None else self._art("REPO", stufe)

    def quelle_darf(self, sid: int, stufe: int | None = None) -> bool:
        """Quelle: verborgen, wenn eines ihrer Archive verborgen ist; sonst die Regel für Quellen."""
        stufe = self.stufe if stufe is None else stufe
        if sid not in self.m.quellen_resn:
            return False
        r = self._datensatz(self.m.quellen_xref.get(sid), self.m.quellen_resn[sid], stufe)
        if r is not None:
            return r
        if any(not self.archiv_darf(a, stufe) for a in self.m.quellen_archive.get(sid, ())):
            return False
        return self._art("SOUR", stufe)

    def medium_darf(self, mid: int, stufe: int | None = None) -> bool:
        """Medium: verborgen, wenn ein Datensatz, der es verwendet, verborgen ist; sonst die Regel für Medien."""
        stufe = self.stufe if stufe is None else stufe
        med = self.m.medien[mid]
        r = self._datensatz(med.xref, med.resn, stufe)
        if r is not None:
            return r
        for art, id_ in self.m.medien_traeger.get(mid, ()):
            if art == "person" and not self.person_darf(id_, stufe):
                return False
            if art == "family" and not self.familie_darf(id_, stufe):
                return False
            if art == "source" and not self.quelle_darf(id_, stufe):
                return False
        return self._art("OBJE", stufe)

    def notiz_darf(self, xref: str | None, resn: str | None, stufe: int | None = None) -> bool:
        """Notiz als eigener Datensatz (mit Kennung); eingebettete Notizen folgen ihrem Fakt."""
        stufe = self.stufe if stufe is None else stufe
        if xref is None:
            return self.fakt_darf("NOTE", resn, stufe)
        r = self._datensatz(xref, resn, stufe)
        return r if r is not None else self._art("NOTE", stufe)

    # ── Familienstruktur (Einstellung „private Beziehungen zeigen“) ─────────────────────────────────

    def als_kind(self, pid: int) -> list[int]:
        """Familien, in denen die Person Kind ist; ohne die Einstellung nur sichtbare."""
        fs = self.m.personen[pid].famc
        return list(fs) if self.e.show_private_relationships else [f for f in fs if self.familie_darf(f)]

    def als_partner(self, pid: int) -> list[int]:
        fs = self.m.personen[pid].fams
        return list(fs) if self.e.show_private_relationships else [f for f in fs if self.familie_darf(f)]

    def kinder(self, fid: int) -> list[int]:
        ks = self.m.familien[fid].kinder
        return list(ks) if self.e.show_private_relationships else [k for k in ks if self.name_darf(k)]

    def partner(self, fid: int) -> dict[int, int]:
        """Platz (1 = HUSB, 2 = WIFE) → Person; ohne die Einstellung nur Partner, deren Name sichtbar ist."""
        ps = self.m.familien[fid].partner
        return dict(ps) if self.e.show_private_relationships else {k: q for k, q in ps.items() if self.name_darf(q)}

    def person_sichtbar(self, xref: str) -> bool:
        pid = self.m.person_xref.get(xref)
        return pid is not None and self.person_darf(pid)

    def fakt_darf(self, tag: str, resn: str | None, stufe: int | None = None, xref: str | None = None) -> bool:
        """Fakt: Sperrvermerk, dann Regel für diese Faktart an diesem Datensatz, dann Regel für die Faktart.
        Gilt auch bei ausgeschaltetem Schutz."""
        stufe = self.stufe if stufe is None else stufe
        r = self._resn(resn, stufe)
        if r is not None:
            return r
        if xref and (xref, tag) in self.r.fakt_am_datensatz:
            return self.r.fakt_am_datensatz[(xref, tag)] >= stufe
        if tag in self.r.art:
            return self.r.art[tag] >= stufe
        return True


def nur_mitglieder(b) -> bool:
    """Ist der Baum nur für Mitglieder (Einstellung members_only)?"""
    return modell(str(b.pfad), b.oeffnen).einst.members_only


def sieht_offenes(rolle: str) -> bool:
    """Offene Änderungen sehen Bearbeiter, Moderatoren und Verwalter; Besucher und Mitglieder nie."""
    return rolle in ("editor", "moderator", "manager")


def sicht_fuer(ctx, baum_name: str) -> Sicht:
    b = ctx.app.state.baeume.baum(baum_name)
    m = modell(str(b.pfad), b.oeffnen)
    rolle = ctx.konten.rolle(ctx.konto, baum_name)
    kb = ctx.konten.kontobaum(ctx.konto, baum_name)
    return Sicht(m, STUFE[rolle], ctx.einstellungen.heute(), kb.person, kb.pfad)
