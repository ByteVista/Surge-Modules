#!/usr/bin/env python3
"""Build the public GitHub Pages artifact from generated Surge files."""

from __future__ import annotations

import argparse
import html
import shutil
import urllib.parse
from pathlib import Path


class PagesBuildError(RuntimeError):
    pass


def build_pages(modules_root: Path, readme_path: Path, site_root: Path) -> None:
    modules = sorted(modules_root.glob("*.sgmodule"), key=lambda path: path.name.lower())
    if not modules:
        raise PagesBuildError(f"No Surge modules found in {modules_root}")
    if not readme_path.is_file():
        raise PagesBuildError(f"README not found: {readme_path}")

    if site_root.exists():
        shutil.rmtree(site_root)
    public_modules = site_root / "Modules" / "Surge"
    public_modules.mkdir(parents=True)

    for module in modules:
        shutil.copy2(module, public_modules / module.name)

    resources = modules_root / "_resources"
    if resources.is_dir():
        shutil.copytree(resources, public_modules / "_resources")

    shutil.copy2(readme_path, site_root / "README.md")
    (site_root / ".nojekyll").touch()

    links = []
    for module in modules:
        href = "Modules/Surge/" + urllib.parse.quote(module.name, safe="._-")
        label = html.escape(module.name)
        links.append(f'        <li><a href="{href}">{label}</a></li>')

    index = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Surge 模块</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { max-width: 760px; margin: 48px auto; padding: 0 20px; line-height: 1.6; }
    h1 { margin-bottom: 0; }
    p { color: #777; }
    ul { padding-left: 1.4rem; }
    li { margin: .55rem 0; }
    a { overflow-wrap: anywhere; }
  </style>
</head>
<body>
  <main>
    <h1>Surge 模块</h1>
    <p>以下链接由 GitHub Actions 自动同步和发布，可直接用于 Surge 从 URL 安装模块。</p>
    <ul>
""" + "\n".join(links) + """
    </ul>
  </main>
</body>
</html>
"""
    (site_root / "index.html").write_text(index, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules", type=Path, default=Path("Modules/Surge"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--site", type=Path, default=Path("_site"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        build_pages(args.modules, args.readme, args.site)
    except (OSError, PagesBuildError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
