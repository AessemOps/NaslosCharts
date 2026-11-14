# Add the ProjectSend app chart

## Change

New catalog entry `apps/projectsend` (chart 0.1.0):

- **App**: `lscr.io/linuxserver/projectsend` on port 80, with `PUID`/`PGID`/`TZ`,
  `MAX_UPLOAD` (MB) and `PHP_MEMORY_LIMIT` env.
- **Database**: bundled `lscr.io/linuxserver/mariadb` Deployment + Service
  `<release>-mariadb`, initialized with database `projectsend`, user
  `projectsend` and the install-form password.
- **Storage**: `<release>-config` PVC at `/config` (sys.config.php, PHP settings,
  translations), `<release>-uploads` PVC at `/data` (client files), and
  `<release>-mariadb` PVC at `/config` for the database.
- **Catalog**: `auth: false` because ProjectSend has its own per-client accounts;
  TLS on, Internet egress on.

## Setup notes

The LSIO image has no unattended installer. After install, the first visit runs
the ProjectSend setup wizard; the operator enters the bundled database values:
host `<release>-mariadb`, database `projectsend`, user `projectsend` and the
password chosen in the install form.

## Validation

- `helm lint apps/projectsend`
- `helm template projectsend apps/projectsend -n naslos-app-1`
- `naslos-app.yaml` name/folder/DNS-1123 and service port checks
- UI install (Apps → Catalog): wizard completes against the bundled MariaDB,
  uploads persist under `/data` across a release restart.
