#!/usr/bin/env python3
"""Fetch, convert, merge, and publish the selected Surge modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

import yaml


SECTION_RE = re.compile(r"^\s*\[([^\]]+)]\s*$")
METADATA_RE = re.compile(r"^#!\s*([^=]+?)\s*=\s*(.*)$")
CATEGORY_RE = re.compile(r"^#!\s*category\s*=", re.IGNORECASE)
MITM_HOST_RE = re.compile(r"^\s*hostname\s*=\s*(?:%APPEND%\s*)?(?P<hosts>.*)$", re.IGNORECASE)

RUNTIME_DEPENDENCY_PATTERNS = [
    (
        "script",
        re.compile(
            r"(?P<prefix>\bscript-path\s*=\s*[\"']?)(?P<url>https?://[^,\"'\s]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "data",
        re.compile(
            r"(?P<prefix>\bdata(?:-path)?\s*=\s*[\"']?)(?P<url>https?://[^,\"'\s]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "ruleset",
        re.compile(
            r"(?P<prefix>^\s*(?:RULE-SET|DOMAIN-SET)\s*,\s*)(?P<url>https?://[^,\s]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
]

CANONICAL_SECTION_ORDER = [
    "General",
    "Rule",
    "Host",
    "URL Rewrite",
    "Header Rewrite",
    "Body Rewrite",
    "Map Local",
    "Script",
    "MITM",
]

README_LINKS_START = "<!-- MODULE_LINKS_START -->"
README_LINKS_END = "<!-- MODULE_LINKS_END -->"


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceResult:
    source_id: str
    provider: str
    source_url: str
    output: str
    bundle: str | None
    content: str


@dataclass
class ParsedModule:
    metadata: list[tuple[str, str]]
    preamble: list[str]
    sections: OrderedDict[str, list[str]]


def log(message: str) -> None:
    print(message, flush=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise SyncError(f"Unsafe output path: {value!r}")
    return path


def request_headers(app: dict) -> dict[str, str]:
    headers = {
        "Accept": "text/plain, */*;q=0.8",
        "User-Agent": "Surge-Module-Sync/1.0",
    }
    url = str(app.get("url", ""))
    host = urllib.parse.urlsplit(url).hostname or ""
    provider = str(app.get("provider", "")).lower()
    if host in {"kelee.one", "rucu6.pages.dev"} or provider in {"kelee", "rucu6"}:
        headers["User-Agent"] = "Loon/861 CFNetwork/1496.0.7 Darwin/23.5.0"
    for key, value in (app.get("headers") or {}).items():
        headers[str(key)] = str(value)
    return headers


def fetch_bytes(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    attempts: int = 3,
    retry_delay: int = 2,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise SyncError(f"HTTP {status} from {url}")
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, SyncError) as exc:
            last_error = exc
            if attempt < attempts:
                delay = min(retry_delay * (2 ** (attempt - 1)), 30)
                host = urllib.parse.urlsplit(url).netloc or url
                log(f"Retrying {host} after {exc} (attempt {attempt + 1}/{attempts}, wait {delay}s)")
                time.sleep(delay)
    raise SyncError(f"Failed to fetch {url}: {last_error}")


def decode_text(data: bytes, url: str) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig", errors="strict")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lowered = text[:500].lower()
    if "<html" in lowered or "<!doctype html" in lowered:
        raise SyncError(f"Received HTML instead of a module from {url}")
    if text.lstrip().startswith("#!error"):
        raise SyncError(f"Converter returned an error for {url}: {text[:200]}")
    return text.rstrip() + "\n"


def validate_module(content: str, source_id: str) -> None:
    if len(content.strip()) < 16:
        raise SyncError(f"{source_id}: module is unexpectedly short")
    if not any(SECTION_RE.match(line) for line in content.splitlines()):
        raise SyncError(f"{source_id}: no Surge module section was found")
    if "http://127.0.0.1:9100" in content or "http://localhost:9100" in content:
        # This is allowed only temporarily; dependency mirroring removes it later.
        return


def set_module_category(content: str, category: str = "AdBlock") -> str:
    if not category or "\n" in category or "\r" in category:
        raise SyncError(f"Invalid module category: {category!r}")
    lines = content.rstrip().splitlines()
    first_section = next((index for index, line in enumerate(lines) if SECTION_RE.match(line)), len(lines))
    category_indexes = [
        index for index, line in enumerate(lines[:first_section]) if CATEGORY_RE.match(line)
    ]
    if category_indexes:
        lines[category_indexes[0]] = f"#!category={category}"
        for index in reversed(category_indexes[1:]):
            del lines[index]
    else:
        name_index = next(
            (
                index
                for index, line in enumerate(lines[:first_section])
                if line.lower().startswith("#!name=")
            ),
            None,
        )
        lines.insert((name_index + 1) if name_index is not None else 0, f"#!category={category}")
    return "\n".join(lines).rstrip() + "\n"


def converter_url(base_url: str, source_url: str, source_id: str, app: dict) -> str:
    format_map = {
        "loon": "loon-plugin",
        "quantumult_x": "qx-rewrite",
        "qx": "qx-rewrite",
    }
    source_format = str(app.get("format", ""))
    try:
        source_type = format_map[source_format]
    except KeyError as exc:
        raise SyncError(f"{source_id}: unsupported conversion format {source_format!r}") from exc

    header_lines = "\n".join(f"{key}:{value}" for key, value in request_headers(app).items())
    query = urllib.parse.urlencode(
        {
            "type": source_type,
            "target": "surge-module",
            "jqEnabled": "true",
            "jsc": "true",
            "noNtf": "true",
            "nocache": "true",
            "headers": header_lines,
        },
        quote_via=urllib.parse.quote,
    )
    clean_base = base_url.rstrip("/")
    filename = urllib.parse.quote(f"{source_id}.sgmodule", safe="._-")
    # Script-Hub expects the source URL literally between its start/end sentinels.
    safe_source = source_url.replace(" ", "%20")
    return f"{clean_base}/file/_start_/{safe_source}/_end_/{filename}?{query}"


def fetch_source(source_id: str, app: dict, script_hub: str) -> str:
    mode = app.get("mode")
    url = str(app.get("url", ""))
    if not url:
        raise SyncError(f"{source_id}: enabled source has no URL")
    if mode == "direct":
        data = fetch_bytes(url, request_headers(app))
    elif mode == "convert":
        url = converter_url(script_hub, url, source_id, app)
        data = fetch_bytes(
            url,
            {"User-Agent": "Surge-Module-Sync/1.0"},
            timeout=120,
            attempts=5,
            retry_delay=6,
        )
    else:
        raise SyncError(f"{source_id}: unsupported mode {mode!r}")
    content = decode_text(data, url)
    validate_module(content, source_id)
    return content


def resolve_output(source_id: str, app: dict, bundles: dict) -> tuple[str, str | None]:
    module = str(app.get("module", ""))
    if not module:
        raise SyncError(f"{source_id}: missing module output")

    explicit_bundle = app.get("bundle")
    if explicit_bundle:
        if explicit_bundle not in bundles:
            raise SyncError(f"{source_id}: unknown bundle {explicit_bundle!r}")
        return str(bundles[explicit_bundle]["module"]), str(explicit_bundle)

    for bundle_id, bundle in bundles.items():
        if module == str(bundle.get("module")):
            return module, str(bundle_id)
        for prefix in bundle.get("source_prefixes") or []:
            if module.startswith(str(prefix)):
                return str(bundle["module"]), str(bundle_id)
    return module, None


def parse_module(content: str) -> ParsedModule:
    metadata: list[tuple[str, str]] = []
    preamble: list[str] = []
    sections: OrderedDict[str, list[str]] = OrderedDict()
    current: str | None = None

    for line in content.splitlines():
        section_match = SECTION_RE.match(line)
        if section_match:
            current = section_match.group(1).strip()
            sections.setdefault(current, [])
            continue
        if current is None:
            metadata_match = METADATA_RE.match(line)
            if metadata_match:
                metadata.append((metadata_match.group(1).strip(), metadata_match.group(2)))
            else:
                preamble.append(line)
        else:
            sections[current].append(line)
    return ParsedModule(metadata=metadata, preamble=preamble, sections=sections)


def split_top_level_commas(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def merge_arguments(parsed_sources: list[tuple[SourceResult, ParsedModule]]) -> tuple[str | None, str | None]:
    arguments: OrderedDict[str, str] = OrderedDict()
    descriptions: list[str] = []
    for source, parsed in parsed_sources:
        for key, value in parsed.metadata:
            normalized = key.lower().replace(" ", "")
            if normalized == "arguments":
                for token in split_top_level_commas(value):
                    argument_name = token.split(":", 1)[0].strip()
                    existing = arguments.get(argument_name)
                    if existing is not None and existing != token:
                        raise SyncError(
                            f"Conflicting argument {argument_name!r} in bundle {source.output}: "
                            f"{existing!r} vs {token!r}"
                        )
                    arguments.setdefault(argument_name, token)
            elif normalized == "arguments-desc" and value.strip():
                descriptions.append(f"【{source.source_id}】{value.strip()}")
    argument_line = ",".join(arguments.values()) if arguments else None
    description_line = r"\n\n".join(descriptions) if descriptions else None
    return argument_line, description_line


def unique_active_lines(lines: Iterable[str], seen: set[str]) -> list[str]:
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";", "//")):
            output.append(line)
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        output.append(line)
    while output and not output[-1].strip():
        output.pop()
    return output


def merge_bundle(results: list[SourceResult], bundle_config: dict) -> str:
    parsed_sources = [(source, parse_module(source.content)) for source in results]
    argument_line, argument_description = merge_arguments(parsed_sources)

    name = str(bundle_config.get("description") or PurePosixPath(results[0].output).stem)
    output: list[str] = [
        f"#!name={name}",
        "#!desc=由 GitHub Actions 自动同步；各成员完整取自已选择的上游",
        "#!author=Upstream authors; automated assembly",
    ]
    if argument_line:
        output.append(f"#!arguments={argument_line}")
    if argument_description:
        output.append(f"#!arguments-desc={argument_description}")
    output.extend(["", "# Sources:"])
    for source in results:
        output.append(f"# - {source.source_id} | {source.provider} | {source.source_url}")

    encountered_sections: list[str] = []
    for _, parsed in parsed_sources:
        for section in parsed.sections:
            if section not in encountered_sections:
                encountered_sections.append(section)
    section_order = [section for section in CANONICAL_SECTION_ORDER if section in encountered_sections]
    section_order.extend(section for section in encountered_sections if section not in section_order)

    for section in section_order:
        output.extend(["", f"[{section}]"])
        seen: set[str] = set()
        mitm_hosts: list[str] = []
        mitm_seen: set[str] = set()
        for source, parsed in parsed_sources:
            source_lines = parsed.sections.get(section)
            if source_lines is None:
                continue
            ordinary_lines: list[str] = []
            for line in source_lines:
                host_match = MITM_HOST_RE.match(line) if section.lower() == "mitm" else None
                if not host_match:
                    ordinary_lines.append(line)
                    continue
                for host in host_match.group("hosts").split(","):
                    host = host.strip()
                    if host and host not in mitm_seen:
                        mitm_seen.add(host)
                        mitm_hosts.append(host)
            merged_lines = unique_active_lines(ordinary_lines, seen)
            if merged_lines:
                output.extend(["", f"# --- {source.source_id} | {source.provider} ---"])
                output.extend(merged_lines)
        if section.lower() == "mitm" and mitm_hosts:
            output.extend(["", f"hostname = %APPEND% {', '.join(mitm_hosts)}"])

    return "\n".join(output).rstrip() + "\n"


def raw_base_from_environment() -> str | None:
    explicit = os.environ.get("MODULE_RAW_BASE")
    if explicit:
        return explicit.rstrip("/")
    repository = os.environ.get("GITHUB_REPOSITORY")
    ref = os.environ.get("GITHUB_REF_NAME")
    if repository and ref:
        quoted_ref = urllib.parse.quote(ref, safe="")
        return f"https://raw.githubusercontent.com/{repository}/{quoted_ref}/Modules/Surge"
    return None


def dependency_target(source_id: str, url: str, kind: str) -> PurePosixPath:
    url_path = urllib.parse.urlsplit(url).path
    suffix = Path(url_path).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = {
            "script": ".js",
            "data": ".json",
            "ruleset": ".list",
        }.get(kind, ".bin")
    original_stem = Path(urllib.parse.unquote(url_path)).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", original_stem).strip("._-")[:60]
    if not safe_stem:
        safe_stem = kind
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    safe_source_id = re.sub(r"[^A-Za-z0-9._-]+", "_", source_id).strip("._-")
    if not safe_source_id:
        raise SyncError(f"Unsafe source id for dependency storage: {source_id!r}")
    return PurePosixPath("_resources") / safe_source_id / f"{safe_stem}-{digest}{suffix}"


def mirror_dependencies(
    source: SourceResult,
    app: dict,
    raw_base: str | None,
    generated: dict[PurePosixPath, bytes],
    dependency_cache: dict[str, str],
) -> SourceResult:
    if not raw_base:
        for _, pattern in RUNTIME_DEPENDENCY_PATTERNS:
            if pattern.search(source.content):
                raise SyncError(f"{source.source_id}: runtime dependencies require MODULE_RAW_BASE")
        return source

    normalized_raw_base = raw_base.rstrip("/")

    def replacement(kind: str):
        def replace(match: re.Match[str]) -> str:
            url = match.group("url")
            if url.startswith(f"{normalized_raw_base}/_resources/"):
                return match.group(0)
            if url in dependency_cache:
                return match.group("prefix") + dependency_cache[url]

            data = fetch_bytes(url, request_headers(app), timeout=120)
            if len(data) < 1:
                raise SyncError(f"{source.source_id}: empty {kind} dependency from {url}")
            lowered = data[:500].lstrip().lower()
            if b"<html" in lowered or b"<!doctype html" in lowered:
                raise SyncError(f"{source.source_id}: received HTML for {kind} dependency from {url}")

            target = dependency_target(source.source_id, url, kind)
            generated[target] = data
            public_url = f"{normalized_raw_base}/{urllib.parse.quote(str(target), safe='/._-')}"
            dependency_cache[url] = public_url
            return match.group("prefix") + public_url

        return replace

    updated = source.content
    for kind, pattern in RUNTIME_DEPENDENCY_PATTERNS:
        updated = pattern.sub(replacement(kind), updated)

    for kind, pattern in RUNTIME_DEPENDENCY_PATTERNS:
        for match in pattern.finditer(updated):
            url = match.group("url")
            if not url.startswith(f"{normalized_raw_base}/_resources/"):
                raise SyncError(f"{source.source_id}: external {kind} dependency remains: {url}")

    return SourceResult(
        source_id=source.source_id,
        provider=source.provider,
        source_url=source.source_url,
        output=source.output,
        bundle=source.bundle,
        content=updated,
    )


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    os.replace(temporary, path)


def update_readme_links(
    readme_path: Path,
    raw_base: str,
    generated: dict[PurePosixPath, bytes],
) -> None:
    module_paths = sorted(
        (path for path in generated if path.suffix == ".sgmodule"),
        key=lambda path: str(path).lower(),
    )
    if not module_paths:
        raise SyncError("Cannot update README because no modules were generated")
    nested = [str(path) for path in module_paths if len(path.parts) != 1]
    if nested:
        raise SyncError(f"Final modules must share one flat directory: {', '.join(nested)}")

    readme = readme_path.read_text(encoding="utf-8")
    if readme.count(README_LINKS_START) != 1 or readme.count(README_LINKS_END) != 1:
        raise SyncError("README must contain exactly one generated module-links marker pair")
    start = readme.index(README_LINKS_START)
    end = readme.index(README_LINKS_END)
    if end < start:
        raise SyncError("README module-links markers are out of order")

    links = []
    for path in module_paths:
        encoded_path = urllib.parse.quote(str(path), safe="/._-")
        links.append(f"- [{path.name}]({raw_base.rstrip('/')}/{encoded_path})")
    generated_block = README_LINKS_START + "\n" + "\n".join(links) + "\n" + README_LINKS_END
    updated = readme[:start] + generated_block + readme[end + len(README_LINKS_END) :]
    atomic_write(readme_path, updated.encode("utf-8"))


def load_previous_generated_files(output_root: Path) -> set[PurePosixPath]:
    manifest_path = output_root / ".generated-manifest.json"
    if not manifest_path.exists():
        return set()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {safe_relative_path(item) for item in manifest.get("generated_files", [])}
    except (OSError, ValueError, TypeError) as exc:
        raise SyncError(f"Cannot read the previous generated manifest: {exc}") from exc


def publish(output_root: Path, generated: dict[PurePosixPath, bytes], sources: list[SourceResult]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    previous_files = load_previous_generated_files(output_root)
    current_files = set(generated)

    for stale in sorted(previous_files - current_files, key=str):
        stale_path = output_root.joinpath(*stale.parts)
        if stale_path.is_file():
            stale_path.unlink()

    for relative, data in sorted(generated.items(), key=lambda item: str(item[0])):
        atomic_write(output_root.joinpath(*relative.parts), data)

    manifest = {
        "schema": 1,
        "generated_files": sorted(str(path) for path in current_files),
        "outputs": {
            str(path): hashlib.sha256(data).hexdigest()
            for path, data in sorted(generated.items(), key=lambda item: str(item[0]))
        },
        "sources": {
            source.source_id: {
                "provider": source.provider,
                "url": source.source_url,
                "output": source.output,
                "sha256": sha256_text(source.content),
            }
            for source in sources
        },
    }
    atomic_write(
        output_root / ".generated-manifest.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def build(
    config_path: Path,
    output_root: Path,
    script_hub: str,
    raw_base: str | None,
    readme_path: Path | None = None,
) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema") != 1:
        raise SyncError("Unsupported or missing configuration schema")
    apps = config.get("apps") or {}
    bundles = config.get("bundles") or {}
    final_category = str((config.get("policy") or {}).get("module_category", "AdBlock"))
    if not isinstance(apps, dict) or not isinstance(bundles, dict):
        raise SyncError("apps and bundles must be mappings")

    results: list[SourceResult] = []
    generated: dict[PurePosixPath, bytes] = {}
    dependency_cache: dict[str, str] = {}

    enabled = [(source_id, app) for source_id, app in apps.items() if app.get("mode") != "disabled"]
    log(f"Enabled sources: {len(enabled)}")
    for index, (source_id, app) in enumerate(enabled, start=1):
        output, bundle = resolve_output(source_id, app, bundles)
        log(f"[{index:02d}/{len(enabled):02d}] {source_id}: {app.get('mode')} -> {output}")
        content = fetch_source(source_id, app, script_hub)
        source = SourceResult(
            source_id=source_id,
            provider=str(app.get("provider", "unknown")),
            source_url=str(app.get("url")),
            output=output,
            bundle=bundle,
            content=content,
        )
        source = mirror_dependencies(source, app, raw_base, generated, dependency_cache)
        if "http://127.0.0.1:9100" in source.content or "http://localhost:9100" in source.content:
            raise SyncError(f"{source_id}: an unreachable local Script-Hub dependency remains")
        results.append(source)

    grouped: OrderedDict[str, list[SourceResult]] = OrderedDict()
    for source in results:
        grouped.setdefault(source.output, []).append(source)

    for output_name, members in grouped.items():
        output_path = safe_relative_path(output_name)
        if len(output_path.parts) != 1:
            raise SyncError(f"Final module must be in the shared output directory: {output_name}")
        bundle_id = members[0].bundle
        force_bundle = bool(bundle_id and not bundles[bundle_id].get("publish_individual_modules", True))
        if len(members) == 1 and not force_bundle:
            content = members[0].content
        else:
            if not bundle_id:
                raise SyncError(f"Multiple sources target {output_name}, but no bundle is configured")
            content = merge_bundle(members, bundles[bundle_id])
        content = set_module_category(content, final_category)
        validate_module(content, output_name)
        generated[output_path] = content.encode("utf-8")

    publish(output_root, generated, results)
    if readme_path:
        if not raw_base:
            raise SyncError("Cannot update README links without MODULE_RAW_BASE")
        update_readme_links(readme_path, raw_base, generated)
    log(f"Published {len(grouped)} modules and {len(generated) - len(grouped)} mirrored resources")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/sources.yaml"))
    parser.add_argument("--output", type=Path, default=Path("Modules/Surge"))
    parser.add_argument("--script-hub", default=os.environ.get("SCRIPT_HUB_URL", "http://127.0.0.1:9100"))
    parser.add_argument("--raw-base", default=raw_base_from_environment())
    parser.add_argument("--readme", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        build(args.config, args.output, args.script_hub, args.raw_base, args.readme)
    except (SyncError, OSError, UnicodeError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
