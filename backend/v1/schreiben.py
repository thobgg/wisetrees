"""v1: schreibende Aktionen (docs/PLAN-M2.md). Schritt 2: Fact – einen Fakt anlegen oder ändern.

Prüfungen und Fehler wie in den Aufzeichnungen der Referenz (vertrag/schreibfaelle.py):
  Datensatz fehlt → not-found (404), nicht sichtbar → private (403), keine Bearbeiterrolle oder gesperrt →
  not-editable (403); factId unbekannt → fact-not-found (404), Fakt gesperrt → fact-locked (403); Wert in Form eines
  Verweises → invalid-value, Art unzulässig → invalid-gedcom, Verknüpfung über den Fakten-Editor →
  link-tag-not-allowed, Name ohne genau zwei „/“ → invalid-name, Datum gar nicht lesbar → invalid-date (alle 400).

Geändert wird nur, was im Rumpf steht; ein leerer Wert entfernt die Angabe. Jede Änderung wird ein Satz der
Schreibschicht (baum/aenderungen.py) – offen oder, mit „sofort annehmen“, gleich angenommen.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select

from baum import aenderungen as ae
from baum import orte
from baum.schema import tabelle as T
from gedcom import datum as gdatum

from .http import POST_AKTIONEN, Kontext, fehler
from .sicht import sicht_fuer

ZEIGER = re.compile(r"^@[^@\n]+@")
ART = re.compile(r"^[A-Z_][A-Z0-9_]*$")
VERKNUEPFUNGEN = {"FAMS", "FAMC", "HUSB", "WIFE", "CHIL", "OBJE", "CHAN"}
EREIGNISSE_MIT_Y = {"BIRT", "CHR", "BAPM", "DEAT", "BURI", "CREM", "MARR", "DIV", "ENGA"}
HEIRATSART = {"civil": "CIVIL", "religious": "RELIGIOUS", "reli": "RELIGIOUS", "partners": "PARTNERS",
              "partnership": "PARTNERS", "common law": "COMMON LAW", "common": "COMMON LAW"}
PATENLISTE = re.compile(r"^(paten|taufpaten|gevattern|trauzeugen|zeugen):", re.I)


def _zeile(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _mehrzeilig(text) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _offen(con, xref: str) -> bool:
    return bool(ae.offene_saetze(con, xref))


def _datum_spalten(text: str) -> dict:
    d = gdatum.lesen(text)
    if d is None:
        return {"date_text": None, "date_kind": None, "date_quality": None, "date_calendar": None,
                "date_from": None, "date_to": None}
    return {"date_text": d.text, "date_kind": d.kind, "date_quality": d.quality, "date_calendar": d.calendar,
            "date_from": d.von, "date_to": d.bis}


def fact(ctx: Kontext):
    try:
        s = sicht_fuer(ctx, ctx.baum_name or "")
    except Exception:  # noqa: BLE001
        return fehler(404, "tree-not-found")
    m = s.m
    xref = ctx.params.get("xref") or ""
    pid, fid = m.person_xref.get(xref), m.familie_xref.get(xref)
    if pid is None and fid is None:
        return fehler(404, "not-found")
    if not (s.person_darf(pid) if pid is not None else s.familie_darf(fid)):
        return fehler(403, "private")
    rolle = ctx.konten.rolle(ctx.konto, ctx.baum_name)
    resn = m.personen[pid].resn if pid is not None else m.familien[fid].resn
    if rolle not in ("editor", "moderator", "manager") or (resn == "locked" and rolle != "manager"):
        return fehler(403, "not-editable")

    r = ctx.rumpf
    for k in ("value", "place", "note", "type"):
        if ZEIGER.match(str(r.get(k) or "").strip()):
            return fehler(400, "invalid-value")

    b = ctx.app.state.baeume.baum(ctx.baum_name)
    con = b.oeffnen()
    try:
        with con.begin():
            a = ae.Aenderung(con, xref, ctx.konto.name)
            antwort = _fakt(con, a, r, pid, fid, rolle == "manager")
            if antwort is not None:
                return antwort
            sofort = ctx.konten.kontobaum(ctx.konto, ctx.baum_name).sofort
            a.speichern(sofort=sofort)
            offen = _offen(con, xref)
    finally:
        con.close()
    return {"ok": True, "xref": xref, "pending": offen}


def _fakt(con, a: ae.Aenderung, r: dict, pid, fid, verwalter: bool):
    """Schritte für Fact sammeln; eine Fehlerantwort oder None."""
    fakt_id = str(r.get("factId") or "")
    if fakt_id:
        art, nr = fakt_id[:1], fakt_id[1:]
        if not nr.isdigit():
            return fehler(404, "fact-not-found")
        nr = int(nr)
        if art == "E":
            rolle = ae.aktueller_stand(con, "event_role", nr)
            traeger_ok = rolle and rolle.get("role") == "PRINCIPAL" and (
                (pid is not None and rolle.get("person_id") == pid) or (fid is not None and rolle.get("family_id") == fid))
            if not traeger_ok:
                return fehler(404, "fact-not-found")
            ereignis = ae.aktueller_stand(con, "event", rolle["event_id"])
            if ereignis.get("resn") == "locked" and not verwalter:
                return fehler(403, "fact-locked")
            return _ereignis_aendern(con, a, rolle["event_id"], ereignis, r)
        if art == "N" and pid is not None:
            name = ae.aktueller_stand(con, "name", nr)
            if not name or name.get("person_id") != pid:
                return fehler(404, "fact-not-found")
            if name.get("resn") == "locked" and not verwalter:
                return fehler(403, "fact-locked")
            return _name_aendern(a, nr, name, r, pid)
        return fehler(404, "fact-not-found")

    tag = _zeile(r.get("tag")).upper()
    if not ART.match(tag):
        return fehler(400, "invalid-gedcom")
    if tag in VERKNUEPFUNGEN:
        return fehler(400, "link-tag-not-allowed")
    if tag == "NAME":
        if pid is None:
            return fehler(400, "invalid-gedcom")
        return _name_aendern(a, None, None, r, pid)
    return _ereignis_neu(con, a, tag, r, pid, fid)


# ── Ereignisse ─────────────────────────────────────────────────────────────────────────────────────────────

def _ereignis_werte(tag: str, r: dict, alt: dict) -> dict | object:
    """Spalten des Ereignisses aus dem Rumpf; nur, was darin steht. Fehlerantwort bei unlesbarem Datum."""
    w = {}
    if "value" in r:
        w["value"] = _mehrzeilig(r["value"]) or None
    if "date" in r:
        text = _zeile(r["date"]).upper()
        d = gdatum.lesen(text) if text else None
        if text and (d is None or (not d.gueltig and d.von is None and d.bis is None)):
            return fehler(400, "invalid-date")   # nichts daraus lesbar; der Import behält solche Texte dagegen
        w.update(_datum_spalten(text))
    if "address" in r:
        w["address"] = _mehrzeilig(r["address"]) or None
    if "type" in r:
        typ = _zeile(r["type"])
        w["subtype"] = (HEIRATSART.get(typ.lower(), typ) if tag == "MARR" else typ) or None
    return w


def _y_regel(tag: str, stand: dict, hat_mehr: bool) -> dict:
    """„1 BIRT Y“: ein Ereignis ohne jede Angabe trägt den Wert Y; kommt etwas dazu, fällt das Y weg."""
    if tag not in EREIGNISSE_MIT_Y:
        return {}
    leer = not hat_mehr and not stand.get("value")
    if leer:
        return {"value": "Y"}
    if stand.get("value") == "Y" and hat_mehr:
        return {"value": None}
    return {}


def _hat_unterzeilen(con, event_id, stand: dict, notiz_neu: bool | None) -> bool:
    if any(stand.get(k) for k in ("date_text", "place_text", "address", "subtype", "cause", "agency")):
        return True
    if notiz_neu is not None:
        return notiz_neu
    if event_id is None:
        return False
    nl, ci = T("note_link"), T("citation")
    return bool(con.execute(select(func.count()).select_from(nl).where(nl.c.event_id == event_id)).scalar()
                or con.execute(select(func.count()).select_from(ci).where(ci.c.event_id == event_id)).scalar())


def _ereignis_neu(con, a: ae.Aenderung, tag: str, r: dict, pid, fid):
    w = _ereignis_werte(tag, r, {})
    if not isinstance(w, dict):
        return w
    if "place" in r and _zeile(r["place"]):
        w["place_text"] = _zeile(r["place"])
        w["place_id"] = orte.zuordnen(con, a, w["place_text"])
    notiz = _mehrzeilig(r.get("note")) if "note" in r else ""
    w.update(_y_regel(tag, w, _hat_unterzeilen(con, None, w, bool(notiz))))
    eid = a.anlegen("event", type=tag, **w)
    traeger = {"person_id": pid} if pid is not None else {"family_id": fid}
    a.anlegen("event_role", event_id=eid, role="PRINCIPAL", sort=0, fact_sort=_naechster_platz(con, pid, fid),
              **traeger)
    if notiz:
        nid = a.anlegen("note", text=notiz)
        a.anlegen("note_link", note_id=nid, event_id=eid, sort=1)
    return None


def _naechster_platz(con, pid, fid) -> int:
    er = T("event_role")
    spalte = er.c.person_id if pid is not None else er.c.family_id
    hoechste = con.execute(select(func.max(er.c.fact_sort)).where(spalte == (pid if pid is not None else fid))).scalar() or 0
    for s in ae.schritte(con, [x["id"] for x in ae.offene_saetze(con)]):
        if s["object_type"] == "event_role" and s["operation"] == "create":
            n = s["neu"]
            if (pid is not None and n.get("person_id") == pid) or (fid is not None and n.get("family_id") == fid):
                hoechste = max(hoechste, n.get("fact_sort") or 0)
    return hoechste + 1


def _ereignis_aendern(con, a: ae.Aenderung, event_id: int, alt: dict, r: dict):
    w = _ereignis_werte(alt["type"], r, alt)
    if not isinstance(w, dict):
        return w
    if "place" in r:
        ort = _zeile(r["place"])
        if ort != (alt.get("place_text") or ""):   # unveränderter Ort: Zuordnung und Angaben bleiben
            w["place_text"] = ort or None
            w["place_id"] = orte.zuordnen(con, a, ort) if ort else None
    notiz_neu = None
    if "note" in r:
        notiz_neu = _notiz_ersetzen(con, a, event_id, _mehrzeilig(r["note"]))
    stand = {**alt, **w}
    w.update(_y_regel(alt["type"], stand, _hat_unterzeilen(con, event_id, stand, notiz_neu)))
    a.aendern("event", event_id, **w)
    return None


def _notiz_ersetzen(con, a: ae.Aenderung, event_id: int, text: str) -> bool:
    """Erste eingebettete Notiz ersetzen (eine Patenliste bleibt stehen); True, wenn danach eine Notiz da ist."""
    nl, no = T("note_link"), T("note")
    verweise = con.execute(select(nl.c.id, nl.c.note_id, nl.c.sort, no.c.xref, no.c.text)
                           .select_from(nl.join(no, no.c.id == nl.c.note_id))
                           .where(nl.c.event_id == event_id).order_by(nl.c.sort)).all()
    ersetzt = False
    for v in verweise:
        if v.xref is None and not PATENLISTE.match((v.text or "").strip()):
            a.loeschen("note_link", v.id)
            a.loeschen("note", v.note_id)
            ersetzt = True
            break
    rest = len(verweise) - (1 if ersetzt else 0)
    if text:
        nid = a.anlegen("note", text=text)
        a.anlegen("note_link", note_id=nid, event_id=event_id, sort=max([v.sort for v in verweise], default=0) + 1)
    return rest > 0 or bool(text)


# ── Namen ──────────────────────────────────────────────────────────────────────────────────────────────────

NAME = re.compile(r"^([^/]*)/([^/]*)/(.*)$", re.S)


def _name_aendern(a: ae.Aenderung, name_id: int | None, alt: dict | None, r: dict, pid: int):
    if "value" not in r:
        return None
    wert = _zeile(r["value"])
    if wert.count("/") not in (0, 2) or "@" in wert:
        return fehler(400, "invalid-name")
    w = {"value": wert}
    mm = NAME.match(wert)
    if mm:
        vor = mm.group(1).strip()
        praefix = (alt or {}).get("name_prefix")
        if praefix and vor.startswith(praefix + " "):
            vor = vor[len(praefix):].strip()
        w.update(given=vor or None, surname=mm.group(2).strip() or None, name_suffix=mm.group(3).strip() or None)
    if name_id is None:
        a.anlegen("name", person_id=pid, sort=99, **w)
    else:
        a.aendern("name", name_id, **w)
    return None


POST_AKTIONEN["Fact"] = fact
