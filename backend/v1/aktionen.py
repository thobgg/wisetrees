"""v1-Aktionen (lesend). Antworten nach docs/API-V1.md und vertrag/api-v1.json."""

from __future__ import annotations

from core.konten import ROLLEN

from .http import GET_AKTIONEN, Kontext

# Stufe, die wisetrees meldet (Info.api). Stufe 1: lesender Teil vollständig, Schreibrouten fehlen noch
# (docs/API-V1.md 5). Die Zahl wird mit jeder erfüllten Stufe angehoben (KONZEPT.md 4.1).
API_STUFE = 1
FEATURES = ["read"]
WILLKOMMEN = "Jeder mit einem Benutzerkonto kann auf diese Website zugreifen."


def _rang(rolle: str) -> int:
    return ROLLEN.index(rolle)


def info(ctx: Kontext) -> dict:
    from main import VERSION

    konto = ctx.konto
    baeume = []
    for b in ctx.app.state.baeume.alle():
        rolle = ctx.konten.rolle(konto, b.name)
        con = b.oeffnen()
        try:
            titel = (con.execute("SELECT value FROM meta WHERE key = 'title'").fetchone() or [""])[0] or b.name
            anzahl = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]
            erste = con.execute("SELECT MIN(xref) FROM person").fetchone()[0] or ""
        finally:
            con.close()
        from .sicht import sicht_fuer

        start = erste if erste and sicht_fuer(ctx, b.name).person_sichtbar(erste) else ""
        baeume.append({
            "name": b.name, "title": titel, "individuals": anzahl, "role": rolle,
            "canEdit": _rang(rolle) >= _rang("editor"), "canUpload": _rang(rolle) >= _rang("editor"),
            "canModerate": _rang(rolle) >= _rang("moderator"), "pending": 0, "autoAccept": False,
            "userXref": "", "defaultXref": "", "startXref": start, "treeDefaultXref": "",
            "availableModules": ["_api4webtrees_"], "lastChange": 0,
        })
    return {
        "api": API_STUFE,
        # E17: Fähigkeiten, die wisetrees vollständig anbietet (docs/FUNKTIONEN.md 1.4)
        "features": FEATURES,
        "module": VERSION,
        "webtrees": f"wisetrees {VERSION}",
        "baseUrl": ctx.basis(),
        "rewriteUrls": False,
        "csrf": ctx.sitzung.csrf,
        "maxUpload": 20 * 1024 * 1024,
        "user": {
            "loggedIn": konto is not None,
            "userName": konto.name if konto else "",
            "realName": (konto.real_name or konto.name) if konto else "GUEST_USER",
            "isAdmin": bool(konto and konto.is_admin),
            "language": konto.language if konto else "",
            "messages": 0,
        },
        "trees": baeume,
        "loginForm": {"welcomeMessage": WILLKOMMEN, "isSelfRegistrationAllowed": False, "registrationTerms": None},
    }


GET_AKTIONEN["Info"] = info

from . import personen  # noqa: E402, F401 – trägt Individuals ein
from . import fakten  # noqa: E402, F401 – trägt Family und Individual ein
