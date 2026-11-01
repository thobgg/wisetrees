"""Schreibschicht (KONZEPT.md E4 a, E21): Sätze, Schritte, annehmen, verwerfen, Konflikte."""

from __future__ import annotations

import pytest
from sqlalchemy import func, insert, select

from baum import aenderungen as ae
from baum import datei
from baum.schema import tabelle as T


@pytest.fixture
def con(tmp_path):
    c = datei.anlegen(tmp_path / "s.wise")
    with c.begin():
        c.execute(insert(T("person")).values(xref="I1", sex="M"))
        c.execute(insert(T("name")).values(person_id=1, sort=1, value="Hans /Alt/", given="Hans", surname="Alt"))
    yield c
    c.close()


def tx(con):
    """Transaktion beginnen; eine offene Lese-Transaktion (Lesen ohne begin) vorher beenden."""
    if con.in_transaction():
        con.rollback()
    return con.begin()


def _wert(con, tab, spalte, id_):
    t = T(tab)
    return con.execute(select(t.c[spalte]).where(t.c.id == id_)).scalar()


def _anzahl(con, tab):
    return con.execute(select(func.count()).select_from(T(tab))).scalar()


def test_offene_aenderung_aendert_die_tabellen_nicht(con):
    with tx(con):
        a = ae.Aenderung(con, "I1", "bearbeiter")
        a.aendern("name", 1, given="Johann")
        sid = a.speichern()
    assert _wert(con, "name", "given", 1) == "Hans"                    # angenommener Stand unverändert
    assert ae.aktueller_stand(con, "name", 1)["given"] == "Johann"      # offener Stand
    assert [s["id"] for s in ae.offene_saetze(con, "I1")] == [sid]
    with tx(con):
        ae.annehmen(con, [sid], "moderator")
    assert _wert(con, "name", "given", 1) == "Johann" and ae.offene_saetze(con) == []


def test_weitere_aenderung_baut_auf_dem_offenen_stand_auf(con):
    with tx(con):
        a = ae.Aenderung(con, "I1", "bearbeiter")
        a.aendern("name", 1, given="Johann")
        s1 = a.speichern()
        b = ae.Aenderung(con, "I1", "bearbeiter")
        b.aendern("name", 1, given="Johannes")
        s2 = b.speichern()
    alt2 = ae.schritte(con, [s2])[0]["alt"]
    assert alt2 == {"given": "Johann"}                                  # alt = offener Stand, nicht angenommener
    with tx(con):
        ae.annehmen(con, [s1, s2], "moderator")
    assert _wert(con, "name", "given", 1) == "Johannes"


def test_anlegen_mit_verweisen_ueber_saetze(con):
    with tx(con):
        a = ae.Aenderung(con, "I2", "bearbeiter")
        xref = ae.neue_kennung(con, "person", "I")
        p = a.anlegen("person", xref=xref, sex="F")
        a.anlegen("name", person_id=p, sort=1, value="Anna /Neu/", given="Anna", surname="Neu")
        s1 = a.speichern()
        # zweite Kennung, solange I2 noch offen ist: nicht doppelt vergeben
        assert ae.neue_kennung(con, "person", "I") == "I3"
        # spätere Bearbeitung derselben, noch nicht angenommenen Person
        person_schritt = ae.schritte(con, [s1])[0]
        b = ae.Aenderung(con, "I2", "bearbeiter")
        b.aendern("person", f"neu:{person_schritt['id']}", sex="X")
        s2 = b.speichern()
    assert xref == "I2" and _anzahl(con, "person") == 1
    with tx(con):
        ae.annehmen(con, [s1, s2], "moderator")
    t = T("person")
    neu = con.execute(select(t).where(t.c.xref == "I2")).one()._mapping
    assert neu["sex"] == "X"
    n = T("name")
    assert con.execute(select(n.c.given).where(n.c.person_id == neu["id"])).scalar() == "Anna"


def test_konflikt_wenn_der_angenommene_stand_sich_geaendert_hat(con):
    with tx(con):
        a = ae.Aenderung(con, "I1", "bearbeiter")
        a.aendern("name", 1, surname="Neu")
        sid = a.speichern()
    with tx(con):   # jemand ändert den angenommenen Stand an der Moderation vorbei
        con.execute(T("name").update().where(T("name").c.id == 1).values(surname="Anders"))
    with pytest.raises(ae.Konflikt), tx(con):
        ae.annehmen(con, [sid], "moderator")
    assert _wert(con, "name", "surname", 1) == "Anders"                 # nichts still überschrieben
    assert [s["id"] for s in ae.offene_saetze(con)] == [sid]            # Satz bleibt offen


def test_verweis_auf_noch_offenes_objekt_ist_ein_konflikt(con):
    with tx(con):
        a = ae.Aenderung(con, "I2", "bearbeiter")
        a.anlegen("person", xref="I2")
        s1 = a.speichern()
        schritt = ae.schritte(con, [s1])[0]
        b = ae.Aenderung(con, "I2", "bearbeiter")
        b.anlegen("name", person_id=f"neu:{schritt['id']}", sort=1, value="X")
        s2 = b.speichern()
    with pytest.raises(ae.Konflikt), tx(con):
        ae.annehmen(con, [s2], "moderator")                             # s1 fehlt noch
    with tx(con):
        ae.annehmen(con, [s1, s2], "moderator")
    assert _anzahl(con, "name") == 2


def test_verwerfen_und_loeschen(con):
    with tx(con):
        a = ae.Aenderung(con, "I1", "bearbeiter")
        a.loeschen("name", 1)
        sid = a.speichern()
        assert ae.aktueller_stand(con, "name", 1) is None
        ae.verwerfen(con, [sid], "moderator")
    assert ae.offene_saetze(con) == [] and _anzahl(con, "name") == 1
    satz = con.execute(select(T("change_set")).where(T("change_set").c.id == sid)).one()._mapping
    assert (satz["status"], satz["decided_by"]) == ("rejected", "moderator")


def test_sofort_annehmen_und_protokoll(con):
    with tx(con):
        a = ae.Aenderung(con, "I1", "verwalter")
        a.aendern("person", 1, sex="F")
        sid = a.speichern(sofort=True)
    assert _wert(con, "person", "sex", 1) == "F" and ae.offene_saetze(con) == []
    satz = con.execute(select(T("change_set")).where(T("change_set").c.id == sid)).one()._mapping
    assert (satz["status"], satz["author"], satz["record_xref"]) == ("accepted", "verwalter", "I1")


def test_ohne_aenderung_kein_satz(con):
    with tx(con):
        a = ae.Aenderung(con, "I1", "bearbeiter")
        a.aendern("name", 1, given="Hans")                              # gleicher Wert
        assert a.speichern() is None
    assert _anzahl(con, "change_set") == 0


def test_ort_zuordnen_findet_vorhandenes_und_legt_fehlendes_an(con):
    from baum import orte

    with tx(con):
        a = ae.Aenderung(con, "I1", "verwalter")
        neu = orte.zuordnen(con, a, "Neudorf, Uelzen, Niedersachsen")
        assert isinstance(neu, str)                       # wird erst mit der Änderung angelegt
        a.speichern(sofort=True)
    assert _anzahl(con, "place") == 3 and _anzahl(con, "place_link") == 2
    with tx(con):
        b = ae.Aenderung(con, "I1", "verwalter")
        wieder = orte.zuordnen(con, b, "neudorf, UELZEN, Niedersachsen")
        assert isinstance(wieder, int) and b.schritte == []   # vorhanden: nichts Neues
        orte.zuordnen(con, b, "Altdorf, Uelzen, Niedersachsen")
        b.speichern(sofort=True)
    assert _anzahl(con, "place") == 4                         # nur Altdorf kam dazu
    pl, pn = T("place_link"), T("place_name")
    altdorf = con.execute(select(pn.c.place_id).where(pn.c.name == "Altdorf")).scalar()
    oben = select(pl.c.parent_id).where(pl.c.place_id == altdorf)
    assert con.execute(oben).scalar() == con.execute(select(pl.c.parent_id).where(pl.c.place_id == wieder)).scalar()
