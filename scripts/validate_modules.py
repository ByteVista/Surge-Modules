#!/usr/bin/env python3
"""Validate source configuration and generated Surge modules."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path, PurePosixPath

import yaml


SECTION_RE = re.compile(r"^\s*\[([^\]]+)]\s*$")
CATEGORY_RE = re.compile(r"^#!\s*category\s*=\s*(?P<value>.*)$", re.IGNORECASE)
LOCAL_REFERENCE_RE = re.compile(r"https?://(?:127\.0\.0\.1|localhost|script\.hub)(?::\d+)?/", re.IGNORECASE)
RUNTIME_DEPENDENCY_PATTERNS = [
    re.compile(r"\bscript-path\s*=\s*[\"']?(?P<url>https?://[^,\"'\s]+)", re.IGNORECASE),
    re.compile(r"\bdata(?:-path)?\s*=\s*[\"']?(?P<url>https?://[^,\"'\s]+)", re.IGNORECASE),
    re.compile(
        r"^\s*(?:RULE-SET|DOMAIN-SET)\s*,\s*(?P<url>https?://[^,\s]+)",
        re.IGNORECASE | re.MULTILINE,
    ),
]


class ValidationError(RuntimeError):
    pass


def safe_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValidationError(f"unsafe module path: {value!r}")


def validate_config(path: Path) -> tuple[dict, int]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema") != 1:
        raise ValidationError("config schema must be 1")
    if (config.get("policy") or {}).get("module_category") != "AdBlock":
        raise ValidationError("policy.module_category must be AdBlock")
    apps = config.get("apps")
    bundles = config.get("bundles")
    if not isinstance(apps, dict) or not isinstance(bundles, dict):
        raise ValidationError("apps and bundles must be mappings")

    for bundle_id, bundle in bundles.items():
        if not isinstance(bundle, dict) or not bundle.get("module"):
            raise ValidationError(f"bundle {bundle_id!r} has no output module")
        safe_path(str(bundle["module"]))

    enabled_count = 0
    for source_id, app in apps.items():
        if not isinstance(app, dict):
            raise ValidationError(f"source {source_id!r} must be a mapping")
        mode = app.get("mode")
        if mode == "disabled":
            if not app.get("reason"):
                raise ValidationError(f"disabled source {source_id!r} must include a reason")
            continue
        enabled_count += 1
        if mode not in {"direct", "convert"}:
            raise ValidationError(f"source {source_id!r} has unsupported mode {mode!r}")
        if app.get("format") not in {"surge", "loon", "quantumult_x", "qx"}:
            raise ValidationError(f"source {source_id!r} has unsupported format {app.get('format')!r}")
        if mode == "direct" and app.get("format") != "surge":
            raise ValidationError(f"direct source {source_id!r} must already be Surge format")
        if mode == "convert" and app.get("format") == "surge":
            raise ValidationError(f"source {source_id!r} does not need conversion")
        url = str(app.get("url", ""))
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValidationError(f"source {source_id!r} must use an HTTPS URL")
        safe_path(str(app.get("module", "")))
        bundle_id = app.get("bundle")
        if bundle_id and bundle_id not in bundles:
            raise ValidationError(f"source {source_id!r} references unknown bundle {bundle_id!r}")
    return config, enabled_count


def validate_module(path: Path) -> None:
    content = path.read_text(encoding="utf-8-sig")
    if len(content.strip()) < 16:
        raise ValidationError(f"{path}: module is unexpectedly short")
    lowered = content[:500].lower()
    if "<html" in lowered or "<!doctype html" in lowered:
        raise ValidationError(f"{path}: contains HTML instead of a module")
    if not any(SECTION_RE.match(line) for line in content.splitlines()):
        raise ValidationError(f"{path}: contains no module section")
    local_reference = LOCAL_REFERENCE_RE.search(content)
    if local_reference:
        raise ValidationError(f"{path}: contains unreachable local reference {local_reference.group(0)!r}")
    if "#!error=" in content:
        raise ValidationError(f"{path}: contains a Script-Hub error marker")
    categories = [match.group("value").strip() for line in content.splitlines() if (match := CATEGORY_RE.match(line))]
    if categories != ["AdBlock"]:
        raise ValidationError(f"{path}: category must be exactly AdBlock")
    for pattern in RUNTIME_DEPENDENCY_PATTERNS:
        for match in pattern.finditer(content):
            dependency_url = match.group("url")
            if "/Modules/Surge/_resources/" not in dependency_url:
                raise ValidationError(f"{path}: contains an external runtime dependency: {dependency_url}")


def validate_generated(output_root: Path, expected_sources: int) -> tuple[int, int]:
    manifest_path = output_root / ".generated-manifest.json"
    if not manifest_path.exists():
        raise ValidationError(f"missing generated manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise ValidationError("unsupported generated manifest schema")
    if len(manifest.get("sources", {})) != expected_sources:
        raise ValidationError("generated manifest does not include every enabled source")

    generated_files = manifest.get("generated_files") or []
    modules = 0
    scripts = 0
    for relative in generated_files:
        safe_path(str(relative))
        path = output_root.joinpath(*PurePosixPath(relative).parts)
        if not path.is_file():
            raise ValidationError(f"manifest references a missing file: {relative}")
        if path.suffix == ".sgmodule":
            if len(PurePosixPath(relative).parts) != 1:
                raise ValidationError(f"Surge modules must share one flat directory: {relative}")
            validate_module(path)
            modules += 1
        elif PurePosixPath(relative).parts[0] == "_resources":
            data = path.read_bytes()
            if not data:
                raise ValidationError(f"{path}: mirrored resource is empty")
            lowered = data[:500].lstrip().lower()
            if b"<html" in lowered or b"<!doctype html" in lowered:
                raise ValidationError(f"{path}: mirrored resource contains HTML")
            scripts += 1
        else:
            raise ValidationError(f"unexpected generated file type: {relative}")
    if modules == 0:
        raise ValidationError("no Surge modules were generated")
    return modules, scripts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/sources.yaml"))
    parser.add_argument("--output", type=Path, default=Path("Modules/Surge"))
    parser.add_argument("--config-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        _, enabled_count = validate_config(args.config)
        if args.config_only:
            print(f"Configuration OK: {enabled_count} enabled sources")
        else:
            modules, scripts = validate_generated(args.output, enabled_count)
            print(f"Validation OK: {enabled_count} sources, {modules} modules, {scripts} mirrored resources")
    except (OSError, ValueError, TypeError, yaml.YAMLError, ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
