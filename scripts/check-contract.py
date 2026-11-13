#!/usr/bin/env python3
"""Static contract checks for the Naslos app catalog.

Runs without cluster access. When a manifest declares `capabilities: [env]` and
`helm` is installed, it also renders the chart and checks the environment
Secret wiring (the `envFrom` reference and the pod annotation):

    python3 scripts/check-contract.py

It enforces the parts of README.md's contract that are visible in the manifests:
folder = chart = app name, chart/manifest version parity, DNS-1123 names, valid
service names and ports, the exposure safety rule, and the env capability.

Exit code 0 = clean, 1 = contract errors.
"""

from __future__ import annotations

import glob
import re
import shutil
import subprocess
import sys

import yaml

DNS1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
RELEASE_NAME = "{{ .Release.Name }}"
ENV_SECRET_PREFIX = "naslos-env-"
ENV_CHECKSUM_ANNOTATION = "naslos.io/env-checksum"
WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet")


def load(path: str):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def is_dns1123_label(value: str) -> bool:
    return isinstance(value, str) and len(value) <= 63 and bool(DNS1123.match(value))


def check_service(service: dict) -> list[str]:
    errors = []
    name = service.get("name", "")
    if name != RELEASE_NAME and not is_dns1123_label(name):
        errors.append(f"service name {name!r} is neither a literal nor {RELEASE_NAME}")
    port = service.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        errors.append(f"service port {port!r} is not 1..65535")
    return errors


def check_env_render(folder: str) -> list[str]:
    """Render an env-capable chart and verify the platform Secret wiring."""
    helm = shutil.which("helm")
    if not helm:
        print(f"warning: helm not found; skipping env render check for {folder}", file=sys.stderr)
        return []

    try:
        rendered = subprocess.run(
            [helm, "template", folder, f"apps/{folder}", "-n", "naslos-app-1"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip().splitlines()
        return [f"{folder}: helm template failed: {detail[-1] if detail else exc.returncode}"]

    errors: list[str] = []
    secret_name = f"{ENV_SECRET_PREFIX}{folder}"
    wired = False
    try:
        documents = [doc for doc in yaml.safe_load_all(rendered) if doc]
    except yaml.YAMLError as exc:
        return [f"{folder}: rendered output is not valid YAML: {exc}"]

    for document in documents:
        if document.get("kind") not in WORKLOAD_KINDS:
            continue
        template = (document.get("spec") or {}).get("template") or {}
        annotations = (template.get("metadata") or {}).get("annotations") or {}
        containers = (template.get("spec") or {}).get("containers") or []
        for container in containers:
            for entry in container.get("envFrom") or []:
                reference = entry.get("secretRef") or {}
                if reference.get("name") != secret_name:
                    continue
                wired = True
                if reference.get("optional") is not True:
                    errors.append(
                        f"{folder}: container {container.get('name')!r} envFrom "
                        f"secretRef {secret_name!r} must be optional: true"
                    )
                if ENV_CHECKSUM_ANNOTATION not in annotations:
                    errors.append(
                        f"{folder}: workload {document.get('metadata', {}).get('name')!r} "
                        f"references {secret_name!r} but its pod template has no "
                        f"{ENV_CHECKSUM_ANNOTATION} annotation"
                    )

    if not wired:
        errors.append(
            f"{folder}: declares capabilities: [env] but no rendered container "
            f"references the {secret_name!r} Secret via envFrom"
        )
    return errors


def main() -> int:
    errors: list[str] = []
    apps = 0

    for manifest_path in sorted(glob.glob("apps/*/naslos-app.yaml")):
        folder = manifest_path.split("/")[1]
        apps += 1
        try:
            manifest = load(manifest_path)
            chart = load(f"apps/{folder}/Chart.yaml")
        except yaml.YAMLError as exc:
            errors.append(f"{folder}: cannot parse YAML: {exc}")
            continue

        name = manifest.get("name")
        if not (folder == chart.get("name") == name):
            errors.append(
                f"{folder}: folder={folder!r} chart={chart.get('name')!r} manifest={name!r}"
            )
        if not is_dns1123_label(folder):
            errors.append(f"{folder}: not a DNS-1123 label")
        if chart.get("version") != manifest.get("version"):
            errors.append(
                f"{folder}: Chart.yaml version {chart.get('version')!r} != "
                f"naslos-app.yaml version {manifest.get('version')!r}"
            )

        services = manifest.get("services") or []
        if not isinstance(services, list):
            errors.append(f"{folder}: services must be a list")
            services = []
        for service in services:
            if not isinstance(service, dict):
                errors.append(f"{folder}: service entry is not a mapping")
                continue
            errors.extend(f"{folder}: {message}" for message in check_service(service))

        exposure = manifest.get("exposure") or {}
        if not isinstance(exposure, dict):
            errors.append(f"{folder}: exposure must be a mapping")
            exposure = {}
        subdomain = exposure.get("subdomain", "")
        if subdomain and not is_dns1123_label(subdomain):
            errors.append(f"{folder}: exposure.subdomain {subdomain!r} is not a DNS-1123 label")
        auth = exposure.get("auth")
        if not isinstance(auth, bool):
            errors.append(f"{folder}: exposure.auth must be a boolean")
        if not isinstance(exposure.get("internet"), bool):
            errors.append(f"{folder}: exposure.internet must be a boolean")

        values = manifest.get("defaultValues") or {}
        if values.get("disableAuth") is True and auth is not True:
            errors.append(
                f"{folder}: disableAuth is true (no app login) but exposure.auth is not true"
            )

        capabilities = manifest.get("capabilities") or []
        if not isinstance(capabilities, list) or any(
            not isinstance(capability, str) for capability in capabilities
        ):
            errors.append(f"{folder}: capabilities must be a list of strings")
        elif "env" in capabilities:
            errors.extend(check_env_render(folder))

    if errors:
        print(f"catalog contract: {len(errors)} error(s) across {apps} app(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"catalog contract: {apps} app(s) OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
