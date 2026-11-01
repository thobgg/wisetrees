"""Gemeinsame Hilfen der Unit-Tests. backend/ kommt in den Importpfad wie beim Start mit uvicorn."""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

import config  # noqa: E402


@pytest.fixture
def einstellungen(tmp_path) -> config.Einstellungen:
    import datetime
    return config.Einstellungen(daten=tmp_path / "daten", port=0, heute_fest=datetime.date(2026, 11, 1))


@pytest.fixture
def server(einstellungen):
    """wisetrees unter uvicorn in einem Thread; liefert die Basisadresse."""
    import uvicorn

    import main

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(main.erstellen(einstellungen), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    ende = time.time() + 10
    while not srv.started:
        if time.time() > ende:
            raise RuntimeError("uvicorn startet nicht")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)
