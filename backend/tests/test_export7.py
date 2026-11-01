"""GEDCOM-7.0-Export und Wechsel der Fassung (KONZEPT.md 6, E23–E27).

Prüfsteine: Falkenrath 1.7.1 als 5.5.1 und als 7.0 (beide CC0). Belegt wird:
- 7.0 → 7.0 ohne Verlust, Export → Import → Export bitgenau;
- 7.0 → 5.5.1 → 7.0 ohne Verlust;
- 5.5.1 → 7.0 → 5.5.1 bis auf das, was 7.0 nicht erlaubt und der Exportbericht nennt;
- der eigene 7.0-Export von Falkenrath ergibt dasselbe Modell wie die 7.0-Fassung des Demobaums.
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest

from baum import datei
from baum.auszug import auszug, unterschiede
from gedcom.export import exportieren
from gedcom.import551 import importieren

DATEN = Path(__file__).with_name("daten")
HEUTE = datetime.datetime(2026, 11, 2, 12, 0, 0)


class Kette:
    """Import, dann abwechselnd Export und Import; hält Auszüge, Texte und Berichte fest."""

    def __init__(self, tmp: Path, gedcom: bytes):
        self.tmp, self.n = Path(tempfile.mkdtemp(dir=tmp)), 0
        self.auszuege, self.texte, self.berichte = [self._import(gedcom)], [], []

    def _import(self, gedcom: bytes) -> dict:
        self.n += 1
        ziel = self.tmp / f"{self.n}.wise"
        importieren(gedcom, ziel)
        con = datei.oeffnen(ziel)
        try:
            self.con_auszug = auszug(con)
            self.letzte = ziel
            return self.con_auszug
        finally:
            con.close()

    def weiter(self, fassung: str) -> Kette:
        con = datei.oeffnen(self.letzte)
        try:
            text, bericht = exportieren(con, HEUTE, fassung)
        finally:
            con.close()
        self.texte.append(text)
        self.berichte.append(bericht)
        self.auszuege.append(self._import(text))
        return self


def pfade(a: dict, b: dict) -> list[tuple[str, str]]:
    return [(art, pfad) for art, pfad, _, _ in unterschiede(a, b)]


@pytest.fixture(scope="module")
def f7(tmp_path_factory):
    return Kette(tmp_path_factory.mktemp("f7"), (DATEN / "falkenrath-1.7.1-gedcom7.ged").read_bytes()).weiter("7.0")


@pytest.fixture(scope="module")
def f5(tmp_path_factory):
    return Kette(tmp_path_factory.mktemp("f5"), (DATEN / "falkenrath-1.7.1.ged").read_bytes()).weiter("7.0")


# ── 7.0 → 7.0 ─────────────────────────────────────────────────────────────────────────────────────────

def test_7_rundlauf_ohne_verlust(f7):
    assert unterschiede(f7.auszuege[0], f7.auszuege[1]) == []


def test_7_fester_punkt_bitgenau(f7, tmp_path):
    k = Kette(tmp_path, f7.texte[0]).weiter("7.0")
    assert k.texte[0] == f7.texte[0]


def test_7_ohne_umsetzung(f7):
    b = f7.berichte[0]
    assert (b.herkunft, b.fassung) == ("7.0", "7.0")
    assert b.umgesetzt == {} and b.nicht_verlustfrei == [] and b.ungueltig == {}


def test_kopf_7(f7):
    text = f7.texte[0].decode()
    assert text.split("\n")[:4] == ["0 HEAD", "1 GEDC", "2 VERS 7.0", "1 SOUR WISE"]
    assert "\n1 CHAR" not in text and " CONC " not in text and "_ADDENDUM" not in text
    assert "\n1 LANG de\n" in text


# ── 7.0 → 5.5.1 → 7.0 ─────────────────────────────────────────────────────────────────────────────────

def test_7_nach_551_nach_7_ohne_verlust(tmp_path):
    k = Kette(tmp_path, (DATEN / "falkenrath-1.7.1-gedcom7.ged").read_bytes()).weiter("5.5.1").weiter("7.0")
    assert unterschiede(k.auszuege[0], k.auszuege[2]) == []
    b = k.berichte[0]
    assert (b.herkunft, b.fassung) == ("7.0", "5.5.1")
    assert b.nicht_verlustfrei == [] and b.ungueltig == {}
    assert {"UID → _UID": 1037, "ASSO @VOID@ mit PHRASE → _GODP/_WITN": 583,
            "PLAC.EXID mit TYPE GOV → PLAC._GOV": 94, "FORM image/jpeg → jpg": 142,
            "MEDI OTHER mit PHRASE → Text": 11}.items() <= b.umgesetzt.items()


# ── 5.5.1 → 7.0 → 5.5.1 ───────────────────────────────────────────────────────────────────────────────

def test_551_nach_7_bericht(f5):
    b = f5.berichte[0]
    assert (b.herkunft, b.fassung) == ("5.5.1", "7.0")
    assert {"_UID → UID": 1037, "_GODP/_WITN → ASSO @VOID@ mit PHRASE": 583, "_ASSO mit RELA → ASSO mit ROLE": 261,
            "PLAC._GOV → PLAC.EXID mit TYPE GOV": 94, "FORM jpg → image/jpeg": 142, "MEDI photo → PHOTO": 131,
            "MEDI document → OTHER mit PHRASE": 11, "MEDI book → BOOK": 140, "LANG German → de": 2,
            "SOUR.EVEN.ROLE (Text) → OTHER mit PHRASE": 3}.items() <= b.umgesetzt.items()
    assert b.ungueltig == {}
    assert b.neue_datensaetze == ["@S205@ SOUR für eine Quellenangabe ohne Quelle"]
    assert len(b.nicht_verlustfrei) == 3   # EMIG- und IMMI-Text als Notiz, die Textquelle als Datensatz


def test_551_nach_7_nach_551_nur_was_7_nicht_erlaubt(f5, tmp_path):
    k = Kette(tmp_path, f5.texte[0]).weiter("5.5.1")
    assert pfade(f5.auszuege[0], k.auszuege[1]) == [
        ("+", "/person/@I25@/facts[2]/event/notes"), ("-", "/person/@I25@/facts[2]/event/value"),
        ("+", "/person/@I65@/facts[2]/event/citations[1]/source"),
        ("-", "/person/@I65@/facts[2]/event/citations[1]/source_text"),
        ("+", "/person/@I65@/facts[2]/event/notes"), ("-", "/person/@I65@/facts[2]/event/value"),
        ("+", "/source/@S205@")]


def test_eigener_7_export_wie_7_fassung_des_demobaums(f5, f7):
    """Das Umwandlungswerkzeug des Demobaums schreibt Rollentexte klein; sonst dasselbe Modell."""
    assert [(art, pfad, alt, neu) for art, pfad, alt, neu in unterschiede(f7.auszuege[0], f5.auszuege[1])] == [
        ("+", "/person/@I57@/facts[1]/event/roles[0]/rela", None, "Godparent"),
        ("~", "/person/@I58@/associations[0]/relation", "godmother", "Godmother"),
        ("~", "/person/@I58@/associations[1]/relation", "godmother", "Godmother")]


# ── Einzelfälle 5.5.1 → 7.0 ───────────────────────────────────────────────────────────────────────────

KLEIN5 = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
1 LANG German
0 @I1@ INDI
1 NAME Anna /Weber/
2 TYPE married
1 NAME Änne /Weber/
2 TYPE Rufname
1 SEX F
1 BIRT
2 DATE @#DJULIAN@ 1 JAN 1700
2 _GODP Hans Meier, Bauer in Hesel
2 _ASSO @I2@
3 RELA godparent
1 CHR
2 DATE INT 1700 (um Ostern)
1 DEAT
2 DATE 10 FEB 1750/51
2 AGE CHILD
1 BURI
2 DATE (Frühjahr 1751)
1 FAMC @F1@
2 PEDI foster
2 STAT proven
1 NOTE @N1@
1 OBJE
2 FILE bilder/foto 1.jpg
3 FORM jpg
2 TITL Ein Foto
0 @I2@ INDI
1 NAME Hans /Weber/
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 CHIL @I1@
1 _STAT NOT MARRIED
0 @N1@ NOTE Eine Notiz
0 TRLR
"""


@pytest.fixture
def klein5(tmp_path):
    return Kette(tmp_path, KLEIN5.encode()).weiter("7.0")


def test_klein5_als_7(klein5):
    text = klein5.texte[0].decode()
    for teil in ("1 LANG de",
                 "1 NAME Anna /Weber/\n2 TYPE MARRIED",
                 "1 NAME Änne /Weber/\n2 TYPE OTHER\n3 PHRASE Rufname",
                 "2 DATE JULIAN 1 JAN 1700",
                 "2 ASSO @VOID@\n3 PHRASE Hans Meier, Bauer in Hesel\n3 ROLE GODP",
                 "2 ASSO @I2@\n3 ROLE GODP\n",              # „godparent“ sagt nicht mehr als GODP
                 "2 DATE 1700\n3 PHRASE um Ostern",
                 "2 DATE 10 FEB 1751\n3 PHRASE 10 FEB 1750/51",
                 "2 AGE < 8y\n3 PHRASE CHILD",
                 "1 BURI\n2 DATE\n3 PHRASE Frühjahr 1751",
                 "1 FAMC @F1@\n2 PEDI FOSTER\n2 STAT PROVEN",
                 "1 SNOTE @N1@", "0 @N1@ SNOTE Eine Notiz",
                 "1 OBJE @M1@",
                 "0 @M1@ OBJE\n1 FILE bilder/foto%201.jpg\n2 FORM image/jpeg\n2 TITL Ein Foto",
                 "1 NO MARR"):
        assert teil in text, teil
    b = klein5.berichte[0]
    assert b.neue_datensaetze == ["@M1@ OBJE für ein eingebettetes Medium"]
    assert b.ungueltig == {}


def test_klein5_zurueck_nach_551(klein5, tmp_path):
    """Zurück nach 5.5.1 kommt alles wieder wie vorher – bis auf das eingebettete Medium, das in 7.0 ein Datensatz
    sein muss."""
    k = Kette(tmp_path, klein5.texte[0]).weiter("5.5.1")
    assert pfade(klein5.auszuege[0], k.auszuege[1]) == [("+", "/media/@M1@"), ("~", "/person/@I1@/media[0]/object")]
    text = k.texte[0].decode()
    for teil in ("2 DATE @#DJULIAN@ 1 JAN 1700", "2 DATE INT 1700 (um Ostern)", "2 DATE 10 FEB 1750/51",
                 "2 AGE CHILD", "2 DATE (Frühjahr 1751)", "2 TYPE Rufname", "2 TYPE married", "2 PEDI foster",
                 "2 STAT proven", "1 _STAT NOT MARRIED", "1 LANG German", "2 _GODP Hans Meier, Bauer in Hesel",
                 "2 _ASSO @I2@\n3 RELA godparent", "1 FILE bilder/foto 1.jpg\n2 FORM jpg"):
        assert teil in text, teil


# ── Einzelfälle 7.0 → 5.5.1 ───────────────────────────────────────────────────────────────────────────

KLEIN7 = """0 HEAD
1 GEDC
2 VERS 7.0
0 @I1@ INDI
1 NAME Anna /Weber/
1 SEX F
1 NO MARR
2 DATE FROM 1900 TO 1920
1 BAPM
2 DATE JULIAN 1 JAN 1700
2 ASSO @I2@
3 ROLE OTHER
4 PHRASE Taufzeugin
2 ASSO @VOID@
3 PHRASE Unbekannter Pate
3 ROLE GODP
1 SNOTE @N1@
1 ASSO @I2@
2 ROLE FRIEND
1 UID 0d5e4ab1-6a1f-4f37-9d8e-3c4b5a6d7e8f
0 @I2@ INDI
1 NAME Berta /Weber/
0 @N1@ SNOTE Geteilte Notiz
0 TRLR
"""


def test_klein7_als_551_und_zurueck(tmp_path):
    k = Kette(tmp_path, KLEIN7.encode()).weiter("5.5.1").weiter("7.0")
    text = k.texte[0].decode()
    for teil in ("1 _NO MARR\n2 DATE FROM 1900 TO 1920", "2 DATE @#DJULIAN@ 1 JAN 1700",
                 "2 _ASSO @I2@\n3 RELA Taufzeugin", "2 _GODP Unbekannter Pate", "1 NOTE @N1@",
                 "0 @N1@ NOTE Geteilte Notiz", "1 ASSO @I2@\n2 RELA FRIEND",
                 "1 _UID 0d5e4ab1-6a1f-4f37-9d8e-3c4b5a6d7e8f"):
        assert teil in text, teil
    # 5.5.1 kennt nur den Rollentext: „Taufzeugin“ wird beim Einlesen als Pate erkannt – das steht im Bericht
    assert k.berichte[0].ungueltig == {}
    assert k.berichte[0].nicht_verlustfrei == ["@I1@: Rolle OTHER mit Text „Taufzeugin“ wird aus 5.5.1 als GODP gelesen"]
    assert unterschiede(k.auszuege[0], k.auszuege[2]) == [
        ("~", "/person/@I1@/facts[1]/event/roles[0]/role", "OTHER", "GODP")]
    assert k.texte[1].decode().count("1 NO MARR") == 1
