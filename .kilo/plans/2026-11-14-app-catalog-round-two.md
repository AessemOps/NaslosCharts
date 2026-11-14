# Add 34 apps to the catalog

## Change

New catalog entries under `apps/`, all chart `0.1.0`, all declaring
`capabilities: [env]` (main container `envFrom` on `naslos-env-<release>` plus
the `naslos.io/env-checksum` pod annotation), all `internet: true`.

| Group | Apps |
| --- | --- |
| Media | plex, emby, navidrome, mealie, pinchflat, immich, invidious |
| Productivity | memos, beaverhabits, code-server, slink, docmost, karakeep, linkwarden, paperless-ngx, nextcloud, wordpress, odoo, joplin, mattermost, kanboard, drawio |
| Networking / infra | pihole, telltaledns, headscale, netdata, rustdesk, mumble, hermes |
| Monitoring / dev | sonarqube, teslamate, dawarich, worldmonitor, rclone |

Bundled dependencies (each auto-created by the chart):

- MariaDB 11: nextcloud, wordpress
- PostgreSQL 16: odoo, joplin, mattermost, sonarqube, teslamate, docmost,
  linkwarden, paperless-ngx, invidious
- PostGIS 17: dawarich
- VectorChord Postgres 14: immich
- Redis: docmost, paperless-ngx, dawarich, immich, worldmonitor
- Meilisearch: karakeep, linkwarden
- Chrome: karakeep
- AIS relay + Redis REST proxy: worldmonitor

## Caveats recorded in the charts

- **rustdesk** and **mumble** have no HTTP UI, so `services: []` and
  `exposure.subdomain: ""`; clients must reach the service ports directly. The
  catalog cannot publish those ports (no hostPort/NodePort). RustDesk's relay
  address is an optional `relayAddress` value.
- **pihole** and **telltaledns** expose DNS on 53/tcp+udp through their
  ClusterIP Services only; the web UI is routed normally.
- **netdata** monitors its own container only; host-wide metrics need
  hostNetwork/host mounts, which the contract forbids.
- **headscale** relies on its own first-start key/database generation (the
  distroless image has no shell for an initContainer) and needs `serverUrl` set
  to the public HTTPS route.
- **pi-hole**, **dawarich**, **telltale** need a first-run admin/token or the
  real hostname in the install form; **odoo** creates its database from the
  database manager; **joplin**, **mattermost**, **sonarqube**, **kanboard** and
  **wordpress** keep their own first-run admin flows.
- **invidious** ships without the separate Invidious companion, so video
  playback may be limited; **immich** ships server + ML + DB + cache.

## Validation

- `python3 scripts/check-contract.py` → `catalog contract: 68 app(s) OK`
- `helm lint` and `helm template <app> apps/<app> -n naslos-app-1` for all 34
  new charts
- `kubectl apply --dry-run=server` of every rendered chart against the node
- Static check: every required schema property has a matching `defaultValues`
  entry, every default matches `values.yaml`, and every `.Values.*` referenced
  by a template exists
- Rendered env wiring check: exactly one `envFrom` and one checksum annotation
  per chart, on the main app workload only
