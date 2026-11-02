# wisetrees

[Deutsch](README.de.md) · **English**

> **wisetrees is no longer developed.** The last version is
> [0.3.0](https://github.com/thobgg/wisetrees/releases/tag/v0.3.0); code, releases and images stay available.

A self-hosted genealogy server with its own JSON interface. It keeps individuals, events, places and sources in its
own data model; GEDCOM is the exchange format. An event such as a baptism is one object, with the child, the parents
and the godparents attached in their roles; places have dated names and a dated hierarchy.

![wtTux showing the Falkenrath demo tree from wisetrees](docs/img/wttux-falkenrath.jpg)

## Status

**What works**

- Importing GEDCOM 5.5.1 with GEDCOM-L. Every line is either taken over or kept as a remainder in its place; the
  import report counts both and lists uncertain place assignments.
- The interface [api4wisetrees v1](docs/API-V1.md) for reading: list and search of individuals, individual, family,
  ancestors, descendants, fact types, images. Visibility per role (visitor, member, editor, moderator, manager)
  including protection of living people.
- Writing through v1 with moderation: add, change and delete facts; add individuals, link and unlink them, delete
  individuals and families. Changes by editors stay pending until a moderator or manager accepts or rejects them;
  editors and above see pending changes, visitors and members never do. Checked against the reference by contract
  tests; not yet tried in the apps.
- wtTux shows the Falkenrath demo tree from wisetrees: tree, navigator, person panel with godparents, sources
  and photos. wtAnd uses the same core; a test on a device is still to come.
- Accounts, roles per tree, sessions; runs as a Docker container (not as root).
- Administration in the browser for administrators: first-run setup with a one-time code, create accounts, set
  passwords and roles, upload and import GEDCOM with the import report, delete trees. Every account can change its
  own password there.
- Privacy settings per tree: privacy on/off, tree for members only, deceased and names of private individuals by
  role, private relationships, maximum age, protection after birth or death, rules per type, record and fact type
  on a record. Per account: "this is me" and relationship privacy (living individuals only within a number of
  relationship steps).
- Database access via SQLAlchemy Core with a portable schema ([docs/SCHEMA.md](docs/SCHEMA.md)).

**What is missing**

- Uploading media and the other parts of milestone 2: the whole tree page by page for the apps, pairing a device,
  bookmarks, anniversaries.
- GEDCOM export and the round-trip test import → export → import.
- GEDCOM 7.0, ANSEL character set.
- PostgreSQL and MariaDB as alternatives to SQLite.
- Relationship names beyond close relatives.

**Planned, not built**

The other parts of milestone 2 in the order of [docs/FUNKTIONEN.md](docs/FUNKTIONEN.md) 1.3: photos (upload, link,
main photo, thumbnails), the whole tree page by page, pairing a device, bookmarks, anniversaries. The concept with all
decisions is in [docs/KONZEPT.md](docs/KONZEPT.md) (German).

## Try it

Ready-made installation with Docker or Synology Container Manager: [install/README.md](install/README.md), as a
package attached to every release. From source:

```sh
mkdir -p data
docker compose up -d --build
docker compose logs wisetrees     # shows the setup code on first start
```

Then open `http://<host>:8099/index.php` and go to “Verwaltung” (administration): on first use, the setup code
creates the first administrator account. After that, further accounts and GEDCOM imports are done there; the page
“App verbinden” gives the address for the apps.
Trees are stored as `data/baeume/<name>.wise` (SQLite), images under `data/medien/<name>/`.

Tests (Python 3.11):

```sh
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest backend/tests      # unit tests
.venv/bin/python -m vertrag.wisetrees         # contract tests of the interface
```

## Contributing

Ideas and bug reports are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[AGPL-3.0-only](LICENSE). Dependencies and their licences: [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

Developed with Claude Code.
