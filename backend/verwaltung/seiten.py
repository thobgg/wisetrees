"""Verwaltung im Browser, Stufe 1 (KONZEPT.md E18).

Adresse: index.php?route={pfad}/wisetrees/verwaltung, Aktionen per POST an …/wisetrees/verwaltung/{aktion}.
Jedes Formular trägt das CSRF-Token der Sitzung; ohne gültiges Token wird nichts ausgeführt. Nach jeder Aktion
geht es per Umleitung (303) zurück zur Übersicht, mit einer Meldung aus einer festen Liste.

Bäume und Konten nur für Administratoren; das eigene Passwort ändern kann jedes Konto.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from baum import datei
from baum.schema import tabelle as T
from core.konten import NAME_LAENGE, ROLLEN, KontenDB, Sitzung
from gedcom.import551 import importieren
from gedcom.lesen import NichtLesbar
from v1.http import COOKIE, anmeldung_pruefen, cookie, sitzung_wechseln

_ENV = Environment(loader=FileSystemLoader(Path(__file__).with_name("vorlagen")),
                   autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
_BAUMNAME = re.compile(r"^[A-Za-z0-9_-]+$")
MIN_PASSWORT = 8

ROLLEN_TEXT = {"visitor": "Besucher", "member": "Mitglied", "editor": "Bearbeiter", "moderator": "Moderator",
               "manager": "Verwalter"}

# Meldungen nach einer Aktion: Code → (Text, Art). {name} wird mit dem mitgegebenen Namen gefüllt.
MELDUNGEN = {
    "angemeldet": ("Angemeldet.", "ok"),
    "anmeldung-fehlgeschlagen": ("Name oder Passwort stimmt nicht.", "fehler"),
    "gesperrt": ("Zu viele Fehlversuche. Bitte eine Minute warten.", "fehler"),
    "konto-angelegt": ("Konto {name} angelegt.", "ok"),
    "konto-geloescht": ("Konto {name} gelöscht.", "ok"),
    "konto-gibt-es": ("Ein Konto {name} gibt es schon.", "fehler"),
    "name-ungueltig": ("Der Name ist leer oder zu lang.", "fehler"),
    "passwort-kurz": (f"Das Passwort braucht mindestens {MIN_PASSWORT} Zeichen.", "fehler"),
    "passwort-ungleich": ("Die beiden Passwörter stimmen nicht überein.", "fehler"),
    "passwort-gesetzt": ("Passwort für {name} gesetzt.", "ok"),
    "passwort-geaendert": ("Das eigene Passwort ist geändert.", "ok"),
    "passwort-falsch": ("Das bisherige Passwort stimmt nicht.", "fehler"),
    "rolle-gesetzt": ("Rollen für {name} gespeichert.", "ok"),
    "selbst": ("Das eigene Konto lässt sich hier nicht löschen.", "fehler"),
    "baum-eingelesen": ("Baum {name} eingelesen.", "ok"),
    "baum-gibt-es": ("Einen Baum {name} gibt es schon.", "fehler"),
    "baumname-ungueltig": ("Baumname: nur Buchstaben, Ziffern, - und _.", "fehler"),
    "keine-datei": ("Bitte eine GEDCOM-Datei wählen.", "fehler"),
    "nicht-lesbar": ("Die Datei ließ sich nicht einlesen: {name}", "fehler"),
    "baum-geloescht": ("Baum {name} gelöscht. Der Bildordner bleibt liegen.", "ok"),
    "bestaetigung-fehlt": ("Zum Löschen bitte den Baumnamen genau eintippen.", "fehler"),
    "unbekannt": ("{name} gibt es nicht.", "fehler"),
}


class _Ort:
    """Adressen der Verwaltung, passend zu dem Pfad, unter dem der Browser uns anspricht."""

    def __init__(self, request: Request, route: str):
        self.request = request
        self.pfad = route.split("/wisetrees/verwaltung", 1)[0]
        self.basis = str(request.url.replace(query=""))

    def url(self, teil: str = "", **params) -> str:
        return self.basis + "?" + urlencode({"route": f"{self.pfad}/wisetrees/verwaltung{teil}", **params})


def _seite(vorlage: str, **werte) -> HTMLResponse:
    resp = HTMLResponse(_ENV.get_template(vorlage).render(**werte))
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _zurueck(ort: _Ort, meldung: str, name: str = "", teil: str = "") -> RedirectResponse:
    params = {"meldung": meldung, **({"name": name} if name else {})}
    return RedirectResponse(ort.url(teil, **params), status_code=303)


def _baeume(request: Request) -> list[dict]:
    aus = []
    for b in request.app.state.baeume.alle():
        eintrag = {"name": b.name, "titel": b.name, "personen": None, "bericht": None, "fehler": None}
        try:
            con = b.oeffnen()
        except (datei.KeineBaumdatei, datei.FalscheVersion) as e:
            eintrag["fehler"] = str(e).split(": ", 1)[-1]
            aus.append(eintrag)
            continue
        try:
            mt = T("meta")
            werte = dict(con.execute(select(mt.c.key, mt.c.value)).all())
            eintrag["titel"] = werte.get("title") or b.name
            eintrag["personen"] = con.execute(select(func.count()).select_from(T("person"))).scalar()
            if werte.get("import_report"):
                eintrag["bericht"] = json.loads(werte["import_report"])
        finally:
            con.close()
        aus.append(eintrag)
    return aus


async def behandeln(request: Request, sitzung: Sitzung, neues_token: str | None, route: str) -> Response:
    ort = _Ort(request, route)
    teil = route.split("/wisetrees/verwaltung", 1)[1]
    if request.method == "GET":
        if teil in ("", "/"):
            return cookie(_uebersicht(request, sitzung, ort), request, neues_token)
        if teil == "/passwort":
            return cookie(_passwortseite(request, sitzung, ort), request, neues_token)
        return cookie(HTMLResponse("<!DOCTYPE html><title>404</title><p>Nicht gefunden.</p>", status_code=404),
                      request, neues_token)

    form = await request.form()
    if form.get("_csrf") != sitzung.csrf:
        return cookie(RedirectResponse(ort.url(), status_code=303), request, neues_token)
    aktion = teil.strip("/")
    if aktion == "anmelden":
        konto = anmeldung_pruefen(request, str(form.get("name", "")), str(form.get("passwort", "")))
        if konto == "gesperrt":
            return cookie(_zurueck(ort, "gesperrt"), request, neues_token)
        if konto is None:
            return cookie(_zurueck(ort, "anmeldung-fehlgeschlagen"), request, neues_token)
        return cookie(_zurueck(ort, "angemeldet"), request, sitzung_wechseln(request, konto))
    if aktion == "abmelden":
        request.app.state.konten.sitzung_beenden(request.cookies.get(COOKIE))
        resp = RedirectResponse(ort.url(), status_code=303)
        resp.delete_cookie(COOKIE, path=request.url.path.rsplit("/index.php", 1)[0] or "/")
        return resp
    if sitzung.konto is None:
        return cookie(RedirectResponse(ort.url(), status_code=303), request, neues_token)
    if aktion == "passwort":
        return cookie(_eigenes_passwort(request, sitzung, form, ort), request, neues_token)
    if not sitzung.konto.is_admin:
        return cookie(RedirectResponse(ort.url(), status_code=303), request, neues_token)
    f = _ADMIN.get(aktion)
    if f is None:
        return cookie(HTMLResponse("<!DOCTYPE html><title>404</title><p>Nicht gefunden.</p>", status_code=404),
                      request, neues_token)
    antwort = await f(request, sitzung, form, ort)
    return cookie(antwort, request, neues_token)


def _meldung(request: Request) -> dict | None:
    code = request.query_params.get("meldung")
    if code not in MELDUNGEN:
        return None
    text, art = MELDUNGEN[code]
    return {"text": text.format(name=request.query_params.get("name", "")), "art": art}


def _uebersicht(request: Request, sitzung: Sitzung, ort: _Ort) -> HTMLResponse:
    from main import VERSION

    konto = sitzung.konto
    werte = {"ort": ort, "csrf": sitzung.csrf, "konto": konto, "meldung": _meldung(request), "version": VERSION,
             "startseite": ort.basis}
    if konto is None:
        return _seite("anmelden.html", **werte)
    if not konto.is_admin:
        return _seite("kein_admin.html", **werte)
    konten: KontenDB = request.app.state.konten
    baeume = _baeume(request)
    rollen = konten.rollen()
    werte.update(baeume=baeume, konten=konten.alle(), rollen=rollen, rollen_text=ROLLEN_TEXT,
                 rollen_wahl=[r for r in ROLLEN], min_passwort=MIN_PASSWORT)
    return _seite("verwaltung.html", **werte)


def _passwortseite(request: Request, sitzung: Sitzung, ort: _Ort) -> HTMLResponse:
    if sitzung.konto is None:
        return _seite("anmelden.html", ort=ort, csrf=sitzung.csrf, konto=None, meldung=_meldung(request),
                      startseite=ort.basis)
    return _seite("passwort.html", ort=ort, csrf=sitzung.csrf, konto=sitzung.konto, meldung=_meldung(request),
                  min_passwort=MIN_PASSWORT, startseite=ort.basis)


def _passwort_neu(form) -> tuple[str | None, str | None]:
    """(Passwort, Fehlercode) aus den Feldern passwort und passwort2."""
    eins, zwei = str(form.get("passwort", "")), str(form.get("passwort2", ""))
    if len(eins) < MIN_PASSWORT:
        return None, "passwort-kurz"
    if eins != zwei:
        return None, "passwort-ungleich"
    return eins, None


def _eigenes_passwort(request: Request, sitzung: Sitzung, form, ort: _Ort) -> Response:
    konten: KontenDB = request.app.state.konten
    if konten.pruefen(sitzung.konto.name, str(form.get("bisher", ""))) is None:
        return _zurueck(ort, "passwort-falsch", teil="/passwort")
    neu, fehler = _passwort_neu(form)
    if fehler:
        return _zurueck(ort, fehler, teil="/passwort")
    konten.passwort_setzen(sitzung.konto.name, neu)  # beendet alle Sitzungen des Kontos
    return _zurueck(ort, "passwort-geaendert")


# ── Aktionen der Administratoren ──────────────────────────────────────────────────────────────────────────────

async def _konto_anlegen(request, sitzung, form, ort):
    konten: KontenDB = request.app.state.konten
    name = str(form.get("name", "")).strip()
    if not name or len(name) > NAME_LAENGE:
        return _zurueck(ort, "name-ungueltig")
    if konten.konto(name) is not None:
        return _zurueck(ort, "konto-gibt-es", name)
    passwort, fehler = _passwort_neu(form)
    if fehler:
        return _zurueck(ort, fehler)
    konten.anlegen(name, passwort, real_name=str(form.get("anzeigename", "")).strip(),
                   email=str(form.get("email", "")).strip(), is_admin=form.get("admin") == "1")
    return _zurueck(ort, "konto-angelegt", name)


async def _passwort_setzen(request, sitzung, form, ort):
    konten: KontenDB = request.app.state.konten
    name = str(form.get("name", ""))
    if konten.konto(name) is None:
        return _zurueck(ort, "unbekannt", name)
    passwort, fehler = _passwort_neu(form)
    if fehler:
        return _zurueck(ort, fehler)
    konten.passwort_setzen(name, passwort)
    return _zurueck(ort, "passwort-gesetzt", name)


async def _rollen_setzen(request, sitzung, form, ort):
    konten: KontenDB = request.app.state.konten
    name = str(form.get("name", ""))
    if konten.konto(name) is None:
        return _zurueck(ort, "unbekannt", name)
    for b in request.app.state.baeume.alle():
        rolle = str(form.get(f"rolle:{b.name}", "visitor"))
        if rolle in ROLLEN:
            konten.rolle_setzen(name, b.name, rolle)
    return _zurueck(ort, "rolle-gesetzt", name)


async def _konto_loeschen(request, sitzung, form, ort):
    konten: KontenDB = request.app.state.konten
    name = str(form.get("name", ""))
    if name == sitzung.konto.name:
        return _zurueck(ort, "selbst")
    if not konten.loeschen(name):
        return _zurueck(ort, "unbekannt", name)
    return _zurueck(ort, "konto-geloescht", name)


async def _baum_hochladen(request, sitzung, form, ort):
    name = str(form.get("baum", "")).strip()
    if not _BAUMNAME.match(name):
        return _zurueck(ort, "baumname-ungueltig")
    ziel = request.app.state.einstellungen.baeume / f"{name}{datei.ENDUNG}"
    if ziel.exists():
        return _zurueck(ort, "baum-gibt-es", name)
    hochgeladen = form.get("datei")
    if hochgeladen is None or not getattr(hochgeladen, "filename", ""):
        return _zurueck(ort, "keine-datei")
    inhalt = await hochgeladen.read()
    titel = str(form.get("titel", "")).strip() or name
    try:
        await run_in_threadpool(importieren, inhalt, ziel, titel, Path(hochgeladen.filename).name)
    except NichtLesbar as e:
        return _zurueck(ort, "nicht-lesbar", str(e)[:200])
    return _zurueck(ort, "baum-eingelesen", name)


async def _baum_loeschen(request, sitzung, form, ort):
    name = str(form.get("baum", ""))
    b = request.app.state.baeume.baum(name)
    if b is None:
        return _zurueck(ort, "unbekannt", name)
    if str(form.get("bestaetigung", "")).strip() != name:
        return _zurueck(ort, "bestaetigung-fehlt", name)
    for rest in (b.pfad, b.pfad.with_name(b.pfad.name + "-wal"), b.pfad.with_name(b.pfad.name + "-shm")):
        rest.unlink(missing_ok=True)
    request.app.state.konten.rollen_entfernen(name)
    return _zurueck(ort, "baum-geloescht", name)


_ADMIN = {
    "konto-anlegen": _konto_anlegen,
    "passwort-setzen": _passwort_setzen,
    "rollen-setzen": _rollen_setzen,
    "konto-loeschen": _konto_loeschen,
    "baum-hochladen": _baum_hochladen,
    "baum-loeschen": _baum_loeschen,
}
