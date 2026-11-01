"""Vertragstests gegen wisetrees selbst (KONZEPT.md 4.3, Meilenstein 1).

    .venv/bin/python -m vertrag.wisetrees            # aufsetzen, Tests, abbauen
    .venv/bin/python -m vertrag.wisetrees --server   # nur aufsetzen und laufen lassen

Setzt unter .work/wisetrees einen frischen Datenordner auf: Falkenrath 1.7.1 als Baum „falkenrath“ (aus
backend/tests/daten, Bilder aus dem Falkenrath-Klon), Konten wie bei der Aufzeichnung (Name, Anzeigename, Sprache,
Rolle), „heute“ = Datum der Aufzeichnung (WISETREES_HEUTE). Dann uvicorn auf einem freien Port.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARBEIT = REPO / ".work" / "wisetrees"
STAND = REPO / "vertrag" / "aufzeichnungen" / "stand.json"
GED = REPO / "backend" / "tests" / "daten" / "falkenrath-1.7.1.ged"

sys.path.insert(0, str(REPO / "backend"))

# Wie bei der Aufzeichnung (vertrag/aufzeichnungen/*/Info.json): Anzeigename und Sprache der Konten.
KONTEN = {
    "verwalter": {"real_name": "Verwalter", "language": "de", "admin": True, "rolle": None},
    "mitglied": {"real_name": "mitglied", "language": "en-US", "admin": False, "rolle": "member"},
    "bearbeiter": {"real_name": "bearbeiter", "language": "en-US", "admin": False, "rolle": "editor"},
    "moderator": {"real_name": "moderator", "language": "en-US", "admin": False, "rolle": "moderator"},
}


def aufsetzen() -> Path:
    from core.konten import KontenDB
    from gedcom.import551 import importieren

    from .faelle import PASSWORT

    shutil.rmtree(ARBEIT, ignore_errors=True)
    daten = ARBEIT / "daten"
    importieren(GED.read_bytes(), daten / "baeume" / "falkenrath.wise", "Falkenrath", GED.name)
    # Testbilder (CC0); FALKENRATH_MEDIEN kann auf den vollständigen Bildordner zeigen
    medien = Path(os.environ.get("FALKENRATH_MEDIEN") or REPO / "backend" / "tests" / "daten" / "medien")
    shutil.copytree(medien, daten / "medien" / "falkenrath")
    db = KontenDB(daten / "konten.sqlite")
    for name, k in KONTEN.items():
        db.anlegen(name, PASSWORT, real_name=k["real_name"], is_admin=k["admin"])
        db._con.execute("UPDATE konto SET language = ? WHERE name = ?", (k["language"], name))
        if k["rolle"]:
            db.rolle_setzen(name, "falkenrath", k["rolle"])
    db.schliessen()
    return daten


def starten(daten: Path) -> tuple[subprocess.Popen, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    heute = json.loads(STAND.read_text(encoding="utf-8"))["datum"]
    env = {**os.environ, "WISETREES_DATEN": str(daten), "WISETREES_HEUTE": heute}
    log = open(ARBEIT / "server.log", "ab")  # noqa: SIM115 – offen, solange der Server läuft
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port),
                          "--log-level", "warning"], cwd=REPO / "backend", env=env, stdout=log, stderr=subprocess.STDOUT)
    basis = f"http://127.0.0.1:{port}"
    ende = time.time() + 20
    while time.time() < ende:
        try:
            urllib.request.urlopen(basis + "/healthz", timeout=1).read()
            return p, basis
        except OSError:
            if p.poll() is not None:
                break
            time.sleep(0.2)
    p.terminate()
    raise RuntimeError(f"wisetrees startet nicht, siehe {ARBEIT / 'server.log'}")


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--server", action="store_true")
    a.add_argument("pytest_args", nargs="*")
    args = a.parse_args(argv)
    p, basis = starten(aufsetzen())
    try:
        if args.server:
            print(f"wisetrees läuft: {basis}", flush=True)
            p.wait()
            return 0
        env = {**os.environ, "WT_VERTRAG_URL": basis}
        return subprocess.run([sys.executable, "-m", "pytest", str(REPO / "vertrag"), *args.pytest_args],
                              env=env).returncode
    finally:
        p.terminate()
        p.wait(5)


if __name__ == "__main__":
    sys.exit(main())
