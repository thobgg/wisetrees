"""Die Bäume des Servers: je Baum eine Datei <daten>/baeume/<name>.wise (E8, E12)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from baum import datei

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class Baum:
    name: str
    pfad: Path

    def oeffnen(self) -> sqlite3.Connection:
        return datei.oeffnen(self.pfad)


class Baeume:
    def __init__(self, ordner: Path):
        self.ordner = ordner

    def alle(self) -> list[Baum]:
        return [Baum(p.stem, p) for p in sorted(self.ordner.glob("*" + datei.ENDUNG)) if _NAME.match(p.stem)]

    def baum(self, name: str) -> Baum | None:
        if not _NAME.match(name or ""):
            return None
        pfad = self.ordner / f"{name}{datei.ENDUNG}"
        return Baum(name, pfad) if pfad.is_file() else None
