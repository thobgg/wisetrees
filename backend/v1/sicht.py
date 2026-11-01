"""Leseschicht (KONZEPT.md 5.2, 5.3, E4 a): Baummodell im Speicher, darüber Sichtbarkeit je Rolle.

Keine v1-Route liest an dieser Schicht vorbei. Offene Änderungen werden hier später über den angenommenen Stand
gelegt (Änderungssätze, nur für Bearbeiter und höher); die Sichtbarkeit wird danach angewendet.

Sichtbarkeit mit den Vorgaben eines neuen Baums:
  Zugriffsstufen: Besucher 2, Mitglied/Bearbeiter/Moderator 1, Verwalter 0.
  Person: RESN (confidential → nur Verwalter, privacy → ab Mitglied, none → alle); Verwalter sehen alles;
          Verstorbene sehen alle (SHOW_DEAD_PEOPLE = 2); Lebende ab Mitglied.
  Name:   Namen Lebender ab Mitglied (SHOW_LIVING_NAMES = 1) oder wenn die Person sichtbar ist.
  Fakt:   RESN wie oben; Standard-Sperrvermerke SOUR und REPO privacy, SSN confidential.
  Lebend: Regel aus KONZEPT.md 5.2 (MAX_ALIVE_AGE 120, Ableitung über Angehörige).
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import threading
from dataclasses import dataclass, field

from gedcom.datum import jd_gregorianisch

MAX_ALIVE_AGE = 120
SHOW_DEAD_PEOPLE = 2
SHOW_LIVING_NAMES = 1
FAKT_SPERRE = {"SSN": 0, "SOUR": 1, "REPO": 1, "SUBM": 0, "SUBN": 0}
STUFE = {"visitor": 2, "member": 1, "editor": 1, "moderator": 1, "manager": 0}
TOD = ("DEAT", "BURI", "CREM")


@dataclass
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


@dataclass
class Person:
    id: int
    xref: str
    sex: str
    resn: str | None
    uid: str | None
    namen: list = field(default_factory=list)       # sqlite3.Row aus name, nach sort
    fakten: list[Ereignis] = field(default_factory=list)
    famc: list[int] = field(default_factory=list)  # Familien als Kind, nach person_sort
    fams: list[int] = field(default_factory=list)  # Familien als Partner, nach person_sort
    weitere_daten: list[int] = field(default_factory=list)  # weitere „2 DATE“ (Aufgaben, CHAN): spätester Tag
    medien: list[tuple[int, bool]] = field(default_factory=list)  # (media.id, Hauptbild) nach Reihenfolge


@dataclass
class Medium:
    id: int
    xref: str | None
    title: str | None
    resn: str | None
    dateien: list[tuple[str, str | None, str | None, str | None]] = field(default_factory=list)  # Pfad, Format, Art, Titel


BILDFORMATE = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff"}


@dataclass
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

    def __init__(self, con: sqlite3.Connection):
        self.personen: dict[int, Person] = {}
        self.familien: dict[int, Familie] = {}
        self.person_xref: dict[str, int] = {}
        self.medien: dict[int, Medium] = {}
        self.quellen_resn: dict[int, str | None] = {}
        # Medium → Datensätze, die es verwenden (auch über Ereignisse und Zitate): ("person"|"family"|"source", id)
        self.medien_traeger: dict[int, set[tuple[str, int]]] = {}
        self.familie_xref: dict[str, int] = {}
        for r in con.execute("SELECT id, xref, sex, resn, uid FROM person"):
            self.personen[r[0]] = Person(r[0], r[1], r[2], r[3], r[4])
            self.person_xref[r[1]] = r[0]
        for r in con.execute("SELECT * FROM name ORDER BY person_id, sort"):
            self.personen[r["person_id"]].namen.append(r)
        for r in con.execute("SELECT id, xref, resn, uid FROM family"):
            self.familien[r[0]] = Familie(r[0], r[1], r[2], r[3])
            self.familie_xref[r[1]] = r[0]
        for r in con.execute("SELECT family_id, person_id, role, sort, person_sort FROM family_member "
                             "ORDER BY person_id, person_sort"):
            f, p = self.familien[r[0]], self.personen[r[1]]
            if r[2] == "partner":
                f.partner[r[3]] = p.id
                p.fams.append(f.id)
            else:
                p.famc.append(f.id)
        for f in self.familien.values():
            f.kinder = [r[0] for r in con.execute(
                "SELECT person_id FROM family_member WHERE family_id = ? AND role = 'child' ORDER BY sort", (f.id,))]
        for r in con.execute("""
                SELECT e.id, e.type, e.subtype, e.value, e.negated, e.place_id, e.place_text, e.address, e.cause,
                       e.date_text, e.date_from, e.date_to, e.resn, er.id, er.fact_sort, er.person_id, er.family_id
                FROM event_role er JOIN event e ON e.id = er.event_id
                WHERE er.role = 'PRINCIPAL' AND (er.person_id IS NOT NULL OR er.family_id IS NOT NULL)
                ORDER BY er.fact_sort"""):
            e = Ereignis(r[0], r[1], r[2], r[3], bool(r[4]), r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12],
                         rolle_id=r[13], fact_sort=r[14])
            (self.personen[r[15]] if r[15] else self.familien[r[16]]).fakten.append(e)
        for r in con.execute("SELECT id, xref, title, resn FROM media"):
            self.medien[r[0]] = Medium(r[0], r[1], r[2], r[3])
        for r in con.execute("SELECT media_id, path, format, media_type, title FROM media_file ORDER BY media_id, sort"):
            self.medien[r[0]].dateien.append((r[1], r[2], r[3], r[4]))
        for r in con.execute("SELECT person_id, media_id, is_primary FROM media_link WHERE person_id IS NOT NULL ORDER BY sort"):
            self.personen[r[0]].medien.append((r[1], bool(r[2])))
        for r in con.execute("SELECT id, resn FROM source"):
            self.quellen_resn[r[0]] = r[1]
        self._medien_traeger(con)
        for r in con.execute("SELECT person_id, family_id, date_from, date_to FROM task WHERE date_from IS NOT NULL"):
            ziel = self.personen.get(r[0]) if r[0] else self.familien.get(r[1])
            if ziel is not None:
                ziel.weitere_daten.append(r[3] if r[3] is not None else r[2])


    def _medien_traeger(self, con: sqlite3.Connection) -> None:
        """Welcher Datensatz verweist irgendwo in sich (auch über Ereignisse und Zitate) auf das Medium."""
        haupt = {r[0]: (("person", r[1]) if r[1] else ("family", r[2]) if r[2] else None) for r in con.execute(
            "SELECT event_id, person_id, family_id FROM event_role WHERE role = 'PRINCIPAL'")}
        rolle_ereignis = dict(con.execute("SELECT id, event_id FROM event_role"))
        name_person = dict(con.execute("SELECT id, person_id FROM name"))
        zitat = {r[0]: r[1:] for r in con.execute(
            "SELECT id, person_id, family_id, name_id, event_id, event_role_id FROM citation")}

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
                p, f, n, e, er = zitat[citation]
                return datensatz(person=p, family=f, name=n, event=e, event_role=er)
            return None

        for r in con.execute("SELECT media_id, person_id, family_id, source_id, event_id, citation_id FROM media_link"):
            d = datensatz(person=r[1], family=r[2], source=r[3], event=r[4], citation=r[5])
            if d and d[1]:
                self.medien_traeger.setdefault(r[0], set()).add(d)


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

    def __init__(self, m: Modell, stufe: int, heute: datetime.date):
        self.m, self.stufe = m, stufe
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
            if any(d <= grenze(MAX_ALIVE_AGE) for d in daten):
                return True
            if any(e.type == "BIRT" and e.date_text for e in p.fakten):
                return False
        for fid in p.famc:
            for eltern in self.m.familien[fid].partner.values():
                if any(d <= grenze(MAX_ALIVE_AGE + 45) for d in self._daten(self.m.personen[eltern])):
                    return True
        for fid in p.fams:
            f = self.m.familien[fid]
            if any(d <= grenze(MAX_ALIVE_AGE - 10) for d in self._familien_daten(f)):
                return True
            for partner in f.partner.values():
                if partner != p.id and any(d <= grenze(MAX_ALIVE_AGE + 40) for d in self._daten(self.m.personen[partner])):
                    return True
            for kind in f.kinder:
                k = self.m.personen[kind]
                if any(d <= grenze(MAX_ALIVE_AGE - 15) for d in self._daten(k)):
                    return True
                for kf in k.fams:
                    for enkel in self.m.familien[kf].kinder:
                        if any(d <= grenze(MAX_ALIVE_AGE - 30) for d in self._daten(self.m.personen[enkel])):
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

    def person_darf(self, pid: int, stufe: int | None = None) -> bool:
        stufe = self.stufe if stufe is None else stufe
        p = self.m.personen[pid]
        r = self._resn(p.resn, stufe)
        if r is not None:
            return r
        if stufe <= 0:
            return True
        if stufe <= SHOW_DEAD_PEOPLE and self.ist_tot(pid):
            return True
        return stufe <= 1

    def name_darf(self, pid: int, stufe: int | None = None) -> bool:
        stufe = self.stufe if stufe is None else stufe
        return stufe <= SHOW_LIVING_NAMES or self.person_darf(pid, stufe)

    def familie_darf(self, fid: int, stufe: int | None = None) -> bool:
        """Familie: RESN, Verwalter sehen alles, sonst nur, wenn alle Mitglieder sichtbar sind."""
        stufe = self.stufe if stufe is None else stufe
        f = self.m.familien[fid]
        r = self._resn(f.resn, stufe)
        if r is not None:
            return r
        if stufe <= 0:
            return True
        return all(self.person_darf(p, stufe) for p in [*f.partner.values(), *f.kinder])

    def quelle_darf(self, sid: int, stufe: int | None = None) -> bool:
        return sid in self.m.quellen_resn and self.fakt_darf("SOUR", self.m.quellen_resn[sid], stufe)

    def medium_darf(self, mid: int, stufe: int | None = None) -> bool:
        """Medium: RESN, Verwalter alles; sonst verborgen, wenn ein Datensatz, der es verwendet, verborgen ist
        """
        stufe = self.stufe if stufe is None else stufe
        r = self._resn(self.m.medien[mid].resn, stufe)
        if r is not None:
            return r
        if stufe <= 0:
            return True
        for art, id_ in self.m.medien_traeger.get(mid, ()):
            if art == "person" and not self.person_darf(id_, stufe):
                return False
            if art == "family" and not self.familie_darf(id_, stufe):
                return False
            if art == "source" and not self.quelle_darf(id_, stufe):
                return False
        return True

    def person_sichtbar(self, xref: str) -> bool:
        pid = self.m.person_xref.get(xref)
        return pid is not None and self.person_darf(pid)

    def fakt_darf(self, tag: str, resn: str | None, stufe: int | None = None) -> bool:
        stufe = self.stufe if stufe is None else stufe
        r = self._resn(resn, stufe)
        if r is not None:
            return r
        if tag in FAKT_SPERRE:
            return FAKT_SPERRE[tag] >= stufe
        return True


def sicht_fuer(ctx, baum_name: str) -> Sicht:
    b = ctx.app.state.baeume.baum(baum_name)
    m = modell(str(b.pfad), b.oeffnen)
    rolle = ctx.konten.rolle(ctx.konto, baum_name)
    return Sicht(m, STUFE[rolle], ctx.einstellungen.heute())
