"""v1-Aktionen (lesend). Antworten nach docs/API-V1.md und vertrag/api-v1.json."""

from __future__ import annotations

from sqlalchemy import func, select

from baum.schema import tabelle as T
from core.konten import ROLLEN

from .http import GET_AKTIONEN, Kontext
from .sicht import nur_mitglieder

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
        if rolle == "visitor" and nur_mitglieder(b):
            continue  # Baum nur für Mitglieder: für Besucher nicht vorhanden (E19)
        con = b.oeffnen()
        try:
            mt, pe = T("meta"), T("person")
            titel = con.execute(select(mt.c.value).where(mt.c.key == "title")).scalar() or b.name
            anzahl = con.execute(select(func.count()).select_from(pe)).scalar()
            erste = con.execute(select(func.min(pe.c.xref))).scalar() or ""
            # offen: Datensätze mit offenen Änderungen, nur für die Moderation; letzte: Nummer des letzten Satzes
            offen = moderation.offene_anzahl(con) if rolle in moderation.MODERATION else 0
            letzte = con.execute(select(func.max(T("change_set").c.id))).scalar() or 0
        finally:
            con.close()
        from .sicht import sicht_fuer

        kb = ctx.konten.kontobaum(konto, b.name)
        s = sicht_fuer(ctx, b.name)
        # Startperson: die eigene Person („Das bin ich“), sonst die erste – nur, wenn sichtbar
        kandidat = kb.person if kb.person in s.m.person_xref else erste
        start = kandidat if kandidat and s.person_sichtbar(kandidat) else ""
        baeume.append({
            "name": b.name, "title": titel, "individuals": anzahl, "role": rolle,
            "canEdit": _rang(rolle) >= _rang("editor"), "canUpload": _rang(rolle) >= _rang("editor"),
            "canModerate": _rang(rolle) >= _rang("moderator"), "pending": offen, "autoAccept": kb.sofort,
            "userXref": kb.person, "defaultXref": "", "startXref": start, "treeDefaultXref": "",
            "availableModules": ["_api4webtrees_"], "lastChange": letzte,
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
from . import moderation  # noqa: E402 – trägt Pending, Accept und Reject ein
from . import schreiben  # noqa: E402, F401 – trägt die schreibenden Aktionen ein
from . import verwandte  # noqa: E402, F401 – trägt AddIndividual, Link, Unlink und DeleteRecord ein
