"""GEDCOM-5.5.1-Import (KONZEPT.md 3 und 6).

Falkenrath 1.7.1 (CC0, backend/tests/daten) als Prüfstein; dazu eine kleine Datei mit den Fällen, die Falkenrath
nicht hat.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from baum import datei
from gedcom.import551 import importieren, rolle_aus_rela
from gedcom.lesen import NichtLesbar

DATEN = Path(__file__).with_name("daten")


@pytest.fixture(scope="module")
def falkenrath(tmp_path_factory):
    ziel = tmp_path_factory.mktemp("falk") / "falkenrath.wise"
    bericht = importieren((DATEN / "falkenrath-1.7.1.ged").read_bytes(), ziel, "Falkenrath", "falkenrath-1.7.1.ged")
    con = datei.oeffnen(ziel)
    yield con, bericht
    con.close()


def eins(con, sql, *args):
    r = con.exec_driver_sql(sql, args).fetchone()
    return r[0] if r and len(r) == 1 else r


def alle(con, sql, *args):
    return [tuple(r) for r in con.exec_driver_sql(sql, args)]


# ── Nichts geht verloren ─────────────────────────────────────────────────────────────────────────────

def test_jede_zeile_uebernommen_oder_als_rest(falkenrath):
    _, b = falkenrath
    assert b.zeilen_gesamt == 26122
    assert b.zeilen_uebernommen + b.zeilen_rest == b.zeilen_gesamt


def test_rest_ist_genau_das_erwartete(falkenrath):
    """Was das Modell nicht übernimmt, ist bekannt: nur SUBM. (In 1.7 standen hier noch 94 _GOV an PLAC, die der
    Kennung von L1 widersprachen – in 1.7.1 berichtigt.)"""
    con, b = falkenrath
    assert b.rest_pfade == {"tree:SUBM": 1}
    assert eins(con, "SELECT gov_id FROM place WHERE xref = 'L1'") == "BIETE1JO53FD"


def test_widersprechende_ortsangabe_bleibt_rest_und_ueberschreibt_nicht(tmp_path):
    """Wie in Falkenrath 1.7: _GOV am Ereignisort widerspricht dem Ortsdatensatz."""
    text = (DATEN / "falkenrath-1.7.1.ged").read_text(encoding="utf-8").replace("3 _GOV BIETE1JO53FD", "3 _GOV BIETELJO53FD")
    b = importieren(text.encode(), tmp_path / "alt.wise")
    assert b.rest_pfade["event:PLAC:_GOV"] == 94
    con = datei.oeffnen(tmp_path / "alt.wise")
    assert eins(con, "SELECT gov_id FROM place WHERE xref = 'L1'") == "BIETE1JO53FD"
    assert eins(con, "SELECT COUNT(*) FROM gedcom_rest WHERE gedcom = '3 _GOV BIETELJO53FD' AND under = 'PLAC'") == 94
    con.close()


def test_verweise_und_bericht(falkenrath):
    con, b = falkenrath
    assert datei.verweise_pruefen(con) == []
    assert (b.datum_unverstanden, b.verweis_fehlt, b.familien_einseitig, b.lesefehler) == ([], [], [], [])
    gespeichert = json.loads(eins(con, "SELECT value FROM meta WHERE key = 'import_report'"))
    assert gespeichert["zeilen_gesamt"] == 26122
    assert eins(con, "SELECT value FROM meta WHERE key = 'gedcom_head'").startswith("0 HEAD\n1 SOUR Python-Skripte")


def test_anzahl_der_datensaetze(falkenrath):
    con, b = falkenrath
    a = b.anzahl
    assert (a["person"], a["family"], a["source"], a["repository"], a["media"]) == (492, 154, 204, 40, 142)
    assert eins(con, "SELECT COUNT(*) FROM place WHERE xref IS NOT NULL") == 5
    assert a["person_association"] == 2 and a["task"] == 3


# ── Ereignisse mit Beteiligten ───────────────────────────────────────────────────────────────────────

def _taufe(con, xref):
    return eins(con, """SELECT e.id FROM event e JOIN event_role r ON r.event_id = e.id JOIN person p ON p.id = r.person_id
                        WHERE p.xref = ? AND e.type = 'CHR' AND r.role = 'PRINCIPAL'""", xref)


def test_taufe_ist_ein_ereignis_mit_paten(falkenrath):
    con, _ = falkenrath
    rollen = alle(con, """SELECT r.role, p.xref, r.rela, r.free_name, r.free_addition, r.free_text FROM event_role r
                          LEFT JOIN person p ON p.id = r.person_id WHERE r.event_id = ? ORDER BY r.sort""", _taufe(con, "I1"))
    assert rollen == [
        ("PRINCIPAL", "I1", None, None, None, None),
        ("GODP", "I10", "godparent", None, None, None),
        ("GODP", None, None, "Martin Hoppe", "Bauingenieur, Hannover", "Martin Hoppe, Bauingenieur, Hannover"),
    ]


def test_notiz_und_zitat_an_der_beteiligung(falkenrath):
    con, _ = falkenrath
    pate = eins(con, "SELECT r.id FROM event_role r JOIN person p ON p.id = r.person_id WHERE r.event_id = ? AND p.xref = 'I10'",
                _taufe(con, "I1"))
    assert alle(con, "SELECT n.text FROM note n JOIN note_link l ON l.note_id = n.id "
                     "WHERE l.event_role_id = ?", pate) == [("Schwester des Vaters",)]
    # _ASSO mit SOUR: Zitat an der Beteiligung, nicht am Ereignis
    assert eins(con, "SELECT COUNT(*) FROM citation WHERE event_role_id IS NOT NULL") == 1


def test_zeuge_bei_fremder_heirat(falkenrath):
    con, _ = falkenrath
    heiraten = alle(con, """SELECT e.type, r.role FROM event_role r JOIN event e ON e.id = r.event_id
                            JOIN person p ON p.id = r.person_id WHERE p.xref = 'I1' AND r.role <> 'PRINCIPAL'""")
    assert ("MARR", "WITN") in heiraten


def test_rollen_aus_rela():
    assert [rolle_aus_rela(t) for t in ("Godmother", "godparent", "Patin", "witness", "Trauzeuge", "Pfarrer", "Nachbar",
                                        "Informant", "Hebamme")] == \
        ["GODP", "GODP", "GODP", "WITN", "WITN", "CLERGY", "NGHBR", "X_INFORMANT", "OTHER"]
    # Taufzeuge: Zeuge einer Taufe ist Pate (alter Sprachgebrauch)
    assert rolle_aus_rela("Taufzeuge") == "GODP"


def test_zahl_der_beteiligten_geht_auf(falkenrath):
    """2510 Ereignisse (mit _STAT) mit je einer Hauptbeteiligung + 176 _ASSO + 522 _GODP an Taufen + 85 _ASSO +
    61 _WITN an Heiraten."""
    con, b = falkenrath
    assert b.anzahl["event"] == 2510
    assert b.anzahl["event_role"] == 2510 + 176 + 522 + 85 + 61


def test_genau_ein_bevorzugtes_ereignis_je_art(falkenrath):
    con, _ = falkenrath
    assert alle(con, """SELECT r.person_id, e.type, SUM(r.preferred) s FROM event_role r JOIN event e ON e.id = r.event_id
                        WHERE r.role = 'PRINCIPAL' AND r.person_id IS NOT NULL GROUP BY 1, 2 HAVING s <> 1""") == []
    # I-Person mit zwei BIRT (493 BIRT bei 492 Personen): das erste ist bevorzugt
    zweimal = eins(con, """SELECT r.person_id FROM event_role r JOIN event e ON e.id = r.event_id
                          WHERE e.type = 'BIRT' AND r.role = 'PRINCIPAL' GROUP BY 1 HAVING COUNT(*) = 2""")
    assert alle(con, """SELECT r.preferred FROM event_role r JOIN event e ON e.id = r.event_id
                       WHERE e.type = 'BIRT' AND r.person_id = ? ORDER BY r.fact_sort""", zweimal) == [(1,), (0,)]


def test_daten_mit_bereich(falkenrath):
    con, _ = falkenrath
    assert alle(con, "SELECT date_text, date_from, date_to FROM event e JOIN event_role r ON r.event_id = e.id "
                     "JOIN person p ON p.id = r.person_id WHERE p.xref = 'I21' AND e.type = 'BIRT'") == \
        [("26 APR 1897", 2414041, 2414041)]
    assert eins(con, "SELECT COUNT(*) FROM event WHERE date_text IS NOT NULL AND date_from IS NULL AND date_to IS NULL") == 0


# ── Familien und Abstammung ──────────────────────────────────────────────────────────────────────────

def test_familien_und_abstammung(falkenrath):
    con, _ = falkenrath
    assert alle(con, """SELECT p.xref, m.role, m.sort FROM family_member m JOIN family f ON f.id = m.family_id
                        JOIN person p ON p.id = m.person_id WHERE f.xref = 'F8' ORDER BY m.role DESC, m.sort""") == \
        [("I21", "partner", 1), ("I22", "partner", 2), ("I23", "child", 1), ("I15", "child", 2), ("I25", "child", 3)]
    # jedes Kind hat je Elternteil eine Abstammung
    assert eins(con, """SELECT COUNT(*) FROM family_member c JOIN family_member e ON e.family_id = c.family_id AND e.role = 'partner'
                        WHERE c.role = 'child'""") == eins(con, "SELECT COUNT(*) FROM parentage")
    assert alle(con, "SELECT DISTINCT kind FROM parentage") == [("birth",)]


def test_familienstand_ist_merkmal_mit_notiz(falkenrath):
    con, _ = falkenrath
    e = eins(con, "SELECT id FROM event WHERE type = '_STAT'")
    assert eins(con, "SELECT value FROM event WHERE id = ?", e) == "UNKNOWN"
    assert eins(con, "SELECT f.xref FROM event_role r JOIN family f ON f.id = r.family_id WHERE r.event_id = ?", e) == "F22"
    assert alle(con, "SELECT n.text FROM note n JOIN note_link l ON l.note_id = n.id WHERE l.event_id = ?", e) == \
        [("Die Mutter der Kinder ist unbekannt, eine Heirat ist nicht belegt.",)]


# ── Orte ─────────────────────────────────────────────────────────────────────────────────────────────

def test_ortsdatensatz_mit_datierten_namen_arten_angaben(falkenrath):
    con, _ = falkenrath
    l1 = eins(con, "SELECT id FROM place WHERE xref = 'L1'")
    assert alle(con, "SELECT name, date_text FROM place_name WHERE place_id = ? ORDER BY sort", l1) == \
        [("Bienenbüttel", "FROM 1885"), ("Kirchspiel Bienenbüttel", "BEF 1885")]
    assert alle(con, "SELECT type_text, gov_type, date_text FROM place_type WHERE place_id = ? ORDER BY sort", l1) == \
        [("Kirchdorf", 66, "BEF 1885"), ("Gemeinde", 18, "FROM 1885")]
    assert ("postal", "29553", None, "FROM 1 JUL 1993") in alle(
        con, "SELECT kind, value, subtype, date_text FROM place_attribute WHERE place_id = ?", l1)
    assert ("demographics", "974", "Einwohner", "1 DEC 1880") in alle(
        con, "SELECT kind, value, subtype, date_text FROM place_attribute WHERE place_id = ?", l1)
    assert eins(con, "SELECT lat || ',' || lng || ',' || maidenhead FROM place WHERE id = ?", l1) == "53.1417,10.4867,JO53FD"


def test_hof_liegt_im_dorf_und_hat_eigene_ereignisse(falkenrath):
    con, _ = falkenrath
    assert alle(con, """SELECT q.xref, l.kind FROM place_link l JOIN place p ON p.id = l.place_id
                        JOIN place q ON q.id = l.parent_id WHERE p.xref = 'L3'""") == [("L1", "POLI")]
    assert alle(con, """SELECT e.subtype, e.date_text FROM event e JOIN event_role r ON r.event_id = e.id
                        JOIN place p ON p.id = r.place_id WHERE p.xref = 'L3' AND r.role = 'PRINCIPAL'""") == [("Umbau", "1884")]


def test_wohnort_ueber_loc_verweis(falkenrath):
    con, _ = falkenrath
    resi = alle(con, "SELECT DISTINCT p.xref, e.place_text FROM event e JOIN place p ON p.id = e.place_id WHERE e.type = 'RESI' "
                     "AND p.xref = 'L3'")
    assert resi == [("L3", "Hof Nr. 3, Bienenbüttel, Uelzen, Niedersachsen, Deutschland")]


def test_ortskette_wird_hierarchie(falkenrath):
    con, _ = falkenrath
    celle = eins(con, """SELECT e.place_id FROM event e WHERE e.place_text = 'Celle, Niedersachsen, Deutschland' LIMIT 1""")
    kette = []
    ort = celle
    while ort:
        kette.append(eins(con, "SELECT name FROM place_name WHERE place_id = ? ORDER BY sort LIMIT 1", ort))
        ort = eins(con, "SELECT parent_id FROM place_link WHERE place_id = ?", ort)
    assert kette == ["Celle", "Niedersachsen", "Deutschland"]
    # gleiche Kette = derselbe Ort
    assert eins(con, "SELECT COUNT(DISTINCT place_id) FROM event WHERE place_text = 'Celle, Niedersachsen, Deutschland'") == 1


def test_unsichere_ortszuordnung_steht_im_bericht(falkenrath):
    """Bienenbüttel ohne _LOC-Verweis am Ereignis: einziger Ortsdatensatz dieses Namens, aber ohne übergeordneten
    Ort – zugeordnet, und ausdrücklich als unsicher gemeldet (KONZEPT.md 6)."""
    con, b = falkenrath
    assert len(b.orte_unsicher) == 1
    u = b.orte_unsicher[0]
    assert u["ortstext"] == "Bienenbüttel, Uelzen, Niedersachsen, Deutschland"
    assert u["ort"] == eins(con, "SELECT id FROM place WHERE xref = 'L1'")
    assert u["ereignisse"] == eins(con, "SELECT COUNT(*) FROM event WHERE place_text = ?", u["ortstext"])
    assert "nur über den Namen" in u["grund"]


# ── Quellen, Medien, Aufgaben, Namen ─────────────────────────────────────────────────────────────────

def test_quelle_archiv_zitat(falkenrath):
    con, _ = falkenrath
    assert alle(con, """SELECT s.title, r.xref, sr.call_number, sr.medium FROM source s
                        JOIN source_repository sr ON sr.source_id = s.id JOIN repository r ON r.id = sr.repository_id
                        WHERE s.xref = 'S1'""") == [("KB Eschede ev. Mischbuch 1768-1808", "R10", "KB Eschede Nr. 1", "book")]
    assert ("CHR", "(Patin)") in alle(con, "SELECT event_type, event_role FROM citation WHERE event_role IS NOT NULL")


def test_hauptbilder_und_medien(falkenrath):
    con, _ = falkenrath
    assert eins(con, "SELECT COUNT(*) FROM media_link WHERE is_primary = 1") == 21
    assert alle(con, "SELECT path, format, media_type, title FROM media_file WHERE media_id = "
                     "(SELECT id FROM media WHERE xref = 'M2')") == [("portrait-i22.jpg", "jpg", "photo", "Anna Rosskamp, Portrait")]


def test_aufgabe_mit_gedcom_l_feldern(falkenrath):
    con, _ = falkenrath
    assert eins(con, "SELECT category || '|' || priority || '|' || status || '|' || completed_text FROM task "
                     "WHERE text LIKE 'Militärpass%'") == "Militär|4|completed|3 OCT 2026"
    assert eins(con, "SELECT r.xref FROM task t JOIN repository r ON r.id = t.repository_id WHERE t.text LIKE 'Militärpass%'") == "R1"


def test_namen_mit_teilen(falkenrath):
    con, _ = falkenrath
    assert alle(con, "SELECT value, given, surname FROM name n JOIN person p ON p.id = n.person_id WHERE p.xref = 'I1'") == \
        [("Jonas /Falkenrath/", "Jonas", "Falkenrath")]
    assert eins(con, "SELECT COUNT(*) FROM name WHERE rufname IS NOT NULL") == 22


# ── Kleine Datei: Fälle, die Falkenrath nicht hat ────────────────────────────────────────────────────

KLEIN = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Karl /Vater/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Erna /Mutter/
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 NAME Paul /Kind/
1 SEX M
1 BIRT
2 DATE Frühjahr 1850
2 PLAC Neustadt, Kreis A
1 ADOP
2 DATE 1860
2 FAMC @F1@
3 ADOP HUSB
1 FAMC @F1@
1 _MILT Infanterie
2 DATE 1870
1 NOTE @N9@
0 @I4@ INDI
1 NAME Grete /Pflege/
1 SEX X
1 FAMC @F1@
0 @F1@ FAM
1 WIFE @I2@
1 HUSB @I1@
1 CHIL @I3@
1 CHIL @I4@
2 _MREL Foster
1 _STAT NOT MARRIED
2 NOTE Nie geheiratet.
0 @L1@ _LOC
1 NAME Neustadt
0 @L2@ _LOC
1 NAME Neustadt
0 TRLR
"""


@pytest.fixture
def klein(tmp_path):
    ziel = tmp_path / "klein.wise"
    b = importieren(KLEIN.encode(), ziel)
    con = datei.oeffnen(ziel)
    yield con, b
    con.close()


def test_klein_zeilen_und_verweise(klein):
    con, b = klein
    assert b.zeilen_uebernommen + b.zeilen_rest == b.zeilen_gesamt
    assert datei.verweise_pruefen(con) == []


def test_partnerplatz_folgt_dem_tag_nicht_der_reihenfolge(klein):
    con, _ = klein
    assert alle(con, "SELECT p.xref, m.sort FROM family_member m JOIN person p ON p.id = m.person_id "
                     "WHERE m.role = 'partner' ORDER BY m.sort") == [("I1", 1), ("I2", 2)]


def test_abstammung_je_elternteil(klein):
    """I3: von der Mutter leiblich, vom Vater adoptiert (ADOP HUSB). I4: _MREL Foster nur zur Mutter."""
    con, _ = klein
    assert alle(con, """SELECT k.xref, e.xref, a.kind FROM parentage a JOIN person k ON k.id = a.child_id
                        JOIN person e ON e.id = a.parent_id ORDER BY k.xref, e.xref""") == [
        ("I3", "I1", "adopted"), ("I3", "I2", "birth"), ("I4", "I1", "birth"), ("I4", "I2", "foster")]


def test_nicht_verheiratet_ist_nicht_ereignis(klein):
    con, _ = klein
    e = eins(con, "SELECT e.id FROM event e JOIN event_role r ON r.event_id = e.id WHERE e.type = 'MARR'")
    assert eins(con, "SELECT negated FROM event WHERE id = ?", e) == 1
    assert alle(con, "SELECT n.text FROM note n JOIN note_link l ON l.note_id = n.id WHERE l.event_id = ?", e) == \
        [("Nie geheiratet.",)]


def test_unbekanntes_bleibt_als_rest_und_luecken_stehen_im_bericht(klein):
    con, b = klein
    i3 = eins(con, "SELECT id FROM person WHERE xref = 'I3'")
    assert alle(con, "SELECT person_id, under, gedcom FROM gedcom_rest ORDER BY id") == [
        (i3, None, "1 _MILT Infanterie\n2 DATE 1870"),
        (i3, None, "1 NOTE @N9@"),
    ]
    assert b.datum_unverstanden == ["Zeile 17: Frühjahr 1850"]
    assert b.verweis_fehlt == ["Zeile 26: NOTE @N9@"]
    assert eins(con, "SELECT sex FROM person WHERE xref = 'I4'") == "X"


def test_mehrdeutiger_ortsname(klein):
    con, b = klein
    assert [u["grund"] for u in b.orte_unsicher] == ["mehrdeutig: 2 Ortsdatensätze heißen „Neustadt“, keiner gewählt"]
    ort = eins(con, "SELECT place_id FROM event WHERE place_text = 'Neustadt, Kreis A'")
    assert eins(con, "SELECT xref FROM place WHERE id = ?", ort) is None


def test_unbekannte_fassung_wird_abgelehnt_und_hinterlaesst_nichts(tmp_path):
    ziel = tmp_path / "sechs.wise"
    with pytest.raises(NichtLesbar, match="6.0"):
        importieren(KLEIN.replace("2 VERS 5.5.1", "2 VERS 6.0").encode(), ziel)
    assert not ziel.exists()


def test_abbruch_hinterlaesst_keine_halbe_datei(tmp_path, monkeypatch):
    from gedcom import import551

    def kaputt(self):
        raise sqlite3.OperationalError("Test")

    monkeypatch.setattr(import551.Importer, "mitglieder", kaputt)
    ziel = tmp_path / "halb.wise"
    with pytest.raises(sqlite3.OperationalError):
        importieren(KLEIN.encode(), ziel)
    assert list(tmp_path.iterdir()) == []


# ── Ortsangaben am Ereignis (entschieden 01.11.2026, KONZEPT 3.5) ────────────────────────────────────

def test_ortsangaben_am_ereignis_vermerkt_wie_in_der_datei(falkenrath):
    con, _ = falkenrath
    text = (DATEN / "falkenrath-1.7.1.ged").read_text(encoding="utf-8")
    erwartet = {"map": text.count("\n3 MAP\n"), "gov": text.count("\n3 _GOV "), "postal": text.count("\n3 _POST "),
                "maidenhead": text.count("\n3 _MAIDENHEAD ")}
    assert dict(alle(con, "SELECT kind, COUNT(*) FROM event_place_detail GROUP BY kind")) == erwartet


def test_geburt_in_bienenbuettel_nennt_nur_die_damalige_postleitzahl(falkenrath):
    """Der Ort L1 kennt 3116 (bis 1993) und 29553 (ab 1993); die Geburt von I130 nannte nur 29553."""
    con, _ = falkenrath
    geburt = eins(con, """SELECT e.id FROM event e JOIN event_role r ON r.event_id = e.id JOIN person p ON p.id = r.person_id
                         WHERE p.xref = 'I130' AND e.type = 'BIRT'""")
    assert alle(con, """SELECT d.kind, a.value, a.date_text FROM event_place_detail d
                       LEFT JOIN place_attribute a ON a.id = d.place_attribute_id WHERE d.event_id = ? ORDER BY d.sort""",
                geburt) == [("map", None, None), ("gov", None, None), ("postal", "29553", "FROM 1 JUL 1993"),
                            ("maidenhead", None, None)]


def test_doppelte_kennung_nur_als_rest(tmp_path):
    """Ein zweiter Datensatz mit derselben Kennung bleibt ganz als Rest und mischt sich nicht in den ersten."""
    text = ("0 HEAD\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Hinrich /Prieß/\n1 BIRT\n2 DATE 1850\n"
            "0 @I1@ INDI\n1 NAME Ludwig /Prieß/\n1 BIRT\n2 DATE 1852\n0 TRLR\n")
    b = importieren(text.encode(), tmp_path / "d.wise")
    con = datei.oeffnen(tmp_path / "d.wise")
    try:
        assert alle(con, "SELECT value FROM name") == [("Hinrich /Prieß/",)]
        assert eins(con, "SELECT COUNT(*) FROM event") == 1
        assert eins(con, "SELECT gedcom FROM gedcom_rest WHERE on_tree = 1").startswith("0 @I1@ INDI\n1 NAME Ludwig")
    finally:
        con.close()
    assert b.zeilen_uebernommen + b.zeilen_rest == b.zeilen_gesamt
    assert any("I1 doppelt" in v for v in b.verweis_fehlt)
