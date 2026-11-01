"""Sperre nach Fehlversuchen beim Anmelden: fünf Fehlschläge in fünf Minuten je Schlüssel → 60 s gesperrt.

Im Speicher und prozesslokal – richtig für den einen Container auf der NAS. Als Objekt, damit jeder Server (und
jeder Test) seine eigene Zählung hat.
"""

from __future__ import annotations

import threading
import time


class Sperre:
    def __init__(self, fenster: float = 300, schwelle: int = 5, dauer: float = 60, uhr=time.time):
        self.fenster, self.schwelle, self.dauer, self.uhr = fenster, schwelle, dauer, uhr
        self._fehler: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def rest(self, schluessel: str) -> float:
        """Verbleibende Sperrzeit in Sekunden (0 = frei)."""
        jetzt = self.uhr()
        with self._lock:
            zeiten = [t for t in self._fehler.get(schluessel, []) if jetzt - t < self.fenster]
            self._fehler[schluessel] = zeiten
            if len(zeiten) >= self.schwelle:
                return max(0.0, self.dauer - (jetzt - max(zeiten)))
        return 0.0

    def fehlschlag(self, schluessel: str) -> None:
        with self._lock:
            self._fehler.setdefault(schluessel, []).append(self.uhr())

    def freigeben(self, schluessel: str) -> None:
        with self._lock:
            self._fehler.pop(schluessel, None)
