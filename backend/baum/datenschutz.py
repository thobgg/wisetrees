"""Datenschutz-Einstellungen und -Regeln eines Baums (KONZEPT.md E19, Stufe A).

Die Einstellungen stehen in meta unter privacy.<name>, die Regeln in der Tabelle privacy_rule. Fehlt ein Wert, gilt
die Vorgabe – sie entspricht dem Verhalten eines neuen Baums.

Stufen wie in der Leseschicht: 2 Besucher, 1 Mitglied (bis Moderator), 0 Verwalter, -1 niemand.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from sqlalchemy import Connection, delete, insert, select

from .schema import RESN_REGEL, meta, privacy_rule

# Sperrvermerk → höchste Stufe, die noch sehen darf
STUFE_VON_RESN = {"none": 2, "privacy": 1, "confidential": 0, "hidden": -1}

# Regeln eines neuen Baums
VORGABE_REGELN = (("SSN", "confidential"), ("SOUR", "privacy"), ("REPO", "privacy"), ("SUBM", "confidential"),
                  ("SUBN", "confidential"))


@dataclass
class Einstellungen:
    """Werte je Baum; die Vorgaben sind das Verhalten eines neuen Baums."""

    enabled: bool = True                     # Schutz an; aus = alle Datensätze für alle sichtbar
    members_only: bool = False               # Baum nur für angemeldete Mitglieder
    show_dead_people: int = 2                # Verstorbene sichtbar bis zu dieser Stufe (2 = auch Besucher)
    show_living_names: int = 1               # Namen privater Personen sichtbar bis zu dieser Stufe
    show_private_relationships: bool = True  # Familienstruktur auch mit privaten Mitgliedern zeigen
    max_alive_age: int = 120                 # Höchstalter für die Lebend-Regel (KONZEPT 5.2)
    keep_alive_years_birth: int = 0          # Verstorbene privat, bis die Geburt so viele Jahre zurückliegt
    keep_alive_years_death: int = 0          # Verstorbene privat, bis der Tod so viele Jahre zurückliegt


@dataclass
class Regeln:
    """Regeln ohne Sperrvermerk in den Daten, als Stufen (STUFE_VON_RESN)."""

    art: dict[str, int] = field(default_factory=dict)                  # Fakt- oder Datensatzart → Stufe
    datensatz: dict[str, int] = field(default_factory=dict)            # xref → Stufe
    fakt_am_datensatz: dict[tuple[str, str], int] = field(default_factory=dict)  # (xref, Faktart) → Stufe


def _als(typ, wert: str):
    if typ is bool or typ == "bool":
        return wert == "1"
    return int(wert)


def laden(con: Connection) -> tuple[Einstellungen, Regeln]:
    werte = {k.removeprefix("privacy."): v for k, v in con.execute(
        select(meta.c.key, meta.c.value).where(meta.c.key.like("privacy.%")))}
    e = Einstellungen()
    for f in fields(e):
        if f.name in werte and werte[f.name] not in (None, ""):
            setattr(e, f.name, _als(f.type, werte[f.name]))
    r = Regeln()
    for xref, tag, resn in con.execute(select(privacy_rule.c.xref, privacy_rule.c.tag, privacy_rule.c.resn)):
        stufe = STUFE_VON_RESN[resn]
        if xref and tag:
            r.fakt_am_datensatz[(xref, tag)] = stufe
        elif xref:
            r.datensatz[xref] = stufe
        else:
            r.art[tag] = stufe
    return e, r


def einstellungen_speichern(con: Connection, e: Einstellungen) -> None:
    """Alle Werte schreiben (in einer offenen Transaktion des Aufrufers)."""
    for f in fields(e):
        wert = getattr(e, f.name)
        text = ("1" if wert else "0") if isinstance(wert, bool) else str(int(wert))
        con.execute(delete(meta).where(meta.c.key == f"privacy.{f.name}"))
        con.execute(insert(meta).values(key=f"privacy.{f.name}", value=text))


def regel_setzen(con: Connection, xref: str | None, tag: str | None, resn: str | None) -> None:
    """Regel setzen oder (resn None) entfernen; je (xref, tag) höchstens eine."""
    if not xref and not tag:
        raise ValueError("Regel braucht eine Kennung oder eine Art")
    if resn is not None and resn not in RESN_REGEL:
        raise ValueError(f"unbekannter Sperrvermerk {resn!r}")
    xref, tag = xref or None, tag or None
    bed = [privacy_rule.c.xref.is_(None) if xref is None else privacy_rule.c.xref == xref,
           privacy_rule.c.tag.is_(None) if tag is None else privacy_rule.c.tag == tag]
    con.execute(delete(privacy_rule).where(*bed))
    if resn is not None:
        con.execute(insert(privacy_rule).values(xref=xref, tag=tag, resn=resn))


def regeln_auflisten(con: Connection) -> list[dict]:
    return [{"id": r.id, "xref": r.xref, "tag": r.tag, "resn": r.resn}
            for r in con.execute(select(privacy_rule).order_by(privacy_rule.c.xref, privacy_rule.c.tag))]


def vorgaben_anlegen(con: Connection) -> None:
    """Die Regeln eines neuen Baums (in einer offenen Transaktion des Aufrufers)."""
    for tag, resn in VORGABE_REGELN:
        regel_setzen(con, None, tag, resn)
