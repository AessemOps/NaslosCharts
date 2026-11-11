# Prowlarr exposure default (2026-11-11)

Remediation of `AUD-2611-N-2` from
`Naslos-Linux/docs/AUDIT-2026-11-11.md`.

## Problem

`apps/prowlarr/naslos-app.yaml` shipped `disableAuth: true` (the chart sets
`PROWLARR__AUTH__METHOD=External`, so Prowlarr trusts Authelia's `Remote-User`
and has no login of its own) **and** `exposure.auth: false`. Accepting the
install defaults therefore published the full Prowlarr admin UI on a public
hostname with neither Authelia nor an app login. Radarr and Sonarr have the same
`disableAuth` default but already shipped `auth: true`.

## Change

- Prowlarr `exposure.auth: true` by default. Turning Authelia off remains
  possible, but it is now an explicit opt-in and the install UI shows the
  existing red "exposed without full protection" confirmation.
- `scripts/check-contract.py`: a static catalog check (folder = chart = manifest
  name, version parity, DNS-1123 names/subdomains, service name/port, and
  `disableAuth: true` ⇒ `exposure.auth: true`).
- `README.md`: the rule is now part of the hard contract, the exposure table and
  the testing checklist; the sample exposure block no longer shows `auth: false`
  for a chart that has no login.

## Verification

- Failing before: run the script against `origin/main`'s Prowlarr manifest →
  `prowlarr: disableAuth is true ... but exposure.auth is not true` (exit 1).
- After: `python3 scripts/check-contract.py` → `33 app(s) OK`.
- `helm lint apps/prowlarr` passes; `helm template` renders the route with the
  Authelia middleware.

## Out of scope (tracked in the Naslos-Linux remediation plan)

The UI still lets an operator turn Authelia off for a `disableAuth` app after
the install. The catalog default is now safe; a hard cross-check in the install
form is a separate UI change (`R2.10` in the remediation plan).
