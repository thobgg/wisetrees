"""Schreibschicht: Änderungen als Sätze mit Einzelschritten (KONZEPT.md E4 a, E21, docs/PLAN-M2.md).

Eine Bearbeitung an einem Datensatz (Person, Familie …) wird ein Satz in change_set mit Schritten in change_step.
Die Modelltabellen enthalten nur den angenommenen Stand; ein offener Satz wirkt erst, wenn er angenommen wird.

- Schritte: anlegen (neue Werte), ändern (alte und neue Werte der geänderten Spalten), löschen (alte Werte).
- Weitere Änderungen bauen auf dem offenen Stand auf (wie in der Referenz): Ihre alten Werte sind die nach den
  offenen Schritten.
- Angelegte Objekte bekommen ihre Datenbank-Kennung erst beim Annehmen. Bis dahin verweisen andere Schritte – auch in
  späteren Sätzen – mit "neu:<Schritt>" auf den Schritt, der sie anlegt; beim Annehmen steht die Kennung dann in
  object_id dieses Schritts.
- Annehmen wendet die Sätze in ihrer Reihenfolge an. Weicht ein alter Wert vom Stand der Datenbank ab, ist das ein
  Konflikt: nichts wird überschrieben, der Satz bleibt offen.

Alle Funktionen arbeiten in einer offenen Transaktion des Aufrufers.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import Connection, delete, insert, select, update

from .schema import change_set, change_step
from .schema import tabelle as T

NEU = re.compile(r"^neu:(\d+)$")


class Konflikt(Exception):
    """Der angenommene Stand hat sich seit der Änderung geändert, oder ein Schritt hängt an einem noch offenen."""


@dataclass
class Schritt:
    tabelle: str
    operation: str               # create, update, delete
    objekt: int | str | None     # Kennung, "neu:<Schritt>" oder bei create ein lokaler Schlüssel
    alt: dict = field(default_factory=dict)
    neu: dict = field(default_factory=dict)


class Aenderung:
    """Sammelt die Schritte einer Bearbeitung an einem Datensatz."""

    def __init__(self, con: Connection, record_xref: str, autor: str):
        self.con, self.record_xref, self.autor = con, record_xref, autor
        self.schritte: list[Schritt] = []

    def anlegen(self, tabelle: str, **werte) -> str:
        """Neues Objekt; Rückgabe ist ein lokaler Schlüssel, den weitere Werte als Verweis nutzen können."""
        schluessel = f"lokal:{len(self.schritte)}"
        self.schritte.append(Schritt(tabelle, "create", schluessel, neu=werte))
        return schluessel

    def aendern(self, tabelle: str, objekt: int | str, **werte) -> None:
        stand = aktueller_stand(self.con, tabelle, objekt, self)
        if stand is None:
            raise KeyError(f"{tabelle} {objekt} gibt es nicht")
        geaendert = {k: v for k, v in werte.items() if stand.get(k) != v}
        if geaendert:
            self.schritte.append(Schritt(tabelle, "update", objekt, alt={k: stand.get(k) for k in geaendert},
                                         neu=geaendert))

    def loeschen(self, tabelle: str, objekt: int | str) -> None:
        stand = aktueller_stand(self.con, tabelle, objekt, self)
        if stand is None:
            raise KeyError(f"{tabelle} {objekt} gibt es nicht")
        self.schritte.append(Schritt(tabelle, "delete", objekt, alt=stand))

    def speichern(self, sofort: bool = False) -> int | None:
        """Satz anlegen; mit sofort gleich annehmen. Ohne Schritte entsteht kein Satz (Rückgabe None)."""
        if not self.schritte:
            return None
        jetzt = _jetzt()
        sid = self.con.execute(insert(change_set).values(
            author=self.autor, created_at=jetzt, status="pending", record_xref=self.record_xref)).inserted_primary_key[0]
        global_von: dict[str, str] = {}
        for nr, s in enumerate(self.schritte, 1):
            neu = {k: global_von.get(v, v) if isinstance(v, str) else v for k, v in s.neu.items()}
            objekt = global_von.get(s.objekt, s.objekt) if isinstance(s.objekt, str) else s.objekt
            werte = dict(change_set_id=sid, sort=nr, object_type=s.tabelle, operation=s.operation,
                         old_json=_json(s.alt) if s.alt else None, new_json=_json(neu) if neu else None,
                         object_id=objekt if isinstance(objekt, int) else None)
            schritt_id = self.con.execute(insert(change_step).values(**werte)).inserted_primary_key[0]
            if s.operation == "create":
                global_von[s.objekt] = f"neu:{schritt_id}"
            elif isinstance(objekt, str):
                # Verweis auf ein noch nicht angenommenes Objekt: in new_json mitführen, object_id bleibt leer
                self.con.execute(update(change_step).where(change_step.c.id == schritt_id)
                                 .values(new_json=_json({**neu, "_objekt": objekt})))
        if sofort:
            annehmen(self.con, [sid], self.autor)
        return sid


# ── Lesen ──────────────────────────────────────────────────────────────────────────────────────────────────

def offene_saetze(con: Connection, record_xref: str | None = None) -> list[dict]:
    q = select(change_set).where(change_set.c.status == "pending").order_by(change_set.c.id)
    if record_xref is not None:
        q = q.where(change_set.c.record_xref == record_xref)
    return [dict(r._mapping) for r in con.execute(q)]


def schritte(con: Connection, satz_ids: list[int]) -> list[dict]:
    if not satz_ids:
        return []
    zeilen = con.execute(select(change_step).where(change_step.c.change_set_id.in_(satz_ids))
                         .order_by(change_step.c.change_set_id, change_step.c.sort))
    aus = []
    for r in zeilen:
        d = dict(r._mapping)
        d["alt"] = json.loads(d["old_json"]) if d["old_json"] else {}
        d["neu"] = json.loads(d["new_json"]) if d["new_json"] else {}
        d["objekt"] = d["object_id"] if d["object_id"] is not None else d["neu"].pop("_objekt", None)
        aus.append(d)
    return aus


def aktueller_stand(con: Connection, tabelle: str, objekt: int | str, laufend: Aenderung | None = None) -> dict | None:
    """Werte eines Objekts nach allen offenen Schritten (und den Schritten einer laufenden Änderung); None, wenn es
    das Objekt so nicht gibt (nie angelegt oder gelöscht)."""
    stand: dict | None = None
    if isinstance(objekt, int):
        t = T(tabelle)
        r = con.execute(select(t).where(t.c.id == objekt)).first()
        stand = dict(r._mapping) if r else None
    offen = schritte(con, [s["id"] for s in offene_saetze(con)])
    for s in offen:
        if s["object_type"] != tabelle:
            continue
        ziel = f"neu:{s['id']}" if s["operation"] == "create" else s["objekt"]
        if ziel != objekt:
            continue
        stand = _anwenden_auf(stand, s["operation"], s["neu"])
    if laufend is not None:
        for s in laufend.schritte:
            if s.tabelle == tabelle and s.objekt == objekt:
                stand = _anwenden_auf(stand, s.operation, s.neu)
    return stand


def _anwenden_auf(stand: dict | None, operation: str, neu: dict) -> dict | None:
    if operation == "create":
        return dict(neu)
    if operation == "delete":
        return None
    return None if stand is None else {**stand, **neu}


def neue_kennung(con: Connection, tabelle: str, vorsatz: str) -> str:
    """Nächste freie GEDCOM-Kennung im Stil des Baums (I…, F…), auch über offene Sätze hinweg."""
    t = T(tabelle)
    hoechste = 0
    for (xref,) in con.execute(select(t.c.xref).where(t.c.xref.is_not(None))):
        m = re.fullmatch(re.escape(vorsatz) + r"(\d+)", xref)
        if m:
            hoechste = max(hoechste, int(m.group(1)))
    for s in schritte(con, [s["id"] for s in offene_saetze(con)]):
        if s["object_type"] == tabelle and s["operation"] == "create":
            m = re.fullmatch(re.escape(vorsatz) + r"(\d+)", s["neu"].get("xref") or "")
            if m:
                hoechste = max(hoechste, int(m.group(1)))
    return f"{vorsatz}{hoechste + 1}"


# ── Annehmen und verwerfen ─────────────────────────────────────────────────────────────────────────────────

def annehmen(con: Connection, satz_ids: list[int], wer: str) -> None:
    """Sätze in ihrer Reihenfolge anwenden. Wirft Konflikt; der Aufrufer rollt dann die Transaktion zurück."""
    for sid in sorted(satz_ids):
        for s in schritte(con, [sid]):
            _schritt_anwenden(con, s)
        con.execute(update(change_set).where(change_set.c.id == sid)
                    .values(status="accepted", decided_by=wer, decided_at=_jetzt()))


@dataclass
class OffenerStand:
    """Was offen ist: berührte Objekte je Tabelle (Kennungen nach dem Anwenden) und, für neu angelegte Objekte,
    der Schritt, der sie anlegt – über ihn lassen sie sich ansprechen, bevor sie angenommen sind („neu:<Schritt>“)."""
    beruehrt: dict[str, set[int]] = field(default_factory=dict)
    neu: dict[tuple[str, int], int] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.beruehrt)


@contextmanager
def offener_stand(con: Connection) -> Iterator[OffenerStand]:
    """Den Baum lesen, als wären alle offenen Sätze angenommen (Sicht der Bearbeiter, E21).

    Die Sätze werden in einer Transaktion angewendet, die am Ende immer zurückgerollt wird; die Datei bleibt
    unverändert. Ein Satz mit Konflikt bleibt außen vor."""
    offen = offene_saetze(con)
    if con.in_transaction():
        con.rollback()
    if not offen:
        yield OffenerStand()
        return
    tx = con.begin()
    # Ausdrücklich beginnen: Der SQLite-Treiber beginnt sonst erst beim ersten Schreiben, und das Freigeben des
    # ersten Sicherungspunkts würde dann festschreiben.
    con.exec_driver_sql("BEGIN")
    stand = OffenerStand()
    try:
        for satz in offen:
            sp = con.begin_nested()
            try:
                annehmen(con, [satz["id"]], satz["author"])
            except Konflikt:
                sp.rollback()
                continue
            sp.commit()
            for s in schritte(con, [satz["id"]]):
                stand.beruehrt.setdefault(s["object_type"], set()).add(s["object_id"])
                if s["operation"] == "create":
                    stand.neu[(s["object_type"], s["object_id"])] = s["id"]
        yield stand
    finally:
        tx.rollback()


def offene_datensaetze(con: Connection) -> list[dict]:
    """Je Datensatz mit offenen Sätzen: xref, Anzahl, Autoren (in Reihenfolge), Zeit des letzten Satzes und ob der
    Datensatz angelegt oder gelöscht wird – in der Reihenfolge des ersten offenen Satzes."""
    aus: dict[str, dict] = {}
    offen = offene_saetze(con)
    art_von = {s["id"]: s for s in schritte(con, [s["id"] for s in offen])
               if s["object_type"] in ("person", "family") and s["operation"] in ("create", "delete")}
    for satz in offen:
        d = aus.setdefault(satz["record_xref"], {"xref": satz["record_xref"], "changes": 0, "users": [],
                                                 "time": satz["created_at"], "new": False, "deleted": False})
        d["changes"] += 1
        d["time"] = satz["created_at"]
        if satz["author"] not in d["users"]:
            d["users"].append(satz["author"])
    for s in art_von.values():
        xref = s["neu"].get("xref") if s["operation"] == "create" else s["alt"].get("xref")
        if xref in aus:
            aus[xref]["new" if s["operation"] == "create" else "deleted"] = True
    return list(aus.values())


def verwerfen(con: Connection, satz_ids: list[int], wer: str) -> None:
    con.execute(update(change_set).where(change_set.c.id.in_(satz_ids), change_set.c.status == "pending")
                .values(status="rejected", decided_by=wer, decided_at=_jetzt()))


def _aufloesen(con: Connection, wert):
    """"neu:<Schritt>" → die Kennung, die das angelegte Objekt beim Annehmen bekam."""
    if isinstance(wert, str) and (m := NEU.match(wert)):
        oid = con.execute(select(change_step.c.object_id).where(change_step.c.id == int(m.group(1)))).scalar()
        if oid is None:
            raise Konflikt(f"Schritt {m.group(1)} ist noch nicht angenommen")
        return oid
    return wert


def _schritt_anwenden(con: Connection, s: dict) -> None:
    t = T(s["object_type"])
    if s["operation"] == "create":
        werte = {k: _aufloesen(con, v) for k, v in s["neu"].items()}
        oid = con.execute(insert(t).values(**werte)).inserted_primary_key[0]
        con.execute(update(change_step).where(change_step.c.id == s["id"]).values(object_id=oid))
        return
    oid = _aufloesen(con, s["objekt"])
    r = con.execute(select(t).where(t.c.id == oid)).first()
    if r is None:
        raise Konflikt(f"{s['object_type']} {oid} gibt es nicht mehr")
    jetzt = dict(r._mapping)
    abweichend = [k for k, v in s["alt"].items() if jetzt.get(k) != _aufloesen(con, v)]
    if abweichend:
        raise Konflikt(f"{s['object_type']} {oid}: {', '.join(abweichend)} inzwischen geändert")
    if s["operation"] == "delete":
        con.execute(delete(t).where(t.c.id == oid))
    else:
        con.execute(update(t).where(t.c.id == oid).values(**{k: _aufloesen(con, v) for k, v in s["neu"].items()}))
    if s["object_id"] is None:
        con.execute(update(change_step).where(change_step.c.id == s["id"]).values(object_id=oid))


def _json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def _jetzt() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
