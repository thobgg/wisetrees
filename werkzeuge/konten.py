"""Konten verwalten.

    python werkzeuge/konten.py anlegen NAME [--admin] [--name "Echter Name"]   # fragt das Passwort ab
    python werkzeuge/konten.py passwort NAME
    python werkzeuge/konten.py rolle NAME BAUM ROLLE        # visitor|member|editor|moderator|manager
    python werkzeuge/konten.py liste

Datenordner aus WISETREES_DATEN (Standard /data).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import config  # noqa: E402
from core.konten import ROLLEN, KontenDB  # noqa: E402


def _passwort() -> str:
    eins = getpass.getpass("Passwort: ")
    if eins != getpass.getpass("Wiederholen: "):
        sys.exit("Passwörter stimmen nicht überein")
    return eins


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    u = p.add_subparsers(dest="befehl", required=True)
    a = u.add_parser("anlegen")
    a.add_argument("name")
    a.add_argument("--admin", action="store_true")
    a.add_argument("--name", dest="real_name", default="")
    u.add_parser("passwort").add_argument("name")
    r = u.add_parser("rolle")
    r.add_argument("name")
    r.add_argument("baum")
    r.add_argument("rolle", choices=ROLLEN)
    u.add_parser("liste")
    args = p.parse_args(argv)

    db = KontenDB(config.laden().konten_db)
    if args.befehl == "anlegen":
        db.anlegen(args.name, _passwort(), real_name=args.real_name, is_admin=args.admin)
    elif args.befehl == "passwort":
        db.passwort_setzen(args.name, _passwort())
    elif args.befehl == "rolle":
        db.rolle_setzen(args.name, args.baum, args.rolle)
    else:
        for k in db.alle():
            print(f"{k.name}\t{'Administrator' if k.is_admin else ''}\t{k.real_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
