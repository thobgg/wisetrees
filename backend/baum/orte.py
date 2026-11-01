"""Ortstext einem Ort zuordnen, beim Schreiben (docs/PLAN-M2.md, Schritt 2).

„Hof Nr. 3, Bienenbüttel, Uelzen, …“ wird von oben nach unten gesucht: oberste Stufe ohne übergeordneten Ort, jede
weitere Stufe mit diesem Namen unter der vorigen (Groß-/Kleinschreibung egal). Fehlende Stufen werden als Teil der
laufenden Änderung angelegt – sie gelten erst, wenn die Änderung angenommen ist.
"""

from __future__ import annotations

from sqlalchemy import Connection, func, select

from .aenderungen import Aenderung
from .schema import tabelle as T


def zuordnen(con: Connection, aenderung: Aenderung, text: str) -> int | str | None:
    teile = [t.strip() for t in text.split(",") if t.strip()]
    if not teile:
        return None
    pn, pl = T("place_name"), T("place_link")
    eltern: int | str | None = None
    for teil in reversed(teile):
        gefunden = None
        if isinstance(eltern, int) or eltern is None:
            kandidaten = [r[0] for r in con.execute(
                select(pn.c.place_id).where(func.lower(pn.c.name) == teil.lower()).order_by(pn.c.place_id))]
            for pid in kandidaten:
                oben = [r[0] for r in con.execute(select(pl.c.parent_id).where(pl.c.place_id == pid))]
                if (eltern is None and not oben) or (eltern is not None and eltern in oben):
                    gefunden = pid
                    break
        if gefunden is None:
            gefunden = aenderung.anlegen("place")
            aenderung.anlegen("place_name", place_id=gefunden, sort=1, name=teil)
            if eltern is not None:
                aenderung.anlegen("place_link", place_id=gefunden, parent_id=eltern, sort=1)
        eltern = gefunden
    return eltern
