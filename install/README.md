# Installing wisetrees

[Deutsch](LIESMICH.md)

wisetrees runs as a container. You need a machine with Docker: a Linux server, a Raspberry Pi or a NAS with container
support (Synology Container Manager, QNAP Container Station, Unraid …). The image is available for amd64 and arm64.
No database has to be set up: every family tree is a single file.

This package contains:

- `docker-compose.yml` – pulls the ready-made image, nothing to build
- `env.beispiel` – settings; put it next to `docker-compose.yml` as `.env`

## With Docker Compose

```sh
mkdir wisetrees && cd wisetrees
# copy docker-compose.yml and env.beispiel here
cp env.beispiel .env          # adjust user (id -u, id -g), port and data folder
mkdir data
docker compose up -d
docker compose logs wisetrees # shows the setup code on first start
```

Then open `http://<machine>:8099/index.php` in a browser and go to **Verwaltung** (administration). On first use,
the setup code creates the first administrator account. After that: import a GEDCOM file, create accounts, assign
roles. The page **App verbinden** (connect app) shows the address for wtAnd, wtTux and wtWin.

Images belong in `data/medien/<tree name>/`, with the paths from the FILE lines of the GEDCOM file.

## On a Synology with Container Manager

1. In File Station, create a folder such as `docker/wisetrees` with a subfolder `data`.
2. Upload `docker-compose.yml` and `env.beispiel` to `docker/wisetrees`, rename `env.beispiel` to `.env`.
3. In `.env`, enter the user wisetrees should run as (`WISETREES_UID`, `WISETREES_GID`). This user needs write
   access to `data`.
4. In Container Manager: **Project** › **Create**, choose the path `docker/wisetrees`, use the existing
   `docker-compose.yml`. Leave the step **Web portal via Web Station** empty; set up access from outside afterwards
   with the reverse proxy (see below). Start the project.
5. The setup code is shown in Container Manager under the container `wisetrees` › **Log**.
6. Continue in the browser as above.

## Data folder

On start, wisetrees sets the folder `data` to owner only (mode 700), so nobody else can read accounts and trees.
Put images into `data/medien/` as the user from `WISETREES_UID`, on a Synology with your own account in File Station.

## Updating and backup

- New version: `docker compose pull && docker compose up -d` (Container Manager: Project › Action › Build).
- Only the folder `data` needs a backup: `konten.sqlite` (accounts, roles, sessions), `baeume/*.wise` (one SQLite
  file per tree) and `medien/`.

## Access

wisetrees itself does not speak HTTPS. Within the home network the address above is enough. For access from outside,
put a reverse proxy with a certificate in front (on a Synology: Control Panel › Login Portal › Advanced › Reverse
Proxy). The apps accept addresses without HTTPS only within the home network.

The reverse proxy forwards to `http://localhost:8099`. wisetrees trusts its headers (HTTPS, visitor address) only
from this machine and the internal Docker networks (`WISETREES_PROXY` in `.env`). If nobody in the home network
should reach port 8099 directly, use `"127.0.0.1:8099:8099"` under `ports` in `docker-compose.yml`; then the only
way in is through the reverse proxy.
