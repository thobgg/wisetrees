-- Schema der Kontendatei aus wisetrees 0.1, eingefroren als Vergleich für Tests.
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
