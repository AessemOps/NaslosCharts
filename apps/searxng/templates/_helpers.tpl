{{/*
Rendered settings.yml.

Kept as a named template so the Deployment's checksum/config annotation hashes
the exact configuration: SearXNG reads settings.yml only at startup, so a
values change must roll the pod.
*/}}
{{- define "searxng.settings" -}}
use_default_settings: true
server:
  bind_address: "0.0.0.0:8080"
  secret_key: {{ .Values.secretKey | quote }}
  limiter: false
  image_proxy: false
search:
  formats: [html, json]
ui:
  # Populated by the patch-templates init container so the Preferences link can
  # be hidden unless Authelia has issued its session cookie.
  templates_path: /templates
outgoing:
  # Upper bound on each engine request.
  request_timeout: {{ .Values.search.requestTimeout }}
  # Upper bound on the whole search: engines that have not answered by now are
  # dropped. This is the knob that bounds user-perceived latency.
  max_request_timeout: {{ .Values.search.maxRequestTimeout }}
engines:
{{- range .Values.search.extraEngines }}
  - {name: {{ . | quote }}, disabled: false}
{{- end }}
{{- end }}
