"""Schemaprüfung gegen die Schemadatei von api4wisetrees v1 (api-v1.json, OpenAPI 3.1 = JSON Schema 2020-12)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

OPENAPI = Path(__file__).with_name("api-v1.json")


@cache
def _openapi() -> dict:
    return json.loads(OPENAPI.read_text(encoding="utf-8"))


def schema_fuer(aktion: str, mit_baum: bool, methode: str = "get") -> dict:
    pfad = f"/module/_api4webtrees_/{aktion}" + ("/{tree}" if mit_baum else "")
    inhalt = _openapi()["paths"][pfad][methode]["responses"]["200"]["content"]
    return inhalt["application/json"]["schema"]


def fehler(aktion: str, mit_baum: bool, daten) -> list[str]:
    """Alle Abweichungen vom Schema als lesbare Zeilen (leer = passt)."""
    v = Draft202012Validator(schema_fuer(aktion, mit_baum))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(Wurzel)'}: {e.message[:200]}"
            for e in sorted(v.iter_errors(daten), key=lambda e: list(map(str, e.absolute_path)))]
