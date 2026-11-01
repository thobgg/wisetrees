"""Konten, Rollen je Baum und Sitzungen in einer SQLite-Datei (konten.sqlite, KONZEPT.md 5.1, E8).

Passwörter als Argon2id mit den OWASP-Werten; ein Dummy-Hash sorgt dafür, dass unbekannte Namen dieselbe Rechenzeit
kosten. Von Sitzungen wird nur der SHA-256 des Tokens gespeichert; abgelaufene werden nebenbei aufgeräumt. Sitzungen
gibt es auch für Besucher, weil v1 das CSRF-Token schon vor der Anmeldung ausgibt (docs/API-V1.md).

Passwörter und Tokens werden nie protokolliert.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

logger = logging.getLogger(__name__)

# OWASP 2024: 64 MiB, 3 Durchläufe, 4 Spuren
_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
# Einmal erzeugt: unbekannte Namen kosten genauso viel Rechenzeit wie bekannte.
_DUMMY_HASH = _ph.hash("kein-echtes-passwort")

# Rollen je Baum, aufsteigend; die Namen sind die von v1 (Info.trees[].role). „visitor“ wird nicht gespeichert.
ROLLEN = ("visitor", "member", "editor", "moderator", "manager")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS konto (
    name        TEXT PRIMARY KEY,
    pw_hash     TEXT NOT NULL,
    real_name   TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    language    TEXT NOT NULL DEFAULT '',
    is_admin    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS baumrolle (
    konto  TEXT NOT NULL REFERENCES konto(name) ON DELETE CASCADE,
    baum   TEXT NOT NULL,
    rolle  TEXT NOT NULL CHECK (rolle IN ('member', 'editor', 'moderator', 'manager')),
    PRIMARY KEY (konto, baum)
);
CREATE TABLE IF NOT EXISTS sitzung (
    token_hash  TEXT PRIMARY KEY,
    konto       TEXT REFERENCES konto(name) ON DELETE CASCADE,  -- NULL = Besucher
    csrf        TEXT NOT NULL,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    ip          TEXT,
    user_agent  TEXT
);
CREATE INDEX IF NOT EXISTS sitzung_ablauf ON sitzung(expires_at);
CREATE INDEX IF NOT EXISTS sitzung_konto ON sitzung(konto);
"""


@dataclass(frozen=True)
class Konto:
    name: str
    real_name: str
    email: str
    language: str
    is_admin: bool


@dataclass(frozen=True)
class Sitzung:
    konto: Konto | None
    csrf: str
    expires_at: float


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class KontenDB:
    """Eine Verbindung je Datei, Zugriffe durch eine Sperre nacheinander (wenig Last)."""

    def __init__(self, pfad: Path):
        pfad.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(pfad), check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA foreign_keys=ON")
        self._con.executescript(_SCHEMA)
        try:
            pfad.chmod(0o600)
        except OSError as e:
            logger.warning("chmod 0600 auf %s: %s", pfad, e)
        self._aufraeumen = 0

    def schliessen(self) -> None:
        self._con.close()

    # Konten ---------------------------------------------------------------------------------------

    @staticmethod
    def _konto(r: sqlite3.Row) -> Konto:
        return Konto(r["name"], r["real_name"], r["email"], r["language"], bool(r["is_admin"]))

    def anlegen(self, name: str, passwort: str, *, real_name: str = "", email: str = "", is_admin: bool = False) -> Konto:
        if not name or not passwort:
            raise ValueError("Name und Passwort dürfen nicht leer sein")
        with self._lock:
            self._con.execute(
                "INSERT INTO konto(name, pw_hash, real_name, email, is_admin, created_at) VALUES(?,?,?,?,?,?)",
                (name, _ph.hash(passwort), real_name, email, int(is_admin), time.time()))
        return self.konto(name)

    def konto(self, name: str) -> Konto | None:
        with self._lock:
            r = self._con.execute("SELECT * FROM konto WHERE name = ?", (name,)).fetchone()
        return self._konto(r) if r else None

    def alle(self) -> list[Konto]:
        with self._lock:
            return [self._konto(r) for r in self._con.execute("SELECT * FROM konto ORDER BY name")]

    def passwort_setzen(self, name: str, passwort: str) -> None:
        if not passwort:
            raise ValueError("Passwort darf nicht leer sein")
        with self._lock:
            n = self._con.execute("UPDATE konto SET pw_hash = ? WHERE name = ?", (_ph.hash(passwort), name)).rowcount
            if n:
                # Nach neuem Passwort gilt keine alte Sitzung mehr.
                self._con.execute("DELETE FROM sitzung WHERE konto = ?", (name,))
        if not n:
            raise KeyError(name)

    def pruefen(self, name: str, passwort: str) -> Konto | None:
        """Name und Passwort prüfen. Unbekannte Namen kosten dieselbe Rechenzeit (Dummy-Hash)."""
        with self._lock:
            r = self._con.execute("SELECT * FROM konto WHERE name = ?", (name,)).fetchone()
        try:
            _ph.verify(r["pw_hash"] if r else _DUMMY_HASH, passwort)
        except (VerificationError, InvalidHashError):
            return None
        return self._konto(r) if r else None

    # Rollen je Baum -------------------------------------------------------------------------------

    def rolle_setzen(self, name: str, baum: str, rolle: str) -> None:
        if rolle not in ROLLEN:
            raise ValueError(f"unbekannte Rolle {rolle!r}")
        with self._lock:
            if rolle == "visitor":
                self._con.execute("DELETE FROM baumrolle WHERE konto = ? AND baum = ?", (name, baum))
            else:
                self._con.execute("INSERT OR REPLACE INTO baumrolle(konto, baum, rolle) VALUES(?,?,?)", (name, baum, rolle))

    def rolle(self, konto: Konto | None, baum: str) -> str:
        """Rolle im Baum. Administratoren sind überall Verwalter, ohne Eintrag gilt „visitor“."""
        if konto is None:
            return "visitor"
        if konto.is_admin:
            return "manager"
        with self._lock:
            r = self._con.execute("SELECT rolle FROM baumrolle WHERE konto = ? AND baum = ?", (konto.name, baum)).fetchone()
        return r["rolle"] if r else "visitor"

    # Sitzungen ------------------------------------------------------------------------------------

    def sitzung_anlegen(self, konto: Konto | None, sekunden: int, *, ip: str | None = None,
                        user_agent: str | None = None) -> str:
        """Neue Sitzung, gibt das Token zurück (nur sein Hash wird gespeichert)."""
        token = secrets.token_urlsafe(32)
        jetzt = time.time()
        with self._lock:
            self._con.execute(
                "INSERT INTO sitzung(token_hash, konto, csrf, created_at, expires_at, last_seen, ip, user_agent) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (_hash(token), konto.name if konto else None, secrets.token_urlsafe(24), jetzt, jetzt + sekunden, jetzt,
                 ip, (user_agent or "")[:300]))
        return token

    def sitzung(self, token: str | None) -> Sitzung | None:
        if not token:
            return None
        jetzt = time.time()
        th = _hash(token)
        with self._lock:
            r = self._con.execute(
                "SELECT s.*, k.name AS k_name, k.real_name, k.email, k.language, k.is_admin "
                "FROM sitzung s LEFT JOIN konto k ON k.name = s.konto WHERE s.token_hash = ?", (th,)).fetchone()
            if r is None:
                return None
            if r["expires_at"] < jetzt:
                self._con.execute("DELETE FROM sitzung WHERE token_hash = ?", (th,))
                return None
            self._con.execute("UPDATE sitzung SET last_seen = ? WHERE token_hash = ?", (jetzt, th))
            self._aufraeumen += 1
            if self._aufraeumen >= 100:
                self._aufraeumen = 0
                self._con.execute("DELETE FROM sitzung WHERE expires_at < ?", (jetzt,))
        konto = None
        if r["k_name"]:
            konto = Konto(r["k_name"], r["real_name"], r["email"], r["language"], bool(r["is_admin"]))
        return Sitzung(konto, r["csrf"], r["expires_at"])

    def sitzung_beenden(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            return self._con.execute("DELETE FROM sitzung WHERE token_hash = ?", (_hash(token),)).rowcount > 0
