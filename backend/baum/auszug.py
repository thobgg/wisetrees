"""Modellauszug: der ganze Baum als verschachtelte Struktur zum Vergleichen (KONZEPT.md 6, Rundlauf-Test).

Datensätze stehen unter ihrer GEDCOM-Kennung, alles andere an seinem Träger. Interne Kennungen und Sortiernummern
fehlen, es zählt nur die Reihenfolge der Listen. Leere Spalten fehlen ebenfalls. Zwei Baumdateien mit demselben
Inhalt ergeben denselben Auszug, gleich in welcher Reihenfolge die Zeilen angelegt wurden.

Orte ohne Kennung (aus dem Ortstext eines Ereignisses angelegt) heißen nach ihrer Namenskette, z. B.
„Hof Nr. 3 < Bienenbüttel < @L1@“.

Nicht im Auszug: Kopf und Importbericht der eingelesenen Datei, Datenschutz-Regeln und Änderungssätze – sie sind kein
GEDCOM. `gesehen` hält fest, welche Zeilen der Auszug erfasst hat; `nicht_erfasst()` nennt die übrigen.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import Connection, select

from .schema import TRAEGER
from .schema import tabelle as T

# Tabellen, die zum Modell gehören und ganz im Auszug stehen müssen
MODELL = ("person", "name", "family", "family_member", "parentage", "place", "place_name", "place_type", "place_link",
          "place_attribute", "event", "event_role", "event_place_detail", "person_association", "repository",
          "source", "source_coverage", "source_repository", "note", "media", "media_file", "task", "citation",
          "note_link", "media_link", "gedcom_rest")
META_OHNE = {"gedcom_head", "import_report"}

# Spalten, die nicht als Wert in den Auszug kommen: Kennung, Reihenfolge, Träger und Verweise (die als Name kommen)
_NIE = {"id", "sort", "person_sort", "fact_sort", "on_tree"}
_VERWEISE = {"person_id", "family_id", "place_id", "event_id", "event_role_id", "name_id", "source_id",
             "repository_id", "media_id", "note_id", "citation_id", "task_id", "person_association_id",
             "child_id", "parent_id", "other_person_id", "place_attribute_id", "entry_id"}


def _rest_text(gedcom: str) -> str:
    """Stufen so verschieben, dass die erste Zeile auf 0 steht."""
    zeilen = gedcom.split("\n")
    try:
        basis = int(zeilen[0].split(" ", 1)[0])
    except ValueError:
        return gedcom
    aus = []
    for z in zeilen:
        stufe, _, rest = z.partition(" ")
        aus.append(f"{int(stufe) - basis} {rest}" if stufe.isdigit() else z)
    return "\n".join(aus)


class Auszug:
    def __init__(self, con: Connection):
        self.z: dict[str, dict[int, dict]] = {}
        for t in MODELL:
            self.z[t] = {r["id"]: dict(r) for r in con.execute(select(T(t))).mappings()}
        self.meta = {k: v for k, v in con.execute(select(T("meta").c.key, T("meta").c.value)) if k not in META_OHNE}
        self.gesehen: dict[str, set[int]] = defaultdict(set)

        # Anhänge je Träger, in Reihenfolge
        self.an: dict[str, dict[tuple[str, int | None], list[dict]]] = {}
        for t, typen in TRAEGER.items():
            nach = defaultdict(list)
            for r in self._sortiert(t):
                for typ in typen:
                    if typ == "tree" and r.get("on_tree"):
                        nach[("tree", None)].append(r)
                    elif typ != "tree" and r.get(f"{typ}_id") is not None:
                        nach[(typ, r[f"{typ}_id"])].append(r)
            self.an[t] = nach

        self.nach: dict[tuple[str, str], dict[int, list[dict]]] = {}
        for t, spalte in (("name", "person_id"), ("place_name", "place_id"), ("place_type", "place_id"),
                          ("place_link", "place_id"), ("place_attribute", "place_id"), ("source_coverage", "source_id"),
                          ("source_repository", "source_id"), ("media_file", "media_id"),
                          ("person_association", "person_id"), ("event_place_detail", "event_id"),
                          ("parentage", "family_id")):
            self.nach[(t, spalte)] = self._gruppiert(t, spalte)
        self.rollen = self._gruppiert("event_role", "event_id")
        self.haupt: dict[tuple[str, int], list[dict]] = defaultdict(list)
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
        self._ortsnamen: dict[int, str] = {}

    # ── Hilfen ─────────────────────────────────────────────────────────────────────────────────────

    def _sortiert(self, t: str) -> list[dict]:
        return sorted(self.z[t].values(), key=lambda r: (r.get("sort", 0), r["id"]))

    def _gruppiert(self, t: str, spalte: str) -> dict[int, list[dict]]:
        g = defaultdict(list)
        for r in self._sortiert(t):
            g[r[spalte]].append(r)
        return g

    def felder(self, t: str, r: dict, **dazu) -> dict:
        """Werte einer Zeile ohne Kennung, Reihenfolge und Verweise; leere Spalten fehlen."""
        self.gesehen[t].add(r["id"])
        d = {k: v for k, v in r.items() if v is not None and k not in _NIE and k not in _VERWEISE}
        d.update({k: v for k, v in dazu.items() if v not in (None, [], {})})
        return d

    def xref(self, t: str, id_: int | None) -> str | None:
        return None if id_ is None else f"@{self.z[t][id_]['xref']}@"

    def person(self, id_):
        return self.xref("person", id_)

    def ort(self, pid: int | None, unterwegs: frozenset = frozenset()) -> str | None:
        """Name eines Ortes: Kennung, sonst Namenskette über die übergeordneten Orte."""
        if pid is None:
            return None
        if pid in self._ortsnamen:
            return self._ortsnamen[pid]
        p = self.z["place"][pid]
        if p["xref"]:
            name = f"@{p['xref']}@"
        else:
            namen = "/".join(n["name"] for n in self.nach[("place_name", "place_id")].get(pid, [])) or "?"
            eltern = sorted(self.ort(link["parent_id"], unterwegs | {pid})
                            for link in self.nach[("place_link", "place_id")].get(pid, [])
                            if link["parent_id"] not in unterwegs | {pid})
            name = " < ".join([namen, " | ".join(eltern)]) if eltern else namen
        if not unterwegs:
            self._ortsnamen[pid] = name
        return name

    # ── Anhänge ────────────────────────────────────────────────────────────────────────────────────

    def anhaenge(self, typ: str, id_: int | None) -> dict:
        k = (typ, id_)
        d = {
            "notes": [self.notizverweis(r) for r in self.an["note_link"].get(k, [])],
            "citations": [self.zitat(r) for r in self.an["citation"].get(k, [])],
            "media": [self.medienverweis(r) for r in self.an["media_link"].get(k, [])],
            "tasks": [self.aufgabe(r) for r in self.an["task"].get(k, [])],
            "rest": [self.rest(r) for r in self.an["gedcom_rest"].get(k, [])],
        }
        return {k_: v for k_, v in d.items() if v}

    def rest(self, r: dict) -> dict:
        self.gesehen["gedcom_rest"].add(r["id"])
        d = {"gedcom": _rest_text(r["gedcom"])}
        if r["under"]:
            d["under"] = r["under"]
        return d

    def notizverweis(self, r: dict) -> dict | str:
        self.gesehen["note_link"].add(r["id"])
        n = self.z["note"][r["note_id"]]
        if n["xref"]:
            return f"@{n['xref']}@"
        return self.felder("note", n, **self.anhaenge("note", n["id"]))

    def zitat(self, r: dict) -> dict:
        return self.felder("citation", r, source=self.xref("source", r["source_id"]),
                           **self.anhaenge("citation", r["id"]))

    def medienverweis(self, r: dict) -> dict:
        m = self.z["media"][r["media_id"]]
        return self.felder("media_link", r, object=f"@{m['xref']}@" if m["xref"] else self.medium(m))

    def medium(self, m: dict) -> dict:
        dateien = [self.felder("media_file", f) for f in self.nach[("media_file", "media_id")].get(m["id"], [])]
        return self.felder("media", m, files=dateien, **self.anhaenge("media", m["id"]))

    def aufgabe(self, r: dict) -> dict:
        return self.felder("task", r, repository=self.xref("repository", r["repository_id"]),
                           **self.anhaenge("task", r["id"]))

    # ── Ereignisse ─────────────────────────────────────────────────────────────────────────────────

    def ortsangabe(self, a_id: int | None) -> dict | None:
        if a_id is None:
            return None
        a = self.z["place_attribute"][a_id]
        return {k: a[k] for k in ("kind", "value", "date_text") if a[k] is not None}

    def beteiligung(self, r: dict) -> dict:
        return self.felder("event_role", r, person=self.person(r["person_id"]),
                           family=self.xref("family", r["family_id"]), place=self.ort(r["place_id"]),
                           **self.anhaenge("event_role", r["id"]))

    def ereignis(self, eid: int, traeger: dict) -> dict:
        e = self.z["event"][eid]
        rollen = self.rollen.get(eid, [])
        andere_haupt = sorted(self.person(r["person_id"]) or self.xref("family", r["family_id"])
                              or self.ort(r["place_id"])
                              for r in rollen if r["role"] == "PRINCIPAL" and r["id"] != traeger["id"])
        details = [self.felder("event_place_detail", d, attribute=self.ortsangabe(d["place_attribute_id"]))
                   for d in self.nach[("event_place_detail", "event_id")].get(eid, [])]
        return self.felder("event", e, place=self.ort(e["place_id"]), place_details=details,
                           roles=[self.beteiligung(r) for r in rollen if r["role"] != "PRINCIPAL"],
                           shared_with=andere_haupt, **self.anhaenge("event", eid))

    def fakten(self, typ: str, id_: int) -> list[dict]:
        aus = []
        for r in self.haupt.get((typ, id_), []):
            d = self.felder("event_role", r, **self.anhaenge("event_role", r["id"]))
            d.pop("role", None)
            d["event"] = self.ereignis(r["event_id"], r)
            aus.append(d)
        return aus

    # ── Datensätze ─────────────────────────────────────────────────────────────────────────────────

    def personen(self) -> dict:
        aus = {}
        for p in self.z["person"].values():
            pid = p["id"]
            namen = [self.felder("name", n, **self.anhaenge("name", n["id"]))
                     for n in self.nach[("name", "person_id")].get(pid, [])]
            mitglied = self.mitglied_person.get(pid, [])
            for m in mitglied:
                self.gesehen["family_member"].add(m["id"])
            famc = [self.xref("family", m["family_id"]) for m in mitglied if m["role"] == "child"]
            fams = [self.xref("family", m["family_id"]) for m in mitglied if m["role"] == "partner"]
            asso = [self.felder("person_association", a, other=self.person(a["other_person_id"]),
                                **self.anhaenge("person_association", a["id"]))
                    for a in self.nach[("person_association", "person_id")].get(pid, [])]
            aus[f"@{p['xref']}@"] = self.felder("person", p, names=namen, facts=self.fakten("person", pid),
                                                famc=famc, fams=fams, associations=asso,
                                                **self.anhaenge("person", pid))
        return aus

    def familien(self) -> dict:
        aus = {}
        for f in self.z["family"].values():
            fid = f["id"]
            mitglied = self.mitglied_familie.get(fid, [])
            partner = [{"person": self.person(m["person_id"]), "slot": m["sort"]} for m in mitglied
                       if m["role"] == "partner"]
            kinder = [self.person(m["person_id"]) for m in mitglied if m["role"] == "child"]
            abst = sorted(({**self.felder("parentage", a), "child": self.person(a["child_id"]),
                            "parent": self.person(a["parent_id"])}
                           for a in self.nach[("parentage", "family_id")].get(fid, [])),
                          key=lambda a: (a["child"], a["parent"]))
            aus[f"@{f['xref']}@"] = self.felder("family", f, partners=partner, children=kinder, parentage=abst,
                                                facts=self.fakten("family", fid), **self.anhaenge("family", fid))
        return aus

    def orte(self) -> dict:
        aus = {}
        for p in self.z["place"].values():
            pid = p["id"]
            n = lambda t, pid=pid: self.nach[(t, "place_id")].get(pid, [])  # noqa: E731
            links = sorted(({**self.felder("place_link", link), "parent": self.ort(link["parent_id"])}
                            for link in n("place_link")), key=lambda d: d["parent"])
            name = self.ort(pid)
            if name in aus:
                name = f"{name} #{sum(1 for k in aus if k.startswith(name))}"
            aus[name] = self.felder("place", p, names=[self.felder("place_name", x) for x in n("place_name")],
                                    types=[self.felder("place_type", x) for x in n("place_type")],
                                    links=links, attributes=[self.felder("place_attribute", x) for x in n("place_attribute")],
                                    facts=self.fakten("place", pid), **self.anhaenge("place", pid))
        return aus

    def quellen(self) -> dict:
        aus = {}
        for s in self.z["source"].values():
            sid = s["id"]
            abdeckung = [self.felder("source_coverage", c) for c in self.nach[("source_coverage", "source_id")].get(sid, [])]
            archive = [self.felder("source_repository", r, repository=self.xref("repository", r["repository_id"]))
                       for r in self.nach[("source_repository", "source_id")].get(sid, [])]
            aus[f"@{s['xref']}@"] = self.felder("source", s, coverage=abdeckung, repositories=archive,
                                                **self.anhaenge("source", sid))
        return aus

    def datensaetze(self, t: str, f) -> dict:
        return {f"@{r['xref']}@": f(r) for r in self.z[t].values() if r["xref"]}

    def ganz(self) -> dict:
        # Orte zuerst: Ihre Namen brauchen die übrigen Teile.
        orte = self.orte()
        return {
            "meta": self.meta,
            "person": self.personen(),
            "family": self.familien(),
            "place": orte,
            "source": self.quellen(),
            "repository": self.datensaetze("repository", lambda r: self.felder(
                "repository", r, **self.anhaenge("repository", r["id"]))),
            "note": self.datensaetze("note", lambda r: self.felder("note", r, **self.anhaenge("note", r["id"]))),
            "media": self.datensaetze("media", self.medium),
            "tree": self.anhaenge("tree", None),
        }

    def nicht_erfasst(self) -> dict[str, list[int]]:
        """Zeilen der Modelltabellen, die nicht im Auszug stehen (sollte leer sein)."""
        return {t: sorted(set(self.z[t]) - self.gesehen[t]) for t in MODELL if set(self.z[t]) - self.gesehen[t]}


def auszug(con: Connection) -> dict:
    return Auszug(con).ganz()
