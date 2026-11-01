"""GEDZIP: ZIP-Archiv mit gedcom.ged (GEDCOM 7.0) und den Mediendateien (KONZEPT.md 6, E23).

Schreiben: der Baum als 7.0, dazu jede Datei aus dem Medienordner des Baums unter ihrem Pfad – so, wie FILE in
gedcom.ged auf sie zeigt (dort mit % verschlüsselt, im Archiv im Klartext). Adressen im Netz und Dateien außerhalb
des Medienordners kommen nicht mit; fehlende Dateien stehen im Exportbericht.

Lesen: gedcom.ged und die übrigen Dateien. Beim Entpacken bleibt alles im Zielordner; Namen, die hinausführen
(absolut, „..“), werden übergangen.
"""

from __future__ import annotations

import datetime
import io
import zipfile
from pathlib import Path, PurePosixPath

from sqlalchemy import Connection, select

from baum.schema import tabelle as T

from .export import Exportbericht, exportieren
from .lesen import NichtLesbar
from .umsetzen import url

GEDCOM = "gedcom.ged"


def schreiben(con: Connection, medienordner: Path | None, heute: datetime.datetime | None = None
              ) -> tuple[bytes, Exportbericht]:
    heute = heute or datetime.datetime.now()
    text, bericht = exportieren(con, heute, "7.0")
    zeit = heute.timetuple()[:6]
    ordner = medienordner.resolve() if medienordner else None
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo(GEDCOM, zeit), text, compress_type=zipfile.ZIP_DEFLATED)
        pfade = sorted({p for p in con.execute(select(T("media_file").c.path)).scalars() if p})
        for pfad in pfade:
            if url(pfad):
                continue
            datei = (ordner / pfad).resolve() if ordner else None
            name = PurePosixPath(pfad.replace("\\", "/"))
            if (datei is None or not datei.is_relative_to(ordner) or not datei.is_file() or name.is_absolute()
                    or ".." in name.parts):
                bericht.medien_fehlen.append(pfad)
                continue
            z.writestr(zipfile.ZipInfo(str(name), zeit), datei.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
            bericht.medien_im_archiv += 1
    return puffer.getvalue(), bericht


def lesen(daten: bytes) -> tuple[bytes, dict[str, bytes]]:
    """GEDZIP → (gedcom.ged, {Pfad: Inhalt}). Wirft NichtLesbar."""
    try:
        z = zipfile.ZipFile(io.BytesIO(daten))
    except zipfile.BadZipFile as e:
        raise NichtLesbar("kein ZIP-Archiv") from e
    with z:
        try:
            gedcom = z.read(GEDCOM)
        except KeyError as e:
            raise NichtLesbar(f"GEDZIP ohne {GEDCOM}") from e
        dateien = {}
        for info in z.infolist():
            name = PurePosixPath(info.filename)
            if info.is_dir() or info.filename == GEDCOM or name.is_absolute() or ".." in name.parts:
                continue
            dateien[info.filename] = z.read(info)
    return gedcom, dateien


def entpacken(daten: bytes, medienordner: Path) -> bytes:
    """Mediendateien in den Medienordner des Baums schreiben; liefert gedcom.ged zum Einlesen."""
    gedcom, dateien = lesen(daten)
    ordner = medienordner.resolve()
    for name, inhalt in dateien.items():
        ziel = (ordner / name).resolve()
        if not ziel.is_relative_to(ordner):
            continue
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
    return gedcom
