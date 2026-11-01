"""v1: Kurzform einer Person (personSummary) und die Personenliste (GET Individuals).

Felder nach vertrag/api-v1.json; Regeln für sichtbare Fakten, erste Geburts-/Todesangabe und Hauptbild nach
docs/API-V1.md.
"""

from __future__ import annotations

import unicodedata

from . import anzeige
from .http import GET_AKTIONEN, Kontext, fehler
from .sicht import BILDFORMATE, Lesestand, Person, Sicht, sicht_fuer

SEITE = 50
GEBURT = ("BIRT", "CHR", "BAPM")
TOD = ("DEAT", "BURI", "CREM")
LEBENSDATEN = ("BIRT", "CHR", "BAPM", "DEAT", "BURI", "CREM", "OCCU")


class Bau:
    """Baut v1-JSON für einen Baum aus einer Sicht."""

    def __init__(self, ctx: Kontext, sicht: Sicht):
        self.ctx, self.s, self.m = ctx, sicht, sicht.m

    # ── Hilfen ─────────────────────────────────────────────────────────────────────────────────────

    def sichtbare_fakten(self, p: Person, tags: tuple[str, ...] | None = None, stufe: int | None = None) -> list:
        """Nichts für unsichtbare Personen, sonst die erlaubten Fakten."""
        if not self.s.person_darf(p.id, stufe):
            return []
        return [e for e in p.fakten if not e.negated and (tags is None or e.type in tags)
                and self.s.fakt_darf(e.type, e.resn, stufe, p.xref)]

    def erstes_datum(self, p: Person, tags: tuple[str, ...]) -> str | None:
        for tag in tags:  # erste Ereignisart mit gültigem Datum, darin das erste
            for e in self.sichtbare_fakten(p, (tag,)):
                if anzeige.datum_grenzen(e.date_text):
                    return e.date_text
        return None

    def erster_ort(self, p: Person, tags: tuple[str, ...]) -> str | None:
        for tag in tags:
            orte = [e.place_text for e in self.sichtbare_fakten(p, (tag,)) if e.place_text]
            if orte:
                return orte[0]
        return None

    @staticmethod
    def ort_json(text: str | None, lat=None, lng=None) -> dict | None:
        if not text:
            return None
        return {"name": text, "short": text, "lat": lat, "lng": lng}

    def ereignis_json(self, date_text: str | None, place_text: str | None) -> dict | None:
        d, o = anzeige.datum_json(date_text), self.ort_json(place_text)
        return None if d is None and o is None else {"date": d, "place": o}

    def zugang(self, pid: int) -> str:
        if self.s.person_darf(pid, 2):
            return "visitor"
        return "member" if self.s.person_darf(pid, 1) else "manager"

    def name_zugang(self, pid: int) -> str:
        if self.s.name_darf(pid, 2):
            return "visitor"
        return "member" if self.s.name_darf(pid, 1) else "manager"

    def eingeschraenkt(self, p: Person) -> list[str]:
        if not self.s.person_darf(p.id, 2):
            return []
        tags = []
        for e in self.sichtbare_fakten(p, LEBENSDATEN):
            if not self.s.fakt_darf(e.type, e.resn, 2, p.xref) and e.type not in tags:
                tags.append(e.type)
        return tags

    def name(self, p: Person) -> str:
        if not self.s.name_darf(p.id):
            return anzeige.PRIVAT
        if not p.namen:
            return f"{anzeige.UNBEKANNT} {anzeige.UNBEKANNT}"     # Person ohne Namen: Vor- und Nachname unbekannt
        n = p.namen[0]
        text = anzeige.voller_name(n["value"])
        nick = (n["nickname"] or "").strip()
        if nick and f'"{nick}"' not in text:
            # Spitzname aus 2 NICK in Anführungszeichen hinter die Vornamen, nicht doppelt
            vor, nach, zusatz = anzeige.name_teile(n["value"])
            vor = anzeige.unbekannt(vor) or anzeige.UNBEKANNT
            text = " ".join(x for x in (vor, f'"{nick}"', anzeige.unbekannt(nach), zusatz) if x)
        return text

    def sort_name(self, p: Person) -> str:
        if not self.s.name_darf(p.id):
            return "," + anzeige.PRIVAT   # nichts vom echten Namen, auch nicht zum Sortieren
        if not p.namen:
            return anzeige.UNBEKANNT + "," + anzeige.UNBEKANNT
        n = p.namen[0]
        nach = " ".join(x for x in (n["surname_prefix"], n["surname"]) if x) or "@N.N."
        return anzeige.unbekannt(f"{nach},{n['given'] or '@P.N.'}")

    def hauptbild(self, p: Person):
        if not self.s.person_darf(p.id):
            return None
        for mid, _ in p.medien:
            med = self.m.medien[mid]
            if not self.s.medium_darf(mid):
                continue
            for pfad, fmt, _typ, _t in med.dateien:
                if (fmt or pfad.rsplit(".", 1)[-1]).lower() in BILDFORMATE:
                    return med, pfad
        return None

    def bild_url(self, med) -> str:
        return self.ctx.adresse(f"/wisetrees/medien/{self.ctx.baum_name}/{med.xref or med.id}")

    def seiten_url(self) -> str:
        """Ziel der url-Felder: die Startseite (wisetrees hat keine eigenen Datensatzseiten)."""
        return self.ctx.basis() + "/index.php"

    # ── Kurzform ───────────────────────────────────────────────────────────────────────────────────

    def person_kurz(self, pid: int, mit_zahlen: bool = False) -> dict:
        p = self.m.personen[pid]
        name_ok = self.s.name_darf(pid)
        n = p.namen[0] if p.namen else None
        geburt, tod = self.erstes_datum(p, GEBURT), self.erstes_datum(p, TOD)
        if pid in self.m.geloescht:
            geburt = tod = None        # offen gelöscht: Orte ja, Daten nicht (wie die Referenz)
        tot = self.s.ist_tot(pid)
        chr_ = next(iter(self.sichtbare_fakten(p, ("CHR",))), None) or next(iter(self.sichtbare_fakten(p, ("BAPM",))), None)
        buri = next(iter(self.sichtbare_fakten(p, ("BURI",))), None) or next(iter(self.sichtbare_fakten(p, ("CREM",))), None)
        beruf = next((e.value for e in self.sichtbare_fakten(p, ("OCCU",)) if e.value), None)
        bild = self.hauptbild(p)
        j = {
            "xref": p.xref,
            "name": self.name(p),
            "sortName": self.sort_name(p),
            "given": (n["given"] or "") if (n and name_ok) else "",
            "surname": " ".join(x for x in (n["surname_prefix"], n["surname"]) if x) if (n and name_ok) else "",
            "sex": p.sex,
            "isDead": tot,
            "private": not self.s.person_darf(pid),
            "access": self.zugang(pid),
            "nameAccess": self.name_zugang(pid),
            "restricted": self.eingeschraenkt(p),
            "lifespan": anzeige.lebensspanne(geburt, tod, tot),
            "birth": self.ereignis_json(geburt, self.erster_ort(p, GEBURT)),
            "death": self.ereignis_json(tod, self.erster_ort(p, TOD)),
            "call": (n["rufname"] or "") if (n and name_ok and self.s.person_darf(pid)) else "",
            "chr": self.ereignis_json(chr_.date_text, chr_.place_text) if chr_ else None,
            "buri": self.ereignis_json(buri.date_text, buri.place_text) if buri else None,
            "occupation": beruf,
            "thumb": self.bild_url(bild[0]) if bild else None,
            "url": self.seiten_url(),
        }
        if mit_zahlen:
            j["hasParents"] = bool(self.s.als_kind(pid))
            j["partnersCount"] = len(self.s.als_partner(pid))
            j["childrenCount"] = sum(len(self.s.kinder(f)) for f in self.s.als_partner(pid))
        return j


# ── GET Individuals ───────────────────────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def individuals(ctx: Kontext) -> dict:
    if not ctx.baum_name:
        return fehler(404, "tree-not-found")
    try:
        s = sicht_fuer(ctx, ctx.baum_name)
    except Exception:  # noqa: BLE001
        return fehler(404, "tree-not-found")
    bau = Bau(ctx, s)
    m = s.m
    query = (ctx.params.get("q") or "").strip()
    try:
        seite = max(1, int(ctx.params.get("page") or 1))
    except ValueError:
        seite = 1
    worte = query.split()
    start = (seite - 1) * SEITE

    def schluessel(pid: int, nr: int = 0):
        n = m.personen[pid].namen[nr]
        nach = " ".join(x for x in (n["surname_prefix"], n["surname"]) if x) or "@N.N."
        return (f"{nach},{n['given'] or '@P.N.'}", m.personen[pid].xref)

    if "liste" not in m.zwischen:
        # Sortierte Liste und Suchtexte je Name: hängen nur am Baum, darum einmal je Modell
        m.zwischen["liste"] = [pid for _, pid in sorted((schluessel(pid), pid) for pid, p in m.personen.items()
                                                         if p.namen)]
        m.zwischen["namen"] = [(pid, nr, schluessel(pid, nr), _norm(anzeige.voller_name(n["value"])),
                                _norm(n["nickname"] or ""))
                               for pid, p in m.personen.items() for nr, n in enumerate(p.namen)]

    if not worte:
        zeilen = m.zwischen["liste"][start:start + SEITE + 1]
    elif ctx.params.get("scope") == "all":
        w = [_norm(x) for x in worte]
        treffer = []
        for pid, p in m.personen.items():
            if not s.name_darf(pid):
                continue
            teile = [n["value"] for n in p.namen] + [n["nickname"] or "" for n in p.namen]
            for e in bau.sichtbare_fakten(p):
                teile += [e.type, e.value or "", e.subtype or "", e.date_text or "", e.place_text or "",
                          e.address or "", e.cause or ""]
            text = _norm("\n".join(teile))
            if all(x in text for x in w):
                treffer.append(pid)
        treffer.sort(key=lambda pid: (bau.sort_name(m.personen[pid]), m.personen[pid].xref))
        zeilen = treffer[start:start + SEITE + 1]
    else:
        w = [_norm(x) for x in worte]
        reihe = [(sk, pid) for pid, _nr, sk, name, nick in m.zwischen["namen"]
                 if all(x in name or x in nick for x in w)]
        reihe.sort()
        zeilen = [pid for _, pid in reihe][start:start + SEITE + 1]
        zeilen = [pid for pid in zeilen if s.name_darf(pid)]

    weiter = len(zeilen) > SEITE
    gesehen, daten = set(), []
    for pid in zeilen[:SEITE]:
        if pid not in gesehen and s.name_darf(pid):
            gesehen.add(pid)
            daten.append(bau.person_kurz(pid))
    return {"query": query, "page": seite, "nextPage": seite + 1 if weiter else None, "data": daten}


GET_AKTIONEN["Individuals"] = individuals


# ── Gemeinsam: Baum und Person aus der Anfrage ──────────────────────────────────────────────────────

def _int(wert, vorgabe: int) -> int:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return vorgabe


def baum_und_person(ctx: Kontext, s: Sicht | None = None):
    """(Bau, person.id) oder eine Fehlerantwort: not-found (404), private (403)."""
    if s is None:
        try:
            s = sicht_fuer(ctx, ctx.baum_name or "")
        except Exception:  # noqa: BLE001
            return fehler(404, "tree-not-found")
    pid = s.m.person_xref.get(ctx.params.get("xref") or "")
    if pid is None:
        return fehler(404, "not-found")
    if not s.person_darf(pid):
        return fehler(403, "private")
    return Bau(ctx, s), pid


# ── GET Pedigree ──────────────────────────────────────────────────────────────────────────────────────

MAX_PEDIGREE = 12
MAX_DESCENDANTS = 10


def _mit_offenem(aktion):
    """Diagramme für Bearbeiter mit den offenen Verknüpfungen (sicht.Lesestand), wie Individual und Family."""
    def mit(ctx: Kontext):
        try:
            ls = Lesestand(ctx, ctx.baum_name or "")
        except Exception:  # noqa: BLE001
            return fehler(404, "tree-not-found")
        with ls:
            r = baum_und_person(ctx, ls.sicht)
            return aktion(ctx, r) if isinstance(r, tuple) else r
    return mit


def pedigree(ctx: Kontext, r: tuple):
    bau, wurzel = r
    m = bau.m
    gen = min(MAX_PEDIGREE, max(1, _int(ctx.params.get("generations"), 4)))
    ahnen = {1: wurzel}
    letzte = 2 ** gen - 1
    n = 1
    while n * 2 <= letzte:
        if n in ahnen:
            famc = bau.s.als_kind(ahnen[n])
            if famc:
                partner = bau.s.partner(famc[0])
                if 1 in partner:
                    ahnen[n * 2] = partner[1]
                if 2 in partner:
                    ahnen[n * 2 + 1] = partner[2]
        n += 1
    mit_geschwistern = (ctx.params.get("siblings") or "") in ("1", "true", "yes", "on")
    geschwister: dict[int, list] = {}
    daten = []
    for n in sorted(ahnen):
        pid = ahnen[n]
        famc = bau.s.als_kind(pid) if bau.s.person_darf(pid) else []
        f = famc[0] if famc else None
        e = {"n": n, "person": bau.person_kurz(pid), "hasParents": bool(f is not None and bau.s.partner(f))}
        if mit_geschwistern:
            if pid not in geschwister:
                geschwister[pid] = [bau.person_kurz(k) for k in bau.s.kinder(f) if k != pid] if f is not None else []
            e["siblings"] = geschwister[pid]
        daten.append(e)
    return {"root": m.personen[wurzel].xref, "generations": gen, "ancestors": daten}


# ── GET Descendants ───────────────────────────────────────────────────────────────────────────────────

def _nachkommen(bau: Bau, pid: int, gen: int) -> dict:
    m = bau.m
    familien = []
    if gen > 1:
        for fid in bau.s.als_partner(pid):
            f = m.familien[fid]
            partner = next((q for q in bau.s.partner(fid).values() if q != pid), None)
            heirat = _heirat(bau, f)
            familien.append({
                "xref": f.xref,
                "spouse": bau.person_kurz(partner) if partner else None,
                "marriage": bau.ereignis_json(*heirat) if heirat else None,
                "children": [_nachkommen(bau, k, gen - 1) for k in bau.s.kinder(fid)],
            })
    return {"person": bau.person_kurz(pid), "families": familien}


def _heirat(bau: Bau, f) -> tuple[str | None, str | None] | None:
    """Datum und Ort der Heirat: erstes gültiges Datum der sichtbaren Heiraten, Ort der ersten Heirat (auch wenn er
    leer ist – wie in den Aufzeichnungen)."""
    if not bau.s.familie_darf(f.id):
        return None
    heiraten = [e for e in f.fakten if e.type == "MARR" and not e.negated and bau.s.fakt_darf(e.type, e.resn, xref=f.xref)]
    datum = next((e.date_text for e in heiraten if anzeige.datum_grenzen(e.date_text)), None)
    ort = heiraten[0].place_text if heiraten else None
    return datum, ort


def descendants(ctx: Kontext, r: tuple):
    bau, wurzel = r
    gen = min(MAX_DESCENDANTS, max(1, _int(ctx.params.get("generations"), 3)))
    return {"root": bau.m.personen[wurzel].xref, "generations": gen, "tree": _nachkommen(bau, wurzel, gen)}


GET_AKTIONEN["Pedigree"] = _mit_offenem(pedigree)
GET_AKTIONEN["Descendants"] = _mit_offenem(descendants)
