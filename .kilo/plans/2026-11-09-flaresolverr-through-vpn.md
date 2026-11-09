# FlareSolverr through the Prowlarr VPN tunnel

## Problem

Adding a Cloudflare-protected indexer (1337x) to Prowlarr failed:

- The cluster's upstream DNS sinkholes blocked indexer domains, so the
  standalone FlareSolverr app resolved `1337x.to` to `::1` and returned
  `ERR_CONNECTION_REFUSED`.
- After fixing DNS, Prowlarr still rejected the indexer with
  "blocked by CloudFlare Protection" / "Empty cookies returned by FlareSolverr".

Prowlarr's FlareSolverr proxy re-issues the request itself with the cookies
returned by FlareSolverr. Cloudflare's `cf_clearance` cookie is bound to the
client IP, so the solver and Prowlarr must egress from the same address.
Prowlarr runs behind gluetun (ProtonVPN); a standalone FlareSolverr exits from
the LAN address, so the cookie is invalid on Prowlarr's retry.

## Change

- **Prowlarr chart (0.1.6)**: run FlareSolverr as a third container in the
  Prowlarr pod, sharing gluetun's network namespace. Both processes now use the
  same VPN exit IP. Allow inbound 8191 through gluetun's input firewall so the
  readiness/liveness probes work. Memory limit 2Gi (Chromium was OOMKilled at
  1Gi while solving a challenge). Point Prowlarr's FlareSolverr indexer proxy at
  `http://localhost:8191/`.
- **FlareSolverr chart (0.1.2)**: set `dnsPolicy: None` with public resolvers so
  the standalone app can resolve blocked indexer domains; raise the memory limit
  to 2Gi for consistency.

## Validation

- `helm lint apps/prowlarr apps/flaresolverr`
- Prowlarr pod reaches 3/3 Ready; Prowlarr and the sidecar report the same
  public egress IP.
- Prowlarr's FlareSolverr proxy test and the saved 1337x indexer test return 200.
- `GET /api/v1/search?query=matrix&indexerIds=1` returns results.
