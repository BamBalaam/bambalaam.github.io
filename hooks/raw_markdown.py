"""MkDocs hook: emit a raw Markdown companion for every page (LLM-friendly).

For each rendered page we copy its verbatim source ``.md`` into ``site/`` at the
page's pretty URL with a ``.md`` suffix, so agents can fetch the raw Markdown
instead of parsing HTML:

    /about/            -> /about.md
    /  (home)          -> /index.md
    /blog/             -> /blog.md
    /blog/<slug>/      -> /blog/<slug>.md

We also write an ``llms.txt`` index (see https://llmstxt.org) linking to each
``.md`` companion.

The site is hosted on GitHub Pages (static hosting), which cannot branch on the
request ``Accept`` header, so this is a URL-based approach rather than true
content negotiation. GitHub Pages does serve ``.md`` files as
``Content-Type: text/markdown``, so the companions are markdown-typed.
"""

from __future__ import annotations

import logging
import os
import shutil

log = logging.getLogger("mkdocs.hooks.raw_markdown")

# Accumulates (title, md_url) per page during the build, consumed by on_post_build.
_pages: list[tuple[str, str]] = []


def _md_relpath(url: str) -> str:
    """Map a page's pretty URL to its ``.md`` companion path (site-relative)."""
    url = url.strip("/")
    if url in ("", "."):
        return "index.md"
    return f"{url}.md"


def on_pre_build(config, **kwargs) -> None:
    _pages.clear()


def on_post_page(output: str, *, page, config, **kwargs) -> str:
    src = getattr(page.file, "abs_src_path", None)
    # Skip generated pages with no backing source file.
    if not src or not os.path.isfile(src):
        return output

    relpath = _md_relpath(page.url)
    dest = os.path.join(config["site_dir"], relpath)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src, dest)

    title = page.title or page.url or "Untitled"
    site_url = (config.get("site_url") or "").rstrip("/")
    md_url = f"{site_url}/{relpath}" if site_url else f"/{relpath}"
    _pages.append((title, md_url))

    return output


def on_post_build(config, **kwargs) -> None:
    site_name = config.get("site_name", "")
    site_description = config.get("site_description", "")

    lines: list[str] = [f"# {site_name}".rstrip(), ""]
    if site_description:
        lines += [f"> {site_description}", ""]
    lines.append("## Pages")
    lines.append("")
    for title, md_url in _pages:
        lines.append(f"- [{title}]({md_url})")
    lines.append("")

    dest = os.path.join(config["site_dir"], "llms.txt")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info("raw_markdown: wrote %d .md companions and llms.txt", len(_pages))
