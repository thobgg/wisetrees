"""Bausteine der GEDCOM-Ausgabe: Strukturen als Baum, GEDCOM-Reste als Strukturen, Zeilen schreiben.

Für 5.5.1 und 7.0 gleich; Unterschiede: 5.5.1 begrenzt die Zeile auf 255 Zeichen (Fortsetzung mit CONC), 7.0 kennt
CONC nicht mehr. Ein Wert, der mit @ beginnt und kein Verweis ist, steht mit @@ – in 5.5.1 außer einer Escape-Folge
wie @#DJULIAN@, die es in 7.0 nicht mehr gibt.
"""

from __future__ import annotations

import re

ZEILE_551 = 255   # Zeichen je Zeile in 5.5.1

_ZEILE = re.compile(r"^(\d+) (?:(@[^@ ]+@) )?([A-Za-z0-9_]+)(?: (.*))?$")
ZEIGER = re.compile(r"^@[^@#][^@]*@$")


class E:
    """Eine Struktur der Ausgabe: Tag, Wert, Kennung, Kinder; eine unlesbare Zeile steht roh in `roh`."""

    __slots__ = ("tag", "wert", "xref", "kinder", "roh")

    def __init__(self, tag: str, wert: str | None = None, xref: str | None = None, roh: str | None = None):
        self.tag, self.wert, self.xref, self.kinder, self.roh = tag, wert, xref, [], roh

    def __repr__(self) -> str:
        return f"E({self.tag!r}, {self.wert!r})"

    def neu(self, tag: str, wert=None) -> E:
        k = E(tag, None if wert is None else str(wert))
        self.kinder.append(k)
        return k

    def falls(self, tag: str, wert) -> E | None:
        """Kind nur, wenn es einen Wert gibt."""
        return None if wert is None or wert == "" else self.neu(tag, wert)

    def erstes(self, tag: str) -> E | None:
        return next((k for k in self.kinder if k.tag == tag), None)

    def bezeichnung(self) -> str:
        return f"{self.tag} {self.wert}" if self.wert else self.tag

    def pfad(self, under: str) -> E:
        """Die Struktur, unter der ein Rest stand („PLAC“, „FAMC @F1@“, „FILE a.jpg:FORM“); fehlt sie, wird sie
        angelegt."""
        if not under:
            return self
        for k in self.kinder:
            if k.roh is not None:
                continue
            for b in dict.fromkeys((k.bezeichnung(), k.tag)):
                if under == b:
                    return k
                if under.startswith(b + ":"):
                    return k.pfad(under[len(b) + 1:])
        kopf, _, rest = under.partition(":")
        tag, _, wert = kopf.partition(" ")
        return self.neu(tag, wert or None).pfad(rest)


def aus_text(text: str) -> list[E]:
    """GEDCOM-Text mit beliebigen Stufen (ein Rest, ein Datensatz) als Strukturen; CONT und CONC gehen in den Wert.
    Eine unlesbare Zeile bleibt roh und hängt wie beim Lesen an der obersten Struktur."""
    oben: list[E] = []
    stapel: list[tuple[int, E]] = []
    for z in text.split("\n"):
        m = _ZEILE.match(z)
        if not m:
            (stapel[0][1].kinder if stapel else oben).append(E("", roh=z))
            continue
        lv, xref, tag, wert = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        while stapel and stapel[-1][0] >= lv:
            stapel.pop()
        if tag in ("CONT", "CONC") and stapel and stapel[-1][0] == lv - 1:
            e = stapel[-1][1]
            e.wert = (e.wert or "") + ("\n" if tag == "CONT" else "") + (wert or "")
            continue
        e = E(tag, wert, xref[1:-1] if xref else None)
        (stapel[-1][1].kinder if stapel else oben).append(e)
        stapel.append((lv, e))
    return oben


def _wert_zeilen(level: int, kopf: str, wert: str | None, v551: bool) -> list[str]:
    """Kopfzeile mit Wert; Zeilenumbrüche als CONT. In 5.5.1 werden lange Zeilen mit CONC fortgesetzt, nicht an
    einem Leerzeichen getrennt (Leser schneiden dort ab)."""
    if wert is None:
        return [kopf]
    if wert.startswith("@") and not ZEIGER.fullmatch(wert) and not (v551 and wert.startswith("@#")):
        wert = "@" + wert
    aus = []
    fort = f"{level + 1} CONC"
    for i, teil in enumerate(wert.split("\n")):
        vorn = kopf if i == 0 else f"{level + 1} CONT"
        while True:
            platz = max(ZEILE_551 - len(vorn) - 1, 20)
            if not v551 or len(teil) <= platz:
                aus.append(vorn + (f" {teil}" if teil else ""))
                break
            schnitt = platz
            while schnitt > 1 and (teil[schnitt - 1] == " " or teil[schnitt] == " "):
                schnitt -= 1
            if schnitt <= 1:
                schnitt = platz
            aus.append(f"{vorn} {teil[:schnitt]}")
            teil = teil[schnitt:]
            vorn = fort
    return aus


def zeilen(e: E, level: int, v551: bool) -> list[str]:
    if e.roh is not None:
        return [e.roh]
    kopf = f"{level} " + (f"@{e.xref}@ " if e.xref else "") + e.tag
    aus = _wert_zeilen(level, kopf, e.wert, v551)
    for k in e.kinder:
        aus += zeilen(k, level + 1, v551)
    return aus
