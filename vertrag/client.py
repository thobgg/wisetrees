"""Ein HTTP-Client, der sich verhält wie die Apps.

Adressen wie in docs/API-V1.md: {basis}/index.php?route={pfad}{route}&lang=…
Cookies werden gehalten, Umleitungen NICHT verfolgt (der Test will sie sehen).
Nur Standardbibliothek.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

MODUL = "_api4webtrees_"
USER_AGENT = "wisetrees-vertragstest/1"


class _KeineUmleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


@dataclass
class Antwort:
    status: int
    content_type: str
    daten: bytes
    location: str | None = None
    json: object = field(default=None)

    @property
    def ist_json(self) -> bool:
        return "json" in self.content_type


class Sitzung:
    def __init__(self, basis: str, sprache: str = "de"):
        self.basis = basis.rstrip("/")
        self.pfad = urllib.parse.urlsplit(self.basis).path.rstrip("/")
        self.sprache = sprache
        self.csrf = ""
        self.oeffner = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), _KeineUmleitung
        )

    # Adressen -------------------------------------------------------------

    def url(self, route: str, params: dict | None = None) -> str:
        q = {"route": self.pfad + route, "lang": self.sprache}
        q.update({k: str(v) for k, v in (params or {}).items()})
        return f"{self.basis}/index.php?" + urllib.parse.urlencode(q)

    @staticmethod
    def api_route(aktion: str, baum: str | None) -> str:
        return f"/module/{MODUL}/{aktion}" + (f"/{baum}" if baum else "")

    # Senden ---------------------------------------------------------------

    def senden(self, req: urllib.request.Request) -> Antwort:
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept-Language", self.sprache)
        try:
            with self.oeffner.open(req, timeout=60) as r:
                a = Antwort(r.status, r.headers.get("Content-Type", ""), r.read())
        except urllib.error.HTTPError as e:
            a = Antwort(e.code, e.headers.get("Content-Type", ""), e.read(), e.headers.get("Location"))
        if a.ist_json:
            try:
                a.json = json.loads(a.daten.decode("utf-8"))
            except ValueError:
                a.json = None
        return a

    def holen(self, url: str) -> Antwort:
        return self.senden(urllib.request.Request(url))

    def get(self, aktion: str, baum: str | None = None, params: dict | None = None) -> Antwort:
        return self.holen(self.url(self.api_route(aktion, baum), params))

    def formular(self, route: str, felder: dict) -> Antwort:
        rumpf = urllib.parse.urlencode(felder).encode()
        req = urllib.request.Request(self.url(route), data=rumpf, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        return self.senden(req)

    # Abläufe wie in den Apps ---------------------------------------------

    def info(self) -> dict:
        a = self.get("Info")
        if not (a.ist_json and isinstance(a.json, dict)):
            raise RuntimeError(f"Info ohne JSON: HTTP {a.status} {a.content_type}")
        self.csrf = a.json.get("csrf", "")
        return a.json

    def anmelden(self, benutzer: str, passwort: str) -> dict:
        self.info()
        self.formular("/login", {"_csrf": self.csrf, "username": benutzer, "password": passwort})
        return self.info()

    def abmelden(self) -> dict:
        self.formular("/logout", {})
        return self.info()
