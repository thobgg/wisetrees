"""Wechselnde Werte vor dem Vergleich ersetzen (KONZEPT.md 4.3, E11).

Zwei Arten:
- Werte, die von Lauf zu Lauf wechseln (Sitzung, CSRF-Token, Zeitstempel, Port in Adressen).
- Werte, die ein Server frei vergibt (factId, Bild- und Seitenadressen, Versionen).
  Für sie bleibt geprüft, OB es den Wert gibt und wo er gleich ist, nicht WELCHER es ist.

Kennungen ohne Bedeutung (factId …) werden je Antwort in der Reihenfolge des ersten Auftretens
durchnummeriert. So bleibt erhalten, dass zwei Stellen dieselbe Kennung tragen.
"""

from __future__ import annotations

import re

# Schlüssel, deren Wert nur ein Platzhalter wird (Wert vorhanden ja/nein bleibt sichtbar).
PLATZHALTER = {
    "csrf": "<csrf>",
    "webtrees": "<version>",
    "module": "<version>",
    "baseUrl": "<basis>",
    "url": "<url>",
    "thumb": "<bild>",
    "file": "<datei>",
    "api": "<api>",
    "time": "<zeit>",    # Zeitpunkt einer Änderung (lastChange, Pending)
}

# Angaben über den Server selbst (Module, Upload-Grenze, Kurzadressen): wisetrees meldet eigene Werte, verglichen
# wird nur die Form (Schema). Entschieden am 01.11.2026.
SERVERWERTE = {"availableModules", "maxUpload", "rewriteUrls"}

# Felder, die erst api4wisetrees v1 kennt (E17); im Vergleich mit den Aufzeichnungen ausgelassen, Form per Schema.
NUR_WISETREES = {"features"}

# Bewusste Abweichungen im Wortlaut: wisetrees schreibt im generischen Maskulinum, ohne Paarformen.
# Bei unbekanntem oder verborgenem Geschlecht heißt ein Pate „Pate“. Entschieden am 01.11.2026.
WORTLAUT = {"label": {"Pate/Patin": "Pate"}}

# Schlüssel mit Kennungen, die je Antwort durchnummeriert werden. Ein Fakt heißt in `facts[]` „id“,
# in Verweisen darauf „factId“ – beide teilen sich eine Nummerierung.
KENNUNGEN = {"factId": "fact", "id": "fact"}


def normalisieren(wert, basis: str):
    zaehler: dict[str, dict[str, str]] = {}
    basis = basis.rstrip("/")

    def kennung(art: str, v: str) -> str:
        tabelle = zaehler.setdefault(art, {})
        if v not in tabelle:
            tabelle[v] = f"<{art}#{len(tabelle) + 1}>"
        return tabelle[v]

    def lauf(x, schluessel=None):
        if schluessel in SERVERWERTE:
            return "<server>"
        if isinstance(x, dict):
            return {k: lauf(v, k) for k, v in x.items() if k not in NUR_WISETREES}
        if isinstance(x, list):
            return [lauf(v, schluessel) for v in x]
        if schluessel == "api" and isinstance(x, int):
            return PLATZHALTER["api"]
        if isinstance(x, str):
            if schluessel in PLATZHALTER and x != "":
                return PLATZHALTER[schluessel]
            if schluessel in KENNUNGEN and x != "":
                return kennung(KENNUNGEN[schluessel], x)
            if x in WORTLAUT.get(schluessel, {}):
                return WORTLAUT[schluessel][x]
            return re.sub(re.escape(basis) + r"/?", "<basis>/", x)
        return x

    return lauf(wert)
