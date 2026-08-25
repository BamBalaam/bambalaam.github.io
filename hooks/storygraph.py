"""MkDocs hook: replace <!-- storygraph --> with a shelf of currently-reading books.

Fetches the public "currently reading" page for a StoryGraph user and renders each
book as a vertical card (cover, title, link to the book page) laid out horizontally.

Configuration lives under ``extra.storygraph`` in mkdocs.yml::

    extra:
      storygraph:
        username: bambalaam          # required
        base_url: https://app.thestorygraph.com   # optional
        empty_message: "Nothing on the nightstand right now."  # optional

The page sits behind an intermittent Cloudflare challenge, so any fetch/parse
failure is logged as a warning and rendered as a graceful fallback rather than
breaking the build.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any

log = logging.getLogger("mkdocs.hooks.storygraph")

PLACEHOLDER = "<!-- storygraph -->"
DEFAULT_BASE_URL = "https://app.thestorygraph.com"
DEFAULT_EMPTY_MESSAGE = "No books to show right now."
DEFAULT_CACHE_TTL = 3600  # seconds; StoryGraph rate-limits repeated build-time fetches
TIMEOUT = 20

# A browser-like UA gets past the intermittent Cloudflare managed challenge that
# rejects the default urllib agent.
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_BOOK_PATH_RE = re.compile(r"^/books/[0-9a-fA-F-]+$")
_ALT_BY_AUTHOR_RE = re.compile(r"\s+by\s+.+$")


class _CurrentlyReadingParser(HTMLParser):
    """Extract cover, title and book path from each ``.book-pane`` on the page.

    Each top-level ``.book-pane`` div carries a ``data-book-id`` and contains a
    cover ``<a href="/books/ID"><img></a>`` followed by an ``<h3>`` whose first
    ``/books/`` anchor holds the title. Nested/mobile duplicates share the same
    book id, so we only open one record per pane and keep the first values seen.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.books: list[dict[str, str]] = []
        self._depth = 0
        self._book: dict[str, Any] | None = None
        self._book_depth: int | None = None
        self._in_h3 = 0
        self._in_title_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}

        if tag == "div":
            self._depth += 1
            if (
                self._book is None
                and "book-pane" in a.get("class", "").split()
                and a.get("data-book-id")
            ):
                self._book = {
                    "cover": None,
                    "title": None,
                    "path": None,
                    "alt": None,
                }
                self._book_depth = self._depth
            return

        if self._book is None:
            return

        if tag == "img" and self._book["cover"] is None:
            if a.get("src"):
                self._book["cover"] = a["src"]
            if a.get("alt") and not self._book["alt"]:
                self._book["alt"] = a["alt"]
        elif tag == "a":
            href = a.get("href", "")
            if self._book["path"] is None and _BOOK_PATH_RE.match(href):
                self._book["path"] = href
            if self._in_h3 and self._book["title"] is None and _BOOK_PATH_RE.match(href):
                self._in_title_anchor = True
        elif tag == "h3":
            self._in_h3 += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_title_anchor = False
        elif tag == "h3" and self._in_h3:
            self._in_h3 -= 1
        elif tag == "div":
            if self._book is not None and self._depth == self._book_depth:
                self._finalize_book()
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title_anchor and self._book is not None:
            text = data.strip()
            if text:
                self._book["title"] = ((self._book["title"] or "") + " " + text).strip()

    def _finalize_book(self) -> None:
        book = self._book
        self._book = None
        self._book_depth = None
        if book is None:
            return
        if not book["title"] and book["alt"]:
            book["title"] = _ALT_BY_AUTHOR_RE.sub("", book["alt"]).strip()
        # A book is only usable if we can both name it and link to it.
        if book["cover"] and book["title"] and book["path"]:
            self.books.append(
                {
                    "cover": book["cover"],
                    "title": book["title"],
                    "path": book["path"],
                }
            )


def _fetch(url: str) -> str | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("storygraph: could not fetch %s (%s)", url, exc)
        return None

    if "book-pane" not in body:
        # Almost certainly the Cloudflare "Just a moment..." challenge page.
        log.warning("storygraph: no books found in response from %s (blocked?)", url)
        return None
    return body


def _cache_path(config: Any, username: str) -> str:
    project_root = os.path.dirname(config.get("config_file_path") or os.getcwd())
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", username)
    return os.path.join(project_root, ".cache", f"storygraph-{safe}.json")


def _read_cache(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("books"), list):
        return data
    return None


def _write_cache(path: str, books: list[dict[str, str]]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"fetched_at": time.time(), "books": books}, fh)
    except OSError as exc:
        log.warning("storygraph: could not write cache %s (%s)", path, exc)


def _get_books(config: Any, url: str, username: str, cache_ttl: int) -> list[dict[str, str]]:
    """Return currently-reading books, preferring a fresh cache and falling back
    to a stale cache when the live fetch is blocked."""
    cache_file = _cache_path(config, username)
    cached = _read_cache(cache_file)

    if cached is not None and (time.time() - cached.get("fetched_at", 0)) < cache_ttl:
        return cached["books"]

    body = _fetch(url)
    if body is not None:
        parser = _CurrentlyReadingParser()
        parser.feed(body)
        _write_cache(cache_file, parser.books)
        return parser.books

    if cached is not None:
        log.info("storygraph: using stale cache for %s (live fetch unavailable)", username)
        return cached["books"]

    return []


def _build_html(books: list[dict[str, str]], base_url: str, empty_message: str) -> str:
    if not books:
        return f'<p class="storygraph-empty">{empty_message}</p>'

    cards = []
    for book in books:
        book_url = base_url + book["path"]
        title = _escape(book["title"])
        cover = _escape(book["cover"])
        href = _escape(book_url)
        cards.append(
            f"""    <article class="storygraph-book">
      <a class="storygraph-cover" href="{href}" target="_blank" rel="noopener">
        <img src="{cover}" alt="Cover of {title}" loading="lazy">
      </a>
      <h3 class="storygraph-title">
        <a href="{href}" target="_blank" rel="noopener">{title}</a>
      </h3>
      <a class="storygraph-link" href="{href}" target="_blank" rel="noopener">View on The StoryGraph</a>
    </article>"""
        )

    return (
        '<div class="storygraph-shelf">\n'
        + "\n".join(cards)
        + "\n</div>"
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def on_page_markdown(markdown: str, *, page, config, files, **kwargs) -> str:
    if PLACEHOLDER not in markdown:
        return markdown

    settings = (config.get("extra") or {}).get("storygraph") or {}
    username = settings.get("username")
    base_url = (settings.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    empty_message = settings.get("empty_message") or DEFAULT_EMPTY_MESSAGE
    cache_ttl = settings.get("cache_ttl", DEFAULT_CACHE_TTL)

    if not username:
        log.warning("storygraph: no extra.storygraph.username configured")
        return markdown.replace(PLACEHOLDER, "", 1)

    url = f"{base_url}/currently-reading/{username}"
    books = _get_books(config, url, username, cache_ttl)
    html = _build_html(books, base_url, empty_message)

    return markdown.replace(PLACEHOLDER, html, 1)
