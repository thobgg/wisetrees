"""v1: offene Änderungen sehen, annehmen und verwerfen (docs/PLAN-M2.md, Schritt 3; KONZEPT.md E21).

  GET  Pending   offene Änderungen je Datensatz: xref, type (INDI/FAM), name, kind (changed/new/deleted), changes
                 (Anzahl der Sätze), users (Autoren), time (letzter Satz)
  POST Accept    offene Sätze annehmen – mit xref die eines Datensatzes, ohne alle des Baums
  POST Reject    ebenso verwerfen
Antwort von Accept und Reject: {ok: true, pending: <Datensätze, die noch offen sind>}.

Nur Moderatoren und Verwalter; sonst not-moderator (403). Unbekannte xref → not-found (404). Lässt sich ein Satz
nicht anwenden, weil sich der angenommene Stand an der Moderation vorbei geändert hat, wird nichts angenommen:
conflict (409).
"""

from __future__ import annotations

from baum import aenderungen as ae

from .http import GET_AKTIONEN, POST_AKTIONEN, Kontext, fehler
from .personen import Bau
from .sicht import Lesestand, sicht_fuer

MODERATION = ("moderator", "manager")


def _pruefen(ctx: Kontext):
    """(Sicht, Baum) oder eine Fehlerantwort."""
    try:
        s = sicht_fuer(ctx, ctx.baum_name or "")
    except Exception:  # noqa: BLE001
        return fehler(404, "tree-not-found")
    if ctx.konten.rolle(ctx.konto, ctx.baum_name) not in MODERATION:
        return fehler(403, "not-moderator")
    return s, ctx.app.state.baeume.baum(ctx.baum_name)


def offene_anzahl(con) -> int:
    """Datensätze mit offenen Änderungen."""
    return len({s["record_xref"] for s in ae.offene_saetze(con)})


def pending(ctx: Kontext):
    r = _pruefen(ctx)
    if not isinstance(r, tuple):
        return r
    _, b = r
    con = b.oeffnen()
    try:
        offen = ae.offene_datensaetze(con)
    finally:
        con.close()
    daten = []
    # Namen wie für Bearbeiter: vorhandene Datensätze mit dem angenommenen Namen, neue mit dem offenen
    with Lesestand(ctx, ctx.baum_name, offen=True) as ls:
        s = ls.sicht
        bau = Bau(ctx, s)
        for d in offen:
            xref = d["xref"]
            pid, fid = s.m.person_xref.get(xref), s.m.familie_xref.get(xref)
            if pid is not None:
                name = bau.name(s.m.personen[pid])
            elif fid is not None:
                name = _familie(bau, fid)
            else:
                name = ""
            art = "FAM" if fid is not None or d["tabelle"] == "family" else "INDI"
            kind = "new" if d["new"] else "deleted" if d["deleted"] else "changed"
            daten.append({"xref": xref, "type": art, "name": name, "kind": kind, "changes": d["changes"],
                          "users": list(dict.fromkeys(_anzeigename(ctx, u) for u in d["users"])), "time": d["time"]})
    return {"data": daten}


def _anzeigename(ctx: Kontext, name: str) -> str:
    """Anzeigename des Kontos (wie Info.user.realName); ein gelöschtes Konto bleibt mit seinem Namen stehen."""
    k = ctx.konten.konto(name)
    return (k.real_name or k.name) if k else name


def _familie(bau: Bau, fid: int) -> str:
    from . import anzeige

    f = bau.m.familien[fid]
    ohne = f"{anzeige.UNBEKANNT} {anzeige.UNBEKANNT}"
    return " + ".join(bau.name(bau.m.personen[f.partner[k]]) if k in f.partner else ohne for k in (1, 2))


def _entscheiden(ctx: Kontext, annehmen: bool):
    r = _pruefen(ctx)
    if not isinstance(r, tuple):
        return r
    s, b = r
    xref = ctx.params.get("xref") or ""
    con = b.oeffnen()
    try:
        saetze = ae.offene_saetze(con, xref) if xref else ae.offene_saetze(con)
        if xref and not saetze and xref not in s.m.person_xref and xref not in s.m.familie_xref:
            return fehler(404, "not-found")
        # Was zusammengehört, geht zusammen: Annehmen nimmt die Sätze mit, deren neu angelegte Objekte gebraucht
        # werden; Verwerfen die, die auf verworfene neue Objekte bauen.
        ids = ae.abhaengige(con, [x["id"] for x in saetze], "vor" if annehmen else "nach")
        if con.in_transaction():
            con.rollback()
        try:
            with con.begin():
                if annehmen:
                    ae.annehmen(con, ids, ctx.konto.name)
                else:
                    ae.verwerfen(con, ids, ctx.konto.name)
        except ae.Konflikt:
            return fehler(409, "conflict")
        return {"ok": True, "pending": offene_anzahl(con)}
    finally:
        con.close()


def accept(ctx: Kontext):
    return _entscheiden(ctx, True)


def reject(ctx: Kontext):
    return _entscheiden(ctx, False)


GET_AKTIONEN["Pending"] = pending
POST_AKTIONEN["Accept"] = accept
POST_AKTIONEN["Reject"] = reject
