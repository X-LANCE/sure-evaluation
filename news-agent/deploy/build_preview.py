"""Render the working README and news Markdown into the local browser preview."""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


STYLES = """
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:#f6f8fa;color:#1f2328;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
.repo-bar{background:#fff;border-bottom:1px solid #d1d9e0;padding:16px 32px;font-size:14px;display:flex;gap:12px;align-items:center}.repo-bar strong{font-weight:600}.repo-bar small{color:#59636e;font-size:11px;border:1px solid #d1d9e0;border-radius:15px;padding:2px 8px}.repo-bar a{margin-left:auto;font-size:12px}
.frame{max-width:1012px;margin:24px auto;background:#fff;border:1px solid #d1d9e0;border-radius:7px;overflow:hidden}.file{padding:14px 24px;border-bottom:1px solid #d1d9e0;font-size:13px;font-weight:600}.markdown-body{padding:28px 36px 40px;font-size:16px;line-height:1.6;overflow-wrap:anywhere}.markdown-body>:first-child{margin-top:0}
a{color:#0969da;text-decoration:none}a:hover{text-decoration:underline}.markdown-body img{max-width:100%;height:auto}.markdown-body h1,.markdown-body h2{border-bottom:1px solid #d1d9e0;padding-bottom:.3em}.markdown-body h1{font-size:32px;line-height:1.25;margin:0 0 16px}.markdown-body h2{font-size:24px;margin:24px 0 16px;line-height:1.25}.markdown-body h3{font-size:20px;line-height:1.25;margin:24px 0 16px}.markdown-body h4{font-size:16px}.markdown-body p,.markdown-body ul,.markdown-body ol{margin:0 0 16px}.markdown-body li+li{margin-top:4px}.markdown-body table{border-spacing:0;border-collapse:collapse;display:block;max-width:100%;overflow:auto;margin-bottom:16px;font-size:14px}.markdown-body th,.markdown-body td{padding:6px 13px;border:1px solid #d1d9e0;text-align:left}.markdown-body th{font-weight:600}.markdown-body tr:nth-child(2n){background:#f6f8fa}.markdown-body code{font-family:Consolas,"Liberation Mono",monospace;font-size:85%;background:#eff1f3;border-radius:4px;padding:2px 5px}.markdown-body pre{padding:16px;background:#f6f8fa;border-radius:6px;overflow:auto;margin:0 0 16px;line-height:1.45}.markdown-body pre code{background:none;padding:0;font-size:13px;white-space:pre}.markdown-body details{margin:0 0 16px}.markdown-body summary{cursor:pointer}.markdown-body details[open]>summary{margin-bottom:16px}.markdown-body kbd{display:inline-block;padding:2px 6px;font-size:11px;background:#f6f8fa;border:1px solid #d1d9e0;border-radius:4px;color:#1a7f37}.markdown-body blockquote{border-left:4px solid #d1d9e0;padding:0 16px;margin:0 0 16px;color:#59636e}.markdown-body hr{height:3px;border:0;background:#d1d9e0;margin:24px 0}.badge{font-size:11px;display:inline-block;border:1px solid #d1d9e0;border-radius:4px;padding:1px 7px;background:#f6f8fa;color:#59636e}.news-location{scroll-margin-top:24px}
@media(max-width:600px){.repo-bar{padding:12px;font-size:12px;gap:8px}.repo-bar small{font-size:9px}.repo-bar a{font-size:10px}.frame{margin:10px 6px}.file{padding:12px 16px}.markdown-body{padding:22px 18px;font-size:14px}.markdown-body h1{font-size:27px}.markdown-body h2{font-size:22px}.markdown-body table{font-size:12px}.markdown-body td,.markdown-body th{padding:6px 9px}}
"""


def render_markdown(root: Path, source: Path, text: str) -> str:
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()

    def image(tokens, index, options, env):
        token = tokens[index]
        url = token.attrGet("src") or ""
        label = token.content
        parts = urlsplit(url)
        if parts.scheme:
            # The news itself uses local assets. Remote README badges keep their
            # labels and original parent links, without fetching live resources.
            return f'<span class="badge">{html.escape(label)}</span>'
        asset = (source.parent / unquote(parts.path)).resolve()
        if asset.is_relative_to(root) and asset.is_file():
            mime = mimetypes.guess_type(asset.name)[0] or ""
            if mime.startswith("image/"):
                data = base64.b64encode(asset.read_bytes()).decode()
                return f'<img src="data:{mime};base64,{data}" alt="{html.escape(label, quote=True)}">'
        raise ValueError(f"Missing local Markdown image: {source.name}: {url}")

    parser.renderer.rules["image"] = image
    markup = parser.render(text)

    def embed_html_asset(match):
        attribute, target = match.groups()
        parts = urlsplit(html.unescape(target))
        if parts.scheme:
            return match.group(0)
        asset = (source.parent / unquote(parts.path)).resolve()
        if not asset.is_relative_to(root) or not asset.is_file():
            raise ValueError(f"Missing local HTML image: {source.name}: {target}")
        mime = mimetypes.guess_type(asset.name)[0] or ""
        if not mime.startswith("image/"):
            raise ValueError(f"Unexpected non-image resource: {target}")
        data = base64.b64encode(asset.read_bytes()).decode()
        return f'{attribute}="data:{mime};base64,{data}"'

    markup = re.sub(r'\b(src|srcset)="([^"]+)"', embed_html_asset, markup)
    markup = markup.replace("<!-- SURE-NEWS:START -->", '<div id="repo-news" class="news-location"></div>')
    local_pages = {
        "README.md": "readme.html", "README_ZH.md": "readme-zh.html",
        "docs/news/index.md": "news-history.html", "docs/news/latest.md": "news-latest.html",
        "docs/news/index.html": "announcement.html",
    }

    def rewrite_link(match):
        target = html.unescape(match.group(1))
        parts = urlsplit(target)
        if parts.scheme:
            return match.group(0) + ' target="_blank" rel="noopener noreferrer"'
        if target.startswith("#"):
            return match.group(0)
        path = (source.parent / unquote(parts.path)).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Link outside repository: {target}")
        relative = path.relative_to(root).as_posix()
        if relative in local_pages:
            destination = local_pages[relative]
        else:
            destination = f"https://github.com/PigeonDan1/sure-evaluation/blob/{revision}/{relative}"
        if parts.fragment:
            destination += "#" + parts.fragment
        extra = ' target="_blank" rel="noopener noreferrer"' if destination.startswith("https://") else ""
        return 'href="' + html.escape(destination, quote=True) + '"' + extra

    return re.sub(r'href="([^"]+)"', rewrite_link, markup)


def page(root: Path, source: Path, text: str) -> str:
    relative = source.relative_to(root).as_posix()
    markup = render_markdown(root, source, text)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(relative)} · Repository preview</title>'
            f'<style>{STYLES}</style></head><body>'
            '<div class="repo-bar"><strong>sure-evaluation</strong>'
            '<small>当前仓库文件 · GitHub 风格预览</small>'
            '<a href="./" target="_top">切换视图 ↗</a></div>'
            f'<main class="frame"><div class="file">{html.escape(relative)}</div>'
            f'<article class="markdown-body">{markup}</article></main></body></html>')


def build(root: Path, output: Path) -> None:
    root = root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    readme = (root / "README.md").read_text(encoding="utf-8")
    sources = {
        "readme.html": "README.md", "readme-zh.html": "README_ZH.md",
        "news-history.html": "docs/news/index.md", "news-latest.html": "docs/news/latest.md",
    }
    for target, name in sources.items():
        source = root / name
        (output / target).write_text(page(root, source, source.read_text(encoding="utf-8")), encoding="utf-8")
    block = readme[readme.index("<!-- SURE-NEWS:START -->"):readme.index("<!-- SURE-NEWS:END -->")]
    (output / "readme-news.html").write_text(page(root, root / "README.md", block), encoding="utf-8")
    (output / "announcement.html").write_bytes((root / "docs/news/index.html").read_bytes())
    (output / "index.html").write_bytes(Path(__file__).with_name("preview.html").read_bytes())
    print(f"Browser preview refreshed from working-tree README and news Markdown: {output}")


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args.add_argument("--output", type=Path)
    options = args.parse_args()
    build(options.root, options.output or options.root / "news-agent/state/visual-preview")
