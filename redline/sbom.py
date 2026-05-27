from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
import re
from typing import Any

from . import __version__


PACKAGE_NAME = "redline-ai"
CYCLONEDX_SCHEMA_URL = "https://cyclonedx.org/schema/bom-1.6.schema.json"
CYCLONEDX_SPEC_VERSION = "1.6"


def build_sbom(*, timestamp: str | None = None) -> dict[str, Any]:
    dependencies = _runtime_dependencies(PACKAGE_NAME)
    dependency_refs = [_package_ref(name, version) for name, version in dependencies]
    component = _component(PACKAGE_NAME, __version__, root=True)
    return {
        "$schema": CYCLONEDX_SCHEMA_URL,
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "version": 1,
        "metadata": {
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "redline",
                        "version": __version__,
                    }
                ]
            },
            "component": component,
        },
        "components": [
            _component(name, version)
            for name, version in dependencies
        ],
        "dependencies": [
            {
                "ref": component["bom-ref"],
                "dependsOn": dependency_refs,
            }
        ],
        "properties": [
            {"name": "redline:local_first", "value": "true"},
            {"name": "redline:telemetry", "value": "none"},
            {"name": "redline:data_egress_default", "value": "none"},
            {"name": "redline:judge_data_flow", "value": "user_supplied"},
            {"name": "redline:runtime_dependency_count", "value": str(len(dependencies))},
        ],
    }


def format_sbom_report(sbom: dict[str, Any]) -> str:
    metadata_obj = sbom.get("metadata")
    metadata_obj = metadata_obj if isinstance(metadata_obj, dict) else {}
    component = metadata_obj.get("component")
    component = component if isinstance(component, dict) else {}
    components = sbom.get("components")
    dependencies = components if isinstance(components, list) else []
    package = str(component.get("name") or PACKAGE_NAME)
    version = str(component.get("version") or __version__)
    spec = str(sbom.get("specVersion") or CYCLONEDX_SPEC_VERSION)
    lines = [
        "redline sbom",
        "",
        f"Format:                CycloneDX {spec}",
        f"Package:               {package} {version}",
        f"Runtime dependencies:  {len(dependencies)}",
        "Telemetry:             none",
        "Default data egress:   none",
        "Judge data flow:       user-supplied command only",
        "Local-first:           yes",
    ]
    if dependencies:
        lines.extend(["", "Dependencies:"])
        for dependency in dependencies:
            if isinstance(dependency, dict):
                dependency_name = str(dependency.get("name") or "")
                dependency_version = str(dependency.get("version") or "").strip()
                suffix = f" {dependency_version}" if dependency_version else ""
                lines.append(f"- {dependency_name}{suffix}")
    lines.extend(
        [
            "",
            "Next:",
            "- Publish this SBOM with release artifacts or attach it to internal review evidence.",
            "- Rebuild from the tagged commit before publishing a public release.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _runtime_dependencies(package_name: str) -> list[tuple[str, str]]:
    try:
        requirements = metadata.requires(package_name) or []
    except metadata.PackageNotFoundError:
        requirements = []
    dependencies: list[tuple[str, str]] = []
    seen: set[str] = set()
    for requirement in requirements:
        if "extra ==" in requirement:
            continue
        name = _requirement_name(requirement)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        dependencies.append((name, _installed_version(name)))
    return sorted(dependencies, key=lambda item: item[0].lower())


def _component(name: str, version: str, *, root: bool = False) -> dict[str, Any]:
    component: dict[str, Any] = {
        "type": "application" if root else "library",
        "bom-ref": _package_ref(name, version),
        "name": name,
        "purl": _package_ref(name, version),
    }
    if version:
        component["version"] = version
    if root:
        component["licenses"] = [{"license": {"id": "MIT"}}]
    return component


def _package_ref(name: str, version: str) -> str:
    normalized = name.lower().replace("_", "-")
    if version:
        return f"pkg:pypi/{normalized}@{version}"
    return f"pkg:pypi/{normalized}"


def _requirement_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    return match.group(1) if match else ""


def _installed_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return ""
