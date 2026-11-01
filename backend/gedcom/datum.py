"""GEDCOM-Datumsangaben (5.5.1 und 7.0) in Originaltext + Bereich in julianischen Tagen (KONZEPT.md 3.8).

Der Bereich ist der früheste und späteste Tag, der zur Angabe passt: „APR 1897“ = 1.–30. April 1897,
„BEF 1885“ = bis 31.12.1884, „FROM 1861 TO 1919“ = 1.1.1861–31.12.1919. Er dient zum Suchen und Sortieren, nie
zur Anzeige – angezeigt wird der Originaltext.

Kalender: gregorianisch und julianisch werden umgerechnet. Französischer Revolutionskalender und hebräischer
Kalender werden erkannt, aber noch nicht umgerechnet (Bereich leer, Kalender vermerkt).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MONATE = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
MONATE_FRANZ = ["VEND", "BRUM", "FRIM", "NIVO", "PLUV", "VENT", "GERM", "FLOR", "PRAI", "MESS", "THER", "FRUC", "COMP"]
MONATE_HEBR = ["TSH", "CSH", "KSL", "TVT", "SHV", "ADR", "ADS", "NSN", "IYR", "SVN", "TMZ", "AAV", "ELL"]

# 5.5.1: @#DJULIAN@ …   7.0: JULIAN …
_KALENDER = {
    "@#DGREGORIAN@": "gregorian", "@#DJULIAN@": "julian", "@#DHEBREW@": "hebrew", "@#DFRENCH R@": "french_r",
    "@#DROMAN@": "roman", "@#DUNKNOWN@": "unknown",
    "GREGORIAN": "gregorian", "JULIAN": "julian", "HEBREW": "hebrew", "FRENCH_R": "french_r",
}
_QUALITAET = {"ABT": "about", "CAL": "calculated", "EST": "estimated"}


@dataclass(frozen=True)
class Datum:
    text: str
    kind: str              # exact, before, after, between, from, to, from_to, phrase
    quality: str           # exact, about, calculated, estimated
    calendar: str          # gregorian, julian, hebrew, french_r, …
    von: int | None        # frühester julianischer Tag
    bis: int | None        # spätester julianischer Tag
    gueltig: bool          # False: nicht verstanden (bleibt als Text, kind = phrase)


# ── Julianische Tageszahl ───────────────────────────────────────────────────────────────────────────

def jd_gregorianisch(jahr: int, monat: int, tag: int) -> int:
    a = (14 - monat) // 12
    y = jahr + 4800 - a
    m = monat + 12 * a - 3
    return tag + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def jd_julianisch(jahr: int, monat: int, tag: int) -> int:
    a = (14 - monat) // 12
    y = jahr + 4800 - a
    m = monat + 12 * a - 3
    return tag + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083


def _schaltjahr(jahr: int, kalender: str) -> bool:
    if kalender == "julian":
        return jahr % 4 == 0
    return jahr % 4 == 0 and (jahr % 100 != 0 or jahr % 400 == 0)


def _monatslaenge(jahr: int, monat: int, kalender: str) -> int:
    if monat == 2:
        return 29 if _schaltjahr(jahr, kalender) else 28
    return 30 if monat in (4, 6, 9, 11) else 31


# ── Einzelnes Datum ─────────────────────────────────────────────────────────────────────────────────

_EINZEL = re.compile(r"^(?:(\d{1,2}) )?(?:([A-Z]{3,4}) )?(\d{1,4})(?:/(\d{2}))?( B\.?C\.?| BCE)?$")


def _einzel(text: str, kalender: str) -> tuple[int, int] | None:
    """Bereich (von, bis) eines einzelnen Datums ohne Vorsatz, oder None."""
    m = _EINZEL.match(text)
    if not m:
        return None
    tag_s, monat_s, jahr_s, doppel, vchr = m.groups()
    if kalender not in ("gregorian", "julian"):
        return None
    jahr = int(jahr_s)
    if doppel:  # 1700/01: Doppeldatierung, gemeint ist das spätere Jahr
        jahr += 1
    if vchr:
        jahr = 1 - jahr  # astronomische Zählung: 1 v. Chr. = 0
    jd = jd_julianisch if kalender == "julian" else jd_gregorianisch
    if monat_s is None:
        if tag_s:
            return None
        return jd(jahr, 1, 1), jd(jahr, 12, 31)
    monat = MONATE.get(monat_s)
    if monat is None:
        return None
    laenge = _monatslaenge(jahr, monat, kalender)
    if tag_s is None:
        return jd(jahr, monat, 1), jd(jahr, monat, laenge)
    tag = int(tag_s)
    if not 1 <= tag <= laenge:
        return None
    return jd(jahr, monat, tag), jd(jahr, monat, tag)


def _kalender_ab(text: str) -> tuple[str, str]:
    for vorsatz, name in _KALENDER.items():
        if text.startswith(vorsatz + " "):
            return name, text[len(vorsatz) + 1:].strip()
    return "gregorian", text


def _bereich(text: str) -> tuple[str, int, int] | None:
    """Ein Datum mit eigenem Kalendervorsatz: (Kalender, von, bis)."""
    kalender, rest = _kalender_ab(text)
    b = _einzel(rest, kalender)
    return (kalender, *b) if b else None


def lesen(text: str | None) -> Datum | None:
    """GEDCOM-Datum lesen. Leer → None. Nicht Verstandenes → kind 'phrase', gueltig False (Text bleibt)."""
    if text is None or not text.strip():
        return None
    original = text.strip()
    t = re.sub(r"\s+", " ", original).upper()

    def ergebnis(kind, quality, teil_von, teil_bis=None):
        kal = (teil_von or teil_bis)[0]
        von = teil_von[1] if teil_von else None
        bis = (teil_bis or teil_von)[2] if (teil_bis or teil_von) else None
        if kind == "before":
            von, bis = None, teil_von[1] - 1
        elif kind == "after":
            von, bis = teil_von[2] + 1, None
        elif kind == "from":
            bis = None
        elif kind == "to":
            von, bis = None, teil_von[2]
        return Datum(original, kind, quality, kal, von, bis, True)

    phrase = Datum(original, "phrase", "exact", "gregorian", None, None, original.startswith("(") and original.endswith(")"))
    # INT Datum (Text): ausgelegtes Datum mit Wortlaut
    m = re.match(r"^INT (.+?) \(.*\)$", t)
    if m:
        t = m.group(1)
    if t.startswith("(") and t.endswith(")"):
        return phrase

    for vorsatz in ("@#DHEBREW@", "@#DFRENCH R@", "HEBREW ", "FRENCH_R "):
        if vorsatz in t:  # erkannt, aber noch nicht umgerechnet
            return Datum(original, "exact", "exact", _KALENDER[vorsatz.strip()], None, None, True)

    m = re.match(r"^(ABT|CAL|EST) (.+)$", t)
    if m:
        b = _bereich(m.group(2))
        return ergebnis("exact", _QUALITAET[m.group(1)], b) if b else _ungueltig(original)
    m = re.match(r"^(BEF|AFT|TO) (.+)$", t)
    if m:
        b = _bereich(m.group(2))
        art = {"BEF": "before", "AFT": "after", "TO": "to"}[m.group(1)]
        return ergebnis(art, "exact", b) if b else _ungueltig(original)
    m = re.match(r"^BET (.+) AND (.+)$", t)
    if m:
        a, b = _bereich(m.group(1)), _bereich(m.group(2))
        return ergebnis("between", "exact", a, b) if a and b else _ungueltig(original)
    m = re.match(r"^FROM (.+) TO (.+)$", t)
    if m:
        a, b = _bereich(m.group(1)), _bereich(m.group(2))
        return ergebnis("from_to", "exact", a, b) if a and b else _ungueltig(original)
    m = re.match(r"^FROM (.+)$", t)
    if m:
        b = _bereich(m.group(1))
        return ergebnis("from", "exact", b) if b else _ungueltig(original)
    b = _bereich(t)
    return ergebnis("exact", "exact", b) if b else _ungueltig(original)


def _ungueltig(text: str) -> Datum:
    return Datum(text, "phrase", "exact", "gregorian", None, None, False)
