# NaslosCharts

The official chart repository for [Naslos](https://github.com/AessemOps/Naslos-Linux).
Naslos turns each directory under `apps/` into an installable app in its web UI.
The API clones this repository (per channel/branch) and installs the chart with
the `helm` and `git` CLIs it bundles (Helm 4) — the node needs no binaries of
its own.

- [Repository layout](#repository-layout)
- [Building an app](#building-an-app)
- [naslos-app.yaml reference](#naslos-appyaml-reference)
- [Chart requirements](#chart-requirements)
- [Environment variables](#environment-variables)
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
- If the chart's `disableAuth` default is `true` (the app trusts Authelia's
  `Remote-User` header and has **no login of its own**), `exposure.auth` MUST
  default to `true`. Turning Authelia off is only safe after re-enabling the
  app's own authentication; the catalog must not ship that combination by
  default.

## naslos-app.yaml reference

```yaml
name: radarr                     # required; MUST equal the folder (DNS-1123 label)
displayName: Radarr              # shown in the catalog (defaults to name)
description: Movie collection manager
category: media                  # media | productivity | smart-home | networking | development
icon: "R"                        # short emoji/letter shown on the card
website: https://radarr.video
version: 0.1.1                   # informational; Chart.yaml's version wins if both exist
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
  required: [timezone, puid, pgid]

# Merged under the user's form values at install (catalog defaults first, form
# values win). Keys here should match your chart's values.yaml.
defaultValues:
  timezone: Etc/UTC
  puid: 1000
  pgid: 1000

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
  auth: true                    # true = Authelia login; required when the app has no login
  protectedPaths: []            # prefixes that need Authelia even when auth is false
  localOnly: false              # true = restrict to the configured LAN CIDR
  internet: true                # on by default; false = DNS + app-to-app only

# Optional. Install into the privileged apps namespace (PSA privileged) instead
# of naslos-apps (PSA baseline). Required when the pod needs NET_ADMIN or other
# caps baseline forbids — e.g. a gluetun VPN sidecar. See below.
privileged: false

# Optional chart capabilities the API may rely on. `env` = the chart wires the
# platform-managed environment Secret into its main container(s); see
# "Environment variables" below.
capabilities: [env]
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

## Environment variables

A chart whose manifest declares `capabilities: [env]` lets an operator add
custom environment variables per installed app. Naslos stores them in a Secret
named `naslos-env-<release>` in the app namespace and never writes them into
Helm values, so the chart template is the only place the Secret is referenced.

When the capability is declared, the chart MUST:

1. Add an `envFrom` reference to every **main** container — not sidecars such as
   `postgres`, `redis`, `gluetun`, `dind`, init containers, or helper jobs:

   ```yaml
             envFrom:
               - secretRef: { name: naslos-env-{{ .Release.Name }}, optional: true }
   ```

   `optional: true` keeps the chart installable with `helm install` outside
   Naslos and before any variable is set.

2. Add the rollout trigger to that workload's pod template:

   ```yaml
       metadata:
         annotations:
           naslos.io/env-checksum: {{ .Values.naslosEnvChecksum | default "" | quote }}
   ```

`naslosEnvChecksum` is platform-owned: do not declare it in `values.yaml`,
`defaultValues`, or the form schema. The API derives it from the Secret contents
and the changed annotation rolls the pod on every variable change.

Names the chart sets in its own `env:` blocks are reserved. The API rejects a
user variable whose name the chart already defines (Kubernetes would otherwise
silently prefer the chart value), reporting `env var X is set by the chart`.

## Exposure & routing

For each app the API owns one Traefik `IngressRoute` plus the middlewares it
references, and one Internet-egress `NetworkPolicy`, all in the app's
namespace:

| Setting | Effect |
| --- | --- |
| `subdomain` | `Host(<subdomain>.<baseDomain>)`; empty ⇒ no route (cluster-internal) |
| `tls` | on ⇒ `websecure` + the base domain's cert Secret; off ⇒ plain `web` HTTP |
| `auth` | on ⇒ Authelia forwardAuth middleware (only on an SSO domain). MUST be on when the app has no login of its own — in particular for any chart with `disableAuth: true` (Radarr/Sonarr/Prowlarr in External-auth mode) |
| `protectedPaths` | path prefixes (`PathPrefix`) that require Authelia even when `auth` is off, e.g. `["/preferences"]`; the rest of the host stays public. Ignored when `auth` is on. The API emits a higher-priority protected route so the public catch-all cannot shadow it. |
| `localOnly` | on ⇒ `IPAllowList` limited to the configured LAN CIDR |
| `internet` | on (default) ⇒ additive `<app>-internet` `NetworkPolicy` allowing public egress (never the cluster, LAN or metadata ranges); off ⇒ only the base DNS + app-to-app policy |

Every catalog entry declares `internet: true` so apps reach search engines,
indexers, APIs and updates out of the box; the install and exposure dialogs
expose the switch so an operator can turn it off. The opt-out is enforced only
for a baseline app with a dedicated namespace (`apps.isolation.enabled`, the
install default). Privileged namespaces (their base policy always allows
Internet) and the legacy shared `naslos-apps` namespace reject
`internet: false` with a 400 instead of silently leaving egress open.

`protectedPaths` is how an app can stay open for day-to-day use while its
settings surface requires a session. SearXNG uses it for `/preferences`,
`/config` and `/stats`, and hides the Preferences link in its theme unless the
Authelia cookie is present.

The shared `security-headers` middleware intentionally omits
`stsIncludeSubdomains`, so a TLS-off subdomain stays reachable.

## Storage

- **Config/state:** a PVC (default `local-path`). Name it
  `{{ .Release.Name }}-<part>`.
- **Datasets (media/books/etc.):** the operator registers datasets in Naslos
  and selects any number of them for an app. The platform injects a `datasets`
  value; a chart mounts every entry at `/datasets/<name>`:

  ```yaml
  # values.yaml
  datasets: []
  ```
  ```yaml
  # templates/app.yaml
  volumeMounts:
    {{- if .Values.datasets }}
    {{- range .Values.datasets }}
    - { name: ds-{{ .name }}, mountPath: {{ .mountPath }} }
    {{- end }}
    {{- else }}
    - { name: data, mountPath: /data }   # legacy fallback
    {{- end }}
  volumes:
    {{- if .Values.datasets }}
    {{- range .Values.datasets }}
    - name: ds-{{ .name }}
      {{- if .claim }}
      persistentVolumeClaim:
        claimName: {{ .claim }}
      {{- else }}
      hostPath:
        path: {{ .hostPath | quote }}
        type: Directory
      {{- end }}
    {{- end }}
    {{- else }}
    - name: data
      persistentVolumeClaim:
        claimName: {{ .Values.datasetsClaim }}
    {{- end }}
  ```

  Baseline entries carry a `claim` (the API creates a PV/PVC per dataset);
  privileged entries carry a `hostPath`. The `ds-` prefix keeps the volume name
  clear of the chart's own volumes. **Never trust client input for
  `datasets`** — the API strips and re-injects it.

- **Legacy single-dataset fallback:** when no dataset is attached the chart must
  keep working with its current volume. Baseline charts fall back to
  `datasetsClaim` (default `naslos-datasets`, the static RWX PVC backed by
  `apps.datasets.hostPath`); privileged charts fall back to `hostPath` (default
  `/var/mnt`). Keep each chart's existing mount path (`/data`, `/books`,
  `/audiobooks`, `/files`, `/games`, `/downloads`, …) in the `else` branch.
- **Privileged apps** (`privileged: true`, e.g. gluetun VPN sidecars) run in
  `naslos-apps-priv`, where PSA allows `hostPath`; they may mount the dataset
  host path directly.
- Apps in `naslos-apps` can reach each other and `naslos-apps-priv`; the
  platform supplies the network policy.
- Do not declare a `hostPath` volume in a managed app chart — the pod is
  rejected with "violates PodSecurity baseline: hostPath volumes".

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

1. `python3 scripts/check-contract.py` — manifest/version/service checks plus a
   `helm template` render of every chart declaring `capabilities: [env]`; it
   must print `catalog contract: N app(s) OK`.
2. `helm lint apps/<name>` — passes.
3. `helm template <name> apps/<name>` renders; `kubectl apply --dry-run=server`
   against a cluster with the CRDs installed (optional).
4. `naslos-app.yaml` validates: name matches the folder, DNS-1123, ports in
   range, service name literal/`{{ .Release.Name }}`.
5. Install from the Naslos UI (Apps → Catalog), confirm the route, then
   uninstall and confirm it is removed.
6. For `privileged: true`, confirm the release lands in `naslos-apps-priv`.
