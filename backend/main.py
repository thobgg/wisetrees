"""wisetrees – FastAPI-Anwendung. Start: uvicorn main:app (aus backend/)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

import config
from core.konten import KontenDB
from core.sperre import Sperre

VERSION = (Path(__file__).with_name("version.txt")).read_text(encoding="utf-8").strip()


def erstellen(einstellungen: config.Einstellungen) -> FastAPI:
    app = FastAPI(title="wisetrees", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.einstellungen = einstellungen
    app.state.konten = KontenDB(einstellungen.konten_db)
    app.state.sperre = Sperre()
    einstellungen.baeume.mkdir(parents=True, exist_ok=True)
    # Quelle der Bäume: ein Verzeichnis mit *.wise. Im Desktop-Modus (E14) tritt hier eine einzelne Datei mit
    # derselben Schnittstelle (alle(), baum(name)) an die Stelle.
    from v1.baeume import Baeume

    app.state.baeume = Baeume(einstellungen.baeume)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "version": VERSION}

    # v1: Schnittstelle api4wisetrees v1 (docs/API-V1.md)
    from v1 import aktionen  # noqa: F401 – trägt die Aktionen ein
    from v1.http import router

    app.include_router(router())

    return app


def __getattr__(name):
    # `uvicorn main:app` – erst beim Zugriff bauen, damit Tests das Modul ohne /data importieren können.
    if name == "app":
        return erstellen(config.laden())
    raise AttributeError(name)
