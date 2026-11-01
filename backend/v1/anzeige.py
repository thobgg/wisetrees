"""Anzeigetexte für v1 auf Deutsch (KONZEPT.md: Wortlaut wie v1, eigene Tabelle; entschieden 01.11.2026).

Datumsanzeige, Lebensspanne und Namen in der Form, die die Apps zeigen. Der Wortlaut folgt den v1-Aufzeichnungen
(vertrag/aufzeichnungen).
"""

from __future__ import annotations

import re

from gedcom import datum as gdatum

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
UNBEKANNT = "…"
PRIVAT = "Vertraulich"   # Name einer verborgenen Person (Wortlaut der Aufzeichnungen)

_TEIL = re.compile(r"^(?:(@#D[A-Z ]+@|JULIAN|GREGORIAN) )?(?:(\d{1,2}) )?(?:([A-Z]{3,4}) )?(\d{1,4})(/\d{2})?( B\.?C\.?)?$")


def _teil_anzeigen(t: str) -> str | None:
    m = _TEIL.match(t.strip())
    if not m:
        return None
    _, tag, monat, jahr, doppel, vchr = m.groups()
    jahr_s = jahr + (doppel or "") + (" v. Chr." if vchr else "")
    if monat is None:
        return jahr_s
    nr = gdatum.MONATE.get(monat)
    if nr is None:
        return None
    return (f"{int(tag)}. " if tag else "") + f"{MONATE[nr - 1]} {jahr_s}"


def _teile(text: str) -> list[tuple[str, str]]:
    """Datum in (Vorsatz, Einzeldatum) zerlegen: „FROM 1861 TO 1919“ → [(FROM, 1861), (TO, 1919)]."""
    t = re.sub(r"\s+", " ", text.strip().upper())
    m = re.match(r"^(BET) (.+) AND (.+)$", t)
    if m:
        return [("BET", m.group(2)), ("AND", m.group(3))]
    m = re.match(r"^FROM (.+) TO (.+)$", t)
    if m:
        return [("FROM", m.group(1)), ("TO", m.group(2))]
    m = re.match(r"^(ABT|CAL|EST|BEF|AFT|FROM|TO|INT) (.+)$", t)
    if m:
        rest = m.group(2)
        if m.group(1) == "INT":
            rest = re.sub(r" \(.*\)$", "", rest)
        return [(m.group(1), rest)]
    return [("", t)]


def datum_anzeige(text: str | None) -> str | None:
    """GEDCOM-Datum → Anzeige („26. April 1897“, „um 1770“, „von 1916 bis 1918“). None, wenn nicht lesbar."""
    if not text:
        return None
    d = gdatum.lesen(text)
    if d is None or not d.gueltig or d.kind == "phrase":
        return None
    teile = [(v, _teil_anzeigen(x)) for v, x in _teile(text)]
    if any(a is None for _, a in teile):
        return None
    vorsatz = {"": "{}", "ABT": "um {}", "CAL": "errechnet {}", "EST": "geschätzt {}", "BEF": "vor {}",
               "AFT": "nach {}", "FROM": "von {}", "TO": "bis {}", "INT": "{}"}
    if len(teile) == 2:
        a, b = teile[0][1], teile[1][1]
        return f"zwischen {a} und {b}" if teile[0][0] == "BET" else f"von {a} bis {b}"
    v, a = teile[0]
    return vorsatz[v].format(a)


def datum_grenzen(text: str | None) -> tuple[int, int] | None:
    """Frühester und spätester julianischer Tag der genannten Daten (BEF 1885 → Tage des Jahres 1885)."""
    if not text:
        return None
    d = gdatum.lesen(text)
    if d is None or not d.gueltig or d.kind == "phrase":
        return None
    bereiche = [gdatum._bereich(x) for _, x in _teile(text)]
    if any(b is None for b in bereiche):
        return None
    return bereiche[0][1], bereiche[-1][2]


def jahr_aus_jd(jd: int) -> int:
    """Gregorianisches Jahr eines julianischen Tages."""
    a = jd + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    return 100 * b + d - 4800 + m // 10


def datum_json(text: str | None, mit_gedcom: bool = False) -> dict | None:
    anzeige = datum_anzeige(text)
    grenzen = datum_grenzen(text)
    if anzeige is None or grenzen is None:
        return None
    # year: das Jahr der Mitte des Bereichs („von 1916 bis 1918“ → 1917), jd der früheste Tag
    j = {"text": anzeige, "year": jahr_aus_jd((grenzen[0] + grenzen[1]) // 2), "jd": grenzen[0]}
    if mit_gedcom:
        j["gedcom"] = text
    return j


def lebensspanne(geburt: str | None, tod: str | None, ist_tot: bool) -> str:
    """„1897–1969“, lebend „1985–“, ohne Geburt „…–1925“, tot ohne Datum „1850–…“."""
    g = datum_grenzen(geburt)
    t = datum_grenzen(tod)
    von = str(jahr_aus_jd(g[0])) if g else UNBEKANNT
    bis = str(jahr_aus_jd(t[1])) if t else (UNBEKANNT if ist_tot else "")
    return f"{von}–{bis}"


def name_teile(wert: str) -> tuple[str, str, str]:
    """„Johann /Falkenrath/ jr.“ → (Vornamen, Familienname, Zusatz)."""
    m = re.match(r"^([^/]*)/([^/]*)/?(.*)$", wert or "")
    if not m:
        return (wert or "").strip(), "", ""
    return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()


def unbekannt(text: str) -> str:
    return text.replace("@N.N.", UNBEKANNT).replace("@P.N.", UNBEKANNT)


def voller_name(wert: str) -> str:
    """Anzeige eines Namens: Schrägstriche weg, Leerraum zusammen, unbekannte Teile als „…“."""
    vor, nach, zusatz = name_teile(wert)
    teile = [unbekannt(vor) or (UNBEKANNT if nach else ""), unbekannt(nach) or UNBEKANNT if "/" in (wert or "") else "",
             zusatz]
    return re.sub(r"\s+", " ", " ".join(t for t in teile if t)).strip() or UNBEKANNT
