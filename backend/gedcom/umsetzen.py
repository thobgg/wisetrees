"""Zwischen GEDCOM 5.5.1 und 7.0 umsetzen (E24, E27).

Arbeitet auf den fertigen Strukturen einer Ausgabe, also auch auf GEDCOM-Resten, und nur beim Wechsel der Fassung:
Ein Baum aus 5.5.1 geht als 5.5.1 so hinaus, wie er kam (Rundlauf ohne Verlust), ebenso einer aus 7.0. Was in der
Zielfassung nicht gültig ist und eine feste Entsprechung hat, wird umgesetzt; Gültiges bleibt, wie es ist. Was danach
nicht gültig ist, zählt `ungueltig`.

Jede Umsetzung wird gezählt („_UID → UID“), damit der Exportbericht zeigt, was aus der einen Fassung in der anderen
wird.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import quote

from baum.schema import ROLLEN_GEDCOM7

from .datum import lesen as datum_lesen
from .import551 import rolle_aus_rela
from .struktur import ZEIGER, E

GOV_EXID = "https://gov.genealogy.net/"   # EXID.TYPE der GOV-Kennung in 7.0

# Dateiformat: 5.5.1 nennt die Endung, 7.0 den MIME-Typ
MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "png": "image/png", "bmp": "image/bmp",
        "tif": "image/tiff", "tiff": "image/tiff", "webp": "image/webp", "heic": "image/heic", "svg": "image/svg+xml",
        "pcx": "image/x-pcx", "pdf": "application/pdf", "txt": "text/plain", "htm": "text/html", "html": "text/html",
        "xml": "application/xml", "rtf": "application/rtf", "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "odt": "application/vnd.oasis.opendocument.text", "zip": "application/zip", "wav": "audio/wav",
        "mp3": "audio/mpeg", "ogg": "audio/ogg", "mp4": "video/mp4", "avi": "video/x-msvideo",
        "mov": "video/quicktime", "mpg": "video/mpeg", "mpeg": "video/mpeg"}
ENDUNG = {}
for _e, _m in MIME.items():
    ENDUNG.setdefault(_m, _e)

MEDIEN_551 = ("audio", "book", "card", "electronic", "fiche", "film", "magazine", "manuscript", "map", "newspaper",
              "photo", "tombstone", "video")
MEDIEN_7 = {m.upper() for m in MEDIEN_551} | {"OTHER"}
NAMENSART_7 = {"AKA", "BIRTH", "IMMIGRANT", "MAIDEN", "MARRIED", "PROFESSIONAL", "OTHER"}
STAT_7 = {"CHALLENGED", "DISPROVEN", "PROVEN"}
RESN_7 = {"CONFIDENTIAL", "LOCKED", "PRIVACY"}
ROLLE_551 = {"CHIL", "HUSB", "WIFE", "MOTH", "FATH", "SPOU"}       # SOUR:EVEN:ROLE, sonst (Text)
ROLLE_7 = set(ROLLEN_GEDCOM7)
ROLLE_TEXT = {"GODP": "godparent", "WITN": "witness", "CLERGY": "clergy", "OFFICIATOR": "officiator",
              "FRIEND": "friend", "NGHBR": "neighbor", "MULTIPLE": "multiple", "PARENT": "parent"}
ALTER_7 = {"CHILD": "< 8y", "INFANT": "< 1y", "STILLBORN": "0y"}
_ALTER_7 = re.compile(r"^(?:[<>] )?(?=\d)(?:\d+y)?(?: ?\d+m)?(?: ?\d+w)?(?: ?\d+d)?$")

# Ereignisse, die in 7.0 als Wert nur Y kennen
NUR_Y = {"ADOP", "BAPM", "BARM", "BASM", "BIRT", "BLES", "BURI", "CENS", "CHR", "CHRA", "CONF", "CREM", "DEAT", "EMIG",
         "FCOM", "GRAD", "IMMI", "NATU", "ORDN", "PROB", "RETI", "WILL", "ANUL", "DIV", "DIVF", "ENGA", "MARB", "MARC",
         "MARL", "MARR", "MARS"}

# Sprachen: Namen aus 5.5.1 ↔ Kennungen nach BCP 47 (7.0)
SPRACHEN = {
    "Afrikaans": "af", "Albanian": "sq", "Anglo-Saxon": "ang", "Arabic": "ar", "Armenian": "hy", "Belorusian": "be",
    "Bengali": "bn", "Bulgarian": "bg", "Burmese": "my", "Cantonese": "yue", "Catalan": "ca", "Catalan_Spn": "ca",
    "Church-Slavic": "cu", "Czech": "cs", "Danish": "da", "Dutch": "nl", "English": "en", "Esperanto": "eo",
    "Estonian": "et", "Faroese": "fo", "Finnish": "fi", "French": "fr", "Georgian": "ka", "German": "de",
    "Greek": "el", "Gujarati": "gu", "Hawaiian": "haw", "Hebrew": "he", "Hindi": "hi", "Hungarian": "hu",
    "Icelandic": "is", "Indonesian": "id", "Italian": "it", "Japanese": "ja", "Kannada": "kn", "Khmer": "km",
    "Korean": "ko", "Lao": "lo", "Latin": "la", "Latvian": "lv", "Lithuanian": "lt", "Macedonian": "mk",
    "Malayalam": "ml", "Mandrin": "cmn", "Marathi": "mr", "Navaho": "nv", "Nepali": "ne", "Norwegian": "no",
    "Persian": "fa", "Polish": "pl", "Portuguese": "pt", "Romanian": "ro", "Russian": "ru", "Sanskrit": "sa",
    "Serb": "sr", "Serbo_Croa": "sh", "Slovak": "sk", "Slovene": "sl", "Spanish": "es", "Swedish": "sv",
    "Tagalog": "tl", "Tamil": "ta", "Telugu": "te", "Thai": "th", "Tibetan": "bo", "Turkish": "tr",
    "Ukrainian": "uk", "Urdu": "ur", "Vietnamese": "vi", "Wendic": "wen", "Yiddish": "yi"}
_SPRACHE_KLEIN = {n.lower(): k for n, k in SPRACHEN.items()}
SPRACHNAME = {}
for _n, _k in SPRACHEN.items():
    SPRACHNAME.setdefault(_k, _n)
_BCP47 = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$")

KALENDER = {"@#DGREGORIAN@": "GREGORIAN", "@#DJULIAN@": "JULIAN", "@#DHEBREW@": "HEBREW", "@#DFRENCH R@": "FRENCH_R"}

NUR_7 = {"EXID", "PHRASE", "SCHMA", "MIME", "TRAN", "SDATE", "CREA", "INIL", "NO"}
NUR_551 = {"AFN", "RFN", "RIN", "SUBN", "BLOB", "CHAR"}


def url(pfad: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", pfad)) or pfad.lower().startswith("file:")


def datei_nach7(pfad: str) -> str:
    """Dateipfad als URL (7.0): Sonderzeichen mit %, Adressen mit Schema bleiben."""
    return pfad if url(pfad) else quote(pfad, safe="/")


def datum_nach7(text: str) -> tuple[str, str | None]:
    """5.5.1-Datum → (7.0-Datum, PHRASE). Unverstandenes wird ein leeres Datum mit dem Text als PHRASE."""
    t = re.sub(r"\s+", " ", text.strip())
    m = re.fullmatch(r"\((.*)\)", t)
    if m:
        return "", m.group(1)
    phrase = None
    m = re.fullmatch(r"INT (.+?) \((.*)\)", t, re.I)
    if m:
        t, phrase = m.group(1), m.group(2)
    for alt, neu in KALENDER.items():
        t = t.replace(alt, neu)
    t = re.sub(r"(\d+) ?B\.C\.", r"\1 BCE", t)
    m = re.search(r"\b(\d{3,4})/(\d{2})\b", t)    # Doppeljahr 1700/01: das spätere Jahr, Wortlaut als PHRASE
    if m:
        jahr = int(m.group(1))
        spaeter = jahr // 100 * 100 + int(m.group(2))
        spaeter += 100 if spaeter < jahr else 0
        t, phrase = t[:m.start()] + str(spaeter) + t[m.end():], phrase or text.strip()
    t = t.upper()
    d = datum_lesen(t)
    if d is None or not d.gueltig or d.kind == "phrase":
        return "", text.strip()
    return t, phrase


def datum_nach551(text: str, phrase: str | None) -> tuple[str, str | None]:
    """7.0-Datum mit PHRASE → (5.5.1-Datum, PHRASE, die nicht unterzubringen war)."""
    vorn, klammer, hinten = text.strip().partition("(")     # nur außerhalb eines Wortlauts in Klammern
    for alt, neu in KALENDER.items():
        vorn = re.sub(rf"(?<![@\w]){neu}\b ?", alt + " ", vorn)
    vorn = re.sub(r"(\d+) BCE\b", r"\1 B.C.", vorn)
    t = vorn + klammer + hinten
    if phrase is None:
        return t, None
    d = datum_lesen(phrase)   # Wortlaut, der selbst ein 5.5.1-Datum ist (Doppeljahr 1700/01): so, wie er war
    if d is not None and d.gueltig and d.kind != "phrase" and datum_nach7(phrase) == (text.strip(), phrase):
        return phrase, None
    if not t:
        return f"({phrase})", None
    d = datum_lesen(t)
    if d is not None and d.gueltig and d.kind == "exact" and d.quality == "exact":
        return f"INT {t} ({phrase})", None
    return t, phrase


class Umsetzer:
    def __init__(self, fassung: str):
        self.v7 = fassung.startswith("7")
        self.umgesetzt: Counter = Counter()
        self.ungueltig: Counter = Counter()
        self.verlust: list[str] = []

    def zaehle(self, was: str) -> None:
        self.umgesetzt[was] += 1

    def saetze(self, saetze: list[E]) -> None:
        for s in saetze:
            self.knoten(s, ())

    def knoten(self, e: E, pfad: tuple[str, ...]) -> None:
        if e.roh is not None:
            return
        (self.nach7 if self.v7 else self.nach551)(e, pfad)
        for k in list(e.kinder):
            self.knoten(k, (*pfad, e.tag))

    @staticmethod
    def _phrase(e: E) -> E | None:
        return e.erstes("PHRASE")

    def _mit_phrase(self, e: E, wert: str, text: str) -> None:
        e.wert = wert
        if self._phrase(e) is None:
            e.kinder.insert(0, E("PHRASE", text))

    # ── 5.5.1 → 7.0 ───────────────────────────────────────────────────────────────────────────────

    def nach7(self, e: E, pfad: tuple[str, ...]) -> None:
        t, eltern = e.tag, (pfad[-1] if pfad else None)
        if t == "_UID":
            e.tag = "UID"
            self.zaehle("_UID → UID")
        elif t == "NOTE" and (not pfad and e.xref or e.wert and ZEIGER.fullmatch(e.wert)):
            e.tag = "SNOTE"
            self.zaehle("NOTE-Datensatz → SNOTE" if not pfad else "NOTE @…@ → SNOTE @…@")
        elif t == "_GOV" and eltern == "PLAC":
            e.tag = "EXID"
            e.kinder.insert(0, E("TYPE", GOV_EXID))
            self.zaehle("PLAC._GOV → PLAC.EXID mit TYPE GOV")
        elif t == "_ASSO":
            e.tag = "ASSO"
            self.zaehle("_ASSO → ASSO")
        elif t == "RELA" and eltern == "ASSO":
            text = e.wert or ""
            code = rolle_aus_rela(text)
            e.tag, e.wert = "ROLE", code
            e.kinder.insert(0, E("PHRASE", text))
            self.zaehle("RELA → ROLE mit PHRASE")
        elif t == "FORM" and eltern == "FILE" and e.wert and "/" not in e.wert:
            mime = MIME.get(e.wert.lower())
            if mime:
                self.zaehle(f"FORM {e.wert} → {mime}")
                e.wert = mime
            else:
                self.ungueltig[f"FORM {e.wert}"] += 1
        elif t == "TYPE" and eltern == "FORM":
            e.tag = "MEDI"
            self.zaehle("FORM.TYPE → FORM.MEDI")
            self._medium7(e)
        elif t == "MEDI" and eltern in ("FORM", "CALN"):
            self._medium7(e)
        elif t == "LANG" and e.wert:
            if e.wert.lower() in _SPRACHE_KLEIN:
                code = _SPRACHE_KLEIN[e.wert.lower()]
                self.zaehle(f"LANG {e.wert} → {code}")
                e.wert = code
            elif not _BCP47.match(e.wert):
                self.ungueltig[f"LANG {e.wert}"] += 1
        elif t == "STAT" and eltern == "FAMC" and e.wert and e.wert not in STAT_7 and e.wert.upper() in STAT_7:
            self.zaehle(f"FAMC.STAT {e.wert} → {e.wert.upper()}")
            e.wert = e.wert.upper()
        elif t == "RESN" and e.wert:
            neu = ", ".join(w.strip().upper() for w in e.wert.split(","))
            if neu != e.wert and all(w in RESN_7 for w in neu.split(", ")):
                self.zaehle(f"RESN {e.wert} → {neu}")
                e.wert = neu
        elif t == "TYPE" and eltern == "NAME" and e.wert and e.wert not in NAMENSART_7:
            if e.wert.upper() in NAMENSART_7:
                self.zaehle(f"NAME.TYPE {e.wert} → {e.wert.upper()}")
                e.wert = e.wert.upper()
            else:
                self._mit_phrase(e, "OTHER", e.wert)
                self.zaehle("NAME.TYPE <Text> → OTHER mit PHRASE")
        elif t == "ROLE" and eltern == "EVEN" and len(pfad) > 1 and pfad[-2] == "SOUR" and e.wert:
            v = e.wert.strip()
            m = re.fullmatch(r"\((.*)\)", v)
            if v in ROLLE_7:
                pass
            elif v.upper() in ROLLE_7:
                e.wert = v.upper()
                self.zaehle("SOUR.EVEN.ROLE in Großbuchstaben")
            else:
                self._mit_phrase(e, "OTHER", m.group(1) if m else v)
                self.zaehle("SOUR.EVEN.ROLE (Text) → OTHER mit PHRASE")
        elif t == "AGE" and e.wert:
            self._alter7(e)
        elif t == "DATE" and e.wert:
            neu, phrase = datum_nach7(e.wert)
            if neu != e.wert or phrase:
                art = "unverstanden → PHRASE" if not neu else "umgeschrieben"
                self.zaehle(f"DATE {art}")
                e.wert = neu or None
                if phrase:
                    if self._phrase(e) is None:
                        e.kinder.insert(0, E("PHRASE", phrase))
                    else:
                        self.ungueltig["DATE mit zweiter PHRASE"] += 1
        elif t in NUR_Y and eltern in ("INDI", "FAM") and e.wert not in (None, "", "Y"):
            self.verlust.append(f"{t} {e.wert[:40]}: 7.0 erlaubt hier nur Y, der Text steht als Notiz")
            e.kinder.insert(0, E("NOTE", e.wert))
            e.wert = None
            self.zaehle(f"{t} <Text> → {t} mit NOTE")
        elif t in NUR_551:
            self.ungueltig[f"{t} (gibt es in 7.0 nicht)"] += 1

    def _medium7(self, e: E) -> None:
        v = e.wert or ""
        if not v or v in MEDIEN_7:
            return
        if v.lower() in MEDIEN_551:
            self.zaehle(f"MEDI {v} → {v.upper()}")
            e.wert = v.upper()
        else:
            self._mit_phrase(e, "OTHER", v)
            self.zaehle(f"MEDI {v} → OTHER mit PHRASE")

    def _alter7(self, e: E) -> None:
        v = e.wert.strip()
        if v.upper() in ALTER_7:
            self._mit_phrase(e, ALTER_7[v.upper()], v)
            self.zaehle(f"AGE {v.upper()} → {ALTER_7[v.upper()]} mit PHRASE")
            return
        neu = re.sub(r"^([<>])(?=\d)", r"\1 ", v)
        neu = re.sub(r"(\d+)([YMWD])", lambda m: m.group(1) + m.group(2).lower(), neu)
        if neu != e.wert and _ALTER_7.match(neu):
            self.zaehle("AGE umgeschrieben")
            e.wert = neu
        elif not _ALTER_7.match(neu):
            self.ungueltig[f"AGE {v}"] += 1

    # ── 7.0 → 5.5.1 ───────────────────────────────────────────────────────────────────────────────

    def nach551(self, e: E, pfad: tuple[str, ...]) -> None:
        t, eltern = e.tag, (pfad[-1] if pfad else None)
        phrase = self._phrase(e)
        if t == "HEAD":
            for k in [k for k in e.kinder if k.tag == "SCHMA"]:
                e.kinder.remove(k)
                self.zaehle("HEAD.SCHMA entfällt")
        elif t == "UID":
            e.tag = "_UID"
            self.zaehle("UID → _UID")
        elif t == "SNOTE" and (not pfad and e.xref or e.wert and ZEIGER.fullmatch(e.wert)):
            e.tag = "NOTE"
            self.zaehle("SNOTE-Datensatz → NOTE" if not pfad else "SNOTE @…@ → NOTE @…@")
        elif t == "EXID" and eltern == "PLAC" and [k.wert for k in e.kinder if k.tag == "TYPE"] == [GOV_EXID]:
            e.tag = "_GOV"
            e.kinder = [k for k in e.kinder if k.tag != "TYPE"]
            self.zaehle("PLAC.EXID mit TYPE GOV → PLAC._GOV")
        elif t == "ASSO" and len(pfad) > 1:     # ASSO an einem Ereignis (an der Person bleibt es ASSO)
            e.tag = "_ASSO"
            self.zaehle("ASSO am Ereignis → _ASSO")
        elif t == "ROLE" and eltern in ("ASSO", "_ASSO"):
            e.tag, e.wert = "RELA", (phrase.wert if phrase else ROLLE_TEXT.get(e.wert or "", (e.wert or "").lower()))
            if phrase:
                e.kinder.remove(phrase)
            self.zaehle("ROLE → RELA")
        elif t == "FORM" and eltern == "FILE" and e.wert and "/" in e.wert:
            endung = ENDUNG.get(e.wert.lower())
            if endung:
                self.zaehle(f"FORM {e.wert} → {endung}")
                e.wert = endung
            else:
                self.ungueltig[f"FORM {e.wert}"] += 1
        elif t == "MEDI" and eltern == "FORM":
            e.tag = "TYPE"
            self.zaehle("FORM.MEDI → FORM.TYPE")
            self._medium551(e, phrase)
        elif t == "MEDI" and eltern == "CALN":
            self._medium551(e, phrase)
        elif t == "LANG" and e.wert and e.wert.lower() not in _SPRACHE_KLEIN:
            name = SPRACHNAME.get(e.wert.split("-")[0].lower())
            if name:
                self.zaehle(f"LANG {e.wert} → {name}")
                e.wert = name
            else:
                self.ungueltig[f"LANG {e.wert}"] += 1
        elif t == "TYPE" and eltern == "NAME" and e.wert == "OTHER" and phrase:
            e.wert = phrase.wert
            e.kinder.remove(phrase)
            self.zaehle("NAME.TYPE OTHER mit PHRASE → Text")
        elif t == "TYPE" and eltern == "NAME" and e.wert in NAMENSART_7:
            self.zaehle(f"NAME.TYPE {e.wert} → {e.wert.lower()}")
            e.wert = e.wert.lower()
        elif t == "STAT" and eltern == "FAMC" and e.wert in STAT_7:
            self.zaehle(f"FAMC.STAT {e.wert} → {e.wert.lower()}")
            e.wert = e.wert.lower()
        elif t == "ROLE" and eltern == "EVEN" and len(pfad) > 1 and pfad[-2] == "SOUR" and e.wert:
            if e.wert not in ROLLE_551:
                text = phrase.wert if phrase else ROLLE_TEXT.get(e.wert, e.wert.lower())
                e.wert = f"({text})"
                if phrase:
                    e.kinder.remove(phrase)
                self.zaehle("SOUR.EVEN.ROLE → (Text)")
        elif t == "AGE" and phrase and (phrase.wert or "").upper() in ALTER_7:
            e.wert = phrase.wert.upper()
            e.kinder.remove(phrase)
            self.zaehle(f"AGE mit PHRASE → {e.wert}")
        elif t == "DATE" and (e.wert or phrase):
            neu, rest = datum_nach551(e.wert or "", phrase.wert if phrase else None)
            if neu != (e.wert or "") or (phrase and rest is None):
                self.zaehle("DATE mit PHRASE → INT/(Text)" if phrase and rest is None else "DATE umgeschrieben")
            e.wert = neu or None
            if phrase and rest is None:
                e.kinder.remove(phrase)
        elif t == "NO" and eltern in ("INDI", "FAM"):
            e.tag = "_NO"
            self.zaehle("NO → _NO")
        elif t in NUR_7:
            self.ungueltig[f"{t} (gibt es in 5.5.1 nicht)"] += 1

    def _medium551(self, e: E, phrase: E | None) -> None:
        if e.wert == "OTHER" and phrase:
            e.wert = phrase.wert
            e.kinder.remove(phrase)
            self.zaehle("MEDI OTHER mit PHRASE → Text")
        elif e.wert in MEDIEN_7:
            self.zaehle(f"MEDI {e.wert} → {e.wert.lower()}")
            e.wert = e.wert.lower()
