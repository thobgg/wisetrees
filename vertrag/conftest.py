"""Einstellungen der Vertragstests.

  WT_VERTRAG_URL       Adresse des Servers (ohne index.php). Fehlt sie, werden alle Vertragstests übersprungen.
  WT_VERTRAG_PASSWORT  Passwort der Testkonten (Standard: das des Referenzservers)

Der Server muss den Baum „falkenrath“ (Falkenrath 1.7.1) und die Konten aus faelle.ROLLEN haben.
"""

from __future__ import annotations

import os

import pytest

from .client import Sitzung
from .faelle import ROLLEN
from .faelle import PASSWORT


@pytest.fixture(scope="session")
def basis() -> str:
    url = os.environ.get("WT_VERTRAG_URL", "").rstrip("/")
    if not url:
        pytest.skip("WT_VERTRAG_URL nicht gesetzt")
    return url


@pytest.fixture(scope="session")
def passwort() -> str:
    return os.environ.get("WT_VERTRAG_PASSWORT", PASSWORT)


@pytest.fixture(scope="session")
def sitzungen(basis, passwort) -> dict[str, Sitzung]:
    """Eine angemeldete Sitzung je Rolle, für alle Lesetests geteilt."""
    alle = {}
    for rolle, konto in ROLLEN.items():
        s = Sitzung(basis)
        if konto is None:
            s.info()
        elif not s.anmelden(konto, passwort).get("user", {}).get("loggedIn"):
            pytest.fail(f"Anmeldung als {konto} fehlgeschlagen")
        alle[rolle] = s
    return alle
