"""
Changelog MkDocs hook: track blog article revisions easily

Drop a changelog file next to any blog post (default: changelog.md).
The hook:
  1. Prevents the blog plugin from treating it as a blog post.
  2. Serves it at /<blog_dir>/<slug>/<changelog_slug>/ alongside the post.
  3. Injects a link into the blog-post sidebar nav directly under the date(s),
     with no template override file required.

Configuration is possible in mkdocs.yml.
All keys are optional, displayed below are the defaults:

  extra:
    changelogs:
      filename:  changelog.md       # source file name to look for
      nav_label: Changelog          # link text in the sidebar
      nav_icon:  material/history   # Material icon (path under .icons/, no .svg)
"""

from __future__ import annotations

import os

import yaml
from mkdocs.plugins import event_priority
from mkdocs.structure.files import InclusionLevel

# ── default configuration ──────────────────────────────────────────────────────

_DEFAULTS: dict[str, str] = {
    "filename": "changelog.md",
    "nav_label": "Changelog",
    "nav_icon": "material/history",
}
_cfg: dict[str, str] = dict(_DEFAULTS)

# ── runtime state ──────────────────────────────────────────────────────────────

# Maps post directory name → site-root-relative URL of its changelog page.
_changelog_map: dict[str, str] = {}

# Normalised path to the blog posts directory (e.g. "blog/posts" on Linux).
_POSTS_DIR = os.path.normpath("blog/posts")

# ── Jinja2 fragment injected into blog-post.html ──────────────────────────────
# $ICON is replaced at on_env time with the resolved icon path.
_FRAGMENT_TMPL = (
    '                    {%- if changelog_url is defined %}\n'
    '                      <li class="md-nav__item">\n'
    '                        <a href="{{ changelog_url | url }}" class="md-nav__link">\n'
    '                          {%- include ".icons/$ICON.svg" %}\n'
    '                          <span class="md-ellipsis">{{ changelog_label }}</span>\n'
    '                        </a>\n'
    '                      </li>\n'
    '                    {%- endif %}\n'
)


# ── hook handlers ──────────────────────────────────────────────────────────────

def on_config(config):
    """Read user-supplied config from extra.changelogs."""
    _cfg.update(_DEFAULTS)
    user = (config.extra or {}).get("changelogs", {})
    if isinstance(user, dict):
        _cfg.update(user)


@event_priority(50)
def on_files(files, config):
    """Relocate changelog files so the blog plugin ignores them."""
    _changelog_map.clear()
    filename = _cfg["filename"]

    changelogs = [
        f for f in list(files)
        if f.src_path.startswith(_POSTS_DIR)
        and os.path.basename(f.src_path) == filename
    ]

    for file in changelogs:
        dir_name = os.path.basename(os.path.dirname(file.src_uri))

        # Read the sibling post's frontmatter to find the slug.
        slug = dir_name
        post_dir = os.path.join(config.docs_dir, os.path.dirname(file.src_uri))
        for fname in os.listdir(post_dir):
            if fname == filename or not fname.endswith(".md"):
                continue
            fpath = os.path.join(post_dir, fname)
            with open(fpath, encoding="utf-8") as fh:
                content = fh.read()
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    fm = yaml.safe_load(content[3:end]) or {}
                    slug = fm.get("slug", dir_name)
            break

        blog_dir = os.path.dirname(_POSTS_DIR)
        changelog_url = f"{blog_dir}/{slug}/changelog/"
        _changelog_map[dir_name] = changelog_url

        actual_abs_src = os.path.normpath(os.path.join(config.docs_dir, file.src_uri))

        files.remove(file)

        # Change src_uri so blog plugin's startswith(_POSTS_DIR) check skips it.
        file.src_uri = f"blog/__changelogs/{dir_name}/{filename}"

        # Clear cached_property values derived from the old paths.
        for attr in ("dest_uri", "url", "abs_dest_path", "abs_src_path", "name"):
            file.__dict__.pop(attr, None)

        file.dest_uri = f"{blog_dir}/{slug}/changelog/index.html"
        file.abs_src_path = actual_abs_src
        file.inclusion = InclusionLevel.NOT_IN_NAV

        files.append(file)


def on_env(env, config, files):
    """Patch blog-post.html in the Jinja2 env to inject the changelog nav link."""
    from jinja2 import BaseLoader, ChoiceLoader, TemplateNotFound

    fragment = _FRAGMENT_TMPL.replace("$ICON", _cfg["nav_icon"])
    original_loader = env.loader

    class _PatchingLoader(BaseLoader):
        def get_source(self, environment, template):
            if template != "blog-post.html":
                raise TemplateNotFound(template)
            source, path, uptodate = original_loader.get_source(environment, template)
            return _inject_fragment(source, fragment), path, uptodate

    env.loader = ChoiceLoader([_PatchingLoader(), original_loader])


def on_page_context(context, page, config, nav):
    """Inject changelog_url and changelog_label into the blog post context."""
    src = page.file.src_path
    if src.startswith(_POSTS_DIR):
        dir_name = os.path.basename(os.path.dirname(src))
        url = _changelog_map.get(dir_name)
        if url:
            context["changelog_url"] = url
            context["changelog_label"] = _cfg["nav_label"]
    return context


# ── helpers ────────────────────────────────────────────────────────────────────

def _inject_fragment(source: str, fragment: str) -> str:
    """Insert the changelog nav link after the date block(s) in blog-post.html.

    Injection priority:
      1. After the {% endif %} closing the date.updated conditional block
         (identified by the 'calendar-clock.svg' anchor). This naturally places
         the link under the update date when it exists, or under the create date
         when it does not.
      2. Fallback: after the </li> closing the date.created block
         (identified by the 'calendar.svg' anchor).
      3. If no anchor is found the source is returned unchanged.
    """
    for anchor, end_marker, offset_fn in [
        ("calendar-clock.svg", "{% endif %}", lambda src, pos: src.find("\n", pos) + 1),
        ("calendar.svg",       "</li>",       lambda src, pos: src.find("\n", pos) + 1),
    ]:
        anchor_pos = source.find(anchor)
        if anchor_pos == -1:
            continue
        marker_pos = source.find(end_marker, anchor_pos)
        if marker_pos == -1:
            continue
        insert_at = offset_fn(source, marker_pos)
        if insert_at <= 0:
            insert_at = marker_pos + len(end_marker)
        return source[:insert_at] + fragment + source[insert_at:]

    return source
