"""Einstellungen von wisetrees.

Gelesen aus Umgebungsvariablen (WISETREES_…), vorher aus der Datei wisetrees.env im Arbeitsordner, falls es sie
gibt (Umgebungsvariablen gewinnen).

  WISETREES_DATEN   Datenordner (Standard /data): konten.sqlite und baeume/*.wise
  WISETREES_PORT    Port (Standard 8099)
  WISETREES_HEUTE   festes Datum für „heute“ (JJJJ-MM-TT), NUR für Tests (KONZEPT.md 4.3)
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_datei(pfad: Path) -> dict[str, str]:
    werte: dict[str, str] = {}
    if pfad.is_file():
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if zeile and not zeile.startswith("#") and "=" in zeile:
                k, _, v = zeile.partition("=")
                werte[k.strip()] = v.strip()
    return werte


@dataclass(frozen=True)
class Einstellungen:
    daten: Path = Path("/data")
    port: int = 8099
    heute_fest: datetime.date | None = None
    sitzung_sekunden: int = 30 * 24 * 3600
    extra: dict = field(default_factory=dict)

    @property
    def konten_db(self) -> Path:
        return self.daten / "konten.sqlite"

    @property
    def baeume(self) -> Path:
        return self.daten / "baeume"

    @property
    def medien(self) -> Path:
        """Mediendateien je Baum: <daten>/medien/<baum>/<Pfad aus FILE>."""
        return self.daten / "medien"

    def heute(self) -> datetime.date:
        """Das Datum für Lebend-Regel und Altersangaben. In Tests fest, sonst das echte."""
        return self.heute_fest or datetime.date.today()


def laden(env_datei: Path = Path("wisetrees.env"), umgebung: dict | None = None) -> Einstellungen:
    werte = {**_env_datei(env_datei), **(os.environ if umgebung is None else umgebung)}
    heute = werte.get("WISETREES_HEUTE")
    return Einstellungen(
        daten=Path(werte.get("WISETREES_DATEN", "/data")),
        port=int(werte.get("WISETREES_PORT", "8099")),
        heute_fest=datetime.date.fromisoformat(heute) if heute else None,
    )
