"""Grundgerüst: Konten, Rollen je Baum, Sitzungen, Sperre, Einstellungen, Start der App."""

from __future__ import annotations

import datetime
import json
import sqlite3
import time

import pytest

import config
from core.konten import KontenDB
from core.sperre import Sperre


@pytest.fixture
def db(tmp_path):
    k = KontenDB(tmp_path / "konten.sqlite")
    yield k
    k.schliessen()


def test_konto_anlegen_und_anmelden(db):
    db.anlegen("anna", "geheim-1", real_name="Anna")
    assert db.pruefen("anna", "geheim-1").real_name == "Anna"
    assert db.pruefen("anna", "falsch") is None
    assert db.pruefen("niemand", "geheim-1") is None


def test_passwort_nur_als_argon2id_gespeichert(db, tmp_path):
    db.anlegen("anna", "geheim-1")
    con = sqlite3.connect(tmp_path / "konten.sqlite")
    pw_hash = con.execute("SELECT pw_hash FROM konto").fetchone()[0]
    con.close()
    assert pw_hash.startswith("$argon2id$") and "geheim-1" not in pw_hash


def test_leeres_passwort_abgelehnt(db):
    with pytest.raises(ValueError):
        db.anlegen("anna", "")


def test_rollen_je_baum(db):
    anna = db.anlegen("anna", "pw")
    assert db.rolle(None, "falkenrath") == "visitor"
    assert db.rolle(anna, "falkenrath") == "visitor"
    db.rolle_setzen("anna", "falkenrath", "editor")
    assert db.rolle(anna, "falkenrath") == "editor"
    assert db.rolle(anna, "anderer") == "visitor"
    db.rolle_setzen("anna", "falkenrath", "visitor")
    assert db.rolle(anna, "falkenrath") == "visitor"
    with pytest.raises(ValueError):
        db.rolle_setzen("anna", "falkenrath", "chef")


def test_administrator_ist_ueberall_verwalter(db):
    admin = db.anlegen("admin", "pw", is_admin=True)
    assert db.rolle(admin, "irgendein-baum") == "manager"


def test_sitzung_besucher_und_konto(db, tmp_path):
    anna = db.anlegen("anna", "pw")
    t_gast = db.sitzung_anlegen(None, 60)
    t_anna = db.sitzung_anlegen(anna, 60)
    assert db.sitzung(t_gast).konto is None
    assert db.sitzung(t_anna).konto.name == "anna"
    assert db.sitzung(t_gast).csrf != db.sitzung(t_anna).csrf
    # gespeichert ist nur der Hash des Tokens
    con = sqlite3.connect(tmp_path / "konten.sqlite")
    hashes = [r[0] for r in con.execute("SELECT token_hash FROM sitzung")]
    con.close()
    assert t_anna not in hashes and len(hashes) == 2


def test_sitzung_laeuft_ab_und_endet(db):
    t = db.sitzung_anlegen(None, -1)
    assert db.sitzung(t) is None
    t = db.sitzung_anlegen(None, 60)
    assert db.sitzung_beenden(t) is True
    assert db.sitzung(t) is None
    assert db.sitzung("gibt-es-nicht") is None


def test_neues_passwort_beendet_sitzungen(db):
    anna = db.anlegen("anna", "pw")
    t = db.sitzung_anlegen(anna, 60)
    db.passwort_setzen("anna", "neu")
    assert db.sitzung(t) is None
    assert db.pruefen("anna", "neu") is not None


def test_sperre_nach_fuenf_fehlschlaegen():
    jetzt = [1000.0]
    s = Sperre(uhr=lambda: jetzt[0])
    for _ in range(4):
        s.fehlschlag("login:1.2.3.4")
    assert s.rest("login:1.2.3.4") == 0
    s.fehlschlag("login:1.2.3.4")
    assert s.rest("login:1.2.3.4") == 60
    assert s.rest("login:5.6.7.8") == 0
    jetzt[0] += 61
    assert s.rest("login:1.2.3.4") == 0
    s.freigeben("login:1.2.3.4")


def test_einstellungen_aus_datei_und_umgebung(tmp_path):
    datei = tmp_path / "wisetrees.env"
    datei.write_text("# Kommentar\nWISETREES_DATEN=/srv/wt\nWISETREES_PORT=9000\n", encoding="utf-8")
    e = config.laden(datei, {"WISETREES_PORT": "9001", "WISETREES_HEUTE": "2026-11-01"})
    assert (e.daten.as_posix(), e.port, e.heute()) == ("/srv/wt", 9001, datetime.date(2026, 11, 1))
    assert config.laden(tmp_path / "fehlt.env", {}).heute() == datetime.date.today()


def test_app_startet(server, einstellungen):
    from vertrag.client import Sitzung

    a = Sitzung(server).holen(server + "/healthz")
    assert a.status == 200 and json.loads(a.daten)["ok"] is True
    assert einstellungen.konten_db.is_file()
    assert einstellungen.baeume.is_dir()


def test_anmelden_dauert_auch_fuer_unbekannte(db):
    """Kein schneller Weg zu erfahren, ob ein Name existiert (Dummy-Hash)."""
    db.anlegen("anna", "pw")
    t0 = time.perf_counter()
    db.pruefen("anna", "falsch")
    bekannt = time.perf_counter() - t0
    t0 = time.perf_counter()
    db.pruefen("niemand", "falsch")
    unbekannt = time.perf_counter() - t0
    assert unbekannt > bekannt / 3


def test_werkzeug_importieren(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    pfad = Path(__file__).resolve().parents[2] / "werkzeuge" / "importieren.py"
    spec = importlib.util.spec_from_file_location("importieren_werkzeug", pfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("WISETREES_DATEN", str(tmp_path))
    ged = Path(__file__).with_name("daten") / "falkenrath-1.7.1.ged"
    assert mod.main(["falkenrath", str(ged)]) == 0
    aus = capsys.readouterr().out
    assert "492 Personen" in aus and (tmp_path / "baeume" / "falkenrath.wise").is_file()
    with pytest.raises(SystemExit):
        mod.main(["falkenrath", str(ged)])  # gibt es schon
