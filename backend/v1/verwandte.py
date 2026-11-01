"""v1: Personen anlegen und verknüpfen, Verknüpfungen lösen, Datensätze löschen (docs/PLAN-M2.md, Schritt 5).

  POST AddIndividual   neue Person, auf Wunsch gleich als Kind, Partner, Vater oder Mutter einer anderen
  POST Link            zwei vorhandene Personen so verknüpfen
  POST Unlink          eine Person aus einer Familie lösen
  POST DeleteRecord    Person oder Familie löschen; Verweise anderer Datensätze fallen weg, eine Familie mit
                       höchstens einem Mitglied und ohne Ereignisse wird mitgelöscht

Rumpf, Fehler und Antworten nach den Aufzeichnungen der Referenz (vertrag/schreibfaelle.py). Eine Aktion wird für
jeden Datensatz, den sie berührt, ein eigener Satz der Schreibschicht – in der Reihenfolge, in der die Referenz
die Datensätze ändert. So zählt die Moderation (Pending) die Änderungen je Datensatz wie dort. Alle Sätze einer
Aktion entstehen in einer Transaktion: Bei einem Fehler bleibt nichts halb angelegt.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from baum import aenderungen as ae
from baum.schema import tabelle as T

from . import schreiben as sch
from .http import POST_AKTIONEN, Kontext, fehler
from .sicht import Sicht, sicht_fuer

BEARBEITER = ("editor", "moderator", "manager")
RELATIONEN = ("child", "spouse", "father", "mother")
GESCHLECHT = ("M", "F", "U", "X")
HUSB, WIFE = 1, 2


class Abbruch(Exception):
    """Fehlerantwort mitten im Schreiben: die Transaktion wird zurückgerollt."""

    def __init__(self, antwort):
        super().__init__()
        self.antwort = antwort


class Saetze:
    """Die Sätze einer Aktion, je berührtem Datensatz einer; jeder wird gleich gespeichert (offen oder angenommen)."""

    def __init__(self, con, autor: str, sofort: bool):
        self.con, self.autor, self.sofort = con, autor, sofort

    @contextmanager
    def satz(self, xref: str, kommentar: str | None = None):
        a = ae.Aenderung(self.con, xref, self.autor)
        a.kommentar = kommentar
        yield a
        a.speichern(sofort=self.sofort)


# ── Gemeinsames ────────────────────────────────────────────────────────────────────────────────────────────

def _rolle(ctx: Kontext) -> str:
    return ctx.konten.rolle(ctx.konto, ctx.baum_name)


def _sicht(ctx: Kontext) -> Sicht | None:
    try:
        return sicht_fuer(ctx, ctx.baum_name or "")
    except Exception:  # noqa: BLE001
        return None


def _bearbeitbar(ctx: Kontext, s: Sicht, xref: str, art: str = "person"):
    """person.id / family.id eines Datensatzes, den die Rolle bearbeiten darf, sonst die Fehlerantwort."""
    m = s.m
    oid = (m.person_xref if art == "person" else m.familie_xref).get(xref or "")
    if oid is None:
        return fehler(404, "not-found")
    if not (s.person_darf(oid) if art == "person" else s.familie_darf(oid)):
        return fehler(403, "private")
    resn = (m.personen[oid] if art == "person" else m.familien[oid]).resn
    rolle = _rolle(ctx)
    if rolle not in BEARBEITER or (resn == "locked" and rolle != "manager"):
        return fehler(403, "not-editable")
    return oid


def _text(r: dict, k: str) -> str:
    return sch._zeile(r.get(k) if isinstance(r.get(k), str) else "")


def _namensteil(text: str) -> str:
    return sch._zeile(text.replace("/", "").replace("@", ""))


def _datum_ok(text: str) -> bool:
    return not text or not isinstance(sch._ereignis_werte("BIRT", {"date": text}, {}), JSONResponse)


def _ausfuehren(ctx: Kontext, xref_antwort, arbeit, status: int = 200):
    """arbeit(con, saetze) → Zusatzangaben der Antwort; xref_antwort(zusatz) → xref für ok/pending."""
    con = ctx.app.state.baeume.baum(ctx.baum_name).oeffnen()
    try:
        try:
            with con.begin():
                sz = Saetze(con, ctx.konto.name, ctx.konten.kontobaum(ctx.konto, ctx.baum_name).sofort)
                zusatz = arbeit(con, sz)
        except Abbruch as e:
            return e.antwort
        xref = xref_antwort(zusatz)
        antwort = {"ok": True, "xref": xref, "pending": sch._offen(con, xref),
                   **{k: v for k, v in zusatz.items() if not k.startswith("_")}}
    finally:
        con.close()
    return JSONResponse(antwort, status_code=status) if status != 200 else antwort


def _hoechste(con, tab: str, wo: dict, spalte: str) -> int:
    """Größter Wert der Spalte unter den Zeilen, auf die wo passt – angenommen und offen angelegt."""
    t = T(tab)
    hoechste = 0
    if all(isinstance(v, int | str) and not (isinstance(v, str) and v.startswith(("neu:", "lokal:")))
           for v in wo.values()):
        q = select(func.max(t.c[spalte]))
        for k, v in wo.items():
            q = q.where(t.c[k] == v)
        hoechste = con.execute(q).scalar() or 0
    for s in ae.schritte(con, [x["id"] for x in ae.offene_saetze(con)]):
        if s["object_type"] == tab and s["operation"] == "create" and all(s["neu"].get(k) == v for k, v in wo.items()):
            hoechste = max(hoechste, s["neu"].get(spalte) or 0)
    return hoechste


def _sortieren(sz: Saetze, xref: str, person, mitglied, rolle: str) -> None:
    """Im Satz der Person die Verknüpfung an ihre Liste (FAMS/FAMC) hängen: person_sort setzen."""
    with sz.satz(xref) as a:
        a.aendern("family_member", mitglied, person_sort=_hoechste(sz.con, "family_member",
                                                                    {"person_id": person, "role": rolle},
                                                                    "person_sort") + 1)


# ── Person und Familie anlegen ─────────────────────────────────────────────────────────────────────────────

def _familie_pruefen(ctx: Kontext, s: Sicht, relation: str, verwandt: int, family_xref: str):
    """Die Familie, in die die Person kommt (family.id), None für eine neue, oder eine Fehlerantwort."""
    m = s.m
    familie = None
    if relation == "child":
        familien = m.personen[verwandt].fams
        if family_xref:
            familie = next((f for f in familien if m.familien[f].xref == family_xref), None)
            if familie is None:
                return fehler(404, "family-not-found")
        elif len(familien) > 1:
            return fehler(400, "family-required")
        else:
            familie = familien[0] if familien else None
    elif relation in ("father", "mother"):
        famc = m.personen[verwandt].famc
        familie = famc[0] if famc else None
        if familie is not None and (HUSB if relation == "father" else WIFE) in m.familien[familie].partner:
            return fehler(409, "parent-exists")
    if familie is not None and m.familien[familie].resn == "locked" and _rolle(ctx) != "manager":
        return fehler(403, "family-locked")
    return familie


def _abstammung(a: ae.Aenderung, familie, kinder, eltern) -> None:
    for k in kinder:
        for e in eltern:
            a.anlegen("parentage", family_id=familie, child_id=k, parent_id=e, kind="birth")


def _verknuepfen(s: Sicht, sz: Saetze, relation: str, person, person_xref: str, verwandt: int, familie,
                 heirat: dict) -> str:
    """person als Kind, Partner, Vater oder Mutter von verwandt eintragen; Rückgabe: xref der Familie."""
    m, con = s.m, sz.con
    v = m.personen[verwandt]
    if familie is not None:
        f = m.familien[familie]
        with sz.satz(f.xref) as a:
            if relation == "child":
                platz = _hoechste(con, "family_member", {"family_id": familie, "role": "child"}, "sort") + 1
                glied = a.anlegen("family_member", family_id=familie, person_id=person, role="child", sort=platz,
                                  person_sort=0)
                _abstammung(a, familie, [person], f.partner.values())
                rolle = "child"
            else:
                glied = a.anlegen("family_member", family_id=familie, person_id=person, role="partner",
                                  sort=HUSB if relation == "father" else WIFE, person_sort=0)
                _abstammung(a, familie, f.kinder, [person])
                rolle = "partner"
        _sortieren(sz, person_xref, person, a.kennung(glied), rolle)
        return f.xref

    neu_xref = ae.neue_kennung(con, "family", "F")
    with sz.satz(neu_xref) as a:
        fam = a.anlegen("family", xref=neu_xref)
        if relation == "child":
            v_rolle, v_platz = "partner", WIFE if v.sex == "F" else HUSB
            p_rolle, p_platz = "child", 1
        elif relation == "spouse":
            v_rolle, v_platz = "partner", WIFE if v.sex == "F" else HUSB
            p_rolle, p_platz = "partner", HUSB if v_platz == WIFE else WIFE
        else:
            v_rolle, v_platz = "child", 1
            p_rolle, p_platz = "partner", HUSB if relation == "father" else WIFE
        g_v = a.anlegen("family_member", family_id=fam, person_id=verwandt, role=v_rolle, sort=v_platz, person_sort=0)
        g_p = a.anlegen("family_member", family_id=fam, person_id=person, role=p_rolle, sort=p_platz, person_sort=0)
        if relation == "child":
            _abstammung(a, fam, [person], [verwandt])
        elif relation in ("father", "mother"):
            _abstammung(a, fam, [verwandt], [person])
        if relation == "spouse" and (heirat.get("date") or heirat.get("place")):
            w = sch._ereignis_neu(con, a, "MARR", heirat, None, fam, platz=1)
            if w is not None:
                raise Abbruch(w)
    _sortieren(sz, v.xref, verwandt, a.kennung(g_v), v_rolle)
    _sortieren(sz, person_xref, person, a.kennung(g_p), p_rolle)
    return neu_xref


def _heirat(r: dict) -> dict:
    return {k: _text(r, f"marriage{k.title()}") for k in ("date", "place") if _text(r, f"marriage{k.title()}")}


def add_individual(ctx: Kontext):
    if _rolle(ctx) not in BEARBEITER:
        return fehler(403, "not-editor")
    s = _sicht(ctx)
    if s is None:
        return fehler(404, "tree-not-found")
    r = ctx.rumpf
    relation = _text(r, "relation") or "none"
    if relation not in (*RELATIONEN, "none"):
        return fehler(400, "invalid-relation")
    verwandt = None
    if relation != "none":
        verwandt = _bearbeitbar(ctx, s, _text(r, "relativeTo"))
        if not isinstance(verwandt, int):
            return verwandt
    if not all(_datum_ok(_text(r, k)) for k in ("birthDate", "deathDate", "marriageDate")):
        return fehler(400, "invalid-date")
    if any(sch.ZEIGER.match(_text(r, k)) for k in ("birthPlace", "deathPlace", "marriagePlace")):
        return fehler(400, "invalid-value")
    vor, nach = _namensteil(_text(r, "given")), _namensteil(_text(r, "surname"))
    if not vor and not nach:
        return fehler(400, "name-required")
    sex = _text(r, "sex").upper() or "U"
    sex = {"father": "M", "mother": "F"}.get(relation, sex if sex in GESCHLECHT else "U")
    familie = None
    if verwandt is not None:
        familie = _familie_pruefen(ctx, s, relation, verwandt, _text(r, "family"))
        if familie is not None and not isinstance(familie, int):
            return familie
    weitere = r.get("facts") or []
    if not isinstance(weitere, list) or not all(isinstance(f, dict) and "gedcom" not in f for f in weitere):
        return fehler(400, "invalid-gedcom")    # Eingabe nur über die Felder (E21), kein GEDCOM-Text
    for f in weitere:
        if any(sch.ZEIGER.match(str(f.get(k) or "").strip()) for k in ("value", "place", "note", "type")):
            return fehler(400, "invalid-value")

    def arbeit(con, sz: Saetze) -> dict:
        xref = ae.neue_kennung(con, "person", "I")
        with sz.satz(xref) as a:
            p = a.anlegen("person", xref=xref, sex=sex)
            wert = f"{vor} /{nach}/".strip()
            a.anlegen("name", person_id=p, sort=1, value=wert, given=vor or None, surname=nach or None)
            platz = 0
            for tag, datum, ort, sicher in (("BIRT", "birthDate", "birthPlace", False),
                                            ("DEAT", "deathDate", "deathPlace", r.get("dead") is True)):
                angaben = {k: _text(r, q) for k, q in (("date", datum), ("place", ort)) if _text(r, q)}
                if angaben or sicher:
                    platz += 1
                    w = sch._ereignis_neu(con, a, tag, angaben, p, None, platz=platz)
                    if w is not None:
                        raise Abbruch(w)
            for f in weitere:
                w = sch._fakt(con, a, {k: v for k, v in f.items() if k != "factId"}, p, None, _rolle(ctx) == "manager")
                if w is not None:
                    raise Abbruch(w)
        zusatz = {"_xref": xref, "family": None}
        if verwandt is not None:
            zusatz["family"] = _verknuepfen(s, sz, relation, a.kennung(p), xref, verwandt, familie, _heirat(r))
        return zusatz

    return _ausfuehren(ctx, lambda z: z["_xref"], arbeit, status=201)


def link(ctx: Kontext):
    s = _sicht(ctx)
    if s is None:
        return fehler(404, "tree-not-found")
    r = ctx.rumpf
    relation = _text(r, "relation")
    if relation not in RELATIONEN:
        return fehler(400, "invalid-relation")
    ids = []
    for k in ("individual", "relativeTo"):
        oid = _bearbeitbar(ctx, s, _text(r, k))
        if not isinstance(oid, int):
            return oid
        ids.append(oid)
    person, verwandt = ids
    if person == verwandt:
        return fehler(400, "invalid-relation")
    if not _datum_ok(_text(r, "marriageDate")):
        return fehler(400, "invalid-date")
    if sch.ZEIGER.match(_text(r, "marriagePlace")):
        return fehler(400, "invalid-value")
    familie = _familie_pruefen(ctx, s, relation, verwandt, _text(r, "family"))
    if familie is not None and not isinstance(familie, int):
        return familie
    m = s.m
    if relation == "child":
        schon = familie is not None and person in m.familien[familie].kinder
    elif relation == "spouse":
        schon = any(person in m.familien[f].partner.values() for f in m.personen[verwandt].fams)
    else:
        schon = familie is not None and person in m.familien[familie].partner.values()
    if schon:
        return fehler(409, "link-exists")
    xref = m.personen[person].xref

    def arbeit(con, sz: Saetze) -> dict:
        return {"family": _verknuepfen(s, sz, relation, person, xref, verwandt, familie, _heirat(r))}

    return _ausfuehren(ctx, lambda z: xref, arbeit)


# ── Lösen und löschen ──────────────────────────────────────────────────────────────────────────────────────

def _glieder(con, person: int, familie: int | None = None) -> list:
    fm = T("family_member")
    q = select(fm.c.id, fm.c.family_id, fm.c.role, fm.c.person_sort).where(fm.c.person_id == person)
    if familie is not None:
        q = q.where(fm.c.family_id == familie)
    return con.execute(q.order_by(fm.c.role, fm.c.person_sort, fm.c.id)).all()


def _abstammung_von(con, familie: int, person: int) -> list[int]:
    pa = T("parentage")
    return [r[0] for r in con.execute(select(pa.c.id).where(
        pa.c.family_id == familie, (pa.c.child_id == person) | (pa.c.parent_id == person)).order_by(pa.c.id))]


def unlink(ctx: Kontext):
    s = _sicht(ctx)
    if s is None:
        return fehler(404, "tree-not-found")
    r = ctx.rumpf
    familie = _bearbeitbar(ctx, s, _text(r, "family"), "family")
    if not isinstance(familie, int):
        return familie
    person = _bearbeitbar(ctx, s, _text(r, "individual"))
    if not isinstance(person, int):
        return person
    m = s.m
    f_xref, p_xref = m.familien[familie].xref, m.personen[person].xref

    def arbeit(con, sz: Saetze) -> dict:
        glieder = _glieder(con, person, familie)
        if not glieder:
            raise Abbruch(fehler(404, "link-not-found"))
        # Wie in GEDCOM an beiden Seiten: die Familie gibt den Platz frei (sort 0), die Person löst die Verknüpfung.
        # Solange nur die Seite der Familie angenommen ist, bleibt die Person verknüpft.
        with sz.satz(f_xref) as a:
            for pid in _abstammung_von(con, familie, person):
                a.loeschen("parentage", pid)
            for g in glieder:
                a.aendern("family_member", g.id, sort=0)
        with sz.satz(p_xref) as a:
            for g in glieder:
                a.loeschen("family_member", g.id)
            _neu_nummerieren(con, a, person, ohne={g.id for g in glieder})
        return {"family": f_xref}

    return _ausfuehren(ctx, lambda z: p_xref, arbeit)


def _neu_nummerieren(con, a: ae.Aenderung, person: int, ohne: set[int]) -> None:
    """Die übrigen Verknüpfungen der Person lückenlos durchzählen (nur, wo sich etwas ändert)."""
    for rolle in ("partner", "child"):
        for n, g in enumerate((g for g in _glieder(con, person) if g.role == rolle and g.id not in ohne), 1):
            if g.person_sort != n:
                a.aendern("family_member", g.id, person_sort=n)


def _ereignis_entfernen(con, a: ae.Aenderung, event_id: int) -> None:
    sch._eingebettete_loeschen(con, a, "event_id", event_id)
    a.loeschen("event", event_id)


def _eigenes_entfernen(con, a: ae.Aenderung, spalte: str, wert: int) -> None:
    """Was nur am Datensatz hängt und nicht von selbst mitgelöscht wird: Ereignisse, an denen er der einzige
    Hauptbeteiligte ist, und eingebettete Notizen (auch an Namen, Quellenangaben und Verknüpfungen)."""
    er = T("event_role")
    for (eid,) in con.execute(select(er.c.event_id).where(er.c[spalte] == wert, er.c.role == "PRINCIPAL")
                              .order_by(er.c.fact_sort)):
        andere = con.execute(select(func.count()).select_from(er).where(
            er.c.event_id == eid, er.c.role == "PRINCIPAL", er.c[spalte].is_distinct_from(wert))).scalar()
        if not andere:
            _ereignis_entfernen(con, a, eid)
    sch._eingebettete_loeschen(con, a, spalte, wert)
    for tab, fremd in (("name", "name_id"), ("citation", "citation_id"), ("person_association", "person_association_id")):
        t = T(tab)
        if spalte in t.c:
            for (oid,) in con.execute(select(t.c.id).where(t.c[spalte] == wert)):
                sch._eingebettete_loeschen(con, a, fremd, oid)


def _person_loeschen(con, s: Sicht, sz: Saetze, person: int) -> None:
    m = s.m
    p = m.personen[person]
    er, pa = T("event_role"), T("person_association")
    fremd: dict[str, list[tuple[str, int]]] = {}
    familien = []
    for g in _glieder(con, person):
        fx = m.familien[g.family_id].xref
        familien.append(g.family_id)
        fremd.setdefault(fx, []).extend([("parentage", i) for i in _abstammung_von(con, g.family_id, person)])
        fremd[fx].append(("family_member", g.id))
    for r in con.execute(select(er.c.id, er.c.event_id).where(er.c.person_id == person, er.c.role != "PRINCIPAL")
                         .order_by(er.c.id)):
        haupt = con.execute(select(er.c.person_id, er.c.family_id).where(
            er.c.event_id == r.event_id, er.c.role == "PRINCIPAL")).first()
        if haupt is None or haupt.person_id == person:
            continue                                   # Ereignis der Person selbst: fällt mit ihr weg
        x = m.personen[haupt.person_id].xref if haupt.person_id else m.familien[haupt.family_id].xref
        fremd.setdefault(x, []).append(("event_role", r.id))
    for r in con.execute(select(pa.c.id, pa.c.person_id).where(pa.c.other_person_id == person,
                                                               pa.c.person_id != person).order_by(pa.c.id)):
        fremd.setdefault(m.personen[r.person_id].xref, []).append(("person_association", r.id))
    for x in sorted(fremd):
        with sz.satz(x, ae.NUR_VERWEISE) as a:
            for tab, oid in fremd[x]:
                if tab == "person_association":
                    sch._eingebettete_loeschen(con, a, "person_association_id", oid)
                a.loeschen(tab, oid)
    with sz.satz(p.xref) as a:
        _eigenes_entfernen(con, a, "person_id", person)
        a.loeschen("person", person)
    # Familien, die danach höchstens ein Mitglied und keine Ereignisse haben, fallen weg
    fm = T("family_member")
    for fid in dict.fromkeys(familien):
        mitglieder = con.execute(select(func.count(func.distinct(fm.c.person_id))).where(fm.c.family_id == fid)).scalar()
        ereignisse = con.execute(select(func.count()).select_from(er).where(er.c.family_id == fid)).scalar()
        if sz.sofort and mitglieder <= 1 and not ereignisse:
            with sz.satz(m.familien[fid].xref) as a:
                _eigenes_entfernen(con, a, "family_id", fid)
                a.loeschen("family", fid)


def _familie_loeschen(con, s: Sicht, sz: Saetze, familie: int) -> None:
    m = s.m
    f = m.familien[familie]
    fm = T("family_member")
    glieder = con.execute(select(fm.c.id, fm.c.person_id).where(fm.c.family_id == familie)).all()
    for pid in sorted({g.person_id for g in glieder}, key=lambda i: m.personen[i].xref):
        with sz.satz(m.personen[pid].xref, ae.NUR_VERWEISE) as a:
            for i in _abstammung_von(con, familie, pid):
                a.loeschen("parentage", i)
            for g in glieder:
                if g.person_id == pid:
                    a.loeschen("family_member", g.id)
    with sz.satz(f.xref) as a:
        _eigenes_entfernen(con, a, "family_id", familie)
        a.loeschen("family", familie)


def delete_record(ctx: Kontext):
    s = _sicht(ctx)
    if s is None:
        return fehler(404, "tree-not-found")
    xref = ctx.params.get("xref") or ""
    art = "family" if xref in s.m.familie_xref else "person"
    oid = _bearbeitbar(ctx, s, xref, art)
    if not isinstance(oid, int):
        return oid

    def arbeit(con, sz: Saetze) -> dict:
        (_person_loeschen if art == "person" else _familie_loeschen)(con, s, sz, oid)
        return {}

    return _ausfuehren(ctx, lambda z: xref, arbeit)


POST_AKTIONEN["AddIndividual"] = add_individual
POST_AKTIONEN["Link"] = link
POST_AKTIONEN["Unlink"] = unlink
POST_AKTIONEN["DeleteRecord"] = delete_record
