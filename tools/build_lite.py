#!/usr/bin/env python3
"""Bundle the Caesium site into a single self-contained lite.html.

Expects a copy of the site in src/ and writes lite.html to the repo root.

How lite.html differs from the multi-page site:
  * one file -- css, js, fonts, cursor and logo are inlined
  * the request form link is dropped
  * credits open in a modal instead of on their own page
  * games play in an in-page overlay, since iframe.html is not there to link to

Usage: python tools/build_lite.py [-o lite.html] [--no-embed-assets]
                                  [--no-analytics] [--no-minify]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
SRC = REPO / "src"
TEMPLATES = TOOLS / "lite"

MIME_TYPES = {
    ".cur": "image/x-icon",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".otf": "font/otf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""")
HTML_ASSET = re.compile(r"""(\s(?:src|href)\s*=\s*)(['"])([^'"]+)\2""")
PAGE_LINK = re.compile(r"""(\shref\s*=\s*)(['"])\.?/?[\w-]+\.html[^'"]*\2""", re.I)
STYLESHEET_TAG = re.compile(r"""[ \t]*<link[^>]+rel=["']stylesheet["'][^>]*>\n?""", re.I)
LOADER_TAG = re.compile(
    r"""[ \t]*<script[^>]+src=["'][^"']*js/loader\.js["'][^>]*>\s*</script>\n?""", re.I
)
ANALYTICS_TAG = re.compile(r"""[ \t]*<script[^>]+counter\.dev[^>]*>\s*</script>\n?""", re.I)
SCRIPT_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
HTML_COMMENT = re.compile(r"<!--(?!\[if).*?-->", re.S)
GAME_CDN = re.compile(r"""["']main["']\s*:\s*["']([^"']+)["']""")

SOURCES = (
    "index.html",
    "credits.html",
    "css/styles.css",
    "js/loader.js",
    "js/iframe.js",
)
TEMPLATE_SOURCES = ("lite.css", "player.js")

EMBEDDED: list[tuple[str, int]] = []

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def data_uri(path: Path) -> str:
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
    EMBEDDED.append((path.relative_to(SRC).as_posix(), path.stat().st_size))
    return f"data:{mime};base64,{payload}"


def local_asset(url: str, base_dir: Path) -> Path | None:
    """Resolve a css/html url to a file inside src/, or None if it is remote."""
    url = url.strip()
    if not url or url.startswith(
        ("http:", "https:", "//", "data:", "#", "mailto:", "javascript:")
    ):
        return None
    path = (base_dir / url.split("?")[0].split("#")[0]).resolve()
    if not path.is_file() or SRC not in path.parents:
        return None
    return path


def minify_css(css: str) -> str:
    """Whitespace-only squeeze. Run before inlining data uris, which contain `:,;`."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};:,>])\s*", r"\1", css)
    return css.replace(";}", "}").strip()


def inline_css_assets(css: str, base_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        path = local_asset(match.group(2), base_dir)
        return match.group(0) if path is None else f"url({data_uri(path)})"

    return CSS_URL.sub(replace, css)


def rebase(url: str, base_dir: Path, out_dir: Path) -> str | None:
    """Repoint a url that was relative to base_dir so it works from out_dir."""
    path = local_asset(url, base_dir)
    if path is None:
        return None
    try:
        rel = os.path.relpath(path, out_dir).replace(os.sep, "/")
    except ValueError:  # windows: different drives
        sys.exit("--no-embed-assets needs an output path on the same drive as the repo")
    return rel if rel.startswith(".") else f"./{rel}"


def rebase_css_urls(css: str, base_dir: Path, out_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        rel = rebase(match.group(2), base_dir, out_dir)
        return match.group(0) if rel is None else f"url({rel})"

    return CSS_URL.sub(replace, css)


def rebase_html_assets(html: str, out_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group(3).lower().endswith((".html", ".css", ".js")):
            return match.group(0)
        rel = rebase(match.group(3), SRC, out_dir)
        quote = match.group(2)
        return match.group(0) if rel is None else f"{match.group(1)}{quote}{rel}{quote}"

    return HTML_ASSET.sub(replace, html)


def inline_html_assets(html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        path = local_asset(match.group(3), SRC)
        if path is None or path.suffix.lower() in {".html", ".css", ".js"}:
            return match.group(0)
        quote = match.group(2)
        return f"{match.group(1)}{quote}{data_uri(path)}{quote}"

    return HTML_ASSET.sub(replace, html)


def game_cdn(path: Path) -> str:
    match = GAME_CDN.search(read(path))
    if not match:
        sys.exit(f"{path.name}: could not find the game cdn base url")
    return match.group(1)


def credits_markup(path: Path) -> str:
    """Lift the credits page's own content out of credits.html for the modal."""
    body = read(path).split("</header>", 1)[-1].split("</body>", 1)[0]
    body = re.sub(r"</?body[^>]*>", "", body)
    body = HTML_COMMENT.sub("", body)
    body = re.sub(r"^\s*(?:<br\s*/?>\s*)+", "", body).strip()
    if len(body) < 50:
        sys.exit(f"{path.name}: could not find the credits content")
    return re.sub(r"<h1(?![^>]*\bid=)", '<h1 id="credits-heading"', body, count=1)


def drop_request_link(html: str) -> str:
    pattern = re.compile(
        r"""\s*<a[^>]*href=["'][^"']*request\.html[^"']*["'][^>]*>.*?</a>"""
        r"""\s*(?:<p class=["']dot["']>[^<]*</p>)?""",
        re.I | re.S,
    )
    html, count = pattern.subn("\n", html)
    if not count:
        print("warning: no request form link found in index.html", file=sys.stderr)
    return html


def credits_link_to_button(html: str) -> str:
    pattern = re.compile(
        r"""<a[^>]*href=["'][^"']*credits\.html[^"']*["'][^>]*>(.*?)</a>""", re.I | re.S
    )
    html, count = pattern.subn(
        lambda m: (
            '<button type="button" class="credits-link" data-opens-credits '
            f'aria-haspopup="dialog">{m.group(1)}</button>'
        ),
        html,
    )
    if not count:
        sys.exit("index.html: no credits link to turn into a modal")
    return html


def overlay_markup(credits: str) -> str:
    return f"""<div class="modal-backdrop" id="credits-modal" role="dialog" aria-modal="true"
     aria-labelledby="credits-heading">
  <div class="modal">
    <button type="button" class="modal-close" id="credits-close"
            aria-label="Close credits">&times;</button>
    {credits}
  </div>
</div>

<div class="player" id="game-player">
  <button type="button" class="player-exit" id="player-exit">&larr; back</button>
  <iframe id="gameframe" title="Game"></iframe>

  <!-- slide-out action tab, ported from iframe.html -->
  <div class="tabs" id="tabs">
    <button class="tabs-handle" id="tabs-handle" type="button" aria-expanded="false"
            aria-controls="tab-actions" aria-label="Open actions">
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" /></svg>
    </button>

    <div class="tab-actions" id="tab-actions" inert>
      <button class="tab-action" id="action-fullscreen" type="button">
        <svg class="icon-enter" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 2H2v4M10 2h4v4M14 10v4h-4M2 10v4h4" /></svg>
        <svg class="icon-exit" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 6h4V2M14 6h-4V2M10 14v-4h4M6 14v-4H2" /></svg>
        <span class="tab-action-label">fullscreen</span>
      </button>

      <button class="tab-action" id="action-download" type="button" disabled>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2v7.5M4.5 6.5 8 10l3.5-3.5M2.5 13h11" /></svg>
        <span class="tab-action-label">download html</span>
      </button>

      <button class="tab-action" id="action-reload" type="button">
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13 8a5 5 0 1 1-1.7-3.77M13.5 3v2.5H11" /></svg>
        <span class="tab-action-label">reload game</span>
      </button>
    </div>
  </div>
</div>
"""


def build(out_dir: Path, embed: bool, minify: bool, analytics: bool) -> str:
    html = read(SRC / "index.html")
    if minify:
        html = HTML_COMMENT.sub("", html)
    if not analytics:
        html = ANALYTICS_TAG.sub("", html)

    html = drop_request_link(html)
    html = credits_link_to_button(html)
    if embed:
        html = inline_html_assets(html)
    else:
        html = rebase_html_assets(html, out_dir)
    # ./index.html and friends are not next to a standalone file; send them to the top
    html = PAGE_LINK.sub(lambda m: f"{m.group(1)}{m.group(2)}#{m.group(2)}", html)

    css = read(SRC / "css" / "styles.css") + "\n" + read(TEMPLATES / "lite.css")
    if minify:
        css = minify_css(css)
    if embed:
        css = inline_css_assets(css, SRC / "css")
    else:
        css = rebase_css_urls(css, SRC / "css", out_dir)
    html, count = STYLESHEET_TAG.subn(f"<style>\n{css}\n</style>\n", html, count=1)
    if not count:
        sys.exit("index.html: no stylesheet link to inline")
    html = STYLESHEET_TAG.sub("", html)

    player = read(TEMPLATES / "player.js").replace(
        "__GAME_CDN__", json.dumps(game_cdn(SRC / "js" / "iframe.js"))
    )
    scripts = (
        overlay_markup(credits_markup(SRC / "credits.html"))
        + f"\n<script>\n{read(SRC / 'js' / 'loader.js')}\n</script>\n"
        + f"<script>\n{player}\n</script>\n"
    )
    html, count = LOADER_TAG.subn(lambda _: scripts, html, count=1)
    if not count:
        sys.exit("index.html: no loader.js tag to replace")
    return html


def verify(html: str, embed: bool) -> None:
    problems = []
    # css/js keep comments like "Request Form Styles", so text checks look at markup only
    markup = SCRIPT_BLOCK.sub("", html)
    if "request.html" in html or re.search(r"request form", markup, re.I):
        problems.append("the request form is still referenced")
    if "credits.html" in html:
        problems.append("the credits page is still linked")
    if re.search(r"""<link[^>]+rel=["']stylesheet""", html, re.I):
        problems.append("a stylesheet is still linked instead of inlined")
    if re.search(r"""<script[^>]+src=["'](?!https?:)""", html, re.I):
        problems.append("a local script is still linked instead of inlined")
    for required in (
        'id="credits-modal"',
        "data-opens-credits",
        'id="gameframe"',
        'id="game-count"',
        "filterGames",
    ):
        if required not in html:
            problems.append(f"missing {required}")
    # the bundled scripts and the markup they drive come from different files
    for element_id in sorted(set(re.findall(r"""getElementById\(['"]([\w-]+)['"]\)""", html))):
        if f'id="{element_id}"' not in markup:
            problems.append(f"a script looks for #{element_id}, which is not in the markup")
    if embed:
        leftover = re.findall(
            r"""\s(?:src|href)\s*=\s*["'](?!https?:|data:|#|mailto:)([^"']+)["']""", markup
        )
        if leftover:
            problems.append(f"not embedded: {', '.join(sorted(set(leftover)))}")
    if problems:
        sys.exit("lite build failed its checks:\n  - " + "\n  - ".join(problems))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", default=REPO / "lite.html", type=Path,
                        help="where to write the bundle (default: lite.html)")
    parser.add_argument("--no-embed-assets", action="store_true",
                        help="keep relative paths for fonts/images instead of embedding them")
    parser.add_argument("--no-analytics", action="store_true",
                        help="drop the counter.dev script so the file makes no third party calls")
    parser.add_argument("--no-minify", action="store_true", help="keep the css readable")
    args = parser.parse_args(argv)

    embed = not args.no_embed_assets
    out = args.out.resolve()
    missing = [f"src/{name}" for name in SOURCES if not (SRC / name).is_file()]
    missing += [f"tools/lite/{name}" for name in TEMPLATE_SOURCES if not (TEMPLATES / name).is_file()]
    if missing:
        sys.exit(f"missing sources under {REPO}: {', '.join(missing)}")
    html = build(out.parent, embed, not args.no_minify, not args.no_analytics)
    verify(html, embed)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8", newline="\n")
    for name, size in EMBEDDED:
        print(f"  embedded {name} ({size / 1024:.0f} KB)")
    print(f"wrote {out} ({len(html.encode('utf-8')) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

