"""docs/SCHEMA.md aus den SQLAlchemy-Tabellen erzeugen (E16 Teil 1).

    python werkzeuge/schema_doku.py            # schreibt docs/SCHEMA.md
    python werkzeuge/schema_doku.py --pruefen  # Fehlercode 1, wenn die Datei nicht zum Schema passt

Die Datei wird nie von Hand bearbeitet; ein Test prüft, dass sie zum Code passt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint  # noqa: E402

from baum import schema  # noqa: E402
from core import konten  # noqa: E402

ZIEL = REPO / "docs" / "SCHEMA.md"


def _typ(spalte) -> str:
    t = spalte.type
    if isinstance(t, String) and t.length:
        return f"Text ({t.length})"
    if isinstance(t, Integer):
        return "Ganzzahl"
    return {"TEXT": "Text", "DOUBLE": "Kommazahl"}.get(t.__class__.__name__.upper(), t.__class__.__name__)


def _zelle(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _tabelle(t) -> list[str]:
    zeilen = [f"### {t.name}", ""]
    if t.comment:
        zeilen += [t.comment + ".", ""]
    zeilen += ["| Spalte | Typ | Pflicht | Vorgabe | Verweis | Bedeutung |", "|---|---|---|---|---|---|"]
    for c in t.columns:
        verweis = ", ".join(f"{fk.column.table.name}.{fk.column.name}"
                            + (f" (beim Löschen: {fk.ondelete})" if fk.ondelete else "") for fk in c.foreign_keys)
        pflicht = "Schlüssel" if c.primary_key else ("ja" if not c.nullable else "")
        if c.unique:
            pflicht = (pflicht + ", " if pflicht else "") + "eindeutig"
        vorgabe = c.server_default.arg.text if c.server_default is not None else ""
        zeilen.append(f"| `{c.name}` | {_typ(c)} | {pflicht} | {_zelle(vorgabe)} | {verweis} | {_zelle(c.comment)} |")
    # t.constraints ist eine Menge: fest sortieren, damit die Datei bei jedem Lauf gleich ist
    regeln = sorted((k for k in t.constraints if isinstance(k, CheckConstraint)), key=lambda k: k.sqltext.text)
    eindeutig = sorted((k for k in t.constraints if isinstance(k, UniqueConstraint) and len(k.columns) > 1),
                       key=lambda k: [c.name for c in k.columns])
    if regeln or eindeutig:
        zeilen += ["", "Regeln:", ""]
        zeilen += [f"- eindeutig: {', '.join(c.name for c in k.columns)}" for k in eindeutig]
        zeilen += [f"- `{k.sqltext.text}`" for k in regeln]
    if t.indexes:
        zeilen += ["", "Indizes: " + "; ".join(f"`{i.name}` ({', '.join(c.name for c in i.columns)})"
                                                for i in sorted(t.indexes, key=lambda i: i.name))]
    return zeilen + [""]


def erzeugen() -> str:
    z = [
        "# Schema der Datenbanken",
        "",
        "*Erzeugt aus dem Code (`backend/baum/schema.py`, `backend/core/konten.py`) mit "
        "`python werkzeuge/schema_doku.py`; nicht von Hand bearbeiten.*",
        "",
        "*Generated from the code; German only for now. Table and column names are English.*",
        "",
        "## Baumdatei (.wise)",
        "",
        f"Jeder Stammbaum ist eine SQLite-Datei mit `PRAGMA application_id = {schema.APPLICATION_ID:#010x}` "
        f"(„WISE“) und `PRAGMA user_version = {schema.SCHEMA_VERSION}` (Schemaversion). Die Datei lässt sich mit "
        "jedem SQLite-Werkzeug lesen. Das Schema ist portabel für PostgreSQL und MariaDB (KONZEPT.md E16): "
        f"Kennungen haben höchstens {schema.XREF_LAENGE} Zeichen, Textspalten mit Index bekommen in MariaDB einen "
        f"Präfix-Index ({schema.PRAEFIX} Zeichen).",
        "",
        "Gemeinsame Bausteine:",
        "",
        "- **Datum** (`date_text`, `date_kind`, `date_quality`, `date_calendar`, `date_from`, `date_to`): der Text wie "
        "in der Quelle, die Art (exact, before, after, between, from, to, from_to, phrase), die Qualität (exact, about, "
        "calculated, estimated), der Kalender und der früheste und späteste julianische Tag (KONZEPT 3.8).",
        "- **Sperrvermerk** `resn`: none, privacy, confidential, locked.",
        "- **Träger**: Notizen, Zitate, Medienverweise, Aufgaben und GEDCOM-Reste hängen über je eine Spalte "
        "`<typ>_id` an ihrem Träger; genau eine davon ist gefüllt (`on_tree` = am ganzen Baum).",
        "- **Rollen** an Ereignissen: `PRINCIPAL` (Hauptbeteiligte) und die Codes von GEDCOM 7 "
        f"({', '.join(schema.ROLLEN_GEDCOM7)}), dazu eigene Codes mit `X_`.",
        "",
    ]
    for t in schema.metadata.tables.values():
        z += _tabelle(t)
    z += ["## Kontendatei (konten.sqlite)", "",
          "Konten, Rollen je Baum und Sitzungen; eine Datei für alle Bäume. Von Sitzungen wird nur der SHA-256 des "
          "Tokens gespeichert, Passwörter als Argon2id.", ""]
    for t in konten.metadata.tables.values():
        z += _tabelle(t)
    return "\n".join(z).rstrip() + "\n"


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--pruefen", action="store_true")
    args = a.parse_args(argv)
    text = erzeugen()
    if args.pruefen:
        if not ZIEL.exists() or ZIEL.read_text(encoding="utf-8") != text:
            print("docs/SCHEMA.md passt nicht zum Schema: python werkzeuge/schema_doku.py", file=sys.stderr)
            return 1
        return 0
    ZIEL.write_text(text, encoding="utf-8")
    print(f"{ZIEL.relative_to(REPO)} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
