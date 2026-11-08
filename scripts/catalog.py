#!/usr/bin/env python3
"""Maintain direct Surge subscriptions; never download files into the repository."""
from __future__ import annotations
import argparse
import concurrent.futures
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- MODULE_LINKS_START -->'
END = '<!-- MODULE_LINKS_END -->'
SECTIONS = {'Rule', 'Script', 'URL Rewrite', 'Header Rewrite', 'Body Rewrite', 'Map Local', 'Host'}
URL_ATTRIBUTES = re.compile(r'''\b(?:script-path|data-path|jq-path|data)\s*=\s*["']?(https?://[^,\s"']+)''', re.I)
RULE_URLS = re.compile(r'^\s*(?:RULE-SET|DOMAIN-SET)\s*,\s*(https?://[^,\s]+)', re.M | re.I)


def valid_url(url: str) -> bool:
    try:
        p = urllib.parse.urlsplit(url)
        return (p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password
                and p.hostname not in {'bytevista.github.io', 'localhost', '127.0.0.1'}
                and not p.fragment)
    except ValueError:
        return False


def load_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or config.get('schema') != 2:
        raise ValueError('Expected direct-subscription schema 2')
    if config.get('policy') != {'delivery': 'direct-upstream', 'fallback': 'romeo',
                               'mirror_modules': False, 'mirror_dependencies': False,
                               'convert_modules': False, 'merge_modules': False}:
        raise ValueError('Delivery must use unmodified upstream subscriptions')
    groups, apps = config.get('groups', {}), config.get('apps', {})
    if not groups or not apps:
        raise ValueError('Groups and apps cannot be empty')
    for key, app in apps.items():
        if app.get('enabled') is False:
            if not app.get('reason'):
                raise ValueError(f'{key}: disabled app needs a reason')
            continue
        if not app.get('name') or not app.get('provider') or app.get('group') not in groups:
            raise ValueError(f'{key}: missing name, provider or group')
        url = app.get('url', '')
        if not valid_url(url):
            raise ValueError(f'{key}: invalid direct URL')
        if app.get('source') not in {'upstream', 'romeo'}:
            raise ValueError(f'{key}: invalid source type')
        is_romeo = '/ifflagged/Romeo/' in url
        if is_romeo != (app['source'] == 'romeo'):
            raise ValueError(f'{key}: source type does not match URL')
        if 'bytevista/' in url.lower():
            raise ValueError(f'{key}: subscriptions must point upstream')
        fallback = app.get('fallback_url')
        if fallback and (not valid_url(fallback) or '/ifflagged/Romeo/' not in fallback):
            raise ValueError(f'{key}: fallback must point to Romeo')
    return config


def escape_cell(text: str) -> str:
    return text.replace('|', '&#124;').replace('\n', ' ')


def install_link(url: str, repository: str) -> str:
    if not re.fullmatch(r'ByteVista/Surge[-_]Modules', repository):
        raise ValueError('Unexpected repository')
    return f'https://raw.githack.com/{repository}/main/install.html#url=' + urllib.parse.quote(url, safe='')


def render_catalog(config: dict, repository: str) -> str:
    lines = [START]
    for group, title in config['groups'].items():
        apps = [a for a in config['apps'].values() if a.get('enabled') is not False and a['group'] == group]
        if not apps:
            continue
        lines += ['', f'### {title}', '', '| 模块 | 来源 | 安装 | 说明 |', '|---|---|---|---|']
        for app in apps:
            source = escape_cell(app['provider']) + (' 原作者' if app['source'] == 'upstream' else ' · Romeo')
            link = install_link(app['url'], repository)
            lines.append(f"| {escape_cell(app['name'])} | {source} | [自动安装]({link}) · [上游订阅]({app['url']}) | {escape_cell(app.get('note', ''))} |")
    lines += ['', END]
    return '\n'.join(lines)


def update_readme(text: str, catalog: str) -> str:
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('README requires exactly one marker pair')
    start, end = text.index(START), text.index(END)
    if end < start:
        raise ValueError('README marker order is invalid')
    return text[:start] + catalog + text[end + len(END):]


def fetch(url: str, *, module: bool = False) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': 'Surge-Direct-Catalog/2.0'})
    with urllib.request.urlopen(request, timeout=25) as response:
        if response.status != 200 or not valid_url(response.url):
            raise ValueError('Unexpected response or redirect')
        data = response.read(2_000_001 if module else 4096)
        if not data or (module and len(data) > 2_000_000):
            raise ValueError('Empty or oversized response')
        text = data.decode('utf-8-sig', errors='replace')
        if text.lstrip().lower().startswith(('<!doctype html', '<html')):
            raise ValueError('Received HTML instead of module/resource')
        return text


def validate_module(content: str) -> None:
    section = ''
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';', '//')):
            continue
        match = re.fullmatch(r'\[([^]]+)\]', line)
        if match:
            section = match[1]
        elif section in SECTIONS:
            if 'bytevista.github.io/' in line or re.search(r'https?://(?:localhost|127\.0\.0\.1)', line):
                raise ValueError('Module still depends on a retired local/Pages service')
            # Keep checking all lines before accepting the module.
    section = ''
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';', '//')):
            continue
        match = re.fullmatch(r'\[([^]]+)\]', line)
        if match:
            section = match[1]
        elif section in SECTIONS:
            return
    raise ValueError('No active Surge rules/rewrites/scripts; MITM alone does not block ads')


def dependencies(content: str) -> set[str]:
    return set(URL_ATTRIBUTES.findall(content)) | set(RULE_URLS.findall(content))


def check_links(config: dict) -> list[str]:
    failures, resource_urls = [], set()
    apps = {k: a for k, a in config['apps'].items() if a.get('enabled') is not False}
    def check(app):
        content = fetch(app['url'], module=True)
        validate_module(content)
        return dependencies(content)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check, app): key for key, app in apps.items()}
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                resource_urls.update(future.result())
            except Exception as exc:
                failures.append(f'{key}: {exc}')
        futures = {pool.submit(fetch, url): url for url in sorted(resource_urls)}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures.append(f'{futures[future]}: {exc}')
    print(f'Checked {len(apps)} module URLs and {len(resource_urls)} runtime resource URLs.')
    return sorted(failures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/sources.yaml')
    parser.add_argument('--readme', type=Path, default=ROOT / 'README.md')
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--check', action='store_true', help='Verify README without writing')
    parser.add_argument('--check-links', action='store_true', help='Check live modules and their resources')
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if not args.repository:
            raise ValueError('Pass --repository OWNER/REPO')
        old = args.readme.read_text(encoding='utf-8')
        new = update_readme(old, render_catalog(config, args.repository))
        if args.check and old != new:
            raise ValueError('README catalog is stale; run scripts/catalog.py')
        if not args.check:
            args.readme.write_text(new, encoding='utf-8')
        if args.check_links:
            failures = check_links(config)
            if failures:
                print('\n'.join(failures), file=sys.stderr)
                return 1
        print('Direct subscription catalog OK.')
        return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
