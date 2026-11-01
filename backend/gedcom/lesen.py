"""GEDCOM-Datei lesen: Zeichensatz, Zeilen, Baum aus Knoten. Für 5.5.1 und 7.0, ohne fremde Bibliothek.

Zeichensatz: BOM (UTF-8, UTF-16) hat Vorrang, sonst die Zeile `1 CHAR` im Kopf. UTF-8, UNICODE (UTF-16),
ASCII und ANSI (Windows-1252) werden gelesen. ANSEL wird erkannt und abgelehnt (noch nicht umgesetzt) –
lieber eine klare Meldung als still verfälschte Umlaute.

CONC und CONT werden in den Wert des Elternknotens eingefügt. Jeder Knoten zählt die Dateizeilen, die in ihm
stecken (`zeilen`), damit der Import belegen kann, dass keine Zeile verloren geht (KONZEPT.md 3, E9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ZEILE = re.compile(r"^\s*(\d+) +(?:(@[^@ ]+@) +)?([A-Za-z0-9_]+)(?: (.*))?$")
_ZEIGER = re.compile(r"^@[^@#][^@]*@$")


class NichtLesbar(Exception):
    """Die Datei lässt sich nicht als GEDCOM lesen (Zeichensatz, kein Kopf)."""


@dataclass
class Knoten:
    level: int
    tag: str
    wert: str | None = None
    xref: str | None = None          # Kennung eines Datensatzes (@I1@ → I1)
    kinder: list[Knoten] = field(default_factory=list)
    zeile: int = 0                   # Zeilennummer in der Datei
    zeilen: int = 1                  # Dateizeilen in diesem Knoten (mit CONC/CONT, ohne Kinder)

    @property
    def zeiger(self) -> str | None:
        """Zeigt der Wert auf einen Datensatz (@I1@), dessen Kennung ohne @."""
        if self.wert and _ZEIGER.match(self.wert):
            return self.wert[1:-1]
        return None

    def erstes(self, tag: str) -> Knoten | None:
        return next((k for k in self.kinder if k.tag == tag), None)

    def alle(self, tag: str) -> list[Knoten]:
        return [k for k in self.kinder if k.tag == tag]

    def wert_von(self, tag: str) -> str | None:
        k = self.erstes(tag)
        return k.wert if k else None

    def zeilen_gesamt(self) -> int:
        return self.zeilen + sum(k.zeilen_gesamt() for k in self.kinder)

    def gedcom(self, level: int | None = None) -> str:
        """Den Teilbaum wieder als GEDCOM (Zeilenumbrüche im Wert als CONT)."""
        if not self.tag:  # unlesbare Zeile: so, wie sie kam
            return self.wert or ""
        lv = self.level if level is None else level
        kopf = f"{lv} " + (f"@{self.xref}@ " if self.xref else "") + self.tag
        teile = (self.wert or "").split("\n") if self.wert is not None else [None]
        zeilen = [kopf + (f" {teile[0]}" if teile[0] else "")]
        zeilen += [f"{lv + 1} CONT" + (f" {t}" if t else "") for t in teile[1:]]
        for k in self.kinder:
            zeilen.append(k.gedcom(lv + 1))
        return "\n".join(zeilen)


@dataclass
class Datei:
    kopf: Knoten | None
    datensaetze: list[Knoten]
    zeichensatz: str
    version: str | None              # 5.5.1, 7.0 …
    zeilen: int                      # nicht leere Zeilen der Datei
    fehler: list[str]                # unlesbare Zeilen (als Knoten mit tag "" erhalten)


def _zeichensatz(daten: bytes) -> tuple[str, bytes]:
    if daten.startswith(b"\xef\xbb\xbf"):
        return "utf-8", daten[3:]
    if daten.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16", daten
    if daten[:2] == b"0\x00":
        return "utf-16-le", daten
    if daten[:2] == b"\x000":
        return "utf-16-be", daten
    m = re.search(rb"\n\s*1 CHAR ([A-Za-z0-9 -]+)", daten[:4000].replace(b"\r", b"\n"))
    char = m.group(1).strip().upper().decode("ascii") if m else "UTF-8"
    if char in ("UTF-8", "UTF8"):
        return "utf-8", daten
    if char in ("ANSI", "WINDOWS-1252", "CP1252"):
        return "cp1252", daten
    if char == "ASCII":
        return "ascii", daten
    if char == "ANSEL":
        raise NichtLesbar("Zeichensatz ANSEL wird noch nicht unterstützt")
    if char == "UNICODE":
        return "utf-16", daten
    raise NichtLesbar(f"unbekannter Zeichensatz {char}")


def lesen(daten: bytes) -> Datei:
    kodierung, rest = _zeichensatz(daten)
    try:
        text = rest.decode(kodierung)
    except UnicodeDecodeError as e:
        raise NichtLesbar(f"Datei passt nicht zum Zeichensatz {kodierung}: Byte {e.start}") from e
    text = text.lstrip("﻿")

    wurzel = Knoten(-1, "")
    stapel = [wurzel]
    fehler: list[str] = []
    anzahl = 0
    for nr, roh in enumerate(re.split(r"\r\n|\r|\n", text), start=1):
        if not roh.strip():
            continue
        anzahl += 1
        m = _ZEILE.match(roh)
        if not m:
            fehler.append(f"Zeile {nr}: {roh[:80]!r}")
            # an den Datensatz hängen, in dem sie steht (dort hebt der Import sie als Rest auf)
            eltern = stapel[1] if len(stapel) > 1 else wurzel
            eltern.kinder.append(Knoten(eltern.level + 1, "", roh, zeile=nr))
            continue
        level, xref, tag, wert = int(m.group(1)), m.group(2), m.group(3).upper(), m.group(4)
        if wert is not None and wert.startswith("@@"):
            wert = wert[1:]
        while len(stapel) > 1 and stapel[-1].level >= level:
            stapel.pop()
        eltern = stapel[-1]
        if tag in ("CONC", "CONT") and eltern is not wurzel and level == eltern.level + 1:
            eltern.wert = (eltern.wert or "") + ("\n" if tag == "CONT" else "") + (wert or "")
            eltern.zeilen += 1
            continue
        k = Knoten(level, tag, wert, xref[1:-1] if xref else None, zeile=nr)
        eltern.kinder.append(k)
        stapel.append(k)

    kopf = next((k for k in wurzel.kinder if k.tag == "HEAD"), None)
    if kopf is None:
        raise NichtLesbar("kein GEDCOM-Kopf (0 HEAD)")
    gedc = kopf.erstes("GEDC")
    version = gedc.wert_von("VERS") if gedc else None
    return Datei(kopf, [k for k in wurzel.kinder if k is not kopf], kodierung, version, anzahl, fehler)
