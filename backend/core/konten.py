"""Konten, Rollen je Baum und Sitzungen in einer SQLite-Datei (konten.sqlite, KONZEPT.md 5.1, E8).

Zugriff über SQLAlchemy Core mit portablem Schema (E16), damit dieselbe Schicht später auch PostgreSQL nutzen kann.

Passwörter als Argon2id mit den OWASP-Werten; ein Dummy-Hash sorgt dafür, dass unbekannte Namen dieselbe Rechenzeit
kosten. Von Sitzungen wird nur der SHA-256 des Tokens gespeichert; abgelaufene werden nebenbei aufgeräumt. Sitzungen
gibt es auch für Besucher, weil v1 das CSRF-Token schon vor der Anmeldung ausgibt (docs/API-V1.md).

Passwörter und Tokens werden nie protokolliert.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import (CheckConstraint, Column, Double, ForeignKey, Index, Integer, MetaData, PrimaryKeyConstraint,
                        String, Table, Text, create_engine, delete, event, insert, select, text, update)
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

# OWASP 2024: 64 MiB, 3 Durchläufe, 4 Spuren
_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
# Einmal erzeugt: unbekannte Namen kosten genauso viel Rechenzeit wie bekannte.
_DUMMY_HASH = _ph.hash("kein-echtes-passwort")

# Rollen je Baum, aufsteigend; die Namen sind die von v1 (Info.trees[].role). „visitor“ wird nicht gespeichert.
ROLLEN = ("visitor", "member", "editor", "moderator", "manager")

NAME_LAENGE = 255   # Kontoname und Baumname (feste Länge für Schlüssel, E16)

metadata = MetaData()

konto_t = Table(
    "konto", metadata,
    Column("name", String(NAME_LAENGE), primary_key=True),
    Column("pw_hash", Text, nullable=False),
    Column("real_name", Text, nullable=False, server_default=text("''")),
    Column("email", Text, nullable=False, server_default=text("''")),
    Column("language", Text, nullable=False, server_default=text("''")),
    Column("is_admin", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Double, nullable=False),
)

baumrolle_t = Table(
    "baumrolle", metadata,
    Column("konto", String(NAME_LAENGE), ForeignKey("konto.name", ondelete="CASCADE"), nullable=False),
    Column("baum", String(NAME_LAENGE), nullable=False),
    Column("rolle", String(20), nullable=False),
    CheckConstraint("rolle IN ('member', 'editor', 'moderator', 'manager')"),
    PrimaryKeyConstraint("konto", "baum"),
)

sitzung_t = Table(
    "sitzung", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("konto", String(NAME_LAENGE), ForeignKey("konto.name", ondelete="CASCADE")),  # NULL = Besucher
    Column("csrf", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("expires_at", Double, nullable=False),
    Column("last_seen", Double, nullable=False),
    Column("ip", Text),
    Column("user_agent", Text),
    Index("sitzung_ablauf", "expires_at"),
    Index("sitzung_konto", "konto"),
)


def _pragmas(dbapi_con, _eintrag) -> None:
    c = dbapi_con.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    c.close()


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
        # Eine Verbindung, Zugriffe nacheinander unter der Sperre; jede Methode schreibt in eigener Transaktion.
        self._engine = create_engine(f"sqlite:///{pfad}", poolclass=StaticPool,
                                     connect_args={"check_same_thread": False})
        event.listen(self._engine, "connect", _pragmas)
        self._con = self._engine.connect()
        with self._con.begin():
            metadata.create_all(self._con, checkfirst=True)
        try:
            pfad.chmod(0o600)
        except OSError as e:
            logger.warning("chmod 0600 auf %s: %s", pfad, e)
        self._aufraeumen = 0

    def schliessen(self) -> None:
        self._con.close()
        self._engine.dispose()

    def _lesen(self, abfrage):
        """Eine Zeile lesen und die Lesetransaktion gleich wieder schließen."""
        with self._con.begin():
            r = self._con.execute(abfrage).first()
        return r._mapping if r is not None else None

    # Konten ---------------------------------------------------------------------------------------

    @staticmethod
    def _konto(r) -> Konto:
        return Konto(r["name"], r["real_name"], r["email"], r["language"], bool(r["is_admin"]))

    def anlegen(self, name: str, passwort: str, *, real_name: str = "", email: str = "", language: str = "",
                is_admin: bool = False) -> Konto:
        if not name or not passwort:
            raise ValueError("Name und Passwort dürfen nicht leer sein")
        if len(name) > NAME_LAENGE:
            raise ValueError(f"Name länger als {NAME_LAENGE} Zeichen")
        with self._lock, self._con.begin():
            self._con.execute(insert(konto_t).values(
                name=name, pw_hash=_ph.hash(passwort), real_name=real_name, email=email, language=language,
                is_admin=int(is_admin), created_at=time.time()))
        return self.konto(name)

    def konto(self, name: str) -> Konto | None:
        with self._lock:
            r = self._lesen(select(konto_t).where(konto_t.c.name == name))
        return self._konto(r) if r else None

    def alle(self) -> list[Konto]:
        with self._lock, self._con.begin():
            return [self._konto(r._mapping) for r in self._con.execute(select(konto_t).order_by(konto_t.c.name))]

    def passwort_setzen(self, name: str, passwort: str) -> None:
        if not passwort:
            raise ValueError("Passwort darf nicht leer sein")
        with self._lock, self._con.begin():
            n = self._con.execute(update(konto_t).where(konto_t.c.name == name)
                                  .values(pw_hash=_ph.hash(passwort))).rowcount
            if n:
                # Nach neuem Passwort gilt keine alte Sitzung mehr.
                self._con.execute(delete(sitzung_t).where(sitzung_t.c.konto == name))
        if not n:
            raise KeyError(name)

    def pruefen(self, name: str, passwort: str) -> Konto | None:
        """Name und Passwort prüfen. Unbekannte Namen kosten dieselbe Rechenzeit (Dummy-Hash)."""
        with self._lock:
            r = self._lesen(select(konto_t).where(konto_t.c.name == name))
        try:
            _ph.verify(r["pw_hash"] if r else _DUMMY_HASH, passwort)
        except (VerificationError, InvalidHashError):
            return None
        return self._konto(r) if r else None

    # Rollen je Baum -------------------------------------------------------------------------------

    def rolle_setzen(self, name: str, baum: str, rolle: str) -> None:
        if rolle not in ROLLEN:
            raise ValueError(f"unbekannte Rolle {rolle!r}")
        with self._lock, self._con.begin():
            # Löschen und neu eintragen statt INSERT OR REPLACE: das gibt es nicht in jeder Datenbank.
            self._con.execute(delete(baumrolle_t).where(baumrolle_t.c.konto == name, baumrolle_t.c.baum == baum))
            if rolle != "visitor":
                self._con.execute(insert(baumrolle_t).values(konto=name, baum=baum, rolle=rolle))

    def rolle(self, konto: Konto | None, baum: str) -> str:
        """Rolle im Baum. Administratoren sind überall Verwalter, ohne Eintrag gilt „visitor“."""
        if konto is None:
            return "visitor"
        if konto.is_admin:
            return "manager"
        with self._lock:
            r = self._lesen(select(baumrolle_t.c.rolle).where(baumrolle_t.c.konto == konto.name,
                                                               baumrolle_t.c.baum == baum))
        return r["rolle"] if r else "visitor"

    # Sitzungen ------------------------------------------------------------------------------------

    def sitzung_anlegen(self, konto: Konto | None, sekunden: int, *, ip: str | None = None,
                        user_agent: str | None = None) -> str:
        """Neue Sitzung, gibt das Token zurück (nur sein Hash wird gespeichert)."""
        token = secrets.token_urlsafe(32)
        jetzt = time.time()
        with self._lock, self._con.begin():
            self._con.execute(insert(sitzung_t).values(
                token_hash=_hash(token), konto=konto.name if konto else None, csrf=secrets.token_urlsafe(24),
                created_at=jetzt, expires_at=jetzt + sekunden, last_seen=jetzt, ip=ip, user_agent=(user_agent or "")[:300]))
        return token

    def sitzung(self, token: str | None) -> Sitzung | None:
        if not token:
            return None
        jetzt = time.time()
        th = _hash(token)
        s, k = sitzung_t, konto_t
        with self._lock, self._con.begin():
            r = self._con.execute(
                select(s, k.c.name.label("k_name"), k.c.real_name, k.c.email, k.c.language, k.c.is_admin)
                .select_from(s.outerjoin(k, k.c.name == s.c.konto)).where(s.c.token_hash == th)).first()
            if r is None:
                return None
            r = r._mapping
            if r["expires_at"] < jetzt:
                self._con.execute(delete(s).where(s.c.token_hash == th))
                return None
            self._con.execute(update(s).where(s.c.token_hash == th).values(last_seen=jetzt))
            self._aufraeumen += 1
            if self._aufraeumen >= 100:
                self._aufraeumen = 0
                self._con.execute(delete(s).where(s.c.expires_at < jetzt))
        konto = None
        if r["k_name"]:
            konto = Konto(r["k_name"], r["real_name"], r["email"], r["language"], bool(r["is_admin"]))
        return Sitzung(konto, r["csrf"], r["expires_at"])

    def sitzung_beenden(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock, self._con.begin():
            return self._con.execute(delete(sitzung_t).where(sitzung_t.c.token_hash == _hash(token))).rowcount > 0
