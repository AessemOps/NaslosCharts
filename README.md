# NaslosCharts

The official chart repository for [Naslos](https://github.com/AessemOps/Naslos-Linux).
Naslos turns each directory under `apps/` into an installable app in its web UI.
The API clones this repository (per channel/branch) with a pure-Go git client and
installs the chart from the clone with the Helm SDK — no `helm` or `git` binary
runs at install time.

- [Repository layout](#repository-layout)
- [Building an app](#building-an-app)
- [naslos-app.yaml reference](#naslos-appyaml-reference)
- [Chart requirements](#chart-requirements)
- [Exposure & routing](#exposure--routing)
- [Storage](#storage)
- [Privileged apps (VPN sidecars)](#privileged-apps-vpn-sidecars)
- [Channels](#channels)
- [Testing checklist](#testing-checklist)

## Repository layout

```
.
└── apps/
    └── <name>/                 # the folder name IS the chart name and the app name
        ├── Chart.yaml          # Helm chart metadata (name MUST equal the folder)
        ├── values.yaml
        ├── naslos-app.yaml     # install-config: catalog metadata, form schema, services, exposure
        └── templates/
            ├── app.yaml        # Deployment/StatefulSet + Service (+ PVC)
            └── ...
```

One app per folder under `apps/`. A release name equals the app name.

## Building an app

1. Copy an existing app (e.g. `apps/radarr`) to `apps/<your-app>`.
2. Set `Chart.yaml` `name:` to `<your-app>` (must match the folder exactly).
3. Edit `naslos-app.yaml`: display metadata, the JSON-Schema `schema` for the
   install form, `defaultValues`, `services` and `exposure` defaults.
4. Edit `values.yaml` + `templates/app.yaml`: image, ports, volumes.
5. Commit to the channel branch (`main` today; see [Channels](#channels)).
6. In the Naslos UI: **Apps → Sources → Refresh**, then install your app.

Hard rules (the API skips a folder that breaks them, and shows a source error):

- A folder under `apps/` is a catalog entry only if it has a `naslos-app.yaml`.
- `naslos-app.yaml` `name` MUST equal the folder name and be a DNS-1123 label
  (`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`).
- `services[].name` may only be a literal or the template
  `{{ .Release.Name }}` — nothing else is templated by the API.
- `services[].port` MUST be 1–65535; `scheme` is `http` or `https`.

## naslos-app.yaml reference

```yaml
name: radarr                     # required; MUST equal the folder (DNS-1123 label)
displayName: Radarr              # shown in the catalog (defaults to name)
description: Movie collection manager
category: media                  # media | productivity | smart-home | networking | development
icon: "R"                        # short emoji/letter shown on the card
website: https://radarr.video
version: 0.1.0                   # informational; Chart.yaml's version wins if both exist
tags: [media, movies]

# JSON Schema (draft-07 subset) that generates the install form in the UI.
# Supported: type string/number/integer/boolean/object, properties, required,
# default, title, description, format (password/email), enum, nested objects.
schema:
  type: object
  properties:
    timezone:
      type: string
      title: Timezone
      default: Etc/UTC
    puid:
      type: integer
      title: PUID
      default: 1000
    pgid:
      type: integer
      title: PGID
      default: 1000
    hostPath:
      type: string
      title: Media host path
      description: Host directory (a Naslos dataset) mounted into the app.
      default: /var/mnt
  required: [timezone, puid, pgid, hostPath]

# Merged under the user's form values at install (catalog defaults first, form
# values win). Keys here should match your chart's values.yaml.
defaultValues:
  timezone: Etc/UTC
  puid: 1000
  pgid: 1000
  hostPath: /var/mnt

# Route targets. The first entry is used by default; the UI can pick another
# (or discover the release's Services if this list is empty — see below).
services:
  - name: "{{ .Release.Name }}"   # typically the release name
    port: 7878
    scheme: http

# Default exposure toggles shown in the install UI. All are overridable there.
exposure:
  subdomain: radarr             # "" = no route (cluster-internal only)
  tls: false                    # true = HTTPS route on Traefik websecure
  auth: false                   # true = Authelia login; only allowed on an SSO domain
  localOnly: false              # true = restrict to the configured LAN CIDR

# Optional. Install into the privileged apps namespace (PSA privileged) instead
# of naslos-apps (PSA baseline). Required when the pod needs NET_ADMIN or other
# caps baseline forbids — e.g. a gluetun VPN sidecar. See below.
privileged: false
```

If `services` is empty, the API discovers the release's Services after install
(matched by the Helm release annotation/label) and routes to the first; the UI's
exposure dialog lists the candidates so an operator can pick.

### Channel configuration

Channels are configured on the Naslos side, not in this repository: the source's
channel map (`apps.officialSource.channels` in the Helm values, or the
`channels` field when adding a source via the API) maps a channel name to a git
branch here. A repository with only a `main` branch therefore uses
`channels: {Prod: main}`. Once added, the branch must exist; a channel that
points at a missing branch reports an error for that source.

## Chart requirements

- `Chart.yaml` `name` equals the folder; `type: application`.
- Render a `Service` and a `Deployment`/`StatefulSet`. Prefer naming the Service
  `{{ .Release.Name }}` and declaring that in `services[].name`.
- Use a `PersistentVolumeClaim` for config/state (the only provisioner is
  `local-path`; leave `storageClassName` empty).
- Set `securityContext` sanely. LinuxServer images expect `PUID`/`PGID`/`TZ`
  environment variables and run as root then drop privileges.
- Do not set `hostNetwork`, `hostPID` or `hostIPC` — PSA baseline rejects them.
  Media directories are mounted with `hostPath` (allowed under baseline); a pod
  that needs extra capabilities goes to the privileged namespace (`privileged: true`).
- Prefer TCP readiness/liveness probes on the app port.

## Exposure & routing

For each app the API owns one Traefik `IngressRoute` plus the middlewares it
references, in the app's namespace:

| Setting | Effect |
| --- | --- |
| `subdomain` | `Host(<subdomain>.<baseDomain>)`; empty ⇒ no route (cluster-internal) |
| `tls` | on ⇒ `websecure` + the base domain's cert Secret; off ⇒ plain `web` HTTP |
| `auth` | on ⇒ Authelia forwardAuth middleware (only on an SSO domain) |
| `localOnly` | on ⇒ `IPAllowList` limited to the configured LAN CIDR |

The shared `security-headers` middleware intentionally omits
`stsIncludeSubdomains`, so a TLS-off subdomain stays reachable.

## Storage

- **Config/state:** a PVC (default `local-path`). Name it `{{ .Release.Name }}`.
- **Media/backups:** mount a host directory with `hostPath`. On Naslos the ZFS
  datasets are exposed at `/var/mnt/<dataset>`; the chart value / schema field
  `hostPath` defaults to `/var/mnt` and is mounted at `/data` (read-write).
- Apps in `naslos-apps` may reach each other (e.g. Radarr → qBittorrent in
  `naslos-apps-priv`); the platform supplies the network policy.

## Privileged apps (VPN sidecars)

PSA `baseline` permits `hostPath` and root, but forbids adding capabilities such
as `NET_ADMIN`. A VPN sidecar (gluetun) needs `NET_ADMIN` and `/dev/net/tun`, so
these apps set `privileged: true`, which installs them into the separate
`naslos-apps-priv` namespace (PSA `privileged`).

Pattern used by `prowlarr` and `qbittorrent`:

```yaml
# templates/app.yaml (abridged)
spec:
  template:
    spec:
      containers:
        - name: gluetun
          image: qmcgaw/gluetun:latest
          securityContext:
            capabilities:
              add: ["NET_ADMIN"]
          env:
            - { name: VPN_SERVICE_PROVIDER, value: "{{ .Values.vpn.provider }}" }
            - { name: VPN_TYPE, value: "{{ .Values.vpn.type }}" }
            - { name: WIREGUARD_PRIVATE_KEY, value: "{{ .Values.vpn.wireguardPrivateKey }}" }
            - { name: SERVER_COUNTRIES, value: "{{ .Values.vpn.serverCountries }}" }
            # optional: FIREWALL_OUTBOUND_SUBNETS for LAN access
          volumeMounts:
            - { name: tun, mountPath: /dev/net/tun }
          ports:
            - { name: http, containerPort: 9696 }
        - name: prowlarr
          image: lscr.io/linuxserver/prowlarr:latest
          # shares the pod network namespace; its traffic exits through gluetun
      volumes:
        - name: tun
          hostPath: { path: /dev/net/tun, type: CharDevice }
```

Both containers share the pod network namespace, so the app's egress goes through
the tunnel set up by gluetun, and the app port is reachable on the pod IP (the
`Service` targets it).

> TLS in the privileged namespace: the base-domain cert Secret is written to
> `naslos-apps`, so a privileged app should use `tls: false` (or the operator
> must provide the Secret in `naslos-apps-priv`).

## Channels

Each channel maps to a git branch (default `Prod`/`Develop`/`Experimental`; this
repo uses `main` for all three via `naslos-repo.yaml`, or `{Prod: main}` in the
Naslos chart values). The API keeps one clone per `(source, channel)` and
refreshes on a TTL. Catalogs from user-added sources override the official repo
on a name collision.

## Testing checklist

Before opening a PR:

1. `helm lint apps/<name>` — passes.
2. `helm template <name> apps/<name>` renders; `kubectl apply --dry-run=server`
   against a cluster with the CRDs installed (optional).
3. `naslos-app.yaml` validates: name matches the folder, DNS-1123, ports in
   range, service name literal/`{{ .Release.Name }}`.
4. Install from the Naslos UI (Apps → Catalog), confirm the route, then
   uninstall and confirm it is removed.
5. For `privileged: true`, confirm the release lands in `naslos-apps-priv`.
