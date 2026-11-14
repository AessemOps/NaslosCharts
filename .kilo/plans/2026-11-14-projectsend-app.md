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

## Fix (0.1.1): assets loaded over http

The first install stored `base_uri` as `http://send.shail.ovh/`, so the login
page emitted mixed-content asset URLs and the browser blocked the CSS/JS.

Root cause: Traefik terminates TLS and forwards `X-Forwarded-Proto`, but the
LinuxServer nginx site config only passes `$https` to PHP, so
`get_current_url()` (used to prefill the setup wizard) always detected `http`.
The nginx config on the config PVC is now patched by an initContainer that
prepends a `map` for `$http_x_forwarded_proto` and injects
`fastcgi_param HTTPS $naslos_forwarded_https if_not_empty;` into the PHP
location. Fresh installs therefore detect `https`, build https asset URLs and
set secure session cookies. The existing instance's `tbl_options.base_uri` was
corrected to `https://send.shail.ovh/` and the same site config was applied and
reloaded.

## Validation

- `helm lint apps/projectsend`
- `helm template projectsend apps/projectsend -n naslos-app-1`
- `naslos-app.yaml` name/folder/DNS-1123 and service port checks
- Patch script run twice against a copy of the image's `default.conf` (no
  duplicate map/param) and against an empty config dir (first-boot path)
- `nginx -t` with the patched config, then `nginx -s reload`
- `curl https://send.shail.ovh/` emits only `https://` asset URLs; CSS returns
  200
- UI install (Apps → Catalog): wizard completes against the bundled MariaDB,
  uploads persist under `/data` across a release restart.
