"""v1: die Schnittstelle api4wisetrees v1, wie die Apps sie ansprechen (docs/API-V1.md).

Alles läuft über /index.php?route=…:
  …/login, …/logout                       Anmelden/Abmelden mit dem Formular
  …/module/_api4webtrees_/{Aktion}[/{Baum}]  die Schnittstelle (JSON)
  …/wisetrees/medien/{Baum}/{Medium}       Bilder (eigene Adressen, für die Apps undurchsichtig)
Vor diesen Teilen darf ein beliebiger Pfad stehen ({pfad} der Basisadresse, docs/API-V1.md 1).

Sitzung über ein Cookie, auch für Besucher (CSRF-Token schon vor der Anmeldung). Fachliche Fehler: HTTP 200 mit
{ok: false, error, status}; nie 401/407. Ungültiges CSRF-Token bei POST: 302 ohne JSON, nichts wird ausgeführt.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from core.konten import KontenDB, Sitzung

COOKIE = "wisetrees_sitzung"
MODUL = "_api4webtrees_"
_API = re.compile(r"/module/" + re.escape(MODUL) + r"/([A-Za-z]+)(?:/([A-Za-z0-9_-]+))?$")
_MEDIEN = re.compile(r"/wisetrees/medien/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)$")

# Aktion -> Funktion(kontext) -> dict | Response. Gefüllt von v1/aktionen.py.
GET_AKTIONEN: dict[str, Callable] = {}
POST_AKTIONEN: dict[str, Callable] = {}


class Kontext:
    """Alles, was eine Aktion über die Anfrage wissen muss."""

    def __init__(self, request: Request, sitzung: Sitzung, baum: str | None, params: dict):
        self.request, self.sitzung, self.baum_name, self.params = request, sitzung, baum, params
        self.app = request.app
        self.konten: KontenDB = request.app.state.konten
        self.einstellungen = request.app.state.einstellungen

    @property
    def konto(self):
        return self.sitzung.konto

    def basis(self) -> str:
        """Die Basisadresse, unter der der Client uns anspricht (ohne index.php)."""
        u = self.request.url
        pfad = u.path.rsplit("/index.php", 1)[0]
        return f"{u.scheme}://{u.netloc}{pfad}"

    def adresse(self, route: str, **params) -> str:
        q = {"route": route, **{k: str(v) for k, v in params.items()}}
        return f"{self.basis()}/index.php?" + urlencode(q)


def fehler(status: int, code: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": code, "status": status})


def _nicht_gefunden() -> HTMLResponse:
    return HTMLResponse("<!DOCTYPE html><title>404</title><p>Nicht gefunden.</p>", status_code=404)


_SEITE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titel}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;color:#222;background:#fff}}
code{{background:#f2f2f2;padding:.1rem .3rem;border-radius:3px}}a{{color:#1f5f99}}.klein{{color:#666;font-size:.9rem}}</style>
</head><body>{inhalt}</body></html>"""


def _seite(titel: str, inhalt: str) -> HTMLResponse:
    return HTMLResponse(_SEITE.format(titel=html.escape(titel), inhalt=inhalt))


def _startseite(request: Request, sitzung: Sitzung) -> HTMLResponse:
    """Schlichte Startseite – auch das Ziel der Umleitung nach dem Anmelden."""
    from main import VERSION

    wer = (f"Angemeldet als <strong>{html.escape(sitzung.konto.name)}</strong>." if sitzung.konto
           else "Nicht angemeldet.")
    app = html.escape(str(request.url.replace(query="")) + "?" + urlencode({"route": "/wisetrees/app"}))
    return _seite("wisetrees", f"<h1>wisetrees läuft</h1><p>Version {html.escape(VERSION)}. {wer}</p>"
                               f'<p><a href="{app}">App verbinden</a></p>')


def _app_seite(request: Request) -> HTMLResponse:
    basis = str(request.url.replace(query="")).rsplit("/index.php", 1)[0]
    return _seite("App verbinden", f"""<h1>App verbinden</h1>
<p>In der App (wtAnd, wtTux, wtWin) unter <em>Andere Adresse</em> diese Adresse eingeben und mit dem eigenen Konto
anmelden:</p><p><code>{html.escape(basis)}</code></p>
<p class="klein">Ohne HTTPS nimmt die App die Adresse nur im Heimnetz an. Das Koppeln per Einmal-Code folgt in einer
späteren Fassung.</p>""")


def _umleitung(request: Request) -> RedirectResponse:
    # Bei ungültigem CSRF-Token: Umleitung; der Client erkennt daran „nichts ausgeführt“ (docs/API-V1.md 4).
    return RedirectResponse(str(request.url.replace(query="")), status_code=302)


def _sitzung(request: Request) -> tuple[Sitzung, str | None]:
    """Sitzung aus dem Cookie, sonst eine neue Besucher-Sitzung (Token zum Setzen zurück)."""
    konten: KontenDB = request.app.state.konten
    token = request.cookies.get(COOKIE)
    s = konten.sitzung(token)
    if s is not None:
        return s, None
    neu = konten.sitzung_anlegen(None, request.app.state.einstellungen.sitzung_sekunden,
                                 ip=request.client.host if request.client else None,
                                 user_agent=request.headers.get("user-agent"))
    return konten.sitzung(neu), neu


def _cookie(resp: Response, request: Request, token: str | None) -> Response:
    if token:
        pfad = request.url.path.rsplit("/index.php", 1)[0] or "/"
        resp.set_cookie(COOKIE, token, max_age=request.app.state.einstellungen.sitzung_sekunden, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax", path=pfad)
    return resp


def router() -> APIRouter:
    r = APIRouter()

    @r.api_route("/index.php", methods=["GET", "POST"])
    @r.api_route("/{praefix:path}/index.php", methods=["GET", "POST"])
    async def index(request: Request, praefix: str = ""):
        route = request.query_params.get("route", "")
        sitzung, neues_token = _sitzung(request)
        if request.method == "POST":
            if route.endswith("/login") or route == "/login":
                return await _anmelden(request, sitzung, neues_token)
            if route.endswith("/logout") or route == "/logout":
                return _abmelden(request, neues_token)
        if request.method == "GET" and not route.strip("/"):
            return _cookie(_startseite(request, sitzung), request, neues_token)
        if request.method == "GET" and route.endswith("/wisetrees/app"):
            return _cookie(_app_seite(request), request, neues_token)
        m = _API.search(route)
        if m is None:
            m_medien = _MEDIEN.search(route)
            if m_medien and request.method == "GET" and "medien" in GET_AKTIONEN:
                ctx = Kontext(request, sitzung, m_medien.group(1), {"xref": m_medien.group(2), **request.query_params})
                return _cookie(GET_AKTIONEN["medien"](ctx), request, neues_token)
            return _cookie(_nicht_gefunden(), request, neues_token)
        aktion, baum = m.group(1), m.group(2)
        params = {k: v for k, v in request.query_params.items() if k not in ("route", "lang")}
        if request.method == "POST":
            if request.headers.get("x-csrf-token") != sitzung.csrf:
                return _cookie(_umleitung(request), request, neues_token)
            tabelle = POST_AKTIONEN
        else:
            tabelle = GET_AKTIONEN
        f = tabelle.get(aktion)
        if f is None:
            return _cookie(_nicht_gefunden(), request, neues_token)
        ctx = Kontext(request, sitzung, baum, params)
        antwort = f(ctx)
        if not isinstance(antwort, Response):
            antwort = JSONResponse(antwort)
        return _cookie(antwort, request, neues_token)

    return r


async def _anmelden(request: Request, sitzung: Sitzung, neues_token: str | None) -> Response:
    form = await request.form()
    ziel = _umleitung(request)
    if form.get("_csrf") != sitzung.csrf:
        return _cookie(ziel, request, neues_token)
    sperre = request.app.state.sperre
    schluessel = f"login:{request.client.host if request.client else ''}"
    if sperre.rest(schluessel) > 0:
        return _cookie(ziel, request, neues_token)
    konten: KontenDB = request.app.state.konten
    konto = konten.pruefen(str(form.get("username", "")), str(form.get("password", "")))
    if konto is None:
        sperre.fehlschlag(schluessel)
        return _cookie(ziel, request, neues_token)
    sperre.freigeben(schluessel)
    konten.sitzung_beenden(request.cookies.get(COOKIE))
    token = konten.sitzung_anlegen(konto, request.app.state.einstellungen.sitzung_sekunden,
                                   ip=request.client.host if request.client else None,
                                   user_agent=request.headers.get("user-agent"))
    return _cookie(ziel, request, token)


def _abmelden(request: Request, neues_token: str | None) -> Response:
    # Abmelden braucht kein Token (der Client schickt keins, docs/API-V1.md 3).
    request.app.state.konten.sitzung_beenden(request.cookies.get(COOKIE))
    resp = _umleitung(request)
    resp.delete_cookie(COOKIE, path=request.url.path.rsplit("/index.php", 1)[0] or "/")
    return resp
